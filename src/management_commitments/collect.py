"""Bounded official-site discovery, acquisition logs and a source pack for Codex."""

from datetime import date
from pathlib import Path
import re
from urllib.parse import urlsplit, urldefrag, parse_qs

from .network import fetch
from .sources import EvidenceError, add_source, extract, now, public_url, read_json, write_json

RELEVANT = re.compile(
    r"(?i)transcript|outlook|earnings.call|earnings.release|press.release|financial.results|prepared.remarks|financial.statement|segment.result|performance|metrics|\.pdf"
)
IRRELEVANT = re.compile(r"(?i)supply.chain|tax.strategy|privacy|cookie|sustainability|code.of.conduct")


def publication(blocks, metadata_dates=None, format="html"):
    from datetime import datetime

    for candidate in metadata_dates or []:
        if re.match(r"^20\d{2}-\d{2}-\d{2}", candidate):
            return date.fromisoformat(candidate[:10]).isoformat()
    date_pattern = r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s*(20\d{2})"
    # Standalone date headings, even after long site navigation, are preferred to narrative financial dates.
    for b in blocks[:200]:
        if b.get("context", {}).get("cells"):
            continue
        m = re.match(r"^(?:Published|Released)?\s*" + date_pattern + r"(?:$|\s+\d{1,2}:\d{2})", b["text"], re.I)
        if m:
            return datetime.strptime(f"{m[1]} {m[2]}, {m[3]}", "%B %d, %Y").date().isoformat()
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", b["text"]):
            return date.fromisoformat(b["text"]).isoformat()
    if format == "pdf" and blocks:
        header = " ".join(b["text"] for b in blocks[:5])[:4500]
        # A financial-table period end is not a publication date. Require a dateline or call header.
        m = re.search(
            r"(?:SAN JOSE|SANTA CLARA|MENLO PARK|BENTONVILLE|ATLANTA|SEATTLE|REDMOND).{0,45}?([A-Za-z]{3,9})\.?\s+(\d{1,2}),?\s*(20\d{2})",
            header,
            re.I,
        )
        if m:
            month = m[1][:3].title()
            return datetime.strptime(f"{month} {m[2]} {m[3]}", "%b %d %Y").date().isoformat()
        if re.search(r"earnings (?:conference )?call", header, re.I):
            m = re.match(r"\s*(20\d{2}-\d{2}-\d{2})\b", header)
            if m:
                return date.fromisoformat(m[1]).isoformat()
            m = re.search(r"(\d{1,2})\s*-\s*([A-Za-z]{3})\s*-\s*(20\d{2})", header)
            if m:
                return datetime.strptime(f"{m[1]}-{m[2]}-{m[3]}", "%d-%b-%Y").date().isoformat()
            m = re.search(date_pattern, header, re.I)
            if m:
                return datetime.strptime(f"{m[1]} {m[2]}, {m[3]}", "%B %d, %Y").date().isoformat()
    text = " ".join(b["text"] for b in blocks[:35])
    match = re.search(
        r"(?:REDMOND|release.date|published)[^\n]{0,90}?\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(20\d{2})",
        text,
        re.I,
    )
    if not match:
        header = " ".join(b["text"] for b in blocks[:5])
        if blocks and "earnings conference call" in blocks[0]["text"].casefold():
            match = re.search(
                r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(20\d{2})",
                header,
                re.I,
            )
        if not match:
            return None
    return datetime.strptime(f"{match[1]} {match[2]}, {match[3]}", "%B %d, %Y").date().isoformat()


def kind(label, url):
    text = label + " " + url
    if re.search("transcript", text, re.I):
        return "transcript"
    if re.search("outlook|guidance", text, re.I):
        return "outlook"
    if re.search("slides|presentation", text, re.I):
        return "presentation"
    if re.search("webcast|recording", text, re.I):
        return "recording_or_webcast_page"
    if re.search("sec-filings|10-[qk]", text, re.I):
        return "regulatory_filing"
    if re.search("financial.statement|financial.tables|segment|performance|metrics", text, re.I):
        return "financial_results"
    return "earnings_release"


def microsoft_profile(year=2025, start=1, count=3):
    if year < 2020 or year > date.today().year + 1 or start not in range(1, 5) or count not in range(1, 9):
        raise EvidenceError("Use a fiscal year from 2020 onward and one to eight quarters")
    from calendar import monthrange

    seeds = []
    for offset in range(count):
        fy, q = year + (start - 1 + offset) // 4, (start - 1 + offset) % 4 + 1
        end_year, end_month = (fy - 1 if q < 3 else fy), {1: 9, 2: 12, 3: 3, 4: 6}[q]
        start_month, start_year = end_month - 2, end_year
        period = {
            "label": f"FY{fy} Q{q}",
            "start": f"{start_year}-{start_month:02d}-01",
            "end": f"{end_year}-{end_month:02d}-{monthrange(end_year, end_month)[1]}",
        }
        seeds.append(
            {
                "url": f"https://www.microsoft.com/en-us/Investor/earnings/FY-{fy}-Q{q}/press-release-webcast",
                "period": period,
                "title_pattern": f"FY{str(fy)[2:]} Q{q}",
            }
        )
    return {
        "company": {"id": "MSFT", "name": "Microsoft Corporation"},
        "allowed_hosts": [
            "www.microsoft.com",
            "microsoft.com",
            "download.microsoft.com",
            "cdn-dynmedia-1.microsoft.com",
        ],
        "seeds": seeds,
        "description": "Official earnings pages; select linked call/financial materials within the request budget",
    }


def collect(profile, root, budget=18, depth=1, fetcher=fetch):
    if not 1 <= budget <= 100 or depth not in (0, 1, 2):
        raise EvidenceError("Request budget must be 1-100 and discovery depth 0-2")
    if not isinstance(profile.get("company"), dict) or not profile["company"].get("id"):
        raise EvidenceError("Profile needs a company identity")
    hosts = {h.lower() for h in profile["allowed_hosts"]}
    if not hosts or not profile.get("seeds"):
        raise EvidenceError("Profile needs explicit allowed hosts and seed URLs")
    root = Path(root)
    pack = {
        "schema_version": 1,
        "company": profile["company"],
        "collected_at": now(),
        "request_budget": budget,
        "documents": [],
        "acquisition": [],
        "coverage": [],
        "candidate_links": [],
        "truncated": False,
        "profile": profile,
        "limitations": ["Bounded official-site discovery; no completeness claim for an entire IR website"],
    }
    queue = [(seed["url"], seed, 0, "earnings_release") for seed in profile["seeds"]]
    seen = set()
    requests = 0
    release_dates = {}
    while queue:
        queue.sort(
            key=lambda x: (
                x[2],
                {"transcript": 0, "outlook": 1, "earnings_release": 2, "financial_results": 3}.get(x[3], 4),
            )
        )
        url, seed, level, document_kind = queue.pop(0)
        url = urldefrag(url)[0]
        key = url.lower() if urlsplit(url).hostname in {"www.microsoft.com", "microsoft.com"} else url
        if key in seen:
            continue
        seen.add(key)
        if requests >= budget:
            pack["truncated"] = True
            pack["candidate_links"].append({"url": url, "period": seed["period"], "status": "budget_not_collected"})
            continue
        try:
            public_url(url)
            if urlsplit(url).hostname.lower() not in hosts:
                raise EvidenceError("Discovered host is not in the official-site allowlist")
            requests += 1
            response = fetcher(url, hosts)
            source = add_source(
                root,
                response["raw"],
                {
                    "url": response["url"],
                    "requested_url": url,
                    "company": profile["company"]["id"],
                    "period": seed["period"],
                    "kind": document_kind,
                    "redirects": response["redirects"],
                    "completeness": "unknown",
                    "origin": "official_site_fetch",
                    **({"charset": response["charset"]} if response.get("charset") else {}),
                },
                response["format"],
            )
            parsed = extract(response["raw"], response["format"], response["url"], response.get("charset"))
            # Only actual source text may satisfy identity/quarter checks; cached display titles are generated.
            observed_title = parsed["title"]
            if source["title"] == source["id"]:
                source["title"] = (
                    f"{profile['company']['name']} {seed['period']['label']} {document_kind.replace('_', ' ')}"
                )
            published_at = publication(source["blocks"], parsed.get("publication_dates"), response["format"])
            own_publication = published_at
            if level == 0 and published_at:
                release_dates[seed["period"]["label"]] = published_at
            publication_basis = (
                "dated source text"
                if published_at
                else "linked earnings package release date; document-specific date unverified"
            )
            published_at = published_at or release_dates.get(seed["period"]["label"])
            title_matches = (
                not seed.get("title_pattern")
                or seed["title_pattern"].casefold()
                in (observed_title + " " + " ".join(b["text"][:1200] for b in source["blocks"][:3])).casefold()
            )
            identity_text = observed_title + " " + " ".join(b["text"] for b in source["blocks"][:80])
            names = [profile["company"]["name"].split()[0], *profile.get("aliases", [])]
            company_matches = any(re.search(r"\b" + re.escape(name) + r"\b", identity_text, re.I) for name in names)
            transcript_header_match = False
            if document_kind == "transcript" and not own_publication:
                header = " ".join(b["text"][:1800] for b in source["blocks"][:3])
                years = re.findall(r"20\d{2}", seed["period"]["label"])
                transcript_header_match = bool(
                    seed.get("title_pattern")
                    and seed["title_pattern"].casefold() in header.casefold()
                    and years
                    and years[0] in header
                )
            if document_kind == "transcript" and profile["company"]["id"] == "MSFT":
                fy, q = re.fullmatch(r"FY(\d+) Q([1-4])", seed["period"]["label"]).groups()
                word = {"1": "First", "2": "Second", "3": "Third", "4": "Fourth"}[q]
                transcript_header_match = bool(
                    re.search(rf"FY{fy[2:]}\s+{word}\s+Quarter", source["blocks"][0]["text"], re.I)
                )
                if not transcript_header_match:
                    raise EvidenceError("Transcript header does not match the expected fiscal year/quarter")
            source.update(
                {
                    "kind": document_kind,
                    "published_at": published_at,
                    "publication_basis": publication_basis,
                    "identity_check": company_matches,
                    "period_check": "transcript_header_match"
                    if transcript_header_match
                    else "seed_title_match"
                    if title_matches
                    else "requires_review",
                }
            )
            write_json(root / "sources" / f"{source['id']}.json", source)
            if not company_matches:
                raise EvidenceError("Expected company name was not found in the acquired document")
            if level == 0 and not title_matches:
                raise EvidenceError("Seed page title does not match its expected fiscal quarter")
            if (
                level == 0
                and published_at
                and not 0 <= (date.fromisoformat(published_at) - date.fromisoformat(seed["period"]["end"])).days <= 120
            ):
                raise EvidenceError("Earnings release date is inconsistent with its assigned financial period")
            if (
                level > 0
                and document_kind == "transcript"
                and release_dates.get(seed["period"]["label"])
                and (
                    (own_publication and own_publication != release_dates[seed["period"]["label"]])
                    or (not own_publication and not transcript_header_match)
                )
            ):
                raise EvidenceError("Transcript call date is missing or differs from the linked quarter's release date")
            entry = {
                k: source.get(k)
                for k in (
                    "id",
                    "url",
                    "title",
                    "period",
                    "kind",
                    "sha256",
                    "published_at",
                    "captured_at",
                    "completeness",
                    "period_check",
                    "publication_basis",
                )
            }
            if not any(d["id"] == source["id"] for d in pack["documents"]):
                pack["documents"].append(entry)
            pack["acquisition"].append(
                {"url": url, "status": "captured", "source_id": source["id"], "period": seed["period"]["label"]}
            )
            if level < depth:
                candidates = []
                for link in source["links"]:
                    if not RELEVANT.search(link["label"] + " " + link["url"]):
                        continue
                    if IRRELEVANT.search(link["label"] + " " + link["url"]):
                        continue
                    target = urldefrag(link["url"])[0]
                    # Inspect the official download URL, not the Office web viewer.
                    if urlsplit(target).hostname == "view.officeapps.live.com":
                        target = parse_qs(urlsplit(target).query).get("src", [target])[0]
                    # Keep HTML links in the quarter's earnings directory; allow official downloads.
                    seed_dir = seed["url"].rsplit("/", 1)[0].casefold()
                    if seed_dir not in target.casefold() and not re.search(
                        r"(?i)\.(pdf|txt|docx|pptx)(?:\?|$)|/is/content/", target
                    ):
                        continue
                    document_type = kind(link["label"], target)
                    if document_type == "presentation":
                        pack["candidate_links"].append(
                            {
                                "url": target,
                                "label": link["label"],
                                "period": seed["period"],
                                "status": "not_selected_presentation",
                            }
                        )
                        continue
                    priority = {"transcript": 0, "outlook": 1, "financial_results": 2}.get(document_type, 3)
                    candidates.append((priority, target, document_type, link["label"]))
                for _, target, dt, label in sorted(set(candidates)):
                    pack["candidate_links"].append(
                        {"url": target, "label": label, "period": seed["period"], "status": "discovered"}
                    )
                    if (
                        target.lower()
                        if urlsplit(target).hostname in {"www.microsoft.com", "microsoft.com"}
                        else target
                    ) not in seen:
                        queue.append((target, seed, level + 1, dt))
        except (ValueError, OSError, UnicodeError, ImportError) as e:
            pack["acquisition"].append(
                {"url": url, "status": "failed", "period": seed["period"]["label"], "message": str(e)[:500]}
            )
        write_json(root / "source-pack.json", pack)
    for seed in profile["seeds"]:
        docs = [d for d in pack["documents"] if d["period"] == seed["period"]]
        pack["coverage"].append(
            {
                "period": seed["period"],
                "documents": len(docs),
                "transcript": "captured" if any(d["kind"] == "transcript" for d in docs) else "not_acquired",
                "earnings_release": any(d["kind"] == "earnings_release" for d in docs),
            }
        )
    pack["requests"] = requests
    pack["status"] = "ready_for_extraction" if pack["documents"] else "blocked"
    if pack["truncated"]:
        pack["limitations"].append("Request budget exhausted; some discovered links were not acquired")
    if any(c["transcript"] != "captured" for c in pack["coverage"]):
        pack["limitations"].append(
            "At least one quarter lacks an acquired transcript; release-only coverage is not call coverage"
        )
    write_json(root / "source-pack.json", pack)
    return pack


def candidates(root, output, limit=250):
    """Shortlist passages for reading, not validated commitments or exhaustive extraction."""
    from .sources import load_source

    pack = read_json(Path(root) / "source-pack.json")
    passages = []
    forward = re.compile(r"(?i)\bexpect|\bguidance|\btarget|\bwill\b|\bplan\b|\banticipat|\boutlook|\bcommit|\baim\b")
    for doc in pack["documents"]:
        source = load_source(root, doc["id"])
        for idx, b in enumerate(source["blocks"]):
            if forward.search(b["text"]):
                passages.append(
                    {
                        "source_id": doc["id"],
                        "block_id": b["id"],
                        "text": b["text"],
                        "context": b["context"],
                        "period": doc["period"],
                        "before": source["blocks"][max(0, idx - 1) : idx],
                        "after": source["blocks"][idx + 1 : idx + 2],
                    }
                )
    result = {
        "schema_version": 1,
        "company": pack["company"],
        "passages": passages[:limit],
        "total_matches": len(passages),
        "truncated": len(passages) > limit,
        "note": "Lexical reading aid. Read full source blocks for omission checks and verify every proposed commitment.",
    }
    write_json(output, result)
    return result
