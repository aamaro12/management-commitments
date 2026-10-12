#!/usr/bin/env python3
"""Replay a curated interpretation of automatically acquired FY25 Q1-Q3 sources.

This is an example, not general-purpose model extraction. Numbers and references
are selected from captured bytes; Codex/analyst interpretations are documented.
No public-company document text is bundled with this repository.
"""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from management_commitments.review import printed_numbers, review
from management_commitments.sources import EvidenceError, load_source, read_json, write_json


def build(root):
    root = Path(root)
    pack = read_json(root / "source-pack.json")
    if pack["company"]["id"] != "MSFT":
        raise EvidenceError("This curated example requires Microsoft's official FY25 Q1-Q3 materials")
    sources = {}
    for doc in pack["documents"]:
        if doc["kind"] in {"transcript", "earnings_release"}:
            sources[(doc["period"]["label"], doc["kind"])] = load_source(root, doc["id"])

    def find(q, kind, needle, cell=False):
        s = sources[(f"FY2025 Q{q}", kind)]
        matches = [
            b
            for b in s["blocks"]
            if (b["context"].get("cells", [None])[0] == needle if cell else needle.casefold() in b["text"].casefold())
        ]
        if not matches:
            raise EvidenceError(f"Example passage missing: quarter {q}, {needle}")
        b = matches[0]
        return {"source_id": s["id"], "block_id": b["id"], "quote": b["text"]}, b

    periods = {int(d["period"]["label"][-1]): d["period"] for d in pack["documents"]}
    periods[4] = {"label": "FY2025 Q4", "start": "2025-04-01", "end": "2025-06-30"}
    commitments, observations = [], []

    def ranged(
        cid,
        title,
        q,
        statement,
        result_q,
        metric,
        rationale,
        question,
        materiality=3,
        unit="percent",
        scale="1",
        result_row=None,
        result_phrase=None,
        result_cell=1,
        actual_basis="constant_currency",
    ):
        ref, _ = find(q, "transcript", statement)
        bounds = printed_numbers(ref["quote"])[-2:]
        if len(bounds) != 2:
            raise EvidenceError("Curated example could not find the two target bounds")
        definition = metric.replace("_", " ")
        c = {
            "id": cid,
            "title": title,
            "topic": "Cloud & AI" if "azure" in cid or "cloud" in cid else "Segment performance",
            "metric_key": metric,
            "kind": "numeric",
            "evidence": [ref],
            "conditions": [],
            "target": {
                "period": periods[q + 1],
                "definition": definition,
                "basis": actual_basis,
                "unit": unit,
                "scale": scale,
                "operator": "range",
                "low": str(bounds[0]),
                "high": str(bounds[1]),
            },
            "materiality": materiality,
            "importance_rationale": rationale,
            "question": question,
            "semantic_review": {
                "state": "reviewed",
                "reviewer": "Codex curated example",
                "notes": "Reviewed the outlook section, fiscal quarter, metric scope, reported versus constant-currency basis, later table headers and relevant call Q&A. This is a replayable reference interpretation, not independent human approval.",
            },
            "observation_ids": [],
        }
        if result_q:
            oref, oblock = (
                find(result_q, "earnings_release", result_row, cell=True)
                if result_row
                else find(result_q, "transcript", result_phrase)
            )
            tokens = printed_numbers(oblock["context"]["cells"][result_cell] if result_row else oblock["text"])
            oid = cid + "-actual"
            o = {
                "id": oid,
                "metric_key": metric,
                "kind": "actual",
                "period": periods[result_q],
                "definition": definition,
                "basis": actual_basis,
                "unit": unit,
                "scale": "million" if result_row and unit == "USD" else "1",
                "value": str(tokens[0]),
                "evidence": [oref],
            }
            if result_row:
                o.update(
                    {
                        "cell_index": result_cell,
                        "column_review": "Selected the current three-month period, not the prior-year or year-to-date column. Revenue is in USD millions; Azure growth uses the constant-currency column.",
                    }
                )
            observations.append(o)
            c["observation_ids"] = [oid]
        commitments.append(c)
        return c

    ranged(
        "azure-q2",
        "Azure growth landed at the bottom of guidance",
        1,
        "In Azure, we expect Q2 revenue growth",
        2,
        "azure_and_other_cloud_services_revenue_growth_yoy",
        "The quarter met the range at its lower edge. Read the non-AI execution explanation alongside the stronger AI contribution; the aggregate result alone hides that difference.",
        "Did the changes in non-AI sales execution improve consumption, or did capacity additions explain the next quarter's progress?",
        4,
        result_row="Azure and other cloud services",
        result_cell=3,
    )
    azure_q3 = ranged(
        "azure-q3",
        "Azure outperformed; the explanation is broader than AI",
        2,
        "In Azure, we expect Q3 revenue growth",
        3,
        "azure_and_other_cloud_services_revenue_growth_yoy",
        "Constant-currency growth exceeded the earlier range. Management's Q&A attributed most of the upside versus its expectations to non-AI services, alongside earlier AI capacity delivery.",
        "How durable is the enterprise and non-AI execution improvement after this quarter?",
        5,
        result_row="Azure and other cloud services",
        result_cell=3,
    )
    update, _ = find(3, "transcript", "the majority of our outperformance")
    azure_q3["updates"] = [
        {
            "type": "wording_changed",
            "interpretation": "Q&A clarified the main source of upside; do not attribute the entire growth outperformance to AI.",
            "evidence": [update],
        }
    ]
    ranged(
        "cloud-q2",
        "Intelligent Cloud was narrowly below dollar guidance",
        1,
        "we expect revenue in Intelligent Cloud to grow",
        2,
        "intelligent_cloud_segment_revenue",
        "The exact financial table is slightly below the lower dollar bound. The transcript's rounded figure is not precise enough to adjudicate this small gap; management also described unfavourable FX and non-AI execution issues.",
        "How much of the shortfall reflects currency, timing and underlying non-AI demand?",
        2,
        unit="USD",
        scale="billion",
        result_row="Intelligent Cloud",
        actual_basis="reported",
    )
    ranged(
        "cloud-q3",
        "Intelligent Cloud exceeded the next quarter's range",
        2,
        "For Intelligent Cloud we expect revenue to grow",
        3,
        "intelligent_cloud_segment_revenue",
        "The segment's reported revenue exceeded the dollar guidance. The growth and capacity commentary helps explain the change, but does not establish how much is repeatable.",
        "What proportion of the upside came from recurring consumption rather than revenue-recognition timing?",
        3,
        unit="USD",
        scale="billion",
        result_row="Intelligent Cloud",
        actual_basis="reported",
    )
    ranged(
        "productivity-q2",
        "Productivity revenue exceeded the earlier range",
        1,
        "we expect revenue in Productivity and Business Processes to grow",
        2,
        "productivity_and_business_processes_segment_revenue",
        "The current-quarter financial table exceeded the dollar range. Management cited Microsoft 365 commercial performance, including transactional purchasing, so recurring adoption and product timing need separate examination.",
        "How much of the improvement reflects recurring cloud adoption versus transactional Office purchasing?",
        2,
        unit="USD",
        scale="billion",
        result_row="Productivity and Business Processes",
        actual_basis="reported",
    )
    ranged(
        "azure-q4",
        "The next Azure target remains open at this review date",
        3,
        "In Azure, we expect Q4 revenue growth",
        None,
        "azure_and_other_cloud_services_revenue_growth_yoy",
        "This target was issued with the latest acquired call. Its financial period had not ended at the historical review date; no outcome is inferred from the absent Q4 sources.",
        "What will the next release say about the capacity constraint and non-AI execution?",
        3,
    )
    # The Q4 paragraph contains no other standalone numbers after its bounds.
    original, _ = find(2, "transcript", "by the end of FY25 we should be roughly")
    later, _ = find(3, "transcript", "constraints beyond June")
    commitments.append(
        {
            "id": "capacity-timeline",
            "title": "Capacity catch-up expectations moved beyond June",
            "topic": "Cloud & AI",
            "metric_key": "ai_capacity_vs_near_term_demand",
            "kind": "qualitative",
            "target": None,
            "evidence": [original],
            "conditions": ["Near-term demand and planned datacenter capacity"],
            "materiality": 5,
            "importance_rationale": "The earlier call expected capacity to be roughly aligned with near-term demand by fiscal year-end. The later call expected constraints beyond June because demand was growing faster. This is a changed expectation, not proof of a delivery failure.",
            "question": "Is the extended constraint driven by faster demand, delayed delivery, or a combination?",
            "semantic_review": {
                "state": "reviewed",
                "reviewer": "Codex curated example",
                "notes": "Compared the full Q2 outlook paragraph with Q3 guidance. No numeric capacity measure or fixed demand baseline was disclosed, so no pass/fail calculation is appropriate.",
            },
            "updates": [
                {
                    "type": "wording_changed",
                    "interpretation": "The expected constraint extended beyond the earlier fiscal-year-end reference; the stated explanation was faster-growing demand.",
                    "evidence": [later],
                }
            ],
        }
    )
    original, _ = find(1, "transcript", "annual revenue run rate of $10 billion")
    later, _ = find(2, "transcript", "annual revenue run rate of $13 billion")
    observations.append(
        {
            "id": "ai-run-rate-actual",
            "metric_key": "management_defined_ai_business_annual_revenue_run_rate",
            "kind": "actual",
            "period": periods[2],
            "definition": "Management-defined AI business annual revenue run rate; not quarterly revenue or an audited segment",
            "basis": "management_defined",
            "unit": "USD",
            "scale": "billion",
            "value": str(printed_numbers(later["quote"])[0]),
            "evidence": [later],
        }
    )
    commitments.append(
        {
            "id": "ai-run-rate",
            "title": "Management reported that the AI run-rate milestone was passed",
            "topic": "Cloud & AI",
            "metric_key": "management_defined_ai_business_annual_revenue_run_rate",
            "kind": "numeric",
            "evidence": [original],
            "target": {
                "period": periods[2],
                "definition": "Management-defined AI business annual revenue run rate; not quarterly revenue or an audited segment",
                "basis": "management_defined",
                "unit": "USD",
                "scale": "billion",
                "operator": "greater_than",
                "measurement_type": "point_in_time",
                "measurement_date": "2024-12-31",
                "low": str(printed_numbers(original["quote"])[0]),
            },
            "conditions": [],
            "materiality": 3,
            "importance_rationale": "The later call reported a run rate above the earlier milestone. The exact measurement date, construction and business mix were not fully disclosed, so the by-quarter-end outcome remains unresolved. It is not quarterly revenue.",
            "question": "When was the milestone passed, and what business mix and annualisation method sit behind it?",
            "observation_ids": ["ai-run-rate-actual"],
            "semantic_review": {
                "state": "reviewed",
                "reviewer": "Codex curated example",
                "notes": "Matched the AI business run-rate wording across calls and preserved the strict 'surpass' target. The precise measurement date was not given, so the by-quarter-end comparison remains unresolved. The underlying metric is not independently verified.",
            },
        }
    )
    analysis = {
        "schema_version": 1,
        "company": pack["company"],
        "as_of": "2025-05-01",
        "mode": "historical_public_company_demo",
        "summary": "Azure outperformed its next-quarter range, capacity expectations shifted beyond June, and a management-defined AI milestone was reported as passed. The review keeps currency, periods and qualitative claims separate.",
        "commitments": commitments,
        "observations": observations,
        "limitations": [
            "Curated Codex interpretation of FY25 Q1-Q3; not exhaustive commitment extraction or independent human review.",
            f"Sources were retrieved on {pack.get('collected_at', 'an unrecorded date')[:10]}. This retrospective demonstration does not prove that the document versions were available unchanged on the historical review date.",
            "Transcript body text was inspected; Office headers/comments and visual-only outlook slides are not covered.",
            "Management's AI run rate is a reported internal measure; its construction is not independently verified.",
        ],
    }
    write_json(root / "analysis.json", analysis)
    return review(root, root / "analysis.json", root / "report")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    args = p.parse_args()
    import json

    print(json.dumps(build(args.workspace), indent=2))
