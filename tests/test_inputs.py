"""Awkward inputs are read faithfully or refused with a clear error, and earlier snapshots keep loading."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import zipfile

from management_commitments import __version__
from management_commitments.cli import main
from management_commitments.network import fetch
from management_commitments.render import fill
from management_commitments.sources import EvidenceError, add_source, extract, load_source


def zipped(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()


def texts(page, **kwargs):
    return [b["text"] for b in extract(page.encode() if isinstance(page, str) else page, "html", **kwargs)["blocks"]]


class OfficeFileTests(unittest.TestCase):
    def test_corrupt_office_files_are_refused_cleanly(self):
        cases = {
            "docx: not a zip": (b"not a zip", "docx"),
            "docx: no document body": (zipped({"word/other.xml": "<x/>"}), "docx"),
            "pptx: malformed slide": (zipped({"ppt/slides/slide1.xml": "<p:sld"}), "pptx"),
        }
        for name, (raw, kind) in cases.items():
            with self.subTest(name), self.assertRaisesRegex(EvidenceError, "Unreadable " + kind.upper()):
                extract(raw, kind)

    def test_the_command_line_reports_a_corrupt_file_as_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            ws = Path(td)
            (ws / "source-pack.json").write_text(
                json.dumps({"company": {"id": "DEMO"}, "documents": [], "acquisition": []})
            )
            metadata = ws / "metadata.json"
            metadata.write_text(
                json.dumps(
                    {
                        "company": "DEMO",
                        "period": "FY2025 Q1",
                        "published_at": "2025-01-01T00:00:00+00:00",
                        "title": "Upload",
                        "kind": "other",
                        "completeness": "complete",
                    }
                )
            )
            broken = ws / "broken.docx"
            broken.write_bytes(b"not a zip")
            with patch("sys.stderr", new_callable=io.StringIO) as err, patch("sys.stdout", new_callable=io.StringIO):
                code = main(["ingest", "--workspace", str(ws), "--file", str(broken), "--metadata", str(metadata)])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(err.getvalue())["status"], "error")


class EncodingTests(unittest.TestCase):
    def test_text_that_is_not_utf8_is_decoded_with_a_warning(self):
        for kind, raw in {
            "html": "<p>Café SA reported 1250</p>".encode("cp1252"),
            "txt": "Café SA reported 1250\n".encode("cp1252"),
        }.items():
            with self.subTest(kind):
                result = extract(raw, kind)
                self.assertIn("Café SA reported 1250", [b["text"] for b in result["blocks"]])
                self.assertTrue(any("windows-1252" in w for w in result["warnings"]))

    def test_a_declared_charset_is_used_without_a_fallback_warning(self):
        page = '<meta charset="iso-8859-1"><p>Café SA reported 1250</p>'.encode("latin-1")
        result = extract(page, "html")
        self.assertIn("Café SA reported 1250", [b["text"] for b in result["blocks"]])
        self.assertFalse(any("windows-1252" in w for w in result["warnings"]))
        header = extract("<p>Café SA reported 1250</p>".encode("latin-1"), "html", charset="ISO-8859-1")
        self.assertIn("Café SA reported 1250", [b["text"] for b in header["blocks"]])

    def test_utf8_text_is_unchanged(self):
        self.assertEqual(texts("<p>Café SA reported 1250</p>"), ["Café SA reported 1250"])


class HiddenTextTests(unittest.TestCase):
    def test_text_the_page_hides_is_not_citable(self):
        page = (
            "<p>Revenue was 100 million</p>"
            '<p style="color: red; display:none">Revenue was 999 million</p>'
            "<p hidden>Revenue was 777 million</p>"
            '<div style="visibility: hidden">Revenue was 444 million</div>'
            "<template><p>Revenue was 333 million</p></template>"
            '<p aria-hidden="true">Shown on screen 42</p>'
            "<p>Margin was 20 percent</p>"
        )
        self.assertEqual(texts(page), ["Revenue was 100 million", "Shown on screen 42", "Margin was 20 percent"])

    def test_an_unclosed_hidden_element_does_not_hide_what_follows(self):
        page = "<p hidden>Revenue was 777 million<p>Revenue was 100 million<ul><li hidden>Secret<li>Visible item</ul>"
        self.assertEqual(texts(page), ["Revenue was 100 million", "Visible item"])

    def test_hidden_table_rows_do_not_disturb_the_table(self):
        page = (
            "<table><tr hidden><td>Secret</td><td>9</td></tr><tr><td>Revenue</td><td>100</td></tr></table><p>After</p>"
        )
        self.assertEqual(texts(page), ["Revenue | 100", "After"])

    def test_links_in_hidden_menus_are_still_discovered(self):
        page = '<nav hidden><a href="/ir/transcript.docx">FY25 Q1 transcript</a></nav><p>Visible</p>'
        result = extract(page.encode(), "html", "https://www.example.com/ir/")
        self.assertIn(
            {"url": "https://www.example.com/ir/transcript.docx", "label": "FY25 Q1 transcript"}, result["links"]
        )
        self.assertEqual([b["text"] for b in result["blocks"]], ["Visible"])


class SnapshotTests(unittest.TestCase):
    def test_snapshots_saved_by_the_earlier_reader_still_load(self):
        page = b"<p>Revenue was 100 million</p><p hidden>Revenue was 777 million</p>"
        meta = {"url": "https://www.example.com/r", "company": "DEMO", "period": "FY2025 Q1"}
        with tempfile.TemporaryDirectory() as td:
            current = add_source(td, page, meta)
            self.assertEqual([b["text"] for b in current["blocks"]], ["Revenue was 100 million"])
            self.assertEqual(load_source(td, current["id"])["id"], current["id"])
            saved = Path(td) / "sources" / (current["id"] + ".json")
            earlier = json.loads(saved.read_text())
            earlier.pop("extractor")
            earlier["blocks"] = extract(page, "html", meta["url"], version=1)["blocks"]
            saved.write_text(json.dumps(earlier))
            self.assertIn("Revenue was 777 million", [b["text"] for b in load_source(td, current["id"])["blocks"]])
            earlier["blocks"] = current["blocks"]
            saved.write_text(json.dumps(earlier))
            with self.assertRaisesRegex(EvidenceError, "no longer matches"):
                load_source(td, current["id"])


class TemplateTests(unittest.TestCase):
    def test_report_data_cannot_fill_a_later_placeholder(self):
        page = fill("<d>__DATA__</d><s>__JS__</s>", DATA="a quote with __JS__ inside", JS="run()")
        self.assertEqual(page, "<d>a quote with __JS__ inside</d><s>run()</s>")


class FetchTests(unittest.TestCase):
    def respond(self, raw, content_type):
        response = MagicMock(status=200)
        response.getheader.side_effect = lambda name: {"Content-Type": content_type}.get(name)
        response.read.return_value = raw
        connection = MagicMock()
        connection.getresponse.return_value = response
        with (
            patch("management_commitments.network.addresses", return_value=["93.184.216.34"]),
            patch("management_commitments.network.Connection", return_value=connection),
        ):
            result = fetch("https://www.example.com/ir", {"www.example.com"})
        return result, connection

    def test_the_charset_and_package_version_travel_with_the_request(self):
        result, connection = self.respond(b"<p>Revenue</p>", "text/html; charset=ISO-8859-1")
        self.assertEqual(result["charset"], "ISO-8859-1")
        agent = connection.request.call_args.kwargs["headers"]["User-Agent"]
        self.assertTrue(agent.startswith("management-commitments/" + __version__ + " "))

    def test_a_response_that_only_looks_like_a_zip_is_refused_cleanly(self):
        with self.assertRaisesRegex(EvidenceError, "Unsupported response"):
            self.respond(b"PK\x03\x04 not really a zip", "application/octet-stream")


if __name__ == "__main__":
    unittest.main()
