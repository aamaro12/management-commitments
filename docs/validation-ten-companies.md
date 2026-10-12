# Validation: dashboard and 10 companies

## Version 0.2.0

76 Python tests pass on Python 3.11 and 3.12, including corrupt Office files, text that is not UTF-8, hidden page text, earlier snapshots that must keep loading, and safe report rendering. The 24 synthetic verifier cases pass, the dashboard DOM checks pass on the synthetic report and company index, and the package check scans every published file.

Version 0.2.0 records the reader that saved each snapshot. The improved reader leaves out page text hidden by the `hidden` attribute or an inline style and honours declared charsets, and snapshots saved earlier are still re-read the earlier way.

## The 10-company review, version 0.1.0

Run on 12 October 2026. Historical review as of 15 September 2025, using official source captures retrieved now. This is a curated workflow test, not a contemporaneous backtest or an extraction-accuracy benchmark.

### Scope

The single-company dashboard uses compact rows, consistent navigation, global search, clear filters and expandable evidence. The company overview adds search, coverage filtering and sorting. Reports link to each other and back to the overview. Numerical work remains in Python.

10 source packs contain 59 documents across 3 quarters per company. 9 transcripts were acquired from company-hosted links: 3 each for Adobe, AMD and Walmart. 7 companies have release-only coverage. 2 AMD transcripts use a visible earnings-package date proxy after company, quarter and year checks; their own call date was absent from the extracted header.

| Company | Tracked | Numerical comparisons | Other assessments |
|---|---:|---:|---|
| NVIDIA | 3 | 3 | H20 charge retained as context |
| AMD | 3 | 2 | MI350 timing remains attributed commentary |
| Adobe | 4 | 4 | Transcript currency convention retained |
| Salesforce | 3 | 3 | Reported revenue and adjusted EPS separated |
| Amazon | 4 | 0 | Explicit contingencies remain unverified |
| Meta | 3 | 2 | Annual capex target not yet due; revisions preserved |
| Uber | 4 | 4 | Bookings and adjusted EBITDA kept distinct |
| PayPal | 3 | 2 | Annual guidance change remains separate |
| Walmart | 3 | 2 | No Q2 profit range was manufactured |
| Delta | 2 | 2 | Q1 comparison clearly uses superseded January guidance |

All 10 reports have zero blocked checks. The overview also includes the original Microsoft report: 11 companies, 40 statements and 29 numerical comparisons in total.

### Issues found and corrected

- The original date detector relied on Microsoft wording and early page blocks. It missed release dates after long navigation. Metadata and dated headings are now read.
- PDF financial-table dates were misread as publication dates. A dateline or call-header date is required; otherwise linked package dates are explicitly labelled as proxies.
- Duplicate release PDFs displaced transcripts within the request budget. Transcripts now have priority; financial tables and regulatory filings have distinct download classifications. Irrelevant policy PDFs are filtered.
- Adobe's old Q3 URL returned a generic newsroom page, and another PDF was prepared remarks. The curated profile uses the verified release PDF. Cached generated display titles can no longer satisfy company/quarter checks.
- Adobe's encrypted PDF exposed a missing crypto dependency and an uncaught dependency exception. The PDF extra includes crypto support; extraction failures become visible acquisition errors and collection continues.
- Printed plus/minus guidance could not be represented without precomputed bounds. The new tolerance operator derives bounds in Python and validates units, scale, signs and printed inputs.
- PayPal's example selector consumed a sentence's trailing full stop as part of EPS. Decimal captures now use strict patterns.
- Delta's example initially selected an annual forecast as a quarterly actual. It now reads the labelled quarterly non-GAAP results section. The March revision is preserved and the January benchmark is explicitly qualified.
- Conditional actuals were labelled as definition mismatches in the simplified UI. They now say that the condition is unverified.

### Checks and remaining limits

With version 0.1.0, 63 Python tests and 24 synthetic verifier cases passed. DOM interaction checks passed on all 10 new reports, the original Microsoft report, the synthetic report and both company indexes. They cover company navigation, search, coverage, filters, sorting, expansion, decisions and downloads. Package checks passed; the wheel installed and generates a demo and company index in a separate environment.

The reports were not inspected in a browser. DOM checks establish interaction behaviour, not rendered layout quality.

Collection remains bounded. AMD exhausted its request budget; an outside-allowlist partner PDF was rejected visibly. Release-only coverage does not mean that no transcript exists elsewhere. PDF text ordering, attached footnote digits, rounding and source errors still require semantic review. Delta's acquired March news update confirms a revision but does not contain its numerical target table, so there is no numerical verdict against the latest Q1 guidance.

These are material selections, not an exhaustive commitment inventory. Evidence anchors and arithmetic do not prove correct interpretation. No independent human approval, measured analyst time saving, investment signal or publication is claimed. Captures and generated reports remain in the ignored `runs/` folder.
