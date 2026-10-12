#!/usr/bin/env python3
"""Replay Codex-reviewed selections from ten real official source packs.

This is a curated validation set, not automatic semantic extraction or a model
benchmark. Values and exact citations are read from acquired bytes. Company-specific
selectors document the reviewed fiscal, metric and table-column mappings. Source
text, financial values and generated reports remain in ignored runs/.
"""

from pathlib import Path
import argparse
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from management_commitments.review import printed_numbers, review
from management_commitments.render import portfolio
from management_commitments.sources import EvidenceError, load_source, read_json, write_json


class Case:
    def __init__(self, root):
        self.root = Path(root)
        self.pack = read_json(self.root / "source-pack.json")
        self.docs = [load_source(self.root, d["id"]) for d in self.pack["documents"]]
        self.periods = [s["period"] for s in self.pack["profile"]["seeds"]]
        self.commitments = []
        self.observations = []

    def find(self, q, pattern, kind="earnings_release", format=None, occurrence=0, cell=None):
        docs = [
            s
            for s in self.docs
            if s["period"] == self.periods[q] and s["kind"] == kind and (not format or s["format"] == format)
        ]
        # Prefer original release HTML over its duplicate PDF; Adobe uses PDF financial tables.
        docs.sort(key=lambda s: s["format"] != "html")
        for s in docs:
            matches = []
            for b in s["blocks"]:
                text = next((v for v in b["context"].get("cells", []) if v), "") if cell is not None else b["text"]
                m = re.search(pattern, text, re.I)
                if m and (cell is None or b["context"].get("cells")):
                    matches.append((b, m))
            if len(matches) > occurrence:
                b, m = matches[occurrence]
                quote = b["text"] if cell is not None else m[0]
                return {"source_id": s["id"], "block_id": b["id"], "quote": quote}, b, m
        raise EvidenceError(f"{self.pack['company']['id']} q{q}: reviewed selector missing: {pattern}")

    def actual_row(self, q, label, number_index=0, occurrence=0):
        ref, b, _ = self.find(q, "^" + re.escape(label) + "$", format="html", cell=True, occurrence=occurrence)
        numeric = [(i, printed_numbers(v)[0]) for i, v in enumerate(b["context"]["cells"]) if printed_numbers(v)]
        index, value = numeric[number_index]
        return ref, str(value), index

    def find_after(self, q, heading, pattern):
        for s in self.docs:
            if s["period"] != self.periods[q] or s["kind"] != "earnings_release" or s["format"] != "html":
                continue
            start = next((i for i, b in enumerate(s["blocks"]) if re.search(heading, b["text"], re.I)), None)
            if start is None:
                continue
            for b in s["blocks"][start + 1 : start + 9]:
                m = re.search(pattern, b["text"], re.I)
                if m:
                    return {"source_id": s["id"], "block_id": b["id"], "quote": m[0]}, b, m
        raise EvidenceError("Result missing from the reviewed actual-results section")

    def add(
        self,
        cid,
        title,
        q,
        ref,
        target,
        actual=None,
        rationale="",
        question="",
        materiality=3,
        conditions=None,
        notes="",
        updates=None,
    ):
        metric = cid.split("-q")[0]
        c = {
            "id": cid,
            "title": title,
            "topic": "Financial guidance",
            "metric_key": metric,
            "kind": "numeric" if target else "qualitative",
            "target": target,
            "evidence": [ref],
            "conditions": conditions or [],
            "materiality": materiality,
            "importance_rationale": rationale,
            "question": question,
            "semantic_review": {
                "state": "reviewed",
                "reviewer": "Codex curated live validation",
                "notes": "Reviewed original guidance, result-period headers, metric definition, basis and surrounding disclosure. "
                + notes,
            },
            "observation_ids": [],
            "updates": updates or [],
        }
        if actual:
            oref, value, scale, basis, cell_index = actual
            oid = cid + "-actual"
            o = {
                "id": oid,
                "metric_key": metric,
                "kind": "actual",
                "period": target["period"],
                "definition": target["definition"],
                "unit": target["unit"],
                "scale": scale,
                "basis": basis,
                "value": value,
                "evidence": [oref],
            }
            if cell_index is not None:
                o.update(
                    {
                        "cell_index": cell_index,
                        "column_review": f"Selected the {target['period']['label']} three-month actual column; inspected opening rows and adjacent rows. {scale} {target['unit']}, {basis} basis. Prior-year and year-to-date columns were excluded.",
                    }
                )
            self.observations.append(o)
            c["observation_ids"] = [oid]
        self.commitments.append(c)
        return c

    def target(self, q, definition, low=None, high=None, unit="USD", scale="billion", basis="reported", **kwargs):
        t = {
            "period": self.periods[q],
            "definition": definition,
            "basis": basis,
            "unit": unit,
            "scale": scale,
            "operator": "range" if "operator" not in kwargs else kwargs.pop("operator"),
        }
        if low is not None:
            t["low"] = str(low)
        if high is not None:
            t["high"] = str(high)
        return {**t, **kwargs}

    def row_actual(self, q, label, number_index=0, occurrence=0, scale="million", basis="reported"):
        ref, value, index = self.actual_row(q, label, number_index, occurrence)
        return ref, value, scale, basis, index

    def finish(self, summary, limitations=None):
        data = {
            "schema_version": 1,
            "company": self.pack["company"],
            "as_of": "2025-09-15",
            "mode": "historical_review",
            "summary": summary,
            "commitments": self.commitments,
            "observations": self.observations,
            "limitations": [
                "Curated material selections across three historical quarters; not an exhaustive extraction or LLM accuracy benchmark.",
                "Sources retrieved in October 2026 may contain later corrections; this is not a contemporaneous backtest.",
                "A numerical gap describes reported results versus an earlier forecast, not management honesty or an investment signal.",
                *(limitations or []),
            ],
        }
        write_json(self.root / "analysis.json", data)
        result = review(self.root, self.root / "analysis.json", self.root / "report")
        print(
            self.pack["company"]["id"], result["status"], {k: v for k, v in result["counts"].items() if v}, flush=True
        )
        return result


def nvidia(c):
    for q in [0, 1]:
        ref, _, m = c.find(
            q, r"Revenue is expected to be \$(\d+(?:\.\d+)?) billion, plus or minus (\d+)%\.[^\n]*?(?=This outlook|$)"
        )
        t = c.target(
            q + 1,
            "Consolidated quarterly revenue",
            operator="tolerance",
            center=m[1],
            tolerance={"value": m[2], "type": "relative_percent"},
        )
        c.add(
            f"revenue-q{q + 1}",
            f"FY26 Q{q + 1} revenue against the original outlook",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Revenue"),
            "Revenue is compared with the full printed tolerance, using the precise financial-table actual rather than the rounded headline.",
            "Which demand and shipment changes explain the outcome against the original forecast?",
            4,
        )
    ref, _, m = c.find(
        0,
        r"GAAP and non-GAAP gross margins are expected to be (\d+(?:\.\d+)?)% and (\d+(?:\.\d+)?)%, respectively, plus or minus (\d+) basis points\.",
    )
    explanation, _, _ = c.find(1, r"On April 9, 2025, NVIDIA was informed.*?first quarter\.")
    t = c.target(
        1,
        "Consolidated non-GAAP gross margin including H20 charge",
        unit="percent",
        scale="1",
        basis="non_gaap",
        operator="tolerance",
        center=m[2],
        tolerance={"value": m[3], "type": "basis_points"},
    )
    c.add(
        "gross-margin-q1",
        "H20 charge explains a margin shortfall",
        0,
        ref,
        t,
        c.row_actual(1, "Gross margin", occurrence=1, scale="1", basis="non_gaap"),
        "The result includes the export-related H20 charge. The separately disclosed charge-excluded margin must not replace this actual.",
        "How does the export shock change the durability of the original margin outlook?",
        5,
        updates=[
            {
                "type": "wording_changed",
                "interpretation": "The later release attributes a material charge and lost shipments to new export restrictions.",
                "evidence": [explanation],
            }
        ],
    )
    return c.finish(
        "Revenue exceeded the earlier tolerance bands. The Q1 margin result needs the H20 export-charge context; a charge-excluded figure would answer a different question."
    )


def amd(c):
    for q in [0, 1]:
        ref, _, m = c.find(
            q,
            r"For the (?:first|second) quarter of 2025, AMD expects revenue to be approximately \$(\d+(?:\.\d+)?) billion, plus or minus \$(\d+) million\.",
        )
        t = c.target(
            q + 1,
            "Consolidated quarterly net revenue",
            operator="tolerance",
            center=m[1],
            tolerance={"value": m[2], "type": "absolute", "scale": "million"},
        )
        c.add(
            f"revenue-q{q + 1}",
            f"Q{q + 1} revenue against the printed tolerance",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Net revenue"),
            "The dollar tolerance is converted from millions to billions in Python; the current three-month financial-table actual is used.",
            "Which segments explain the outcome, and how much reflects demand rather than shipment timing?",
            4,
        )
    ref, _, _ = c.find(1, r"We b egan sampling our next Gen MI350 series.*?mid-year\.", kind="transcript")
    update, _, _ = c.find(2, r"We b egan volume production of the MI350 series.*?June,", kind="transcript")
    c.add(
        "mi350-launch",
        "MI350 production timing is a management-reported milestone",
        1,
        ref,
        None,
        rationale="The later call reports production starting in June. Neither passage supplies an audited production-volume measure, so a numerical delivery verdict would overstate the evidence.",
        question="What production volume and customer deployment evidence establishes the scale of the ramp?",
        materiality=3,
        notes="Read the later call's surrounding AI deployment remarks. Two transcripts use an earnings-package date proxy; their company/quarter headers were checked.",
        updates=[
            {
                "type": "wording_changed",
                "interpretation": "The later call reports volume production beginning in June; retain this as attributed commentary.",
                "evidence": [update],
            }
        ],
    )
    return c.finish(
        "The revenue comparisons use precise reported tables and printed dollar tolerances. The MI350 timing claim remains attributed management commentary."
    )


def salesforce(c):
    for q in [0, 1]:
        ref, b, _ = c.find(q, r"^(?:Total revenue|Revenue)$", format="html", cell=True)
        nums = printed_numbers(b["context"]["cells"][1])
        t = c.target(q + 1, "Consolidated quarterly revenue", *nums[:2])
        c.add(
            f"revenue-q{q + 1}",
            f"FY26 Q{q + 1} revenue against dollar guidance",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Total revenues"),
            "Dollar guidance and the exact current-quarter revenue table are compared on reported basis. Constant-currency growth is a separate metric.",
            "How much of the improvement reflects currency and how much reflects underlying subscription demand?",
            4,
            notes="Guidance table's first column is next quarter; its annual column is not used.",
        )
    ref, b, _ = c.find(1, r"^Diluted net income per share$", format="html", cell=True)
    low, high = printed_numbers(b["context"]["cells"][-1])[:2]
    t = c.target(2, "Non-GAAP diluted earnings per share", low, high, scale="1", basis="non_gaap")
    c.add(
        "eps-q2",
        "FY26 Q2 adjusted EPS against adjusted guidance",
        1,
        ref,
        t,
        c.row_actual(2, "Non-GAAP diluted net income per share", occurrence=1, scale="1", basis="non_gaap"),
        "The next-quarter non-GAAP guidance cell is matched with the reconciled current-quarter non-GAAP actual, excluding year-to-date EPS.",
        "Which operating and share-count changes explain the EPS outcome?",
        3,
    )
    return c.finish(
        "Revenue and adjusted EPS are matched to the correct fiscal-quarter columns. The source tables separate reported dollars, constant-currency growth and non-GAAP earnings."
    )


def amazon(c):
    for q in [0, 1]:
        condition, _, _ = c.find(
            q,
            r"This guidance assumes, among other things, that no additional business acquisitions, restructurings, or legal settlements are concluded\.",
        )
        for metric, label, pattern in [
            (
                "sales",
                "Total net sales",
                r"Net sales are expected to be between \$(\d+(?:\.\d+)?) billion and \$(\d+(?:\.\d+)?) billion.*?foreign exchange rates\.",
            ),
            (
                "income",
                "Operating income",
                r"Operating income is expected to be between \$(\d+(?:\.\d+)?) billion and \$(\d+(?:\.\d+)?) billion.*?\.",
            ),
        ]:
            ref, _, m = c.find(q, pattern)
            t = c.target(q + 1, "Consolidated quarterly " + label.lower(), m[1], m[2])
            item = c.add(
                f"{metric}-q{q + 1}",
                f"Q{q + 1} {label.lower()}: stated contingencies remain open",
                q,
                ref,
                t,
                c.row_actual(q + 1, label, number_index=1),
                "The actual is disclosed, but the source's no-acquisition/restructuring/settlement condition has not been established. The review therefore preserves a conditional assessment.",
                "Were the stated contingencies satisfied, and did any exceptional items change the comparison?",
                3,
                conditions=[condition["quote"]],
                notes="The prior-year-first table uses its second numerical value for the current quarter; annual/YTD and segment rows are excluded.",
            )
            item["evidence"].append(condition)
    return c.finish(
        "Revenue and operating-income actuals are available. The original guidance's explicit contingencies remain unverified, so the dashboard keeps these assessments conditional.",
        [
            "No additional filings were collected to establish the no-acquisition, restructuring and legal-settlement conditions."
        ],
    )


def meta(c):
    for q in [0, 1]:
        ref, _, m = c.find(
            q,
            r"We expect (?:first|second) quarter 2025 total revenue to be in the range of \$(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?) billion\.",
        )
        t = c.target(q + 1, "Consolidated quarterly revenue", m[1], m[2])
        c.add(
            f"revenue-q{q + 1}",
            f"Q{q + 1} revenue against the earlier range",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Revenue"),
            "The dollar range is compared with the precise current-quarter actual. The adjacent foreign-exchange assumptions help explain a gap but do not change the reported-dollar metric.",
            "How much of the outcome reflects ad demand, pricing and currency?",
            4,
        )
    ref, _, _ = c.find(0, r"We anticipate our full year 2025 capital expenditures.*?core business\.")
    update, _, _ = c.find(1, r"We anticipate our full year 2025 capital expenditures.*?core business\.")
    low, high = printed_numbers(ref["quote"])[1:3]
    t = c.target(2, "Management-defined full-year capital expenditures", low, high, basis="management_defined")
    t["period"] = {"label": "FY2025", "start": "2025-01-01", "end": "2025-12-31"}
    c.add(
        "capex-revision",
        "Capital-spending expectations moved higher; full year remains open",
        0,
        ref,
        t,
        rationale="The later disclosure raises the spending range and explicitly includes finance-lease principal payments. The original passage does not establish that scope, so the change is preserved without a calculated like-for-like delta.",
        question="Is the revised capital-spending scope directly comparable, and what capacity will the extra investment deliver?",
        materiality=5,
        updates=[
            {
                "type": "revised_target",
                "interpretation": "The later spending range is higher; scope includes finance-lease principal payments. No full-year actual is in this pack.",
                "evidence": [update],
            }
        ],
    )
    return c.finish(
        "Revenue exceeded the original ranges. Higher capital-spending expectations warrant a separate review of investment scope and returns; they do not establish a full-year outcome."
    )


def uber(c):
    for q in [0, 1]:
        ref, _, m = c.find(
            q,
            r"(?:This translates to reported )?Gross Bookings of \$(\d+(?:\.\d+)?) billion to \$(\d+(?:\.\d+)?) billion[^.]*\.",
        )
        t = c.target(q + 1, "Consolidated gross bookings in reported USD", m[1], m[2], basis="management_defined")
        c.add(
            f"bookings-q{q + 1}",
            f"Q{q + 1} gross bookings on reported-dollar basis",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Gross Bookings", number_index=1, basis="management_defined"),
            "Reported gross-bookings dollars are used, rather than revenue or constant-currency growth. The company defines this operational measure separately from GAAP revenue.",
            "What do trips, pricing and currency explain about the bookings result?",
            4,
        )
        ref, _, m = c.find(q, r"Adjusted EBITDA of \$(\d+(?:\.\d+)?) billion to \$(\d+(?:\.\d+)?) billion,.*?\.")
        t = c.target(q + 1, "Consolidated adjusted EBITDA", m[1], m[2], basis="non_gaap")
        c.add(
            f"ebitda-q{q + 1}",
            f"Q{q + 1} adjusted EBITDA against the stated range",
            q,
            ref,
            t,
            c.row_actual(q + 1, "Adjusted EBITDA", number_index=1, basis="non_gaap"),
            "The consolidated adjusted-EBITDA reconciliation is used, rather than Mobility, Delivery or GAAP operating income.",
            "Does the earnings result reflect sustained cost leverage or items excluded by the adjusted definition?",
            3,
        )
    return c.finish(
        "Gross bookings and adjusted EBITDA landed within their ranges. Reported-dollar bookings, currency-neutral growth and GAAP revenue remain separate metrics."
    )


def paypal(c):
    for q in [0, 1]:
        ref, _, m = c.find(
            q,
            r"(?:1Q|2Q)'25 GAAP EPS \$\d+(?:\.\d+)? - \$\d+(?:\.\d+)?.*?Non-GAAP EPS1 \$(\d+(?:\.\d+)?) - \$(\d+(?:\.\d+)?)",
            format="pdf",
        )
        aref, _, am = c.find(q + 1, r"non-GAAP EPS increased \d+% to \$(\d+(?:\.\d+)?)", format="pdf")
        t = c.target(q + 1, "Non-GAAP diluted earnings per share", m[1], m[2], scale="1", basis="non_gaap")
        c.add(
            f"eps-q{q + 1}",
            f"Q{q + 1} non-GAAP EPS against non-GAAP guidance",
            q,
            ref,
            t,
            (aref, am[1], "1", "non_gaap", None),
            "The release's non-GAAP EPS is matched to the same-basis next-quarter target. GAAP headline figures can have attached footnote digits in PDF text, so they are not used here.",
            "How much of the EPS result came from transaction margin, expenses and buybacks?",
            4,
            notes="Read the PDF guidance headers and non-GAAP definitions. Quarterly guidance is selected before the annual section.",
        )
    original, _, _ = c.find(1, r"2025 Guidance: PayPal is maintaining full year guidance.*?year\.", format="pdf")
    update, _, _ = c.find(
        2, r"2025 Guidance: Following a strong start to the year, PayPal is raising.*?guidance\.", format="pdf"
    )
    c.add(
        "annual-guidance",
        "Full-year guidance was held, then raised",
        1,
        original,
        None,
        rationale="The original annual stance cited macro uncertainty; the later release raises transaction-margin-dollar and EPS guidance. A first-half result cannot settle a full-year target.",
        question="What evidence supports the higher annual expectations despite the earlier macro caution?",
        materiality=3,
        updates=[
            {
                "type": "revised_target",
                "interpretation": "Management later raises annual TM-dollar and EPS guidance; no full-year actual is acquired.",
                "evidence": [update],
            }
        ],
    )
    return c.finish(
        "Non-GAAP quarterly EPS exceeded the earlier non-GAAP ranges. The shift in annual guidance is tracked separately from completed quarterly outcomes."
    )


def adobe(c):
    for q in [0, 1]:
        ref, _, m = c.find(q, r"Total revenue \$(\d+(?:\.\d+)?) billion to \$(\d+(?:\.\d+)?) billion", format="pdf")
        aref, _, am = c.find(q + 1, r"Total revenue\s*[. ]*\s*([\d,]+)\s+([\d,]+)", format="pdf")
        t = c.target(q + 1, "Consolidated quarterly revenue", m[1], m[2])
        c.add(
            f"revenue-q{q + 2}",
            f"FY25 Q{q + 2} revenue against the original range",
            q,
            ref,
            t,
            (aref, str(printed_numbers(am[1])[0]), "million", "reported", None),
            "The precise PDF income-statement total is used, rather than the rounded revenue headline. The first numerical column is the current three-month period.",
            "Which customer groups and currency movements explain the outcome?",
            4,
            notes="Reviewed the PDF's three-month and six/nine-month headers, revenue line, footnotes and call's constant-currency convention. This comparison uses reported dollars.",
        )
        ref, _, m = c.find(
            q,
            r"Earnings per share GAAP: \$\d+(?:\.\d+)? to \$\d+(?:\.\d+)? Non-GAAP: \$(\d+(?:\.\d+)?) to \$(\d+(?:\.\d+)?)",
            format="pdf",
        )
        aref, _, am = c.find(
            q + 1,
            r"Diluted earnings per share was \$\d+(?:\.\d+)? on a GAAP basis and \$(\d+(?:\.\d+)?) on a non-GAAP basis",
            format="pdf",
        )
        t = c.target(q + 1, "Non-GAAP diluted earnings per share", m[1], m[2], scale="1", basis="non_gaap")
        c.add(
            f"eps-q{q + 2}",
            f"FY25 Q{q + 2} adjusted EPS against adjusted guidance",
            q,
            ref,
            t,
            (aref, am[1], "1", "non_gaap", None),
            "The non-GAAP target and outcome share the stated basis. Forecast tax, operating-margin and diluted-share assumptions remain in the full source context; the gap is descriptive, not a causal delivery judgment.",
            "Which operating, tax and share-count differences explain the adjusted EPS result?",
            3,
        )
        context, _, _ = c.find(
            q + 1,
            r"During this presentation, Adobe.s executives will refer to constant currency growth rates[^.]*\.",
            kind="transcript",
        )
        c.observations[-1]["context_evidence"] = [context]
    return c.finish(
        "Revenue and adjusted EPS exceeded the earlier ranges. Official call transcripts use constant-currency growth unless stated otherwise, so growth commentary cannot replace reported-dollar results."
    )


def walmart(c):
    for q in [0, 1]:
        ref, _, m = c.find(q, r"Net sales \(cc\) Increase (\d+(?:\.\d+)?)% to (\d+(?:\.\d+)?)%", format="pdf")
        aref, _, am = c.find(
            q + 1, r"Revenue growth of \d+(?:\.\d+)?%, up (\d+(?:\.\d+)?)% in constant currency", format="pdf"
        )
        t = c.target(
            q + 1,
            "Consolidated net-sales year-over-year growth",
            m[1],
            m[2],
            unit="percent",
            scale="1",
            basis="constant_currency",
        )
        c.add(
            f"sales-growth-q{q + 1}",
            f"FY26 Q{q + 1} sales growth on constant-currency basis",
            q,
            ref,
            t,
            (aref, am[1], "1", "constant_currency", None),
            "The source's constant-currency consolidated growth is used. Reported growth, U.S. comparable sales and their different retail-week calendar do not settle this target.",
            "How do currency, VIZIO and underlying volumes explain the consolidated outcome?",
            4,
            notes="Read the fiscal net-sales guidance, release non-GAAP notes and call commentary. Stable-consumer/macro assumptions remain context, not evidence that a permit-like contingency was satisfied.",
        )
    ref, _, _ = c.find(1, r"Given the dynamic nature of the backdrop.*?full year guidance", format="pdf")
    # Call Q&A is deliberately retained as context for the missing quarterly profitability range.
    update, _, _ = c.find(
        2, r"growth also affected ~560 bps from higher self- insured general liability claims expense", format="pdf"
    )
    call, _, _ = c.find(
        1, r"And lastly, our method of accounting for inventory.*?credibly rely upon\.", kind="transcript"
    )
    later_call, _, _ = c.find(
        2, r"Adjusted SG&A expenses deleveraged.*?mitigate the number and cost of these claims\.", kind="transcript"
    )
    item = c.add(
        "profitability-guidance",
        "Q2 profitability guidance was withheld",
        1,
        ref,
        None,
        rationale="Management provided Q2 sales guidance but withheld an operating-income and EPS range. A later claims-expense headwind cannot be labelled a miss against a range that was never issued.",
        question="How did the uncertain tariff backdrop and later claims expense affect profitability planning?",
        materiality=5,
        updates=[
            {
                "type": "wording_changed",
                "interpretation": "The Q2 release describes a general-liability claims headwind; no original quarterly profitability range exists to adjudicate.",
                "evidence": [update],
            }
        ],
    )
    item["evidence"].append(call)
    item["updates"][0]["evidence"].append(later_call)
    return c.finish(
        "Constant-currency sales guidance is compared with constant-currency results. Q2 profitability had no numerical range; the review does not manufacture one."
    )


def delta(c):
    ref, b, _ = c.find(0, r"^Earnings Per Share$", format="html", cell=True)
    low, high = printed_numbers(b["context"]["cells"][-1])[:2]
    aref, _, am = c.find_after(
        1, r"March Quarter 2025 Non-GAAP Financial Results", r"Earnings per share of \$(\d+(?:\.\d+)?)"
    )
    update, _, _ = c.find(
        1, r"Delta Air Lines provided an update to investors on March 10.*?presentation \.", kind="guidance_update"
    )
    t = c.target(1, "Adjusted diluted earnings per share", low, high, scale="1", basis="non_gaap")
    c.add(
        "eps-q1",
        "Q1 EPS below January guidance, which was later revised",
        0,
        ref,
        t,
        (aref, am[1], "1", "non_gaap", None),
        "This is the January benchmark, not the latest pre-release guidance. Delta's official March update confirms a revision; the numerical revised range is not in the acquired news text.",
        "What changed between the original outlook and the March revision?",
        5,
        updates=[
            {
                "type": "revised_target",
                "interpretation": "An official March 10 investor update announces changed quarterly guidance before the period ended. Do not present the January comparison as a miss against the latest target.",
                "evidence": [update],
            }
        ],
    )
    ref, b, _ = c.find(1, r"^Earnings Per Share$", format="html", cell=True)
    low, high = printed_numbers(b["context"]["cells"][-1])[:2]
    aref, _, am = c.find_after(
        2, r"June Quarter 2025 Non-GAAP Financial Results", r"Earnings per share of \$(\d+(?:\.\d+)?)"
    )
    t = c.target(2, "Adjusted diluted earnings per share", low, high, scale="1", basis="non_gaap")
    c.add(
        "eps-q2",
        "Q2 adjusted EPS against April guidance",
        1,
        ref,
        t,
        (aref, am[1], "1", "non_gaap", None),
        "The June-quarter guidance is matched to the June-quarter adjusted actual, not GAAP EPS or the new full-year target.",
        "How much of the result reflects fuel prices, premium demand and capacity decisions?",
        4,
    )
    return c.finish(
        "Q2 adjusted EPS landed within April guidance. Q1 is compared only with the original January range, with the subsequent March revision clearly retained.",
        [
            "The official March news update confirms a revision but does not contain its numerical target table. No latest-guidance numerical verdict is made."
        ],
    )


BUILDERS = {
    "nvda": nvidia,
    "amd": amd,
    "crm": salesforce,
    "amzn": amazon,
    "meta": meta,
    "uber": uber,
    "pypl": paypal,
    "adbe": adobe,
    "wmt": walmart,
    "dal": delta,
}


def run(root):
    results = []
    for ticker, builder in BUILDERS.items():
        try:
            results.append({"ticker": ticker.upper(), **builder(Case(Path(root) / ticker))})
        except (ValueError, OSError, KeyError, IndexError, TypeError) as e:
            results.append({"ticker": ticker.upper(), "status": "failed", "message": str(e)})
            print(ticker, "FAILED", str(e), flush=True)
        write_json(Path(root) / "review-summary.json", results)
    if results and all(r["status"] == "review_ready" for r in results):
        portfolio([Path(root) / ticker / "report" for ticker in BUILDERS], root)
    return results


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    results = run(p.parse_args().workspace)
    raise SystemExit(1 if any(r["status"] in {"failed", "blocked"} for r in results) else 0)
