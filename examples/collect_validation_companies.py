#!/usr/bin/env python3
"""Acquire ten official company source packs with bounded requests per issuer."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from management_commitments.collect import collect
from management_commitments.sources import read_json, write_json


def profiles():
    result = []

    def add(ticker, name, labels, starts, ends, urls, extra_hosts=()):
        result.append(
            {
                "company": {"id": ticker, "name": name},
                "aliases": [ticker, name],
                "allowed_hosts": sorted({urlsplit(u).hostname for u in urls} | set(extra_hosts)),
                "seeds": [
                    {"url": u, "period": {"label": label, "start": start, "end": end}}
                    for u, label, start, end in zip(urls, labels, starts, ends)
                ],
                "description": "Historical three-quarter source pack for live workflow validation. Dates and metric mappings require review.",
            }
        )

    calendar_labels = ["2024 Q4", "2025 Q1", "2025 Q2"]
    calendar_starts = ["2024-10-01", "2025-01-01", "2025-04-01"]
    calendar_ends = ["2024-12-31", "2025-03-31", "2025-06-30"]

    def cal(ticker, name, urls, hosts=()):
        add(ticker, name, calendar_labels, calendar_starts, calendar_ends, urls, hosts)

    add(
        "NVDA",
        "NVIDIA",
        ["FY2025 Q4", "FY2026 Q1", "FY2026 Q2"],
        ["2024-10-28", "2025-01-27", "2025-04-28"],
        ["2025-01-26", "2025-04-27", "2025-07-27"],
        [
            "https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Announces-Financial-Results-for-Fourth-Quarter-and-Fiscal-2025/default.aspx",
            "https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Announces-Financial-Results-for-First-Quarter-Fiscal-2026/default.aspx",
            "https://investor.nvidia.com/news/press-release-details/2025/NVIDIA-Announces-Financial-Results-for-Second-Quarter-Fiscal-2026/default.aspx",
        ],
        ["nvidianews.nvidia.com", "s201.q4cdn.com"],
    )
    add(
        "AMD",
        "Advanced Micro Devices",
        calendar_labels,
        ["2024-09-29", "2024-12-29", "2025-03-30"],
        ["2024-12-28", "2025-03-29", "2025-06-28"],
        [
            "https://ir.amd.com/news-events/press-releases/detail/1236/amd-reports-fourth-quarter-and-full-year-2024-financial-results",
            "https://ir.amd.com/news-events/press-releases/detail/1247/amd-reports-first-quarter-2025-financial-results",
            "https://ir.amd.com/news-events/press-releases/detail/1257/amd-reports-second-quarter-2025-financial-results",
        ],
        ["d1io3yog0oux5.cloudfront.net"],
    )
    add(
        "ADBE",
        "Adobe",
        ["FY2025 Q1", "FY2025 Q2", "FY2025 Q3"],
        ["2024-11-30", "2025-03-01", "2025-05-31"],
        ["2025-02-28", "2025-05-30", "2025-08-29"],
        [
            "https://news.adobe.com/news/2025/03/adobe-q1fy25-financial-results",
            "https://news.adobe.com/news/2025/06/adobe-q2fy25-financial-results",
            "https://www.adobe.com/cc-shared/assets/investor-relations/pdfs/11905202/aiy4w5teshy5t.pdf",
        ],
        ["www.adobe.com"],
    )
    add(
        "CRM",
        "Salesforce",
        ["FY2025 Q4", "FY2026 Q1", "FY2026 Q2"],
        ["2024-11-01", "2025-02-01", "2025-05-01"],
        ["2025-01-31", "2025-04-30", "2025-07-31"],
        [
            "https://investor.salesforce.com/news/news-details/2025/Salesforce-Announces-Fourth-Quarter-and-Fiscal-Year-2025-Results/default.aspx",
            "https://investor.salesforce.com/news/news-details/2025/Salesforce-Reports-Record-First-Quarter-Fiscal-2026-Results/default.aspx",
            "https://investor.salesforce.com/news/news-details/2025/Salesforce-Reports-Record-Second-Quarter-Fiscal-2026-Results/default.aspx",
        ],
        ["s23.q4cdn.com"],
    )
    cal(
        "AMZN",
        "Amazon",
        [
            f"https://ir.aboutamazon.com/news-release/news-release-details/2025/Amazon-com-Announces-{q}-Quarter-Results/default.aspx"
            for q in ["Fourth", "First", "Second"]
        ],
        ["s2.q4cdn.com"],
    )
    cal(
        "META",
        "Meta",
        [
            "https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-Fourth-Quarter-and-Full-Year-2024-Results/default.aspx",
            "https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-First-Quarter-2025-Results/default.aspx",
            "https://investor.atmeta.com/investor-news/press-release-details/2025/Meta-Reports-Second-Quarter-2025-Results/default.aspx",
        ],
        ["s21.q4cdn.com"],
    )
    cal(
        "UBER",
        "Uber",
        [
            "https://investor.uber.com/news-events/news/press-release-details/2025/Uber-Announces-Results-for-Fourth-Quarter-and-Full-Year-2024/default.aspx",
            "https://investor.uber.com/news-events/news/press-release-details/2025/Uber-Announces-Results-for-First-Quarter-2025/default.aspx",
            "https://investor.uber.com/news-events/news/press-release-details/2025/Uber-Announces-Results-for-Second-Quarter-2025/default.aspx",
        ],
        ["s23.q4cdn.com"],
    )
    cal(
        "PYPL",
        "PayPal",
        [
            "https://investor.pypl.com/files/doc_financials/2024/q4/PYPL-4Q-24-Earnings-Release.pdf",
            "https://investor.pypl.com/files/doc_financials/2025/q1/PYPL-1Q-25-Earnings-Release.pdf",
            "https://investor.pypl.com/files/doc_financials/2025/q2/PYPL-2Q-25-Earnings-Release.pdf",
        ],
        ["s205.q4cdn.com"],
    )
    add(
        "WMT",
        "Walmart",
        ["FY2025 Q4", "FY2026 Q1", "FY2026 Q2"],
        ["2024-11-01", "2025-02-01", "2025-05-01"],
        ["2025-01-31", "2025-04-30", "2025-07-31"],
        [
            "https://corporate.walmart.com/news/2025/02/20/walmart-releases-q4-fy25-earnings",
            "https://corporate.walmart.com/news/2025/05/15/walmart-releases-q1-fy26-earnings",
            "https://corporate.walmart.com/news/2025/08/21/walmart-releases-q2-fy26-earnings",
        ],
        ["stock.walmart.com"],
    )
    cal(
        "DAL",
        "Delta Air Lines",
        [
            "https://ir.delta.com/news/news-details/2025/Delta-Air-Lines-Announces-December-Quarter-and-Full-Year-2024-Financial-Results/default.aspx",
            "https://ir.delta.com/news/news-details/2025/Delta-Air-Lines-Announces-March-Quarter-2025-Financial-Results/default.aspx",
            "https://ir.delta.com/news/news-details/2025/Delta-Air-Lines-Announces-June-Quarter-2025-Financial-Results/default.aspx",
        ],
        ["s2.q4cdn.com"],
    )
    for p in result:
        for i, seed in enumerate(p["seeds"]):
            seed["title_pattern"] = (
                ["Q1", "Q2", "Q3"][i]
                if p["company"]["id"] == "ADBE"
                else ["Q4 FY25", "Q1 FY26", "Q2 FY26"][i]
                if p["company"]["id"] == "WMT"
                else ["December Quarter", "March Quarter", "June Quarter"][i]
                if p["company"]["id"] == "DAL"
                else ["Fourth Quarter", "First Quarter", "Second Quarter"][i]
            )
    return result


def run(output, budget=9, depth=1, only=None):
    out = Path(output)
    all_profiles = profiles()
    ps = [p for p in all_profiles if not only or p["company"]["id"] in only]
    write_json(out / "profiles.json", all_profiles)
    summary_path = out / "collection-summary.json"
    results = read_json(summary_path) if only and summary_path.exists() else []

    def one(p):
        folder = out / p["company"]["id"].lower()
        write_json(folder / "profile.json", p)
        pack = collect(p, folder, budget=budget, depth=depth)
        return {
            "company": p["company"],
            "workspace": str(folder),
            "requests": pack["requests"],
            "documents": len(pack["documents"]),
            "status": pack["status"],
            "failures": [a for a in pack["acquisition"] if a["status"] == "failed"],
            "missing_dates": sum(not d.get("published_at") for d in pack["documents"]),
            "coverage": pack["coverage"],
        }

    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(one, p): p["company"]["id"] for p in ps}
        for job in as_completed(jobs):
            try:
                result = job.result()
            except Exception as e:
                result = {"company": {"id": jobs[job]}, "status": "failed", "message": str(e)}
            results = [r for r in results if r["company"]["id"] != result["company"]["id"]]
            results.append(result)
            write_json(out / "collection-summary.json", results)
            print(
                result["company"]["id"],
                result["status"],
                result.get("documents", 0),
                "documents;",
                result.get("missing_dates", 0),
                "unverified dates",
                flush=True,
            )
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--budget", type=int, default=9)
    p.add_argument("--depth", type=int, default=1)
    p.add_argument("--only", nargs="*")
    a = p.parse_args()
    run(a.output, a.budget, a.depth, a.only)
