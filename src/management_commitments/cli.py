"""Collect -> Codex interpretation -> deterministic review -> analyst decisions."""

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .sources import EvidenceError, add_source, load_source, read_json, write_json


def parser():
    p = argparse.ArgumentParser(prog="commitments", description="Track management statements against later evidence.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect", help="Discover and capture official company documents")
    c.add_argument("--company", choices=["MSFT"], default="MSFT")
    c.add_argument("--profile", help="Custom official-site profile JSON; replaces the built-in company profile")
    c.add_argument("--fiscal-year", type=int, default=2025)
    c.add_argument("--start-quarter", type=int, default=1)
    c.add_argument("--quarters", type=int, default=3)
    c.add_argument("--budget", type=int, default=18)
    c.add_argument("--depth", type=int, default=1)
    c.add_argument("--output", required=True)
    c = sub.add_parser("candidates", help="Create a lexical reading aid; Codex must inspect and interpret sources")
    c.add_argument("--workspace", required=True)
    c.add_argument("--output")
    c.add_argument("--limit", type=int, default=250)
    c = sub.add_parser("read", help="Read exact source blocks, including table context")
    c.add_argument("--workspace", required=True)
    c.add_argument("--source", required=True)
    c.add_argument("--find", default="")
    c.add_argument("--start", type=int, default=0)
    c.add_argument("--limit", type=int, default=40)
    c = sub.add_parser("ingest", help="Add an explicitly selected local document to an existing source pack")
    c.add_argument("--workspace", required=True)
    c.add_argument("--file", required=True)
    c.add_argument(
        "--metadata",
        required=True,
        help="Source metadata JSON: company, period, title, published_at, kind, completeness",
    )
    c = sub.add_parser("review", help="Verify evidence and calculate comparisons; render review HTML")
    c.add_argument("--workspace", required=True)
    c.add_argument("--analysis", required=True)
    c.add_argument("--output", required=True)
    c = sub.add_parser("apply-decisions", help="Apply exported analyst decisions and append a review log")
    c.add_argument("--report", required=True)
    c.add_argument("--file", required=True)
    c = sub.add_parser("portfolio", help="Connect company reports with a searchable local index")
    c.add_argument("--reports", nargs="+", required=True)
    c.add_argument("--output", required=True)
    c = sub.add_parser("demo", help="Run a complete offline synthetic example")
    c.add_argument("--output", default="runs/demo")
    c = sub.add_parser("evaluate", help="Run 24 synthetic verifier cases; does not measure LLM extraction")
    c.add_argument("--output", default="runs/evaluation")
    return p


def main(argv=None):
    p = parser()
    a = p.parse_args(argv)
    try:
        if a.command == "collect":
            from .collect import collect, microsoft_profile

            profile = (
                read_json(a.profile) if a.profile else microsoft_profile(a.fiscal_year, a.start_quarter, a.quarters)
            )
            pack = collect(profile, a.output, a.budget, a.depth)
            result = {k: pack[k] for k in ("status", "company", "requests", "truncated", "coverage", "limitations")}
            result["source_pack"] = str((Path(a.output) / "source-pack.json").resolve())
        elif a.command == "candidates":
            from .collect import candidates

            out = a.output or str(Path(a.workspace) / "candidates.json")
            data = candidates(a.workspace, out, a.limit)
            result = {
                "status": "ready_for_reading",
                "matches": data["total_matches"],
                "truncated": data["truncated"],
                "output": str(Path(out).resolve()),
            }
        elif a.command == "read":
            if a.start < 0 or not 1 <= a.limit <= 500:
                raise EvidenceError("Read start must be nonnegative; limit 1-500")
            data = load_source(a.workspace, a.source)
            blocks = [b for b in data["blocks"] if a.find.casefold() in b["text"].casefold()]
            result = {
                "source_id": data["id"],
                "title": data["title"],
                "period": data["period"],
                "published_at": data.get("published_at"),
                "warnings": data["warnings"],
                "total_matches": len(blocks),
                "blocks": blocks[a.start : a.start + a.limit],
                "truncated": a.start + a.limit < len(blocks),
            }
        elif a.command == "ingest":
            pack_path = Path(a.workspace) / "source-pack.json"
            pack = read_json(pack_path)
            metadata = read_json(a.metadata)
            if metadata.get("company") != pack["company"]["id"] or not all(
                k in metadata for k in ("period", "published_at", "title", "kind", "completeness")
            ):
                raise EvidenceError(
                    "Metadata must match the company and include period/publication/title/kind/completeness"
                )
            file = Path(a.file)
            source = add_source(
                a.workspace,
                file.read_bytes(),
                {**metadata, "origin": "user_selected_document"},
                file.suffix.lower().lstrip("."),
            )
            entry = {
                k: source.get(k)
                for k in ("id", "url", "title", "period", "kind", "sha256", "published_at", "completeness")
            }
            if source["id"] not in {d["id"] for d in pack["documents"]}:
                pack["documents"].append(entry)
                pack["acquisition"].append({"status": "user_selected_document", "source_id": source["id"]})
            write_json(pack_path, pack)
            result = {"status": "captured", "source_id": source["id"]}
        elif a.command == "review":
            from .review import review

            result = review(a.workspace, a.analysis, a.output)
        elif a.command == "apply-decisions":
            from .render import apply_decisions

            result = apply_decisions(a.report, a.file)
        elif a.command == "portfolio":
            from .render import portfolio

            result = portfolio(a.reports, a.output)
        elif a.command == "evaluate":
            from .demo import evaluate

            result = evaluate(a.output)
        else:
            from .demo import run

            result = run(a.output)
        print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
        return 2 if result.get("status") in {"blocked", "failed"} else 0
    except (ValueError, OSError, KeyError, TypeError, UnicodeError) as e:
        print(json.dumps({"status": "error", "message": str(e)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
