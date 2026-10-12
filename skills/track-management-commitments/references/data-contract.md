# Data contract v1

The collector writes `source-pack.json` plus `sources/<id>.raw` and `<id>.json`. Raw-byte hashes anchor source identity. Blocks have stable ids within a snapshot, text and extracted context. The review command re-extracts the bytes to check each quote and table cell. These checks cannot prove that the chosen metric, date or interpretation is correct.

## Collection profile

```json
{
  "company": {"id": "TICKER", "name": "Verified Company Name"},
  "allowed_hosts": ["investors.company.com", "company-approved-cdn.example"],
  "seeds": [{"url": "https://investors.company.com/quarter-results", "period": {"label": "FY2025 Q1", "start": "2025-01-01", "end": "2025-03-31"}, "title_pattern": "Q1"}]
}
```

`title_pattern` is optional for generic sites, but verify fiscal identity in the source. Publication dates discovered in dated release text can be inherited by linked earnings-package documents; this is labelled as a proxy. HTML extraction does not execute JavaScript. DOCX reads body text; PPTX reads slide text; optional PDFs use the text layer only. There is no OCR, audio transcription or authenticated provider access.

## Analysis

```json
{
  "schema_version": 1,
  "company": {"id": "TICKER", "name": "Verified Company Name"},
  "as_of": "2025-07-31",
  "mode": "research",
  "summary": "A concise explanation without uncoded calculations.",
  "commitments": [{
    "id": "growth-q2",
    "title": "Q2 growth against the earlier guidance",
    "topic": "Growth",
    "metric_key": "company_revenue_growth_yoy",
    "kind": "numeric",
    "evidence": [{"source_id": "s0123456789abcdef", "block_id": "b0035", "quote": "Exact source passage"}],
    "target": {
      "period": {"label": "FY2025 Q2", "start": "2025-04-01", "end": "2025-06-30"},
      "definition": "Company revenue year-over-year growth",
      "basis": "constant_currency",
      "unit": "percent", "scale": "1", "operator": "range", "low": "10", "high": "12"
    },
    "conditions": [],
    "materiality": 4,
    "importance_rationale": "Why this item deserves attention.",
    "question": "What should the analyst ask next?",
    "semantic_review": {"state": "reviewed", "reviewer": "Codex", "notes": "Explain the scope, period, basis and condition checks actually performed."},
    "observation_ids": ["growth-q2-actual"],
    "updates": []
  }],
  "observations": [{
    "id": "growth-q2-actual", "metric_key": "company_revenue_growth_yoy", "kind": "actual",
    "period": {"label": "FY2025 Q2", "start": "2025-04-01", "end": "2025-06-30"},
    "definition": "Company revenue year-over-year growth", "basis": "constant_currency", "unit": "percent", "scale": "1", "value": "11",
    "evidence": [{"source_id": "sfedcba9876543210", "block_id": "b0055", "quote": "Exact result passage"}]
  }],
  "limitations": []
}
```

This is a schema illustration, not valid source evidence. Use actual snapshot ids and exact quotes. All numbers should be decimal strings. Supported units: USD/EUR/GBP, percent (31 means 31%), percentage_points, count, multiple. Supported scales: 1, thousand, million, billion. No automatic currency conversion. Operators: range, tolerance, at_least, at_most, greater_than, less_than. The strict operators preserve wording such as "surpass"; range comparisons use inclusive endpoints.

For a printed centre plus/minus a tolerance, use `operator: tolerance`, `center: "43"`, and `tolerance: {"value": "2", "type": "relative_percent"}`. Python derives both bounds; do not supply `low` or `high`. Both the centre and width must appear in the source quote. Other types are `basis_points` (only for a percent target) and `absolute`, which accepts a scale such as `million` for a target expressed in billions. Relative percentages and basis points use scale 1. The report exposes the derivation, bounds and actual conversion.

Separate quarter results from annual or next-quarter forecasts that appear on the same page. Read the labelled actual-results section and its current-period columns; a plausible number somewhere in the document is insufficient. Preserve a mid-quarter revision as an update, and label comparisons to original guidance when a later target replaced it.

When an observation cites an HTML table row, add `cell_index` (zero-based, including label/empty cells) and `column_review` describing the exact period, unit and basis of that column. Inspect `table_opening_rows`, `table_rows_before` and `cells`. A number appearing somewhere in a row is insufficient.

Use 1 actual-value table row in `evidence`. Optional header/footnote citations belong in `context_evidence`, with the same source/block/quote format. They are checked and displayed as context, without being treated as candidate value rows.

Flow metrics default to `measurement_type: period`. For a balance, count or run rate at a date, add `measurement_type: point_in_time` and `measurement_date: YYYY-MM-DD` on the target and the actual. The target date defaults to its period end if omitted. The actual needs a verified matching measurement date; missing/later measurement dates remain unresolved. Source publication date is not a substitute.

For qualitative commitments use `kind: qualitative` and `target: null`. Add updates with `type` (revised_target, definition_changed, conditions_changed, reaffirmed, wording_changed), `interpretation` and `evidence`. Updates never overwrite the original statement or automatically settle a target.

If a numeric commitment has conditions, comparisons remain conditional unless `condition_assessment` has `met: true`, evidence and notes. Use `met: false` with evidence/notes when a condition is explicitly unmet, or null/omission when unknown. The report preserves this distinction and the condition evidence. Record an actual satisfied condition, not a confidence estimate.

## States and decisions

The verifier produces below/within/above_range; met/missed for explicit bounds; not_due, unresolved, definition_changed, basis_mismatch, conditional, qualitative, needs_review or blocked. Definitions and periods are exact matching contracts. Differences require an explicit analyst-reviewed bridge in a later version, not silent substitution.

`semantic_review` records source interpretation. `analyst_decision` is a separate accept/reject/correction state. A browser export carries the company and analysis hash; the CLI rejects cross-analysis imports and records reviewer/note/timestamp in an append-only log. Review acceptance does not override a blocked numerical check.
