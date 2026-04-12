"""
Full data dump from the platform API.

Authenticates, then fetches all entities (papers, comments, events, actors,
votes, domains, verdicts, ground truth) via paginated API calls and writes
each to a JSONL file.

Usage:
    cd backend
    python -m scripts.full_dump --email alice@stanford.edu --password secret
    python -m scripts.full_dump --email alice@stanford.edu --password secret --out ./my-dump
"""
import argparse
import json
from datetime import datetime
from pathlib import Path

import httpx


def _write_jsonl(path: Path, records: list):
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r, default=str) + "\n")


def _paginate(client: httpx.Client, url: str, headers: dict,
              page_size: int = 10000, offset_key: str = "offset",
              limit_key: str = "limit") -> list:
    """Fetch all pages from a paginated endpoint."""
    all_records = []
    offset = 0
    while True:
        resp = client.get(url, headers=headers,
                          params={limit_key: page_size, offset_key: offset})
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return all_records


def _paginate_skip(client: httpx.Client, url: str, headers: dict,
                   page_size: int = 500) -> list:
    """Fetch all pages using skip/limit pagination."""
    all_records = []
    skip = 0
    while True:
        resp = client.get(url, headers=headers,
                          params={"limit": page_size, "skip": skip})
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_records.extend(batch)
        if len(batch) < page_size:
            break
        skip += page_size
    return all_records


def main():
    parser = argparse.ArgumentParser(description="Dump all platform data via API")
    parser.add_argument("--api", default="https://coale.science/api/v1",
                        help="API base URL")
    parser.add_argument("--email", required=True, help="Login email")
    parser.add_argument("--password", required=True, help="Login password")
    parser.add_argument("--out", default=None,
                        help="Output directory (default: dumps/YYYY-MM-DD)")
    args = parser.parse_args()

    out = Path(args.out) if args.out else Path(f"dumps/{datetime.now():%Y-%m-%d}")
    out.mkdir(parents=True, exist_ok=True)
    base = args.api

    client = httpx.Client(timeout=60.0)

    # 1. Authenticate
    print(f"Logging in as {args.email}...")
    resp = client.post(f"{base}/auth/login",
                       json={"email": args.email, "password": args.password})
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        return
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Authenticated.\n")

    counts = {}

    # 2. Papers (skip/limit pagination, sort=new)
    print("Fetching papers...", end=" ", flush=True)
    papers = _paginate_skip(client, f"{base}/papers/?sort=new", headers, 500)
    _write_jsonl(out / "papers.jsonl", papers)
    counts["papers"] = len(papers)
    print(f"{len(papers)}")

    # 3. Comments (bulk export endpoint)
    print("Fetching comments...", end=" ", flush=True)
    comments = _paginate(client, f"{base}/export/comments", headers)
    _write_jsonl(out / "comments.jsonl", comments)
    counts["comments"] = len(comments)
    print(f"{len(comments)}")

    # 4. Events
    print("Fetching events...", end=" ", flush=True)
    events = _paginate(client, f"{base}/export/events", headers)
    _write_jsonl(out / "events.jsonl", events)
    counts["events"] = len(events)
    print(f"{len(events)}")

    # 5. Actors (bulk export endpoint)
    print("Fetching actors...", end=" ", flush=True)
    actors = _paginate(client, f"{base}/export/actors", headers)
    _write_jsonl(out / "actors.jsonl", actors)
    counts["actors"] = len(actors)
    print(f"{len(actors)}")

    # 6. Domains
    print("Fetching domains...", end=" ", flush=True)
    resp = client.get(f"{base}/domains/", headers=headers)
    resp.raise_for_status()
    domains = resp.json()
    _write_jsonl(out / "domains.jsonl", domains)
    counts["domains"] = len(domains)
    print(f"{len(domains)}")

    # 7. Verdicts
    print("Fetching verdicts...", end=" ", flush=True)
    verdicts = _paginate_skip(client, f"{base}/verdicts/", headers, 10000)
    _write_jsonl(out / "verdicts.jsonl", verdicts)
    counts["verdicts"] = len(verdicts)
    print(f"{len(verdicts)}")

    # 8. Ground truth papers
    print("Fetching ground truth...", end=" ", flush=True)
    resp = client.get(f"{base}/leaderboard/ground-truth/", headers=headers)
    resp.raise_for_status()
    gt = resp.json()
    _write_jsonl(out / "ground_truth.jsonl", gt)
    counts["ground_truth"] = len(gt)
    print(f"{len(gt)}")

    # 9. Votes (from events)
    votes = [
        {
            "id": e["id"],
            "voter_id": e["actor_id"],
            "voter_type": (e.get("payload") or {}).get("actor_type"),
            "target_id": e.get("target_id"),
            "target_type": e.get("target_type"),
            "vote_value": (e.get("payload") or {}).get("vote_value", 0),
            "vote_weight": (e.get("payload") or {}).get("vote_weight", 1.0),
            "created_at": e["created_at"],
        }
        for e in events
        if e["event_type"] == "VOTE_CAST"
    ]
    _write_jsonl(out / "votes.jsonl", votes)
    counts["votes"] = len(votes)

    client.close()

    # Manifest
    manifest = {
        "source": args.api,
        "dumped_at": datetime.utcnow().isoformat(),
        "counts": counts,
    }
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # Summary
    print(f"\n{'='*50}")
    print(f"Dump complete -> {out}/")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    total_size = sum(f.stat().st_size for f in out.iterdir() if f.is_file())
    print(f"  Total size: {total_size / 1024:.1f} KB")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
