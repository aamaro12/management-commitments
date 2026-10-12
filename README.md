# Management Commitments

**What did management say? What happened next? What deserves another look?**

A small Codex project that compares company guidance and commitments with later disclosures. It collects official documents, preserves source evidence and calculates like-for-like comparisons in Python. An interactive review page makes the important changes and unresolved questions easy to inspect.

The workflow is designed for an analyst reviewing a company across quarters. A missing actual stays unresolved. A changed definition stays incomparable. A broad ambition stays qualitative. Each assessment is open to analyst review.

## Try the offline demo

Python 3.11 or later. No model API key or external package is needed for HTML, text and Office documents.

```sh
python scripts/commitments.py demo --output runs/demo
```

Open `runs/demo/report/review.html`. The synthetic company beat its growth range, missed its margin range and changed its retention definition. Inspect the quoted evidence, calculation inputs and next questions. Switch between the review queue, all commitments and source coverage; filter by assessment, topic or period.

Accept, reject or request a correction. These decisions remain in browser-local storage until you export them. To retain them in an append-only local audit log:

```sh
python scripts/commitments.py apply-decisions --report runs/demo/report --file /path/to/review-decisions.json
```

Reviewer acceptance records judgement; it never overrides the calculated assessment.

## Run on Microsoft's published documents

The built-in profile discovers Microsoft's official earnings pages and linked transcript assets, including download URLs embedded behind Office viewer links. Dates and fiscal-quarter headers are checked. Collection is bounded and missing sources remain visible.

```sh
python scripts/commitments.py collect --company MSFT --fiscal-year 2025 --start-quarter 1 --quarters 3 --budget 18 --output runs/msft
python scripts/commitments.py candidates --workspace runs/msft
```

Use Codex with the [track-management-commitments skill](skills/track-management-commitments/SKILL.md) to read the sources, select material commitments and write `runs/msft/analysis.json`. The skill explains how to preserve definitions, conditions and measurement bases. Codex supplies the interpretation; the package does not call an LLM or claim autonomous extraction.

```sh
python scripts/commitments.py review --workspace runs/msft --analysis runs/msft/analysis.json --output runs/msft/report
```

For a reproducible reference demonstration, replay the curated FY25 Q1-Q3 interpretation:

```sh
python examples/build_msft_demo.py --workspace runs/msft
```

This example selects references and numbers from the acquired bytes. Its scope, period mappings and qualitative judgements are documented in the generated analysis. It is a curated historical example, not a general extractor or investment backtest. Sources retrieved today can include later restatements.

The reference case examines Azure growth, segment revenue, management's AI run-rate milestone and a changed capacity expectation. It distinguishes reported from constant-currency growth and uses exact financial table cells to avoid settling a small miss from rounded commentary. Public company documents are downloaded into ignored `runs/`; no transcript text is bundled in the source repository.

## How it works

```text
Official IR pages / selected uploads
             │
             ▼
Scripted acquisition → raw snapshots + blocks + table context
             │
             ▼
Codex reads and interprets → commitments + actuals + changes
             │
             ▼
Python checks evidence, dates, definitions, basis and arithmetic
             │
             ▼
Review queue → source inspection → analyst decision + audit log
```

- **Original statements stay intact.** Later updates do not erase the earlier wording.
- **Numbers remain reproducible.** Decimal arithmetic normalises scale and records every formula and input. Gaps outside the range are distinct from gaps to the midpoint.
- **Meaning remains a review task.** Quote matching proves that an excerpt appears in a captured document. It does not prove that an interpretation is correct.
- **Coverage is explicit.** Acquisition errors, budgets, missing transcripts, date proxies and unsupported source layers are visible.
- **Review priority is explainable.** Analyst-assigned materiality comes first, followed by attention category. It is not a stock-return score.

Source formats: HTML, UTF-8 text, DOCX body and PPTX slide text. Optional text-layer PDF support: `pip install '.[pdf]'`. No OCR, audio transcription, JavaScript execution, Excel formula engine or paid data feed is included. Custom company profiles and explicitly selected uploads are supported; see the [data contract](skills/track-management-commitments/references/data-contract.md).

This applies the evidence and calculation approach of [Citations & Calculations](https://github.com/aamaro12/citations-and-calculations) to a specific financial workflow. It is standalone and does not yet integrate that package or require it as a dependency.

## Review several companies

The dashboard uses a compact list with status labels, earlier targets, comparable actuals and gaps. Expand a row for source evidence, changes and review controls. Calculation details and acquisition logs stay behind labelled controls. Search covers all tracked statements.

Connect saved reports with a searchable company overview and navigation between companies:

```sh
python scripts/commitments.py portfolio --reports runs/company-a/report runs/company-b/report --output runs/company-reviews
```

Open `runs/company-reviews/index.html`. Filter by transcript coverage or search by company, ticker and finding. Downloads contain Python-generated calculations; the dashboard does not recalculate financial results in JavaScript.

The 10-company historical validation can be reproduced from official source downloads:

```sh
pip install '.[pdf]'
python examples/collect_validation_companies.py --output runs/ten-companies --budget 12 --depth 1
python examples/collect_validation_supplements.py --workspace runs/ten-companies
python examples/build_validation_reports.py --workspace runs/ten-companies
```

The curated example covers NVIDIA, AMD, Adobe, Salesforce, Amazon, Meta, Uber, PayPal, Walmart and Delta. It reads values from captured bytes using reviewed company-specific selectors. It is not a general semantic extractor. The completed run produced 32 tracked statements, 24 numerical comparisons, 4 conditional assessments, 3 qualitative reviews and 1 open annual target, with no blocked verifier checks. See [the validation report](docs/validation-ten-companies.md) for coverage and corrected errors.

The report builder also creates `runs/ten-companies/index.html` when all 10 reviews complete successfully.

## Evaluation and development

```sh
PYTHONPATH=src python -m unittest discover -s tests
python scripts/commitments.py evaluate --output runs/evaluation
python scripts/check_package.py
```

The 24 synthetic reference cases test deterministic verifier behaviour: definition/basis changes, stale periods, absent results, strict bounds, scale conversion, negative values, future publications and unsupported numbers. The separate second synthetic issuer exercises a reserved subset of edge cases; this is **not** an independent held-out model benchmark. These cases do not establish Codex extraction precision, analyst acceptance, time savings or a trading edge.

Dashboard DOM interaction tests use a pinned development-only package and need Node.js 22.13 or later:

```sh
pnpm install --ignore-scripts
pnpm test:ui
```

They exercise views, filters, evidence expansion, review exports and safe rendering without opening a browser. Visual layout still needs browser review. The Python runtime has no required third-party dependencies.

For the company overview, generate a demo index with `commitments portfolio --reports runs/demo/report --output runs/demo/index`, then run `pnpm test:portfolio`.

## Packaging

This repository contains a skills-only plugin with a portable `plugin.json` and a `.codex-plugin/plugin.json` compatibility manifest. The workflow uses Codex's existing shell and file capabilities. It does not install a server or silently register itself in global configuration. See [official OpenAI skill guidance](https://developers.openai.com/plugins/build/skills).

For a normal Python installation: `pip install .`. The `commitments` console command has the same options as `scripts/commitments.py`.

This is an independent prototype by Alessandro Amaro, not an OpenAI product. It uses public source documents and synthetic examples. The MIT licence covers the project's code and synthetic fixtures, not the company documents downloaded at runtime.
