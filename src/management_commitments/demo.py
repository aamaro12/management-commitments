"""Synthetic financial edge cases, kept separate from live company evidence."""

from copy import deepcopy
from pathlib import Path

from .sources import add_source, read_json, write_json, now
from .review import review

P1 = {"label": "FY2025 Q1", "start": "2025-01-01", "end": "2025-03-31"}
P2 = {"label": "FY2025 Q2", "start": "2025-04-01", "end": "2025-06-30"}
P3 = {"label": "FY2025 Q3", "start": "2025-07-01", "end": "2025-09-30"}


def base_case(id, title, low="10", high="12", actual="11", unit="percent", scale="1", operator="range"):
    return {
        "id": id,
        "title": title,
        "low": low,
        "high": high,
        "actual": actual,
        "unit": unit,
        "scale": scale,
        "operator": operator,
        "basis": "reported",
        "definition": "same scope and measurement",
        "expected": "within_range",
    }


def cases():
    # Exact expectations are hand-authored; these test verifier behavior, not LLM extraction quality.
    result = [
        {
            **base_case("growth_above", "Growth exceeded the stated range", actual="14"),
            "expected": "above_range",
            "rationale": "Growth surpassed the earlier range. Check whether the source of the upside is repeatable.",
            "question": "How much of the upside came from recurring demand rather than timing?",
            "materiality": 5,
        },
        {
            **base_case("margin_below", "Margin fell below guidance", actual="9"),
            "expected": "below_range",
            "rationale": "The reported margin is below both ends of guidance, despite strong growth.",
            "question": "Which costs explain the gap, and are they temporary?",
            "materiality": 5,
        },
        {
            **base_case("definition_changed", "Retention looks stronger after a definition change", actual="12"),
            "observation_definition": "excludes small customers",
            "expected": "definition_changed",
            "materiality": 5,
            "rationale": "The new retention figure excludes a customer group included in the original target. A direct comparison would be misleading.",
            "question": "What would retention have been using the original customer population?",
        },
        {**base_case("growth_met", "Revenue growth landed inside guidance"), "expected": "within_range"},
        {
            **base_case("no_actual", "A target with no disclosed actual"),
            "omit_observation": True,
            "expected": "unresolved",
        },
        {
            **base_case("not_due", "Next-quarter target remains open"),
            "target_period": P3,
            "omit_observation": True,
            "expected": "not_due",
        },
        {
            **base_case("conditional", "Expansion depends on a permit"),
            "conditions": ["permit approved"],
            "expected": "conditional",
        },
        {
            **base_case("currency_basis", "Reported growth is not constant-currency growth"),
            "observation_basis": "constant_currency",
            "expected": "basis_mismatch",
        },
        {**base_case("qualitative", "Become the preferred platform"), "kind": "qualitative", "expected": "qualitative"},
        {**base_case("unreviewed", "An interpretation awaiting review"), "reviewed": False, "expected": "needs_review"},
        {
            **base_case("wrong_period", "A prior-quarter result cannot settle this target"),
            "observation_period": P1,
            "expected": "unresolved",
        },
        {**base_case("lower_edge", "Actual equals the lower bound", actual="10"), "expected": "within_range"},
        {**base_case("upper_edge", "Actual equals the upper bound", actual="12"), "expected": "within_range"},
        {
            **base_case("atleast_met", "Minimum target was achieved", operator="at_least", actual="10"),
            "expected": "met",
        },
        {
            **base_case("atleast_missed", "Minimum target was missed", operator="at_least", actual="9"),
            "expected": "missed",
        },
        {**base_case("atmost_met", "Cost ceiling was respected", operator="at_most", actual="11"), "expected": "met"},
        {
            **base_case("atmost_missed", "Cost ceiling was exceeded", operator="at_most", actual="13"),
            "expected": "missed",
        },
        {
            **base_case(
                "scale_alignment",
                "Million and billion figures reconcile",
                low="1",
                high="1.2",
                actual="1100",
                unit="USD",
                scale="billion",
            ),
            "observation_scale": "million",
            "expected": "within_range",
        },
        {
            **base_case(
                "negative_cost",
                "Negative result below a negative range",
                low="-12",
                high="-10",
                actual="-13",
                unit="USD",
                scale="million",
            ),
            "expected": "below_range",
        },
        {
            **base_case("zero_midpoint", "A range with a zero midpoint", low="-1", high="1", actual="0", unit="USD"),
            "expected": "within_range",
        },
        {
            **base_case("future_actual", "A future publication cannot settle the review"),
            "result_published_at": "2025-09-01",
            "expected": "blocked",
        },
        {
            **base_case("wrong_number", "An unsupported printed number is blocked"),
            "stated_actual": "9",
            "actual": "11",
            "expected": "blocked",
        },
        {
            **base_case("wrong_company", "Another issuer's result is blocked"),
            "observation_company": "OTHER",
            "expected": "blocked",
        },
        {
            **base_case("forecast_not_actual", "A later forecast is not an actual"),
            "observation_kind": "forecast",
            "expected": "blocked",
        },
    ]
    return result


def build(root, selected=None, company=None):
    root = Path(root)
    company = company or {"id": "HARBOR", "name": "Harbor Software (synthetic)"}
    selected = selected if selected is not None else cases()[:10]
    docs, commitments, observations = [], [], []
    for case in selected:
        c = deepcopy(case)
        unit = c["unit"]
        suffix = "%" if unit == "percent" else f" {c['scale']} {unit}"
        statement = (
            f"We expect {c['title'].lower()} at {c['low']} to {c['high']}{suffix} next quarter."
            if c.get("kind") != "qualitative"
            else "We aim to become the preferred platform for independent retailers."
        )
        if c.get("conditions"):
            statement += " This depends on the permit being approved."
        metadata = {
            "company": company["id"],
            "period": P1,
            "published_at": "2025-04-15",
            "completeness": "complete",
            "kind": "synthetic_statement",
            "title": f"{company['name']} statement: {c['id']}",
            "origin": "synthetic_fixture",
        }
        source = add_source(root, statement.encode(), metadata, "txt")
        docs.append(
            {
                k: source.get(k)
                for k in ("id", "title", "url", "period", "kind", "sha256", "published_at", "completeness")
            }
        )
        target = {
            "period": c.get("target_period", P2),
            "definition": c["definition"],
            "basis": c["basis"],
            "unit": unit,
            "scale": c["scale"],
            "operator": c["operator"],
            "low": c["low"],
            "high": c["high"],
        }
        commitment = {
            "id": c["id"],
            "title": c["title"],
            "metric_key": c["id"],
            "topic": "Margins" if "margin" in c["id"] else "Growth & execution",
            "kind": c.get("kind", "numeric"),
            "target": target if c.get("kind") != "qualitative" else None,
            "materiality": c.get("materiality", 2),
            "importance_rationale": c.get("rationale", "Synthetic edge case for the comparison rules."),
            "question": c.get(
                "question", "Is the definition, period and source evidence sufficient to support this assessment?"
            ),
            "evidence": [{"source_id": source["id"], "block_id": "b0001", "quote": statement}],
            "conditions": c.get("conditions", []),
            "semantic_review": {
                "state": "reviewed" if c.get("reviewed", True) else "proposed",
                "reviewer": "Synthetic reference author",
                "notes": "Deliberately constructed definitions and periods; not a real issuer claim.",
            },
            "observation_ids": [],
        }
        if not c.get("omit_observation") and c.get("kind") != "qualitative":
            actual = c.get("stated_actual", c["actual"])
            observation_scale = c.get("observation_scale", c["scale"])
            result_text = f"Reported {c['title'].lower()}: {actual}{'%' if unit == 'percent' else ' ' + observation_scale + ' ' + unit}."
            if c.get("observation_definition"):
                result_text += " The new definition excludes small customers."
            source_o = add_source(
                root,
                result_text.encode(),
                {
                    **metadata,
                    "period": c.get("observation_period", P2),
                    "company": c.get("observation_company", company["id"]),
                    "published_at": c.get("result_published_at", "2025-07-15"),
                    "kind": "synthetic_result",
                    "title": f"{company['name']} result: {c['id']}",
                },
                "txt",
            )
            docs.append(
                {
                    k: source_o.get(k)
                    for k in ("id", "title", "url", "period", "kind", "sha256", "published_at", "completeness")
                }
            )
            oid = c["id"] + "_actual"
            observations.append(
                {
                    "id": oid,
                    "metric_key": c["id"],
                    "kind": c.get("observation_kind", "actual"),
                    "period": c.get("observation_period", P2),
                    "value": c["actual"],
                    "unit": unit,
                    "scale": observation_scale,
                    "basis": c.get("observation_basis", c["basis"]),
                    "definition": c.get("observation_definition", c["definition"]),
                    "evidence": [{"source_id": source_o["id"], "block_id": "b0001", "quote": result_text}],
                }
            )
            commitment["observation_ids"] = [oid]
        commitments.append(commitment)
    pack = {
        "schema_version": 1,
        "company": company,
        "collected_at": now(),
        "documents": docs,
        "coverage": [
            {"period": P1, "documents": len(selected), "transcript": "not_acquired", "earnings_release": False},
            {"period": P2, "documents": len(observations), "transcript": "not_acquired", "earnings_release": False},
        ],
        "acquisition": [{"status": "synthetic_fixture", "url": None}],
        "limitations": ["All companies, statements and figures in this demo are synthetic."],
    }
    analysis = {
        "schema_version": 1,
        "company": company,
        "as_of": "2025-07-31",
        "mode": "synthetic_demo",
        "summary": "Growth beat the stated range, margin fell short, and retention changed definition. Inspect the evidence before accepting an assessment.",
        "commitments": commitments,
        "observations": observations,
        "limitations": ["Hand-authored semantic interpretations; no model extraction quality claim."],
    }
    write_json(root / "source-pack.json", pack)
    write_json(root / "analysis.json", analysis)
    return analysis


def run(output):
    build(output)
    return review(output, Path(output) / "analysis.json", Path(output) / "report")


def evaluate(output):
    sets = [
        ("development", cases()[:17], {"id": "HARBOR", "name": "Harbor Software (synthetic)"}),
        ("held_out_verifier_cases", cases()[17:], {"id": "CEDAR", "name": "Cedar Industries (synthetic)"}),
    ]
    records = []
    for split, selected, company in sets:
        folder = Path(output) / split
        build(folder, selected, company)
        review(folder, folder / "analysis.json", folder / "report")
        report = read_json(folder / "report" / "report.json")
        results = {c["id"]: c for c in report["commitments"]}
        for c in selected:
            records.append(
                {
                    "id": c["id"],
                    "split": split,
                    "expected": c["expected"],
                    "observed": results[c["id"]]["status"],
                    "passed": c["expected"] == results[c["id"]]["status"],
                }
            )
    result = {
        "status": "passed" if all(r["passed"] for r in records) else "failed",
        "cases": len(records),
        "passed": sum(r["passed"] for r in records),
        "records": records,
        "scope": "Synthetic deterministic verifier cases only. Not a benchmark of Codex extraction, semantic review or investment usefulness.",
    }
    write_json(Path(output) / "evaluation.json", result)
    return result
