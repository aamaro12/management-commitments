"""Self-contained review UI and a short portable research brief."""

from html import escape
from importlib.resources import files
import json
from pathlib import Path
import os
import re

from .sources import write_json


def fill(template, **values):
    """Replace each __NAME__ placeholder once, in a single pass, so inserted text is never scanned again."""
    return re.sub("__(" + "|".join(map(re.escape, values)) + ")__", lambda m: values[m[1]], template)


def brief(report, output):
    lines = [
        f"# {report['company']['name']}: management commitments",
        "",
        f"Review as of {report['as_of']}. {report['mode']} mode.",
        "",
        report.get("summary", ""),
        "",
        "## Three items to review",
        "",
    ]
    by_id = {c["id"]: c for c in report["commitments"]}
    for cid in report["top_three"]:
        c = by_id[cid]
        lines.extend(
            [
                f"### {c['title']}",
                "",
                f"Assessment: {c['status'].replace('_', ' ')}.",
                c["importance_rationale"],
                "",
                f"Question: {c['question']}",
                "",
            ]
        )
        calc = c.get("calculation")
        if calc:
            lines.append(f"Actual: {calc['actual_in_target_scale']} {calc['scale']} {calc['unit']}.")
            lines.append(f"Formula: `{calc['formula']}`; inputs: `{json.dumps(calc['inputs'])}`.")
        for r in c["evidence"] + c["result_evidence"]:
            url = r.get("url") or os.path.relpath(r["snapshot_path"], output)
            lines.append(f"Source: [{r['title']}]({url}), {r['source_id']} / {r['block_id']}.")
        lines.extend([*c["flags"], ""])
    lines.extend(
        [
            "## Coverage and limits",
            "",
            *[f"- {s}" for s in report["limitations"]],
            "",
            report["interpretation"],
            "",
            report["priority_method"],
            "",
        ]
    )
    return "\n".join(lines)


def render(report, output):
    output = Path(output)
    assets = files("management_commitments") / "assets"
    data = json.dumps(report, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    css = (assets / "review.css").read_text()
    js = (assets / "review.js").read_text()
    title = escape(report["company"]["name"] + " | Management Commitments")
    html = fill((assets / "review.html").read_text(), TITLE=title, CSS=css, DATA=data, JS=js)
    (output / "review.html").write_text(html)
    (output / "brief.md").write_text(brief(report, output))
    write_json(output / "report.json", report)


def apply_decisions(report_folder, decisions_file):
    from .sources import EvidenceError, now, read_json

    folder = Path(report_folder)
    report = read_json(folder / "report.json")
    data = read_json(decisions_file)
    if data.get("analysis_sha256") != report["analysis_sha256"] or data.get("company") != report["company"]["id"]:
        raise EvidenceError("Decisions were exported from a different analysis or company")
    ids = {c["id"] for c in report["commitments"]}
    reviewer = data.get("reviewer", "").strip()
    if not reviewer or len(reviewer) > 100:
        raise EvidenceError("Provide a reviewer name in the export before applying decisions")
    pending = []
    for d in data.get("decisions", []):
        if d.get("id") not in ids or d.get("decision") not in {
            "accepted",
            "rejected",
            "correction_requested",
            "pending",
        }:
            raise EvidenceError("Unknown commitment or decision")
        if d.get("decision") in {"rejected", "correction_requested"} and not d.get("note", "").strip():
            raise EvidenceError("Rejections and corrections need a note")
        if len(d.get("note", "")) > 2000:
            raise EvidenceError("Decision note exceeds 2000 characters")
        pending.append(
            {
                "id": d["id"],
                "decision": d["decision"],
                "note": d.get("note", ""),
                "reviewer": reviewer,
                "recorded_at": now(),
                "analysis_sha256": report["analysis_sha256"],
            }
        )
    log_path = folder / "review-log.json"
    log = read_json(log_path) if log_path.exists() else []
    log.extend(pending)
    write_json(log_path, log)
    latest = {d["id"]: d for d in log if d["analysis_sha256"] == report["analysis_sha256"]}
    for c in report["commitments"]:
        if c["id"] in latest:
            c["analyst_decision"] = latest[c["id"]]["decision"]
            c["analyst_note"] = latest[c["id"]]["note"]
    report["review_log"] = log
    render(report, folder)
    return {"status": "recorded", "decisions": len(pending), "log": str(log_path.resolve())}


def portfolio(report_folders, output):
    """Connect existing reports with a searchable local company index."""
    from .sources import EvidenceError, now, read_json

    output = Path(output).resolve()
    folders = [Path(p).resolve() for p in report_folders]
    reports = [read_json(p / "report.json") for p in folders]
    if not reports or len({r["company"]["id"] for r in reports}) != len(reports):
        raise EvidenceError("Provide at least one report, with distinct company identities")
    attention = {
        "blocked",
        "below_range",
        "missed",
        "definition_changed",
        "basis_mismatch",
        "conditional",
        "unresolved",
        "needs_review",
    }
    rows = []
    for folder, r in zip(folders, reports):
        rows.append(
            {
                "company": r["company"],
                "summary": r["summary"],
                "as_of": r["as_of"],
                "href": os.path.relpath(folder / "review.html", output),
                "tracked": len(r["commitments"]),
                "compared": sum(bool(c.get("calculation")) for c in r["commitments"]),
                "attention": sum(c["status"] in attention or bool(c.get("updates")) for c in r["commitments"]),
                "blocked": r["counts"].get("blocked", 0),
                "transcripts": sum(c["transcript"] == "captured" for c in r["coverage"]),
                "quarters": len(r["coverage"]),
            }
        )
    data = {
        "schema_version": 1,
        "generated_at": now(),
        "reports": rows,
        "review_dates": sorted({r["as_of"] for r in reports}),
        "totals": {
            "companies": len(rows),
            **{key: sum(r[key] for r in rows) for key in ["tracked", "compared", "transcripts", "blocked"]},
        },
    }
    assets = files("management_commitments") / "assets"
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace("<", "\\u003c").replace("&", "\\u0026")
    html = fill(
        (assets / "portfolio.html").read_text(),
        CSS=(assets / "review.css").read_text() + "\n" + (assets / "portfolio.css").read_text(),
        DATA=payload,
        JS=(assets / "portfolio.js").read_text(),
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "index.html").write_text(html)
    write_json(output / "portfolio.json", data)
    for folder, r in zip(folders, reports):
        r["portfolio_href"] = os.path.relpath(output / "index.html", folder)
        r["related_reports"] = [
            {"ticker": other["company"]["id"], "href": os.path.relpath(other_folder / "review.html", folder)}
            for other_folder, other in zip(folders, reports)
        ]
        render(r, folder)
    return {"status": "ready", "index": str(output / "index.html"), "totals": data["totals"]}
