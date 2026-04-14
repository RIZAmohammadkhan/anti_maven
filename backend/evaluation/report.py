"""
Report CLI — exports evaluation results as report-ready tables.

Usage:
    python -m evaluation.report --runs evaluation/runs/baseline
    python -m evaluation.report --runs evaluation/runs/baseline evaluation/runs/improved

Exports:
    evaluation/reports/summary.json
    evaluation/reports/scores.csv
    evaluation/reports/failure_taxonomy.csv
    evaluation/reports/report.md
"""

import argparse
import csv
import json
import os
import pathlib
import sys
import time
from collections import defaultdict


def load_scores(run_dir: pathlib.Path) -> dict:
    """Load scores.json from a run directory."""
    scores_path = run_dir / "scores.json"
    if not scores_path.exists():
        print(f"Error: scores.json not found at {scores_path}")
        print("Run the scorer first: python -m evaluation.score --run <run_dir> --gold <gold.jsonl>")
        sys.exit(1)
    with open(scores_path) as f:
        return json.load(f)


def export_summary(runs: dict[str, dict], out_dir: pathlib.Path):
    """Export summary.json with overall metrics for each run."""
    summary = {}
    for run_name, scores in runs.items():
        summary[run_name] = {
            "query_accuracy": scores["query_accuracy"],
            "product_accuracy": scores["product_accuracy"],
            "passing": scores["passing"],
            "total_queries": scores["total_queries"],
            "total_products": scores["total_products"],
            "scored_at": scores["scored_at"],
            "category_accuracy": scores.get("category_accuracy", {}),
            "difficulty_accuracy": scores.get("difficulty_accuracy", {}),
            "failure_taxonomy": scores.get("failure_taxonomy", {}),
        }

    out_path = out_dir / "summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  → {out_path}")


def export_scores_csv(runs: dict[str, dict], out_dir: pathlib.Path):
    """Export per-query scores as CSV."""
    out_path = out_dir / "scores.csv"
    fieldnames = [
        "run_id", "query_id", "category", "difficulty",
        "query_score", "mean_product_score",
        "recommendation_alignment", "response_integrity",
        "product_count",
    ]

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for run_name, scores in runs.items():
            for qr in scores.get("query_results", []):
                writer.writerow({
                    "run_id": run_name,
                    "query_id": qr["query_id"],
                    "category": qr["category"],
                    "difficulty": qr["difficulty"],
                    "query_score": qr["query_score"],
                    "mean_product_score": qr["mean_product_score"],
                    "recommendation_alignment": qr["recommendation_alignment"],
                    "response_integrity": qr["response_integrity"],
                    "product_count": qr["product_count"],
                })
    print(f"  → {out_path}")


def export_failure_taxonomy_csv(runs: dict[str, dict], out_dir: pathlib.Path):
    """Export failure taxonomy counts as CSV."""
    out_path = out_dir / "failure_taxonomy.csv"

    all_failures = set()
    for scores in runs.values():
        all_failures.update(scores.get("failure_taxonomy", {}).keys())

    fieldnames = ["failure_type"] + list(runs.keys())

    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for failure in sorted(all_failures):
            row = {"failure_type": failure}
            for run_name, scores in runs.items():
                row[run_name] = scores.get("failure_taxonomy", {}).get(failure, 0)
            writer.writerow(row)
    print(f"  → {out_path}")


def export_report_md(runs: dict[str, dict], out_dir: pathlib.Path):
    """Export Markdown tables for the report."""
    out_path = out_dir / "report.md"
    run_names = list(runs.keys())

    lines = []
    lines.append("# Maven Evaluation Report\n")
    lines.append(f"**Generated:** {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n")

    # Config
    lines.append("## Configuration\n")
    lines.append("| Parameter | Value |")
    lines.append("|-----------|-------|")
    lines.append("| Provider | `groq` |")
    lines.append("| Model | `llama-3.3-70b-versatile` |")
    lines.append(f"| Benchmark Size | {runs[run_names[0]]['total_queries']} queries |")
    lines.append(f"| Evaluation Date | {time.strftime('%Y-%m-%d', time.gmtime())} |")
    if len(run_names) > 1:
        lines.append(f"| Runs Compared | {', '.join(f'`{r}`' for r in run_names)} |")
    lines.append("")

    # Overall metrics
    lines.append("## Overall Metrics\n")
    header = "| Metric |" + "|".join(f" {r} " for r in run_names) + "|"
    sep = "|--------|" + "|".join("-------" for _ in run_names) + "|"
    lines.append(header)
    lines.append(sep)

    qa_row = "| **Query Accuracy** |"
    pa_row = "| Product Accuracy |"
    pass_row = "| Status |"

    for r in run_names:
        s = runs[r]
        qa = s["query_accuracy"]
        pa = s["product_accuracy"]
        passing = s["passing"]
        qa_row += f" {qa:.1f}% |"
        pa_row += f" {pa:.1f}% |"
        pass_row += f" {'✅ PASS' if passing else '❌ FAIL'} |"

    lines.append(qa_row)
    lines.append(pa_row)
    lines.append(pass_row)
    lines.append("")

    # Category accuracy
    lines.append("## Category-wise Accuracy\n")
    all_cats = set()
    for s in runs.values():
        all_cats.update(s.get("category_accuracy", {}).keys())

    header = "| Category |" + "|".join(f" {r} " for r in run_names) + "|"
    sep = "|----------|" + "|".join("-------" for _ in run_names) + "|"
    lines.append(header)
    lines.append(sep)

    for cat in sorted(all_cats):
        row = f"| {cat} |"
        for r in run_names:
            acc = runs[r].get("category_accuracy", {}).get(cat, 0)
            row += f" {acc:.1f}% |"
        lines.append(row)
    lines.append("")

    # Difficulty accuracy
    lines.append("## Difficulty-wise Accuracy\n")
    all_diffs = set()
    for s in runs.values():
        all_diffs.update(s.get("difficulty_accuracy", {}).keys())

    header = "| Difficulty |" + "|".join(f" {r} " for r in run_names) + "|"
    sep = "|------------|" + "|".join("-------" for _ in run_names) + "|"
    lines.append(header)
    lines.append(sep)

    for diff in ["simple", "medium", "hard"]:
        if diff not in all_diffs:
            continue
        row = f"| {diff} |"
        for r in run_names:
            acc = runs[r].get("difficulty_accuracy", {}).get(diff, 0)
            row += f" {acc:.1f}% |"
        lines.append(row)
    lines.append("")

    # Failure taxonomy
    lines.append("## Failure Taxonomy\n")
    all_failures = set()
    for s in runs.values():
        all_failures.update(s.get("failure_taxonomy", {}).keys())

    if all_failures:
        header = "| Failure Type |" + "|".join(f" {r} " for r in run_names) + "|"
        sep = "|--------------|" + "|".join("-------" for _ in run_names) + "|"
        lines.append(header)
        lines.append(sep)

        for fail in sorted(all_failures):
            row = f"| {fail} |"
            for r in run_names:
                count = runs[r].get("failure_taxonomy", {}).get(fail, 0)
                row += f" {count} |"
            lines.append(row)
    else:
        lines.append("No failures detected.\n")
    lines.append("")

    # Methodology note
    lines.append("## Methodology\n")
    lines.append("Scoring uses a two-level rubric:\n")
    lines.append("**Product-level** (out of 100):\n")
    lines.append("| Component | Weight |")
    lines.append("|-----------|--------|")
    lines.append("| Relevance/Existence | 25 |")
    lines.append("| Budget & Price Fit | 20 |")
    lines.append("| Feature Match | 20 |")
    lines.append("| Link Integrity | 20 |")
    lines.append("| Evidence Completeness | 15 |")
    lines.append("")
    lines.append("**Query-level** (out of 100):\n")
    lines.append("```")
    lines.append("query_score = 0.70 × mean(product_scores)")
    lines.append("            + 0.20 × recommendation_alignment")
    lines.append("            + 0.10 × response_integrity")
    lines.append("```\n")
    lines.append("**Pass threshold:** `query_accuracy ≥ 60%`\n")
    lines.append("Same gold sheet and query set are reused across all runs for fair comparison.\n")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"  → {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Export Maven evaluation report")
    parser.add_argument(
        "--runs",
        nargs="+",
        required=True,
        help="One or more run directories to include in the report",
    )
    args = parser.parse_args()

    # Load all runs
    runs = {}
    for run_path in args.runs:
        run_dir = pathlib.Path(run_path)
        run_name = run_dir.name
        runs[run_name] = load_scores(run_dir)
        print(f"Loaded run '{run_name}': query_accuracy={runs[run_name]['query_accuracy']:.1f}%")

    # Create output directory
    out_dir = pathlib.Path("evaluation/reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\nExporting to {out_dir}/:")
    export_summary(runs, out_dir)
    export_scores_csv(runs, out_dir)
    export_failure_taxonomy_csv(runs, out_dir)
    export_report_md(runs, out_dir)

    print(f"\nDone! Report files are in {out_dir}/")


if __name__ == "__main__":
    main()
