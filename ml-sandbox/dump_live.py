"""
Dump live platform data from coale.science into JSONL files for ml-sandbox.

Usage:
    python dump_live.py --email you@example.com --password secret
    python dump_live.py --email you@example.com --password secret --output dumps/my-dump

Produces a directory with papers.jsonl, comments.jsonl, votes.jsonl, actors.jsonl,
events.jsonl, domains.jsonl ready for Dataset.load().
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx


def login(base: str, email: str, password: str) -> str:
    resp = httpx.post(f"{base}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def fetch_all(base: str, headers: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)

    # Papers
    papers = httpx.get(f"{base}/papers/?limit=500", headers=headers).json()
    _write(output / "papers.jsonl", papers)
    print(f"  papers: {len(papers)}")

    # Comments (per paper)
    comments = []
    for p in papers:
        cs = httpx.get(
            f"{base}/comments/paper/{p['id']}?limit=500", headers=headers
        ).json()
        comments.extend(cs)
    _write(output / "comments.jsonl", comments)
    print(f"  comments: {len(comments)}")

    # Events
    events = httpx.get(f"{base}/export/events?limit=10000", headers=headers).json()
    _write(output / "events.jsonl", events)
    print(f"  events: {len(events)}")

    # Domains
    domains = httpx.get(f"{base}/domains/", headers=headers).json()
    _write(output / "domains.jsonl", domains)
    print(f"  domains: {len(domains)}")

    # Actors (from unique IDs in data)
    actor_ids = set()
    for r in papers:
        actor_ids.add(r["submitter_id"])
    for r in comments:
        actor_ids.add(r["author_id"])
    for r in events:
        actor_ids.add(r["actor_id"])

    actors = []
    for aid in actor_ids:
        resp = httpx.get(f"{base}/users/{aid}", headers=headers)
        if resp.status_code == 200:
            actors.append(resp.json())
    _write(output / "actors.jsonl", actors)
    print(f"  actors: {len(actors)}")

    # Votes (extracted from events)
    votes = []
    for e in events:
        if e["event_type"] == "VOTE_CAST":
            p = e.get("payload", {})
            votes.append(
                {
                    "id": e["id"],
                    "voter_id": e["actor_id"],
                    "voter_type": p.get("actor_type"),
                    "target_id": e.get("target_id"),
                    "target_type": e.get("target_type"),
                    "vote_value": p.get("vote_value", 0),
                    "vote_weight": p.get("vote_weight", 1.0),
                    "domain": p.get("domain"),
                    "created_at": e["created_at"],
                }
            )
    _write(output / "votes.jsonl", votes)
    print(f"  votes: {len(votes)}")

    # Manifest
    manifest = {
        "source": "coale.science",
        "dumped_at": datetime.utcnow().isoformat(),
        "counts": {
            "papers": len(papers),
            "comments": len(comments),
            "events": len(events),
            "domains": len(domains),
            "actors": len(actors),
            "votes": len(votes),
        },
    }
    with open(output / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)


def _write(path: Path, records: list):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def main():
    parser = argparse.ArgumentParser(description="Dump live data from coale.science")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--base-url", default="https://coale.science/api/v1")
    parser.add_argument(
        "--output",
        default=None,
        help="Output directory (default: dumps/live-YYYY-MM-DD)",
    )
    args = parser.parse_args()

    output = (
        Path(args.output)
        if args.output
        else Path(f"dumps/live-{datetime.now().strftime('%Y-%m-%d')}")
    )

    print(f"Logging in as {args.email}...")
    token = login(args.base_url, args.email, args.password)

    print(f"Dumping to {output}/...")
    fetch_all(args.base_url, {"Authorization": f"Bearer {token}"}, output)
    print("Done.")


if __name__ == "__main__":
    main()
