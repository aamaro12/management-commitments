"""Snapshot and anchor source documents without model-generated extraction."""

from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit, parse_qsl
import zipfile
from xml.etree import ElementTree as ET

MAX_BYTES = 12 * 1024 * 1024


class EvidenceError(ValueError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normal(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def digest(data):
    return sha256(data).hexdigest()


def read_json(path):
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise EvidenceError(f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def no_constant(value):
        raise EvidenceError(f"Non-finite JSON value: {value}")

    return json.loads(Path(path).read_text(), object_pairs_hook=no_duplicates, parse_constant=no_constant)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    temporary.replace(path)


def public_url(url):
    if not isinstance(url, str) or any(c in url for c in "\r\n\t"):
        raise EvidenceError("Invalid URL")
    p = urlsplit(url)
    if p.scheme != "https" or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise EvidenceError("Use a public HTTPS URL without credentials or a custom port")
    if any(re.search(r"(?i)key|token|secret|signature|password|authorization", k) for k, _ in parse_qsl(p.query)):
        raise EvidenceError("Credential-like URL parameters are not stored")
    return url


EXTRACTOR = 2  # 1: the first reader; 2: leaves out hidden page text and honours declared charsets
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
# Start tags that close an open paragraph, as browsers do when </p> is omitted.
CLOSES_P = {
    "address", "article", "aside", "blockquote", "dd", "details", "div", "dl", "dt", "fieldset", "figcaption",
    "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "menu", "nav",
    "ol", "p", "pre", "section", "table", "ul",
}  # fmt: skip
P_BOUNDS = {"button", "caption", "table", "td", "template", "th"}
# An open item closes when its next sibling starts, within the container that bounds it.
SIBLINGS = {
    "li": ({"li"}, {"ol", "ul"}),
    "dt": ({"dd", "dt"}, {"dl"}),
    "dd": ({"dd", "dt"}, {"dl"}),
    "tr": ({"tr"}, {"table", "tbody", "tfoot", "thead"}),
    "td": ({"td", "th"}, {"table", "tr"}),
    "th": ({"td", "th"}, {"table", "tr"}),
    "option": ({"option"}, {"datalist", "optgroup", "select"}),
}
HIDDEN_STYLE = re.compile(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)\s*(?:!important\s*)?(?:;|$)", re.I)
META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]+)""", re.I)


def decode(raw, declared=None):
    """Valid UTF-8 first, then a declared charset, then windows-1252 with a warning."""
    try:
        return raw.decode("utf-8-sig"), []
    except UnicodeDecodeError:
        pass
    if declared:
        try:
            return raw.decode(declared), []
        except (UnicodeDecodeError, LookupError):
            pass
    for codec, name in (("cp1252", "windows-1252"), ("latin-1", "latin-1")):
        try:
            return raw.decode(codec), [
                f"Not UTF-8 and no usable declared charset: decoded as {name}; check accented characters and symbols"
            ]
        except UnicodeDecodeError:
            continue


class Page(HTMLParser):
    """Preserve block order and table rows; table context is carried on each row."""

    boundaries = {"p", "div", "li", "h1", "h2", "h3", "h4", "section", "article", "br"}

    def __init__(self, url="", skip_hidden=False):
        super().__init__(convert_charrefs=True)
        self.url = url
        # Each open element and whether it hides its content, so hidden text is never a citable block.
        self.skip_hidden = skip_hidden
        self.open = []
        self.parts = []
        self.blocks = []
        self.links = []
        self.link = None
        self.skip = 0
        self.tables = []
        self.row = None
        self.cell = None
        self.title = []
        self.in_title = False
        self.publication_dates = []

    def add(self, text, context=None):
        text = normal(text)
        if text:
            self.blocks.append({"id": f"b{len(self.blocks) + 1:04d}", "text": text, "context": context or {}})

    def flush(self):
        self.add(" ".join(self.parts))
        self.parts = []

    def hidden(self):
        return any(hides for _, hides in self.open)

    def close_open(self, names, bounds):
        for i in range(len(self.open) - 1, -1, -1):
            if self.open[i][0] in names:
                del self.open[i:]
                return
            if self.open[i][0] in bounds:
                return

    def track(self, tag, attrs):
        if not self.skip_hidden:
            return
        if tag in CLOSES_P:
            self.close_open({"p"}, P_BOUNDS)
        if tag in SIBLINGS:
            self.close_open(*SIBLINGS[tag])
        if tag not in VOID:
            hides = tag == "template" or "hidden" in attrs or bool(HIDDEN_STYLE.search(attrs.get("style") or ""))
            self.open.append((tag, hides))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and (
            attrs.get("name", "").lower()
            in {"publishdate", "published_time", "date", "pubdate", "search_corporate_article_date"}
            or attrs.get("property", "").lower() == "article:published_time"
        ):
            self.publication_dates.append(attrs.get("content", ""))
        was_hidden = self.hidden()
        self.track(tag, attrs)
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip += 1
        if self.skip:
            return
        if tag == "title":
            self.in_title = True
        if tag == "a" and attrs.get("href"):
            self.link = {"url": urljoin(self.url, attrs["href"]), "parts": []}
        # Some IR websites render download links from custom-element attributes.
        if attrs.get("link"):
            self.links.append(
                {
                    "url": urljoin(self.url, attrs["link"]),
                    "label": attrs.get("arialabel", attrs.get("aria-label", "Download")),
                }
            )
        # Links inside hidden menus are still discovered; only their text is kept out of the blocks.
        if was_hidden:
            return
        if self.hidden():
            if tag in self.boundaries and self.cell is None:
                self.flush()
            return
        if tag == "table":
            self.flush()
            self.tables.append({"rows": []})
        elif tag == "tr" and self.tables:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []
        elif tag in self.boundaries and self.cell is None:
            self.flush()

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"}:
            self.skip = max(0, self.skip - 1)
            self.close_open({tag}, ())
            return
        if self.skip:
            return
        if tag == "title":
            self.in_title = False
        if tag == "a" and self.link:
            self.links.append({"url": self.link["url"], "label": normal(" ".join(self.link["parts"]))})
            self.link = None
        was_hidden = self.hidden()
        self.close_open({tag}, ())
        if was_hidden:
            if not self.hidden() and tag in self.boundaries and self.cell is None:
                self.flush()
            return
        if tag in {"td", "th"} and self.cell is not None:
            self.row.append(normal(" ".join(self.cell)))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.tables:
            table = self.tables[-1]
            context = {
                "table_rows_before": table["rows"][-8:],
                "table_opening_rows": table["rows"][:6],
                "cells": self.row,
            }
            self.add(" | ".join(self.row), context)
            table["rows"].append(self.row)
            self.row = None
        elif tag == "table" and self.tables:
            self.tables.pop()
            self.row = self.cell = None
        elif tag in self.boundaries and self.cell is None:
            self.flush()

    def handle_data(self, text):
        if self.skip:
            return
        if self.in_title:
            self.title.append(text)
            return
        if self.link:
            self.link["parts"].append(text)
        if self.hidden():
            return
        if self.cell is not None:
            self.cell.append(text)
        else:
            self.parts.append(text)


def extract(raw, format, url="", charset=None, version=EXTRACTOR):
    if len(raw) > MAX_BYTES:
        raise EvidenceError("Source exceeds 12 MiB")
    warnings = []
    links = []
    title = ""
    publication_dates = []
    if format == "html":
        page = Page(url, skip_hidden=version >= 2)
        if version >= 2:
            sniffed = META_CHARSET.search(raw[:4096])
            text, decoding = decode(raw, charset or (sniffed[1].decode("ascii") if sniffed else None))
            warnings += decoding
        else:
            text = raw.decode("utf-8-sig", errors="replace")
        page.feed(text)
        page.flush()
        blocks, links, title = page.blocks, page.links, normal(" ".join(page.title))
        publication_dates = page.publication_dates
        warnings.append("HTML text extraction; scripts, visuals and client-rendered content are not executed")
    elif format == "pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise EvidenceError("Install management-commitments[pdf] to read PDFs") from e
        from pypdf.errors import DependencyError, PyPdfError

        try:
            reader = PdfReader(io.BytesIO(raw))
            blocks = []
            for page_no, page in enumerate(reader.pages, 1):
                for paragraph in re.split(r"\n\s*\n", page.extract_text() or ""):
                    if normal(paragraph):
                        blocks.append(
                            {"id": f"b{len(blocks) + 1:04d}", "text": normal(paragraph), "context": {"page": page_no}}
                        )
        except (PyPdfError, DependencyError) as e:
            raise EvidenceError(f"PDF text extraction failed: {e}") from e
        warnings.append("PDF text layer only; reading order and table columns require semantic review; no OCR")
    elif format in {"docx", "pptx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist()) > MAX_BYTES * 4:
                    raise EvidenceError("Expanded Office document exceeds the extraction budget")
                if format == "docx":
                    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                    tree = ET.fromstring(z.read("word/document.xml"))
                    paragraphs = tree.findall(".//w:p", ns)
                    blocks = [
                        {
                            "id": f"b{i:04d}",
                            "text": normal("".join(t.text or "" for t in p.findall(".//w:t", ns))),
                            "context": {"paragraph": i},
                        }
                        for i, p in enumerate(paragraphs, 1)
                    ]
                    blocks = [b for b in blocks if b["text"]]
                    warnings.append(
                        "DOCX body only; headers, comments and tracked-change interpretation are not included"
                    )
                else:
                    ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
                    names = sorted(
                        (n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"slide(\d+)", n)[1]),
                    )
                    blocks = []
                    for slide, name in enumerate(names, 1):
                        tree = ET.fromstring(z.read(name))
                        for p in tree.findall(".//a:p", ns):
                            text = normal(" ".join(t.text or "" for t in p.findall(".//a:t", ns)))
                            if text:
                                blocks.append(
                                    {"id": f"b{len(blocks) + 1:04d}", "text": text, "context": {"slide": slide}}
                                )
                    warnings.append(
                        "PPTX slide text only; charts, images, notes and visual reading order require separate review"
                    )
        except EvidenceError:
            raise
        except (zipfile.BadZipFile, ET.ParseError, KeyError, IndexError, ValueError) as e:
            raise EvidenceError(f"Unreadable {format.upper()} file: {e}") from e

    elif format == "txt":
        if version >= 2:
            text, decoding = decode(raw, charset)
            warnings += decoding
        else:
            text = raw.decode("utf-8-sig")
        blocks = [
            {"id": f"b{i:04d}", "text": normal(t), "context": {}}
            for i, t in enumerate((t for t in text.splitlines() if t.strip()), 1)
        ]
    else:
        raise EvidenceError("Supported documents: HTML, text, DOCX, PPTX and text-layer PDF")
    if not blocks or len(blocks) > 50000:
        raise EvidenceError("Source has no readable text or exceeds the block budget")
    return {
        "title": title,
        "blocks": blocks,
        "links": links,
        "warnings": warnings,
        "publication_dates": publication_dates,
    }


def add_source(root, raw, metadata, format="html"):
    root = Path(root)
    parsed = extract(raw, format, metadata.get("url", ""), metadata.get("charset"))
    sid = "s" + digest(raw)[:16]
    parsed.update(metadata)
    parsed.update({"id": sid, "sha256": digest(raw), "format": format, "captured_at": now(), "extractor": EXTRACTOR})
    parsed["title"] = metadata.get("title") or parsed["title"] or sid
    parsed["text_sha256"] = digest(json.dumps(parsed["blocks"], sort_keys=True).encode())
    folder = root / "sources"
    folder.mkdir(parents=True, exist_ok=True)
    existing = folder / f"{sid}.json"
    if existing.exists():
        prior = read_json(existing)
        if prior.get("company") != metadata.get("company") or prior.get("period") != metadata.get("period"):
            raise EvidenceError(
                "Identical content assigned to different company/period; likely stale or wrong document"
            )
        return prior
    (folder / f"{sid}.raw").write_bytes(raw)
    write_json(existing, parsed)
    return parsed


def load_source(root, sid):
    if not re.fullmatch(r"s[a-f0-9]{16}", sid):
        raise EvidenceError("Invalid source identifier")
    folder = Path(root) / "sources"
    path = folder / f"{sid}.json"
    if path.is_symlink() or (folder / f"{sid}.raw").is_symlink():
        raise EvidenceError("Source symlinks are not supported")
    data = read_json(path)
    raw = (folder / f"{sid}.raw").read_bytes()
    if data.get("id") != sid or digest(raw) != data.get("sha256"):
        raise EvidenceError("Source snapshot hash mismatch")
    # A snapshot is re-read with the reader that saved it, so improvements never invalidate saved evidence.
    actual = extract(raw, data["format"], data.get("url", ""), data.get("charset"), data.get("extractor", 1))
    if actual["blocks"] != data["blocks"]:
        raise EvidenceError("Source extraction no longer matches the captured bytes")
    return data


def resolve(root, ref):
    source = load_source(root, ref["source_id"])
    block = next((b for b in source["blocks"] if b["id"] == ref["block_id"]), None)
    quote = normal(ref.get("quote", ""))
    if not block or len(quote) < 8 or quote not in block["text"]:
        raise EvidenceError("Evidence quote does not match its source block")
    return {
        **ref,
        "quote": quote,
        "text": block["text"],
        "context": block["context"],
        "url": source.get("url"),
        "title": source["title"],
        "period": source["period"],
        "company": source["company"],
        "published_at": source.get("published_at"),
        "publication_basis": source.get("publication_basis", "caller-supplied metadata"),
        "snapshot_path": str((Path(root) / "sources" / f"{source['id']}.json").resolve()),
        "completeness": source.get("completeness", "unknown"),
        "warnings": source["warnings"],
    }
