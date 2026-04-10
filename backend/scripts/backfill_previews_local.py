"""
Backfill preview images using LOCAL PDFs from the benchmarks directory.
Much faster than backfill_previews.py since no downloads needed.

Matches DB papers to local PDFs by title (ICLR) or pdf_url arxiv ID (FLAWS).

Usage:
    cd backend
    python -m scripts.backfill_previews_local
"""
import asyncio
import json
import os
import re
from pathlib import Path

from sqlalchemy import select, func
from app.db.session import AsyncSessionLocal
from app.models.platform import Paper
from app.core.pdf_preview import extract_best_preview_bytes
from app.core.storage import storage

BENCHMARK_DIR = Path(__file__).resolve().parent.parent.parent / "benchmarks" / "koalascience" / "molbook"
METADATA_DIR = BENCHMARK_DIR / "metadata"
PDF_DIR = BENCHMARK_DIR / "pdfs"


def build_title_to_pdf_map() -> dict[str, str]:
    """Map paper titles to local PDF paths using metadata."""
    title_map = {}
    for f in os.listdir(METADATA_DIR):
        if not f.endswith(".json"):
            continue
        meta = json.load(open(METADATA_DIR / f))
        paper_id = meta.get("paper_id", "")
        pdf_path = PDF_DIR / f"{paper_id}.pdf"
        if pdf_path.exists():
            title = meta.get("title", "")
            # For ICLR papers, title is clean and unique
            if title and meta.get("source") == "iclr2025":
                title_map[title] = str(pdf_path)
            # For FLAWS papers, match by arxiv ID in pdf_url
            arxiv_id = meta.get("arxiv_id", "")
            if arxiv_id:
                arxiv_base = re.sub(r"v\d+$", "", arxiv_id)
                title_map[f"arxiv:{arxiv_base}"] = str(pdf_path)
    return title_map


async def backfill():
    print("Building title -> local PDF map...")
    title_map = build_title_to_pdf_map()
    print(f"Mapped {len(title_map)} entries to local PDFs")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Paper).where(Paper.preview_image_url.is_(None))
        )
        papers = result.scalars().all()
        print(f"Found {len(papers)} papers without previews")

        generated = 0
        failed = 0

        for i, paper in enumerate(papers):
            # Try to find local PDF
            pdf_path = title_map.get(paper.title)
            if not pdf_path and paper.pdf_url and "arxiv.org" in paper.pdf_url:
                # Extract arxiv ID from pdf_url like https://arxiv.org/pdf/2501.00701.pdf
                match = re.search(r"(\d{4}\.\d{4,5})", paper.pdf_url)
                if match:
                    pdf_path = title_map.get(f"arxiv:{match.group(1)}")
            if not pdf_path and paper.pdf_url and "openreview.net" in paper.pdf_url:
                # Try matching by title directly
                pdf_path = title_map.get(paper.title)

            if not pdf_path:
                failed += 1
                continue

            png_bytes = extract_best_preview_bytes(pdf_path)
            if not png_bytes:
                failed += 1
                continue

            import uuid
            key = f"previews/{uuid.uuid4().hex}.png"
            url = await storage.save(key, png_bytes, content_type="image/png")
            paper.preview_image_url = url
            generated += 1

            if generated % 50 == 0:
                await session.flush()
                print(f"  Progress: {generated} previews generated ({i+1}/{len(papers)} processed)")

        await session.commit()

    print(f"\nDone: {generated} previews generated, {failed} skipped")


if __name__ == "__main__":
    asyncio.run(backfill())
