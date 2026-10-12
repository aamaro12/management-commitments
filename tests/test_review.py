from copy import deepcopy
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from management_commitments.demo import base_case, build, evaluate, P2
from management_commitments.review import compare, decimal, printed_numbers, review, review_commitment
from management_commitments.sources import EvidenceError, add_source, read_json, write_json


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data = build(self.root, [base_case("x", "Revenue growth")])
        self.c = self.data["commitments"][0]
        self.o = {o["id"]: o for o in self.data["observations"]}

    def run_case(self):
        return review_commitment(self.root, self.c, self.o, "HARBOR", date(2025, 7, 31))

    def test_full_synthetic_suite(self):
        result = evaluate(self.root / "suite")
        self.assertEqual(result["passed"], 24)
        self.assertEqual(result["status"], "passed")

    def test_decimal_exactness_and_range_gap(self):
        t = {"unit": "USD", "scale": "billion", "operator": "range", "low": "25.55", "high": "25.85"}
        o = {"value": "25544", "scale": "million"}
        c = compare(t, o)
        self.assertEqual(c["actual_in_target_scale"], "25.544")
        self.assertEqual(c["gap_to_range"], "-0.006")
        self.assertEqual(c["gap_to_midpoint"], "-0.156")
        self.assertEqual(c["result"], "below_range")

    def test_relative_and_absolute_tolerance(self):
        t = {
            "unit": "USD",
            "scale": "billion",
            "operator": "tolerance",
            "center": "43",
            "tolerance": {"value": "2", "type": "relative_percent"},
        }
        c = compare(t, {"value": "44062", "scale": "million"})
        self.assertEqual(c["tolerance_calculation"]["derived_low"], "42.14")
        self.assertEqual(c["tolerance_calculation"]["derived_high"], "43.86")
        self.assertEqual(c["gap_to_range"], "0.202")
        t.update({"center": "7.1", "tolerance": {"value": "300", "type": "absolute", "scale": "million"}})
        c = compare(t, {"value": "7438", "scale": "million"})
        self.assertEqual(c["tolerance_calculation"]["derived_high"], "7.4")
        self.assertEqual(c["gap_to_range"], "0.038")

    def test_basis_point_tolerance(self):
        c = compare(
            {
                "unit": "percent",
                "scale": "1",
                "operator": "tolerance",
                "center": "71",
                "tolerance": {"value": "50", "type": "basis_points"},
            },
            {"value": "70.6", "scale": "1"},
        )
        self.assertEqual(c["result"], "within_range")
        self.assertEqual(c["tolerance_calculation"]["derived_low"], "70.5")

    def test_tolerance_rejects_invalid_dimensions_and_negative_width(self):
        t = {"unit": "USD", "scale": "billion", "operator": "tolerance", "center": "43"}
        for tol in [
            {"type": "relative_percent", "value": "-2"},
            {"type": "relative_percent", "value": "2", "scale": "million"},
            {"type": "basis_points", "value": "50"},
            {"type": "absolute", "value": "2", "scale": "unknown"},
        ]:
            with self.subTest(tol=tol), self.assertRaises(EvidenceError):
                compare({**t, "tolerance": tol}, {"value": "44", "scale": "billion"})

    def test_tolerance_requires_printed_width(self):
        self.c["target"].update(
            {"operator": "tolerance", "center": "10", "tolerance": {"type": "relative_percent", "value": "50"}}
        )
        self.c["target"].pop("low")
        self.c["target"].pop("high")
        result = self.run_case()
        self.assertEqual(result["status"], "blocked")
        self.assertIn("Tolerance value is not printed", str(result["flags"]))

    def test_tolerance_cannot_use_supplied_derived_bounds(self):
        t = {
            "unit": "percent",
            "scale": "1",
            "operator": "tolerance",
            "center": "10",
            "low": "8",
            "high": "12",
            "tolerance": {"type": "absolute", "value": "2"},
        }
        with self.assertRaises(EvidenceError):
            compare(t, {"value": "11", "scale": "1"})

    def test_percentage_gap_is_points(self):
        c = compare(
            {"unit": "percent", "scale": "1", "operator": "range", "low": "31", "high": "32"},
            {"value": "35", "scale": "1"},
        )
        self.assertEqual(c["gap_to_range"], "3")
        self.assertEqual(c["gap_to_midpoint"], "3.5")
        self.assertEqual(c["gap_unit"], "percentage_points")

    def test_strict_surpass_operator(self):
        t = {"unit": "USD", "scale": "billion", "operator": "greater_than", "low": "10"}
        self.assertEqual(compare(t, {"value": "10", "scale": "billion"})["result"], "missed")
        self.assertEqual(compare(t, {"value": "10.1", "scale": "billion"})["result"], "met")

    def test_printed_sign_and_financial_parentheses(self):
        self.assertEqual(
            printed_numbers("Income ($250), expense -$10, margin −2%."), [Decimal(-250), Decimal(-10), Decimal(-2)]
        )

    def test_invalid_quantities(self):
        for v in [True, None, "NaN", "Infinity", "-Infinity"]:
            with self.subTest(v=v), self.assertRaises(EvidenceError):
                decimal(v)

    def test_wrong_metric_blocked(self):
        self.o["x_actual"]["metric_key"] = "another"
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_duplicate_observation_links_blocked(self):
        self.c["observation_ids"] *= 2
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_conflicting_actuals_blocked(self):
        o = deepcopy(self.o["x_actual"])
        source = add_source(
            self.root,
            b"Reported revenue growth: 12%.",
            {
                "company": "HARBOR",
                "period": P2,
                "published_at": "2025-07-15",
                "title": "Conflicting result",
                "completeness": "complete",
            },
            "txt",
        )
        o.update(
            {
                "id": "different",
                "value": "12",
                "evidence": [
                    {"source_id": source["id"], "block_id": "b0001", "quote": "Reported revenue growth: 12%."}
                ],
            }
        )
        self.o["different"] = o
        self.c["observation_ids"].append("different")
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_future_update_blocked(self):
        source = add_source(
            self.root,
            b"The target will remain unchanged.",
            {
                "company": "HARBOR",
                "period": P2,
                "published_at": "2025-09-15",
                "title": "Future update",
                "completeness": "complete",
            },
            "txt",
        )
        self.c["updates"] = [
            {
                "type": "reaffirmed",
                "evidence": [
                    {"source_id": source["id"], "block_id": "b0001", "quote": "The target will remain unchanged."}
                ],
            }
        ]
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_missing_conditions_are_not_assumed_met(self):
        self.c["conditions"] = ["permit approved"]
        self.assertEqual(self.run_case()["status"], "conditional")
        self.c["condition_assessment"] = None
        self.assertEqual(self.run_case()["status"], "conditional")
        self.c["condition_assessment"] = {"met": True}
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_null_semantic_review_is_pending(self):
        self.c["semantic_review"] = None
        self.assertEqual(self.run_case()["status"], "needs_review")

    def test_unmet_condition_evidence_is_preserved(self):
        source = add_source(
            self.root,
            b"The regulator has not approved the permit.",
            {
                "company": "HARBOR",
                "period": P2,
                "published_at": "2025-07-15",
                "title": "Permit status",
                "completeness": "complete",
            },
            "txt",
        )
        self.c["conditions"] = ["permit approved"]
        self.c["condition_assessment"] = {
            "met": False,
            "notes": "The result update explicitly says approval is pending.",
            "evidence": [
                {"source_id": source["id"], "block_id": "b0001", "quote": "The regulator has not approved the permit."}
            ],
        }
        r = self.run_case()
        self.assertEqual(r["status"], "conditional")
        self.assertIs(r["condition_assessment"]["met"], False)
        self.assertIn("documented as not satisfied", r["flags"][0])
        self.assertEqual(len(r["condition_assessment"]["evidence"]), 1)

    def test_explicit_header_context_supported(self):
        source = add_source(
            self.root,
            b"<table><tr><th>Metric</th><th>Current reported</th><th>Prior</th></tr><tr><td>Revenue growth</td><td>11%</td><td>5%</td></tr></table>",
            {
                "company": "HARBOR",
                "period": P2,
                "published_at": "2025-07-15",
                "title": "Table",
                "completeness": "complete",
            },
            "html",
        )
        o = self.o["x_actual"]
        o.update(
            {
                "evidence": [{"source_id": source["id"], "block_id": "b0002", "quote": "Revenue growth | 11% | 5%"}],
                "context_evidence": [
                    {"source_id": source["id"], "block_id": "b0001", "quote": "Metric | Current reported | Prior"}
                ],
                "cell_index": 1,
                "column_review": "Current reported, same financial period.",
            }
        )
        r = self.run_case()
        self.assertEqual(r["status"], "within_range")
        self.assertEqual(r["result_evidence"][1]["role"], "column_or_metric_context")

    def test_missing_actual_never_becomes_missed(self):
        self.c["observation_ids"] = []
        self.assertEqual(self.run_case()["status"], "unresolved")
        self.assertIsNone(self.run_case()["calculation"])

    def test_point_in_time_requires_measurement_date(self):
        self.c["target"].update({"measurement_type": "point_in_time", "measurement_date": "2025-06-30"})
        self.assertEqual(self.run_case()["status"], "unresolved")
        self.o["x_actual"]["measurement_date"] = "2025-07-15"
        self.assertEqual(self.run_case()["status"], "unresolved")
        self.o["x_actual"]["measurement_date"] = "2025-06-30"
        self.assertEqual(self.run_case()["status"], "within_range")

    def test_unknown_source_pack_reference_rejected(self):
        self.c["evidence"][0]["source_id"] = "s0000000000000000"
        write_json(self.root / "analysis.json", self.data)
        with self.assertRaises(EvidenceError):
            review(self.root, self.root / "analysis.json", self.root / "report")

    def test_actual_table_column_selection(self):
        source = add_source(
            self.root,
            b"<table><tr><td>Revenue growth</td><td>11%</td><td>5%</td></tr></table>",
            {
                "company": "HARBOR",
                "period": P2,
                "published_at": "2025-07-15",
                "title": "Table",
                "completeness": "complete",
            },
            "html",
        )
        o = self.o["x_actual"]
        o["evidence"] = [{"source_id": source["id"], "block_id": "b0001", "quote": "Revenue growth | 11% | 5%"}]
        self.assertEqual(self.run_case()["status"], "blocked")
        o.update({"cell_index": 2, "column_review": "Current fiscal quarter, reported growth"})
        self.assertEqual(self.run_case()["status"], "blocked")
        o["cell_index"] = 1
        self.assertEqual(self.run_case()["status"], "within_range")

    def test_unit_mismatch_does_not_calculate(self):
        self.o["x_actual"]["unit"] = "USD"
        r = self.run_case()
        self.assertEqual(r["status"], "basis_mismatch")
        self.assertIsNone(r["calculation"])

    def test_bad_scale_blocked(self):
        self.c["target"]["scale"] = "billion"
        self.assertEqual(self.run_case()["status"], "blocked")

    def test_unverified_publication_blocks(self):
        sid = self.c["evidence"][0]["source_id"]
        path = self.root / "sources" / f"{sid}.json"
        s = read_json(path)
        s["published_at"] = None
        write_json(path, s)
        self.assertEqual(self.run_case()["status"], "blocked")
