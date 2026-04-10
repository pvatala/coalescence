"""
Fix BigBang papers: extract real abstracts from PDFs and assign correct domains.

Usage (inside backend container):
    python -m scripts.fix_bigbang_papers
"""
import asyncio
import json
import re
import sys
import fitz  # PyMuPDF

from google import genai
from google.genai import types as genai_types

from app.core.config import settings
from app.core.storage import storage
from app.db.session import AsyncSessionLocal
from app.models.platform import Paper, Domain
from sqlalchemy import select


BIGBANG_ACTOR_ID = "dd8deb9a-5d20-4b81-aa5b-5dffc43757c6"

# Domains to create if needed
DOMAIN_DESCRIPTIONS = {
    "d/NLP": "Natural language processing, text understanding, generation, and multilingual models.",
    "d/Computer-Vision": "Image recognition, object detection, video understanding, and visual representation learning.",
    "d/Reinforcement-Learning": "Sequential decision making, policy optimization, multi-agent RL, and reward modeling.",
    "d/LLM-Alignment": "Research on aligning large language models with human values, safety, and interpretability.",
    "d/Optimization": "Mathematical optimization, convex and non-convex methods, and training algorithms.",
    "d/Generative-Models": "Diffusion models, GANs, VAEs, and other generative approaches.",
    "d/Robotics": "Robot learning, manipulation, locomotion, and embodied AI.",
    "d/Speech-Audio": "Speech recognition, synthesis, audio processing, and music generation.",
    "d/Graph-Learning": "Graph neural networks, knowledge graphs, and relational reasoning.",
    "d/ML-Theory": "Statistical learning theory, generalization bounds, and theoretical foundations of ML.",
    "d/Bioinformatics": "Computational biology, genomics, protein structure prediction, and biological data analysis.",
    "d/QuantumComputing": "Quantum algorithms, error correction, quantum machine learning, and quantum hardware.",
    "d/MaterialScience": "Computational and experimental materials science, crystal structure prediction, and materials informatics.",
    "d/Security-Privacy": "Adversarial ML, differential privacy, federated learning, and model security.",
    "d/Multimodal": "Vision-language models, cross-modal learning, and multimodal reasoning.",
    "d/Recommender-Systems": "Collaborative filtering, content-based recommendations, and information retrieval.",
    "d/Time-Series": "Forecasting, temporal modeling, anomaly detection in sequential data.",
    "d/Healthcare-AI": "Medical imaging, clinical NLP, drug discovery, and health informatics.",
}

DOMAIN_LIST = list(DOMAIN_DESCRIPTIONS.keys())


def extract_abstract_from_pdf(pdf_bytes: bytes) -> str | None:
    """Extract abstract from PDF using PyMuPDF."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        # Get text from first 2 pages
        text = ""
        for i in range(min(2, len(doc))):
            text += doc[i].get_text()
        doc.close()

        if not text.strip():
            return None

        # Try to find abstract section
        # Common patterns: "Abstract", "ABSTRACT", "Abstract.", "A BSTRACT"
        patterns = [
            r'(?i)\bA\s*B\s*S\s*T\s*R\s*A\s*C\s*T\b[.\s:]*\n?(.*?)(?:\n\s*\n|\b(?:1\.?\s*Introduction|I\.\s*INTRODUCTION|Keywords|Index Terms|CCS Concepts))',
            r'(?i)\bAbstract\b[.\s:\-—]*\n?(.*?)(?:\n\s*\n|\b(?:1\.?\s*Introduction|I\.\s*INTRODUCTION|Keywords|Index Terms))',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                abstract = match.group(1).strip()
                # Clean up
                abstract = re.sub(r'\s+', ' ', abstract)
                abstract = abstract.strip()
                if len(abstract) > 50:  # Sanity check
                    return abstract[:3000]  # Cap at 3000 chars

        # Fallback: take text between title area and first section
        # Skip first ~200 chars (likely title/authors), take next chunk
        lines = text.split('\n')
        content_lines = []
        started = False
        for line in lines:
            stripped = line.strip()
            if not started and len(stripped) > 40:
                started = True
            if started:
                if re.match(r'^(1\.?\s|I\.\s|Introduction|INTRODUCTION)', stripped):
                    break
                content_lines.append(stripped)
            if len(content_lines) > 30:
                break

        if content_lines:
            fallback = ' '.join(content_lines)
            fallback = re.sub(r'\s+', ' ', fallback).strip()
            if len(fallback) > 100:
                return fallback[:3000]

        return None
    except Exception as e:
        print(f"  PDF extraction error: {e}")
        return None


async def classify_papers_batch(papers_data: list[dict], gemini_client) -> dict[str, list[str]]:
    """Use Gemini to classify a batch of papers into domains."""
    prompt = f"""You are classifying academic papers into research domains.

Available domains: {json.dumps(DOMAIN_LIST)}

For each paper below, assign 1-3 most relevant domains from the list above.
If none of the existing domains fit well, you may suggest a new domain using the format "d/DomainName".

Return a JSON object mapping paper_id to a list of domain strings.

Papers:
"""
    for p in papers_data:
        prompt += f"\n---\nID: {p['id']}\nTitle: {p['title']}\nAbstract: {p['abstract'][:500]}\n"

    prompt += "\n\nReturn ONLY valid JSON. Example: {\"id1\": [\"d/NLP\", \"d/ML-Theory\"], \"id2\": [\"d/Computer-Vision\"]}"

    try:
        response = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=genai_types.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=4096,
            ),
        )
        text = response.text.strip()
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        print(f"  Gemini classification error: {e}")

    return {}


async def ensure_domains_exist(domain_names: set[str], session):
    """Create any domains that don't exist yet."""
    for name in domain_names:
        result = await session.execute(select(Domain).where(Domain.name == name))
        if not result.scalar_one_or_none():
            desc = DOMAIN_DESCRIPTIONS.get(name, f"Research in {name.replace('d/', '')}.")
            domain = Domain(name=name, description=desc)
            session.add(domain)
            print(f"  Created domain: {name}")
    await session.flush()


async def main():
    gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)

    async with AsyncSessionLocal() as session:
        # Get all BigBang papers
        result = await session.execute(
            select(Paper)
            .where(Paper.submitter_id == BIGBANG_ACTOR_ID)
            .order_by(Paper.created_at)
        )
        papers = result.scalars().all()
        print(f"Found {len(papers)} BigBang papers")

        # Process in batches
        BATCH_SIZE = 20
        total_updated = 0
        total_abstracts = 0
        all_domains_used = set()

        for batch_start in range(0, len(papers), BATCH_SIZE):
            batch = papers[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            print(f"\n--- Batch {batch_num} ({batch_start+1}-{batch_start+len(batch)}) ---")

            # Step 1: Extract abstracts from PDFs
            papers_data = []
            for paper in batch:
                abstract = None
                if paper.pdf_url:
                    # Convert /storage/pdfs/xxx.pdf to storage key
                    key = paper.pdf_url.lstrip("/storage/")
                    pdf_bytes = await storage.read(key)
                    if pdf_bytes:
                        abstract = extract_abstract_from_pdf(pdf_bytes)

                if abstract:
                    paper.abstract = abstract
                    total_abstracts += 1

                papers_data.append({
                    "id": str(paper.id),
                    "title": paper.title,
                    "abstract": paper.abstract,
                })

            # Step 2: Classify domains
            classifications = await classify_papers_batch(papers_data, gemini_client)

            # Step 3: Update papers
            for paper in batch:
                pid = str(paper.id)
                if pid in classifications:
                    domains = classifications[pid]
                    if domains and isinstance(domains, list):
                        # Normalize domain names
                        normalized = []
                        for d in domains:
                            if not d.startswith("d/"):
                                d = f"d/{d}"
                            normalized.append(d)
                        paper.domains = normalized
                        all_domains_used.update(normalized)
                        total_updated += 1

            # Ensure all domains exist
            await ensure_domains_exist(all_domains_used, session)

            await session.flush()
            print(f"  Updated {len([p for p in batch if str(p.id) in classifications])} papers")

        await session.commit()
        print(f"\n=== Done ===")
        print(f"Total papers: {len(papers)}")
        print(f"Abstracts extracted: {total_abstracts}")
        print(f"Domains classified: {total_updated}")
        print(f"Unique domains: {sorted(all_domains_used)}")


if __name__ == "__main__":
    asyncio.run(main())
