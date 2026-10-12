# Validation of version 0.1.0

12 October 2026. No plugin was installed globally.

## Verified

- 47 Python tests pass. They cover source integrity, table cells and headers, chronology, financial periods, definitions, units/scales, conditional targets, point-in-time measurements, strict bounds, missing results, safe embedding and analyst review imports.
- 24 synthetic verifier cases pass. This is a deterministic check suite, not an LLM accuracy benchmark. The second synthetic issuer's reserved cases are not an independent model holdout.
- The offline demo produces 10 assessments, an interactive HTML report, structured JSON and a Markdown brief.
- The live Microsoft collection made 18 public requests and captured 13 documents, including 3 official earnings releases and all 3 company-published FY25 Q1-Q3 transcript downloads. Fiscal-quarter headers and transcript dates match the intended periods.
- 5 acquisitions failed visibly: 3 outlook assets lacked readable slide text, and 2 financial workbooks were unsupported. The request budget also left further discovered links uncollected. These gaps appear in the source pack and dashboard.
- The curated Microsoft interpretation produces 8 commitments with zero blocked checks. The AI run-rate deadline remains unresolved because the precise measurement date was not supplied. The next-quarter Azure target is not yet due at the historical review date; the capacity expectation change remains qualitative.
- DOM interaction checks pass on the synthetic and Microsoft reports: views, status/topic/period filters, sorting, empty results, evidence expansion, review notes, browser-local state, downloadable exports, print action, coverage and escaping.
- The skill validator and local package/manifest checks pass. The Python wheel builds and runs the offline demo in a separate installation environment.

## Independent skill forward test

A separate agent received the skill and a fresh synthetic Cedar Materials source pack, without the curated example's expected answers. It generated 5 reviewed assessments and a report with zero blocked checks:

| Task | Observed assessment |
|---|---|
| Constant-currency revenue guidance | Within range using the constant-currency table column |
| GAAP gross-margin target | Basis mismatch against an adjusted-margin disclosure |
| All-customer retention target | Definition changed against an enterprise-only metric |
| Partner count conditional on permit approval | Conditional; the permit was explicitly not approved |
| Preferred-platform ambition | Qualitative, with reaffirmation rather than proof of attainment |

The first attempt exposed an awkward header-citation restriction. The implementation now supports separate `context_evidence` for headers/footnotes. The test also exposed dropped condition evidence, a misleading unresolved-condition label, future-source inventory ambiguity and dead links for local uploads. These were corrected with regression coverage and source/DOM checks.

This is one small forward test, not evidence of broad extraction reliability or analyst acceptance. No time-savings claim has been measured.

## Still outstanding

- Inspection of the visual layout in a browser. Static and DOM checks do not establish visual quality.
- A larger manually reviewed public-company dataset and evaluation of extraction omissions, interpretation errors and analyst usefulness.
- Direct integration with Citations & Calculations. This prototype independently applies the same snapshot/anchor/calculation approach.
- A short recorded demonstration.

Live documents and generated reports are in ignored `runs/`. Source snapshots retrieved now do not establish historical document vintage or a trading backtest.
