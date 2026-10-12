from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from management_commitments.collect import candidates, collect, kind, microsoft_profile, publication
from management_commitments.network import addresses
from management_commitments.sources import EvidenceError
from management_commitments.demo import P1


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.profile = {
            "company": {"id": "A", "name": "Acme"},
            "allowed_hosts": ["example.com"],
            "seeds": [{"url": "https://example.com/q1/results", "period": P1, "title_pattern": "Q1"}],
        }

    def fetcher(self, url, hosts):
        if "transcript" in url:
            body = "<title>Acme Q1 transcript</title><p>April 15, 2025</p><p>We expect revenue growth of 10% to 12% next quarter.</p>"
        else:
            body = '<title>Acme Q1 results</title><p>Published April 15, 2025. Acme results.</p><a href="transcript">Call transcript</a><a href="transcript">duplicate</a>'
        return {"raw": body.encode(), "url": url, "format": "html", "redirects": []}

    def test_discovery_deduplicates_and_logs(self):
        p = collect(self.profile, self.root, budget=5, fetcher=self.fetcher)
        self.assertEqual(p["requests"], 2)
        self.assertEqual(p["coverage"][0]["transcript"], "captured")
        self.assertFalse(p["truncated"])
        self.assertEqual(candidates(self.root, self.root / "candidates.json")["total_matches"], 1)

    def test_budget_truncation_visible(self):
        p = collect(self.profile, self.root, budget=1, fetcher=self.fetcher)
        self.assertTrue(p["truncated"])
        self.assertEqual(p["coverage"][0]["transcript"], "not_acquired")
        self.assertIn("budget_not_collected", str(p["candidate_links"]))

    def test_fetch_failure_is_visible(self):
        def fail(url, hosts):
            raise EvidenceError("HTTP 429")

        p = collect(self.profile, self.root, fetcher=fail)
        self.assertEqual(p["status"], "blocked")
        self.assertEqual(p["acquisition"][0]["message"], "HTTP 429")

    def test_title_mismatch_rejected(self):
        self.profile["seeds"][0]["title_pattern"] = "Q9"
        p = collect(self.profile, self.root, fetcher=self.fetcher)
        self.assertFalse(p["documents"])

    def test_company_mismatch_rejected(self):
        self.profile["company"]["name"] = "OtherCo"
        p = collect(self.profile, self.root, fetcher=self.fetcher)
        self.assertFalse(p["documents"])

    def test_msft_fiscal_rollover(self):
        p = microsoft_profile(2025, 4, 2)
        self.assertEqual(p["seeds"][0]["period"]["end"], "2025-06-30")
        self.assertEqual(p["seeds"][1]["period"], {"label": "FY2026 Q1", "start": "2025-07-01", "end": "2025-09-30"})

    def test_financial_period_date_is_not_publication(self):
        self.assertIsNone(publication([{"text": "Income statements three months ended September 30, 2024."}]))
        self.assertEqual(
            publication([{"text": "REDMOND, Wash. — October 30, 2024 — Microsoft announced results."}]), "2024-10-30"
        )

    def test_transcript_header_date(self):
        self.assertEqual(
            publication(
                [
                    {"text": "Microsoft FY25 First Quarter Earnings Conference Call"},
                    {"text": "Wednesday October 30, 2024"},
                ]
            ),
            "2024-10-30",
        )

    def test_date_after_long_navigation(self):
        blocks = [{"text": "Navigation item"}] * 90 + [
            {"text": "May 28, 2025"},
            {"text": "Quarter ended April 27, 2025"},
        ]
        self.assertEqual(publication(blocks), "2025-05-28")
        self.assertEqual(publication([], ["2025-08-21T06:00:00"]), "2025-08-21")

    def test_pdf_publication_requires_dateline_or_call_date(self):
        self.assertIsNone(publication([{"text": "Quarter End Date December 28, 2024 Net revenue 7,658"}], format="pdf"))
        self.assertEqual(
            publication(
                [
                    {
                        "text": "Meta Reports Results MENLO PARK, Calif., Jan. 29, 2025 /PRNewswire/ quarter ended December 31, 2024"
                    }
                ],
                format="pdf",
            ),
            "2025-01-29",
        )
        self.assertEqual(
            publication(
                [{"text": "Corrected Transcript"}, {"text": "20-Feb -2025 Walmart, Inc. Q4 2025 Earnings Call"}],
                format="pdf",
            ),
            "2025-02-20",
        )

    def test_pdf_dateline_dashes_and_iso_call_header(self):
        self.assertEqual(
            publication([{"text": "SANTA CLARA, Calif. — February 4, 2025 — AMD results"}], format="pdf"), "2025-02-04"
        )
        self.assertEqual(publication([{"text": "2025-02-04 AMD 4Q 2024 Earnings Call"}], format="pdf"), "2025-02-04")

    def test_document_types_are_distinct(self):
        self.assertEqual(
            kind("Financial Tables", "https://example.com/financial_tables_pdf/q1.pdf"), "financial_results"
        )
        self.assertEqual(kind("10-K", "https://example.com/sec-filings/report.pdf"), "regulatory_filing")

    def test_cached_generated_title_cannot_establish_identity(self):
        def fetcher(url, hosts):
            return {"raw": b"<p>Wrong issuer Q1 results.</p>", "url": url, "format": "html", "redirects": []}

        collect(self.profile, self.root, fetcher=fetcher)
        p = collect(self.profile, self.root, fetcher=fetcher)
        self.assertFalse(p["documents"])

    def test_undated_call_with_matching_quarter_year_is_a_visible_proxy(self):
        def fetcher(url, hosts):
            response = self.fetcher(url, hosts)
            if "transcript" in url:
                response["raw"] = b"<p>Acme Q1 2025 Earnings Call</p><p>Expect growth of 10%.</p>"
            return response

        p = collect(self.profile, self.root, fetcher=fetcher)
        self.assertEqual(p["coverage"][0]["transcript"], "captured")
        self.assertIn("document-specific date unverified", p["documents"][-1]["publication_basis"])

    def test_undated_transcript_does_not_inherit_verified_call_date(self):
        def fetcher(url, hosts):
            response = self.fetcher(url, hosts)
            if "transcript" in url:
                response["raw"] = response["raw"].replace(b"<p>April 15, 2025</p>", b"")
            if "transcript" not in url:
                response["raw"] = response["raw"].replace(b"Published April 15, 2025. Acme results.", b"April 15, 2025")
            return response

        p = collect(self.profile, self.root, fetcher=fetcher)
        self.assertEqual(p["coverage"][0]["transcript"], "not_acquired")
        self.assertIn("Transcript call date", str(p["acquisition"]))

    def test_transcript_has_priority_over_duplicate_pdf(self):
        def fetcher(url, hosts):
            response = self.fetcher(url, hosts)
            if "results" in url:
                response["raw"] += (
                    b'<a href="https://example.com/download.pdf">Download as PDF</a><a href="https://example.com/tax-strategy.pdf">Tax strategy</a>'
                )
            return response

        p = collect(self.profile, self.root, budget=2, fetcher=fetcher)
        self.assertEqual(p["coverage"][0]["transcript"], "captured")
        self.assertNotIn("tax-strategy", str(p["candidate_links"]))

    def test_local_and_mixed_dns_rejected(self):
        for ips in [["127.0.0.1"], ["169.254.169.254"], ["8.8.8.8", "10.0.0.1"], ["::1"]]:
            answers = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ips]
            with (
                self.subTest(ips=ips),
                patch("socket.getaddrinfo", return_value=answers),
                self.assertRaises(EvidenceError),
            ):
                addresses("example.com")
