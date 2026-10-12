from pathlib import Path
import tempfile
import unittest

from management_commitments.demo import run
from management_commitments.render import apply_decisions, portfolio, render
from management_commitments.sources import EvidenceError, read_json, write_json


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        run(self.root)
        self.folder = self.root / "report"
        self.report = read_json(self.folder / "report.json")

    def test_offline_artifacts_and_safe_embedded_json(self):
        self.report["summary"] = "</script><script>steal()</script>"
        render(self.report, self.folder)
        html = (self.folder / "review.html").read_text()
        self.assertNotIn(self.report["summary"], html)
        self.assertNotIn("<script src=", html)
        self.assertTrue((self.folder / "brief.md").exists())

    def test_company_portfolio_uses_real_relative_links_and_safe_data(self):
        self.report["summary"] = "</script><script>steal()</script>"
        render(self.report, self.folder)
        result = portfolio([self.folder], self.root / "index")
        self.assertEqual(result["totals"]["companies"], 1)
        self.assertEqual(result["totals"]["tracked"], 10)
        html = (self.root / "index/index.html").read_text()
        self.assertNotIn(self.report["summary"], html)
        r = read_json(self.folder / "report.json")
        self.assertTrue((self.folder / r["portfolio_href"]).exists())
        self.assertTrue((self.folder / r["related_reports"][0]["href"]).exists())

    def test_portfolio_rejects_duplicate_company(self):
        with self.assertRaises(EvidenceError):
            portfolio([self.folder, self.folder], self.root / "index")

    def decision_file(self, **changes):
        d = {
            "schema_version": 1,
            "company": "HARBOR",
            "analysis_sha256": self.report["analysis_sha256"],
            "reviewer": "Analyst",
            "decisions": [
                {
                    "id": self.report["commitments"][0]["id"],
                    "decision": "accepted",
                    "note": "Reviewed source and mapping.",
                }
            ],
        }
        d.update(changes)
        path = self.root / "decisions.json"
        write_json(path, d)
        return path

    def test_review_log_preserves_calculation_and_appends(self):
        before = self.report["commitments"][0]["calculation"]
        path = self.decision_file()
        apply_decisions(self.folder, path)
        apply_decisions(self.folder, path)
        r = read_json(self.folder / "report.json")
        self.assertEqual(r["commitments"][0]["calculation"], before)
        self.assertEqual(r["commitments"][0]["analyst_decision"], "accepted")
        self.assertEqual(len(read_json(self.folder / "review-log.json")), 2)

    def test_cross_analysis_import_rejected(self):
        with self.assertRaises(EvidenceError):
            apply_decisions(self.folder, self.decision_file(analysis_sha256="wrong"))

    def test_local_source_links_are_real_paths(self):
        self.assertNotIn("](#)", (self.folder / "brief.md").read_text())

    def test_missing_reviewer_rejected(self):
        with self.assertRaises(EvidenceError):
            apply_decisions(self.folder, self.decision_file(reviewer=""))

    def test_rejection_requires_note(self):
        d = [{"id": self.report["commitments"][0]["id"], "decision": "rejected", "note": ""}]
        with self.assertRaises(EvidenceError):
            apply_decisions(self.folder, self.decision_file(decisions=d))
