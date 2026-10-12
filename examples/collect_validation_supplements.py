#!/usr/bin/env python3
"""Acquire official Adobe transcript links and Delta's mid-quarter guidance update.

Uses the same pinned public HTTPS acquisition and source snapshot checks as the collector.
The archive capture is retained locally; no public document text is bundled in the repo.
"""

from pathlib import Path
import argparse
import re
import sys
from urllib.parse import urldefrag

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from management_commitments.network import fetch
from management_commitments.collect import publication
from management_commitments.sources import EvidenceError, add_source, extract, read_json, write_json


def run(root):
    root = Path(root)
    archive_url = "https://www.adobe.com/investor-relations/financial-documents.html"
    response = fetch(archive_url, {"www.adobe.com"})
    archive = extract(response["raw"], "html", archive_url)
    capture = root / "adbe" / "discovery" / "financial-documents.html"
    capture.parent.mkdir(parents=True, exist_ok=True)
    capture.write_bytes(response["raw"])
    links = {
        urldefrag(a["url"])[0] for a in archive["links"] if re.search(r"adbe-q[123]fy25-transcript\.pdf", a["url"])
    }
    for ticker in ["adbe", "dal"]:
        folder = root / ticker
        pack = read_json(folder / "source-pack.json")
        if ticker == "adbe":
            tasks = []
            for url in sorted(links):
                q = re.search(r"adbe-q([123])", url)[1]
                period = next(d["period"] for d in pack["documents"] if d["period"]["label"] == f"FY2025 Q{q}")
                tasks.append((url, period, "transcript", {"www.adobe.com"}))
        else:
            period = next(d["period"] for d in pack["documents"] if d["period"]["label"] == "2025 Q1")
            tasks = [
                ("https://news.delta.com/delta-provides-investor-update", period, "guidance_update", {"news.delta.com"})
            ]
        for url, period, kind, hosts in tasks:
            try:
                response = fetch(url, hosts)
                parsed = extract(response["raw"], response["format"], response["url"])
                published = publication(parsed["blocks"], parsed.get("publication_dates"), response["format"])
                if not published:
                    raise EvidenceError("Supplement publication date unverified")
                if kind == "transcript":
                    release_date = next(
                        d["published_at"]
                        for d in pack["documents"]
                        if d["period"] == period and d["kind"] == "earnings_release"
                    )
                    header = " ".join(b["text"] for b in parsed["blocks"][:5])
                    q = period["label"][-1]
                    if not re.search(rf"Q{q}\s+2025", header) or published != release_date or "Adobe" not in header:
                        raise EvidenceError("Transcript date/company/quarter differs from its release")
                source = add_source(
                    folder,
                    response["raw"],
                    {
                        "company": pack["company"]["id"],
                        "period": period,
                        "kind": kind,
                        "url": response["url"],
                        "requested_url": url,
                        "published_at": published,
                        "publication_basis": "dated source text",
                        "origin": "official_site_fetch",
                        "title": f"{pack['company']['name']} {period['label']} {kind.replace('_', ' ')}",
                        "completeness": "unknown",
                        "redirects": response["redirects"],
                        "period_check": "transcript_header_match"
                        if kind == "transcript"
                        else "reviewed_mid_quarter_update",
                        "discovered_from": archive_url if ticker == "adbe" else "official investor update",
                    },
                    response["format"],
                )
                entry = {
                    k: source.get(k)
                    for k in (
                        "id",
                        "url",
                        "title",
                        "period",
                        "kind",
                        "sha256",
                        "published_at",
                        "captured_at",
                        "completeness",
                        "period_check",
                        "publication_basis",
                    )
                }
                if not any(d["id"] == source["id"] for d in pack["documents"]):
                    pack["documents"].append(entry)
                pack["acquisition"].append(
                    {
                        "url": url,
                        "status": "captured",
                        "source_id": source["id"],
                        "period": period["label"],
                        "discovery": "official_archive_supplement",
                    }
                )
                print(ticker, kind, published, "captured", flush=True)
            except (ValueError, OSError, ImportError) as e:
                pack["acquisition"].append(
                    {"url": url, "status": "failed", "period": period["label"], "message": str(e)[:500]}
                )
                print(ticker, kind, "failed:", str(e)[:150], flush=True)
        for coverage in pack["coverage"]:
            if any(d["kind"] == "transcript" and d["period"] == coverage["period"] for d in pack["documents"]):
                coverage["transcript"] = "captured"
            coverage["documents"] = sum(d["period"] == coverage["period"] for d in pack["documents"])
        if all(c["transcript"] == "captured" for c in pack["coverage"]):
            pack["limitations"] = [s for s in pack["limitations"] if "release-only" not in s]
        pack["supplement_requests"] = len(tasks)
        write_json(folder / "source-pack.json", pack)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    run(parser.parse_args().workspace)
