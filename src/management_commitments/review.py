"""Deterministic comparisons over explicitly reviewed, source-linked interpretations."""

from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re

from .sources import EvidenceError, now, read_json, resolve, write_json

UNITS = {"USD", "EUR", "GBP", "percent", "percentage_points", "count", "multiple"}
SCALES = {"1": Decimal(1), "thousand": Decimal(1000), "million": Decimal(1000000), "billion": Decimal(1000000000)}
NUMBER = re.compile(r"(?<![\w.])(?:\(?[-−]?[$€£]?\d[\d,]*(?:\.\d+)?%?\)?)(?![\w.])")
STATUSES = {
    "within_range",
    "above_range",
    "below_range",
    "met",
    "missed",
    "not_due",
    "unresolved",
    "definition_changed",
    "basis_mismatch",
    "conditional",
    "qualitative",
    "needs_review",
    "blocked",
}


def decimal(value):
    if isinstance(value, bool) or value is None:
        raise EvidenceError("Numeric input must be a finite decimal, not a boolean/null")
    try:
        d = Decimal(str(value))
    except InvalidOperation as e:
        raise EvidenceError("Invalid numerical input") from e
    if not d.is_finite() or abs(d) > Decimal("1e18"):
        raise EvidenceError("Numeric input is non-finite or outside the supported magnitude")
    return d


def printed_numbers(text):
    result = []
    for match in NUMBER.finditer(text):
        token = match.group(0)
        negative = token.startswith("(") and token.endswith(")")
        clean = token.strip("()%").replace(",", "").replace("−", "-")
        clean = clean.replace("$", "").replace("€", "").replace("£", "")
        result.append(-decimal(clean) if negative else decimal(clean))
    return result


def period(value):
    if not isinstance(value, dict) or not value.get("label"):
        raise EvidenceError("Period needs label, start and end dates")
    start, end = date.fromisoformat(value["start"]), date.fromisoformat(value["end"])
    if start > end:
        raise EvidenceError("Period starts after its end")
    return start, end


def period_same(a, b):
    return period(a) == period(b)


def source_refs(root, refs, company, as_of):
    if not isinstance(refs, list) or not refs:
        raise EvidenceError("Every statement needs source evidence")
    items = []
    for ref in refs:
        item = resolve(root, ref)
        if item["company"] != company:
            raise EvidenceError("Evidence belongs to a different company")
        published = item["published_at"]
        if not published:
            raise EvidenceError("Source publication date is unverified; confirm before comparison")
        if date.fromisoformat(published) > as_of:
            raise EvidenceError("Evidence was published after the review as-of date")
        items.append(item)
    return items


def quantities(value, refs, fields):
    if value.get("unit") not in UNITS or value.get("scale", "1") not in SCALES:
        raise EvidenceError("Unsupported unit or scale")
    if value["unit"] in {"percent", "percentage_points", "multiple"} and value.get("scale", "1") != "1":
        raise EvidenceError("Dimensionless values must use scale 1")
    if not value.get("definition") or not value.get("basis"):
        raise EvidenceError("Metric needs an explicit definition and measurement basis")
    tokens = [n for r in refs for n in printed_numbers(r["quote"])]
    for field in fields:
        if field in value:
            number = decimal(value[field])
            if number not in tokens:
                raise EvidenceError(f"{field} is not printed in the cited excerpt")
    if "value" in fields:
        table_refs = [r for r in refs if r["context"].get("cells")]
        if table_refs:
            if (
                len(table_refs) != 1
                or not isinstance(value.get("cell_index"), int)
                or isinstance(value.get("cell_index"), bool)
            ):
                raise EvidenceError("Table actual needs one source row and an explicit zero-based cell_index")
            cells = table_refs[0]["context"]["cells"]
            index = value["cell_index"]
            if index < 0 or index >= len(cells) or decimal(value["value"]) not in printed_numbers(cells[index]):
                raise EvidenceError("Actual does not match the selected table cell")
            if not value.get("column_review"):
                raise EvidenceError("Table actual needs a reviewed column/period/basis explanation")
    return SCALES[value.get("scale", "1")]


def tolerance_bounds(target):
    if "low" in target or "high" in target:
        raise EvidenceError("Tolerance bounds must be derived in Python, not supplied as printed inputs")
    scale_t = SCALES[target.get("scale", "1")]
    if target["operator"] == "tolerance":
        center = decimal(target["center"])
        tolerance = target["tolerance"]
        value = decimal(tolerance["value"])
        if value < 0:
            raise EvidenceError("Tolerance cannot be negative")
        if tolerance["type"] in {"relative_percent", "basis_points"} and tolerance.get("scale", "1") != "1":
            raise EvidenceError("Relative percentages and basis points must use tolerance scale 1")
        if target["unit"] in {"percent", "percentage_points", "multiple"} and tolerance.get("scale", "1") != "1":
            raise EvidenceError("Dimensionless tolerances must use scale 1")
        if tolerance["type"] == "relative_percent":
            width = abs(center) * value / 100
            formula = "abs(center) * tolerance_percent / 100"
        elif tolerance["type"] == "basis_points" and target["unit"] == "percent":
            width = value / 100
            formula = "tolerance_basis_points / 100"
        elif tolerance["type"] == "absolute" and tolerance.get("scale", "1") in SCALES:
            width = value * SCALES[tolerance.get("scale", "1")] / scale_t
            formula = "tolerance_printed * tolerance_scale / target_scale"
        else:
            raise EvidenceError("Unsupported tolerance type/unit/scale")
        low, high = center - width, center + width
        tolerance_work = {
            "center": str(center),
            "tolerance": tolerance,
            "half_width_in_target_scale": str(width),
            "formula": formula,
            "derived_low": str(low),
            "derived_high": str(high),
        }
        return low, high, tolerance_work
    raise EvidenceError("Expected a tolerance target")


def compare(target, observation):
    scale_t, scale_o = SCALES[target.get("scale", "1")], SCALES[observation.get("scale", "1")]
    actual = decimal(observation["value"]) * scale_o / scale_t
    low = decimal(target["low"]) if "low" in target else None
    high = decimal(target["high"]) if "high" in target else None
    operator = target["operator"]
    tolerance_work = None
    if operator == "tolerance":
        low, high, tolerance_work = tolerance_bounds(target)
    result = {
        "actual_in_target_scale": str(actual),
        "unit": target["unit"],
        "scale": target.get("scale", "1"),
        "formula": "actual_printed * actual_scale / target_scale",
        "inputs": {
            "actual_printed": observation["value"],
            "actual_scale": str(scale_o),
            "target_scale": str(scale_t),
            "low": str(low) if low is not None else None,
            "high": str(high) if high is not None else None,
        },
    }
    if operator in {"range", "tolerance"}:
        if low is None or high is None or low > high:
            raise EvidenceError("Range needs ordered low and high bounds")
        status = "below_range" if actual < low else "above_range" if actual > high else "within_range"
        midpoint = (low + high) / 2
        result.update(
            {
                "midpoint": str(midpoint),
                "gap_to_midpoint": str(actual - midpoint),
                "gap_formula": "actual_in_target_scale - (low + high) / 2",
            }
        )
        result["gap_to_range"] = str(actual - low if actual < low else actual - high if actual > high else Decimal(0))
        result["gap_to_range_formula"] = "actual - low when below; actual - high when above; 0 when within"
        if tolerance_work:
            result["tolerance_calculation"] = tolerance_work
        if midpoint != 0:
            result["relative_gap_percent"] = str((actual / midpoint - 1) * 100)
            result["relative_gap_formula"] = "(actual_in_target_scale / midpoint - 1) * 100"
        if target["unit"] == "percent":
            result["gap_unit"] = "percentage_points"
    elif operator in {"at_least", "greater_than"}:
        if low is None:
            raise EvidenceError("At-least target needs low bound")
        status = "met" if (actual >= low if operator == "at_least" else actual > low) else "missed"
        result.update({"gap_to_bound": str(actual - low), "gap_formula": "actual_in_target_scale - low"})
    elif operator in {"at_most", "less_than"}:
        if high is None:
            raise EvidenceError("At-most target needs high bound")
        status = "met" if (actual <= high if operator == "at_most" else actual < high) else "missed"
        result.update({"gap_to_bound": str(actual - high), "gap_formula": "actual_in_target_scale - high"})
    else:
        raise EvidenceError("Supported operators: range, at_least, at_most, greater_than, less_than")
    result["result"] = status
    return result


def review_commitment(root, commitment, observations, company, as_of):
    c = commitment
    output = {
        "id": c.get("id"),
        "title": c.get("title"),
        "topic": c.get("topic", "Other"),
        "metric_key": c.get("metric_key"),
        "kind": c.get("kind"),
        "materiality": c.get("materiality", 1),
        "importance_rationale": c.get("importance_rationale", ""),
        "question": c.get("question", ""),
        "semantic_review": c.get("semantic_review", {}),
        "target": c.get("target"),
        "conditions": c.get("conditions", []),
        "condition_assessment": None,
        "evidence": [],
        "result_evidence": [],
        "updates": [],
        "calculation": None,
        "flags": [],
        "status": "blocked",
        "analyst_decision": "pending",
    }
    try:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", c.get("id", "")) or not c.get("title") or not c.get("metric_key"):
            raise EvidenceError("Commitment needs a stable id, title and metric key")
        if (
            isinstance(output["materiality"], bool)
            or not isinstance(output["materiality"], int)
            or not 1 <= output["materiality"] <= 5
        ):
            raise EvidenceError("Materiality must be an analyst-assigned integer from 1 to 5")
        refs = source_refs(root, c["evidence"], company, as_of)
        output["evidence"] = refs
        if any(r["completeness"] != "complete" for r in refs):
            output["flags"].append("Statement source coverage is partial or unconfirmed")
        review = c.get("semantic_review") or {}
        if not isinstance(review, dict):
            raise EvidenceError("Semantic review must be a structured object")
        reviewed = review.get("state") == "reviewed" and bool(review.get("reviewer")) and bool(review.get("notes"))
        statement_date = max(date.fromisoformat(r["published_at"]) for r in refs)
        ca = c.get("condition_assessment")
        if ca is not None:
            if not isinstance(ca, dict) or (ca.get("met") is not None and not isinstance(ca.get("met"), bool)):
                raise EvidenceError("Condition assessment must use true, false or null")
            evidence = source_refs(root, ca.get("evidence", []), company, as_of) if ca.get("evidence") else []
            if ca.get("met") is not None and (not evidence or not ca.get("notes")):
                raise EvidenceError("A satisfied or unmet condition needs evidence and notes")
            output["condition_assessment"] = {**ca, "evidence": evidence}
        for update in c.get("updates", []):
            update_refs = source_refs(root, update["evidence"], company, as_of)
            if min(date.fromisoformat(r["published_at"]) for r in update_refs) < statement_date:
                raise EvidenceError("Update predates the original statement")
            if update.get("type") not in {
                "revised_target",
                "definition_changed",
                "conditions_changed",
                "reaffirmed",
                "wording_changed",
            }:
                raise EvidenceError("Unknown update type")
            output["updates"].append({**update, "evidence": update_refs})
        if c["kind"] == "qualitative":
            output["status"] = "qualitative" if reviewed else "needs_review"
            output["flags"].append("No numerical pass/fail test; later wording is a reviewed interpretation")
            return output
        if c["kind"] != "numeric":
            raise EvidenceError("Commitment kind must be numeric or qualitative")
        target = c["target"]
        _, deadline = period(target["period"])
        measurement_type = target.get("measurement_type", "period")
        if measurement_type not in {"period", "point_in_time"}:
            raise EvidenceError("Measurement type must be period or point_in_time")
        if measurement_type == "point_in_time":
            deadline = date.fromisoformat(target.get("measurement_date") or target["period"]["end"])
            if not period(target["period"])[0] <= deadline <= period(target["period"])[1]:
                raise EvidenceError("Point-in-time target date falls outside its stated period")
        quantities(target, refs, ["low", "high"] if target["operator"] != "tolerance" else ["center"])
        if target["operator"] == "tolerance":
            tol = target.get("tolerance", {})
            if decimal(tol.get("value")) not in [n for r in refs for n in printed_numbers(r["quote"])]:
                raise EvidenceError("Tolerance value is not printed in the cited excerpt")
            tolerance_bounds(target)
        if statement_date > deadline:
            raise EvidenceError("Commitment was stated after the target period ended")
        requested = c.get("observation_ids", [])
        if len(requested) != len(set(requested)):
            raise EvidenceError("Duplicate observation link")
        obs = []
        for oid in requested:
            if oid not in observations:
                raise EvidenceError("Observation id not found")
            o = observations[oid]
            if o.get("metric_key") != c["metric_key"]:
                raise EvidenceError("Linked observation measures a different metric")
            orefs = source_refs(root, o["evidence"], company, as_of)
            context_refs = source_refs(root, o["context_evidence"], company, as_of) if o.get("context_evidence") else []
            if any(date.fromisoformat(r["published_at"]) < statement_date for r in orefs):
                raise EvidenceError("Result evidence predates the commitment")
            quantities(o, orefs, ["value"])
            if o.get("kind") != "actual":
                raise EvidenceError("A later forecast is not an actual result")
            _, actual_end = period(o["period"])
            if any(date.fromisoformat(r["published_at"]) < actual_end for r in orefs):
                raise EvidenceError("Actual result was published before its financial period ended")
            if not period_same(o["period"], target["period"]):
                output["flags"].append(f"Observation {oid} has a different period and was not compared")
                continue
            obs.append((o, orefs + [{**r, "role": "column_or_metric_context"} for r in context_refs]))
        if len(obs) > 1:
            values = {
                (str(decimal(o["value"]) * SCALES[o.get("scale", "1")]), o["unit"], o["basis"], o["definition"])
                for o, _ in obs
            }
            if len(values) > 1:
                raise EvidenceError("Conflicting actuals: reconcile or separate observations before comparison")
        if not reviewed:
            output["status"] = "needs_review"
            output["flags"].append("Codex/analyst must review the meaning, conditions and period mapping")
            return output
        if as_of < deadline:
            output["status"] = "not_due"
            return output
        if not obs:
            output["status"] = "unresolved"
            output["flags"].append("No verified, matching-period actual was linked; absence is not a missed target")
            return output
        o, orefs = obs[0]
        output["result_evidence"] = orefs
        output["observation"] = o
        if measurement_type == "point_in_time" and (
            not o.get("measurement_date") or date.fromisoformat(o["measurement_date"]) != deadline
        ):
            output["status"] = "unresolved"
            output["flags"].append(
                "The actual's measurement date is missing or differs from the target date; an announcement date is not a measurement date"
            )
        elif o["definition"] != target["definition"]:
            output["status"] = "definition_changed"
            output["flags"].append("Metric definitions differ; a like-for-like bridge is required")
        elif o["basis"] != target["basis"] or o["unit"] != target["unit"]:
            output["status"] = "basis_mismatch"
            output["flags"].append("Basis or units differ; no numerical comparison was performed")
        elif c.get("conditions") and (not ca or ca.get("met") is not True):
            output["status"] = "conditional"
            output["flags"].append(
                "A stated condition was documented as not satisfied; do not adjudicate the target as unconditional"
                if ca and ca.get("met") is False
                else "Stated conditions have not been established as satisfied"
            )
        else:
            if c.get("conditions"):
                ca = c["condition_assessment"]
                source_refs(root, ca.get("evidence", []), company, as_of)
                if not ca.get("notes"):
                    raise EvidenceError("Satisfied conditions need an explanation and evidence")
            output["calculation"] = compare(target, o)
            output["status"] = output["calculation"]["result"]
            if any(r["completeness"] != "complete" for r in orefs):
                output["flags"].append("Result source coverage is partial or unconfirmed")
        return output
    except (ValueError, OSError, KeyError, TypeError) as e:
        output["status"] = "blocked"
        output["flags"].append(str(e))
        return output


def priority(c):
    attention = {
        "blocked": 6,
        "definition_changed": 5,
        "basis_mismatch": 5,
        "below_range": 4,
        "missed": 4,
        "conditional": 3,
        "unresolved": 3,
        "needs_review": 3,
        "above_range": 2,
        "qualitative": 2,
    }.get(c["status"], 1)
    materiality = c["materiality"] if type(c["materiality"]) is int and 1 <= c["materiality"] <= 5 else 1
    return (materiality, attention, str(c["id"]))


def review(root, analysis_path, output):
    data = read_json(analysis_path)
    pack = read_json(Path(root) / "source-pack.json")
    if data.get("schema_version") != 1 or data.get("company", {}).get("id") != pack["company"]["id"]:
        raise EvidenceError("Analysis schema/company must match the source pack")
    as_of = date.fromisoformat(data["as_of"])
    observations = {o["id"]: o for o in data.get("observations", [])}
    if len(observations) != len(data.get("observations", [])):
        raise EvidenceError("Duplicate observation ids")
    commitments = data.get("commitments", [])
    allowed_sources = {d["id"] for d in pack["documents"]}
    for c in commitments:
        all_refs = c.get("evidence", []) + c.get("condition_assessment", {}).get("evidence", [])
        for u in c.get("updates", []):
            all_refs += u.get("evidence", [])
        if any(r.get("source_id") not in allowed_sources for r in all_refs):
            raise EvidenceError("Commitment evidence is outside this source pack")
    if any(
        r.get("source_id") not in allowed_sources
        for o in observations.values()
        for r in o.get("evidence", []) + o.get("context_evidence", [])
    ):
        raise EvidenceError("Observation evidence is outside this source pack")
    if len({c["id"] for c in commitments}) != len(commitments) or len(commitments) > 500:
        raise EvidenceError("Duplicate commitment ids or commitment budget exceeded")
    results = [review_commitment(root, c, observations, pack["company"]["id"], as_of) for c in commitments]
    results.sort(key=priority, reverse=True)
    counts = {status: sum(c["status"] == status for c in results) for status in sorted(STATUSES)}
    report = {
        "schema_version": 1,
        "company": data["company"],
        "as_of": data["as_of"],
        "generated_at": now(),
        "mode": data.get("mode", "research"),
        "summary": data.get("summary", ""),
        "commitments": results,
        "counts": counts,
        "top_three": [c["id"] for c in results[:3]],
        "coverage": pack["coverage"],
        "acquisition": pack["acquisition"],
        "documents": [
            {
                **d,
                "evidence_eligibility": "date_unverified"
                if not d.get("published_at")
                else "after_as_of"
                if date.fromisoformat(d["published_at"]) > as_of
                else "within_date_cutoff",
            }
            for d in pack["documents"]
        ],
        "limitations": pack["limitations"] + data.get("limitations", []),
        "analysis_sha256": __import__("hashlib").sha256(Path(analysis_path).read_bytes()).hexdigest(),
        "status": "blocked" if counts["blocked"] else "review_ready",
        "interpretation": "Statements and mappings are Codex/analyst interpretations; source matching and arithmetic are deterministic checks, not proof of semantic correctness.",
        "priority_method": "Analyst-assigned materiality (1-5), then attention category; this is a review queue, not an investment score.",
    }
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "report.json", report)
    from .render import render

    render(report, output)
    return {
        "status": report["status"],
        "commitments": len(results),
        "counts": counts,
        "report": str((output / "review.html").resolve()),
    }
