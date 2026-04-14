"""
Collector CLI — calls the Maven API to collect responses for evaluation queries.

Usage:
    python -m evaluation.collect --queries evaluation/queries.jsonl --out evaluation/runs/baseline --resume
    python -m evaluation.collect --queries evaluation/queries.jsonl --out evaluation/runs/baseline --resume --limit 5

Options:
    --queries   Path to queries.jsonl
    --out       Output directory for this run (e.g. evaluation/runs/baseline)
    --resume    Skip already-completed queries and rerun only failed/missing
    --limit N   Only run N queries (useful for smoke tests)
    --delay S   Seconds to wait between requests (default: 2)
    --base-url  API base URL (default: http://localhost:8000)
"""

import argparse
import json
import os
import pathlib
import sys
import time
from datetime import datetime, timezone

import httpx


def load_queries(path: str) -> list[dict]:
    """Load queries from JSONL file."""
    queries = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def load_checkpoint(run_dir: pathlib.Path) -> dict:
    """Load or initialize checkpoint."""
    cp_path = run_dir / "checkpoint.json"
    if cp_path.exists():
        with open(cp_path) as f:
            return json.load(f)
    return {
        "run_id": run_dir.name,
        "provider": os.getenv("LLM_PROVIDER", "groq"),
        "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries": {},
    }


def save_checkpoint(run_dir: pathlib.Path, checkpoint: dict):
    """Save checkpoint to disk."""
    cp_path = run_dir / "checkpoint.json"
    with open(cp_path, "w") as f:
        json.dump(checkpoint, f, indent=2)


def collect_single(
    query_id: str,
    query_text: str,
    base_url: str,
    responses_dir: pathlib.Path,
    timeout: float = 180.0,
) -> tuple[bool, str | None]:
    """Send a single query to the API and save the response.

    Returns (success, error_message).
    """
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(
                f"{base_url}/api/research",
                json={"query": query_text},
            )

        if resp.status_code != 200:
            error = f"HTTP {resp.status_code}: {resp.text[:500]}"
            return False, error

        data = resp.json()

        # Save response
        out_path = responses_dir / f"{query_id}.json"
        with open(out_path, "w") as f:
            json.dump(data, f, indent=2)

        return True, None

    except httpx.TimeoutException:
        return False, "Request timed out (180s)"
    except httpx.ConnectError:
        return False, f"Cannot connect to {base_url}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:300]}"


def main():
    parser = argparse.ArgumentParser(description="Collect Maven API responses for evaluation")
    parser.add_argument("--queries", required=True, help="Path to queries.jsonl")
    parser.add_argument("--out", required=True, help="Output run directory")
    parser.add_argument("--resume", action="store_true", help="Skip completed queries")
    parser.add_argument("--limit", type=int, default=None, help="Max queries to run")
    parser.add_argument("--delay", type=float, default=2.0, help="Delay between requests (seconds)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    # Load queries
    queries = load_queries(args.queries)
    print(f"Loaded {len(queries)} queries from {args.queries}")

    # Setup output directory
    run_dir = pathlib.Path(args.out)
    responses_dir = run_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    # Load checkpoint
    checkpoint = load_checkpoint(run_dir)
    save_checkpoint(run_dir, checkpoint)

    # Filter queries based on resume
    to_run = []
    for q in queries:
        qid = q["query_id"]
        status = checkpoint["queries"].get(qid, {}).get("status")
        if args.resume and status == "done":
            continue
        to_run.append(q)

    if args.limit:
        to_run = to_run[: args.limit]

    skipped = len(queries) - len(to_run) - (len(queries) - len(to_run) if not args.limit else 0)
    print(f"Running {len(to_run)} queries (skipped {len(queries) - len(to_run)} already done)")

    if not to_run:
        print("Nothing to run. All queries already completed.")
        return

    # Run collection
    success_count = 0
    fail_count = 0
    start_time = time.time()

    for idx, q in enumerate(to_run, 1):
        qid = q["query_id"]
        query_text = q["query_text"]

        print(f"\n[{idx}/{len(to_run)}] {qid}: {query_text[:60]}...")

        t0 = time.time()
        success, error = collect_single(
            query_id=qid,
            query_text=query_text,
            base_url=args.base_url,
            responses_dir=responses_dir,
        )
        elapsed = time.time() - t0

        if success:
            success_count += 1
            status = "done"
            print(f"  ✓ Done ({elapsed:.1f}s)")
        else:
            fail_count += 1
            status = "failed"
            print(f"  ✗ Failed: {error} ({elapsed:.1f}s)")

        # Update checkpoint
        checkpoint["queries"][qid] = {
            "status": status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "error": error,
            "elapsed_seconds": round(elapsed, 1),
        }
        save_checkpoint(run_dir, checkpoint)

        # Delay between requests (skip delay after last query)
        if idx < len(to_run) and args.delay > 0:
            time.sleep(args.delay)

    # Summary
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Collection complete!")
    print(f"  Total: {len(to_run)}")
    print(f"  Success: {success_count}")
    print(f"  Failed: {fail_count}")
    print(f"  Time: {total_time:.0f}s")
    print(f"  Output: {run_dir}")

    # Update checkpoint with completion info
    checkpoint["completed_at"] = datetime.now(timezone.utc).isoformat()
    checkpoint["total_queries"] = len(queries)
    checkpoint["completed_queries"] = sum(
        1 for v in checkpoint["queries"].values() if v["status"] == "done"
    )
    checkpoint["failed_queries"] = sum(
        1 for v in checkpoint["queries"].values() if v["status"] == "failed"
    )
    save_checkpoint(run_dir, checkpoint)


if __name__ == "__main__":
    main()
