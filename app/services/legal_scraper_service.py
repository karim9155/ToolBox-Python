"""
Legal scraper service using Scrapling.

- EurLexScraper: uses fast HTTP Fetcher (no browser needed, site is public)
- LegiFranceScraper: uses StealthyFetcher (headless browser) to bypass bot protection
"""

import logging
from typing import Optional
from urllib.parse import urlencode, quote

from app.schemas.scraper import LegalDocument, DocumentDetail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# EUR-LEX
# ---------------------------------------------------------------------------

class EurLexScraper:
    BASE_URL = "https://eur-lex.europa.eu"
    SEARCH_URL = f"{BASE_URL}/search.html"
    LEGAL_CONTENT_URL = f"{BASE_URL}/legal-content/EN/TXT/"

    def search(self, query: str, max_results: int = 10) -> list[LegalDocument]:
        """Search EUR-Lex for documents matching *query*."""
        from scrapling.fetchers import Fetcher

        params = {
            "scope": "EURLEX",
            "type": "quick",
            "lang": "en",
            "text": query,
        }
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        logger.info(f"[EUR-Lex] Searching: {url}")

        try:
            page = Fetcher.get(url, stealthy_headers=True, timeout=30)
        except Exception as e:
            logger.error(f"[EUR-Lex] Fetch error: {e}")
            raise RuntimeError(f"EUR-Lex search failed: {e}") from e

        documents: list[LegalDocument] = []

        # Each result is inside a <div class="SearchResult"> container
        result_items = page.css(".SearchResult")
        if not result_items:
            # fallback: try list items inside results panel
            result_items = page.css("#results .result-item, .results-by-act li")

        for item in result_items[:max_results]:
            # Title: EUR-Lex puts the title text inside <a class="title">,
            # but the text itself is split into <em> fragments (matched keywords).
            # Use get_all_text() to join them, or fall back to the `name` attribute
            # which holds the canonical document URL including the full title context.
            link_el = item.css("a.title")
            if not link_el:
                link_el = item.css("a[href*='legal-content']")
            if not link_el:
                link_el = item.css("a")
            if not link_el:
                continue

            a = link_el[0]
            href = a.attrib.get("href", "")
            if href and not href.startswith("http"):
                # href is relative like "./legal-content/..." — resolve against base
                if href.startswith("./"):
                    href = self.BASE_URL + href[1:]  # strips leading dot only
                else:
                    href = self.BASE_URL + "/" + href.lstrip("/")

            # Title: EUR-Lex search results only highlight query-matching keyword
            # fragments inside <em> tags — the full title is NOT in the search HTML.
            # Build a best-effort title from the OJ reference <i> element, which
            # contains the official journal citation (e.g. "OJ L 338, 13.11.2004").
            oj_el = item.css("i")
            oj_text = ""
            for el in oj_el:
                t = el.get_all_text().strip()
                if t.startswith("OJ"):
                    oj_text = t.split("\n")[0].strip()  # first line only
                    break
            # Fall back to joining the em fragments (partial keyword match)
            em_text = a.get_all_text().strip().replace("\n", " ").strip()
            title = oj_text or em_text or href

            # Date and doc_type live in dt/dd pairs inside the result.
            # EUR-Lex wraps the label text in <em>, so use get_all_text().
            date = None
            doc_type = None
            dts = item.css("dt")
            dds = item.css("dd")
            for dt, dd in zip(dts, dds):
                label = dt.get_all_text().strip().rstrip(":")
                value = dd.get_all_text().strip()
                if "Date of document" in label:
                    # Strip any trailing annotation (e.g. "; Date of signature")
                    date = value.split(";")[0].strip() or None
                elif label == "Form":
                    doc_type = value or None

            # CELEX from URL
            celex = None
            if "CELEX:" in href:
                celex = href.split("CELEX:")[-1].split("&")[0].split("?")[0]
            elif "uri=CELEX:" in href:
                celex = href.split("uri=CELEX:")[-1].split("&")[0]

            # Also try the <dd> for CELEX number directly (most reliable)
            if not celex:
                for dt, dd in zip(dts, dds):
                    if "CELEX" in dt.get_all_text():
                        celex = dd.get_all_text().strip() or None
                        break

            # Summary: not present in EUR-Lex search results HTML; leave empty
            summary = None

            if title:
                documents.append(LegalDocument(
                    title=title,
                    url=href,
                    date=date,
                    doc_type=doc_type,
                    source="eurlex",
                    celex_or_id=celex,
                    summary=summary,
                ))

        logger.info(f"[EUR-Lex] Found {len(documents)} results")
        return documents

    def get_document(self, celex: str) -> DocumentDetail:
        """Fetch a single EUR-Lex document by CELEX number."""
        from scrapling.fetchers import Fetcher

        url = f"{self.BASE_URL}/legal-content/AUTO/?uri=CELEX:{quote(celex)}"
        logger.info(f"[EUR-Lex] Fetching document: {url}")

        try:
            page = Fetcher.get(url, stealthy_headers=True, timeout=30)
        except Exception as e:
            logger.error(f"[EUR-Lex] Fetch error: {e}")
            raise RuntimeError(f"EUR-Lex document fetch failed: {e}") from e

        # Title: prefer the <title> tag on EUR-Lex TXT pages; it reads
        # "Regulation - 10/2011 - EN - EUR-Lex" which is decent.
        # Also try the document's own heading.
        title_el = page.css("h1#translationTitle, h1.eli-title, h2.eli-title")
        if title_el:
            title = title_el[0].get_all_text().strip()
        else:
            # Fall back to <title> tag (browser page title)
            page_title_el = page.css("title")
            title = page_title_el[0].text.strip() if page_title_el else f"CELEX:{celex}"

        # Main body text: #document1 is the primary content div on TXT pages
        body_el = page.css("#document1, .tabContent, .eli-main-title + div")
        body_text: Optional[str] = None
        if body_el:
            body_text = "\n".join(
                el.get_all_text().strip()
                for el in body_el[0].css("p, li, h2, h3")
                if el.get_all_text()
            ) or body_el[0].get_all_text().strip()

        # Metadata: EUR-Lex document pages don't have a metadata table on the
        # /TXT/ URL — metadata lives on the search results page via dt/dd pairs.
        # Parse it from the page using the same dt/dd pattern.
        metadata: dict = {}
        dts = page.css("dt")
        dds = page.css("dd")
        for dt, dd in zip(dts, dds):
            key = (dt.text or "").strip().rstrip(":")
            val = (dd.text or "").strip()
            if key and val:
                metadata[key] = val

        # Date and doc_type from metadata if available
        date = metadata.get("Date of document") or metadata.get("Date")
        doc_type = metadata.get("Form") or metadata.get("Type")

        return DocumentDetail(
            title=title,
            url=page.url or url,
            source="eurlex",
            celex_or_id=celex,
            date=date,
            doc_type=doc_type,
            body_text=body_text,
            metadata=metadata,
        )


# ---------------------------------------------------------------------------
# LEGIFRANCE
# ---------------------------------------------------------------------------

class LegiFranceScraper:
    BASE_URL = "https://www.legifrance.gouv.fr"
    SEARCH_URL = f"{BASE_URL}/search/all"

    def search(self, query: str, max_results: int = 10) -> list[LegalDocument]:
        """
        Search Legifrance using StealthyFetcher (headless browser) because
        the site returns 403 to plain HTTP clients / bots.
        """
        from scrapling.fetchers import StealthyFetcher

        params = {
            "tab_selection": "all",
            "query": query,
            "searchField": "ALL",
            "typePagination": "DEFAULT",
            "sortValue": "PERTINENCE",
            "pageSize": str(min(max_results, 25)),
            "page": "1",
            "init": "true",
        }
        url = f"{self.SEARCH_URL}?{urlencode(params)}"
        logger.info(f"[Legifrance] Searching: {url}")

        try:
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                disable_resources=False,
                network_idle=True,
                timeout=60_000,
            )
        except Exception as e:
            logger.error(f"[Legifrance] Fetch error: {e}")
            raise RuntimeError(f"Legifrance search failed: {e}") from e

        documents: list[LegalDocument] = []

        # Results are in <article class="result-item"> containers
        result_items = page.css(".result-item")
        if not result_items:
            result_items = page.css("article.result, .search-result-item")

        for item in result_items[:max_results]:
            # Title: <h2 class="title-result-item"> — contains full title text
            title_el = item.css("h2.title-result-item, h2.title, h3.title")
            if not title_el:
                continue
            title = title_el[0].get_all_text().strip().replace("\n", " ").strip()
            if not title:
                continue

            # Link: first <a> inside the result item leads to the document
            link_el = item.css("a")
            href = ""
            if link_el:
                href = link_el[0].attrib.get("href", "")
                if href and not href.startswith("http"):
                    href = self.BASE_URL + href
                # Strip search query params from URL — keep only the path
                if "?" in href:
                    href = href.split("?")[0]

            # Extract legifrance doc ID from URL path segments only (no query string)
            doc_id = None
            for segment in href.split("/"):
                if (segment.startswith("LEGIARTI") or segment.startswith("LEGITEXT")
                        or segment.startswith("JORFTEXT")):
                    doc_id = segment.split("?")[0]  # extra safety strip
                    break

            # Summary: .teaser holds a text excerpt
            teaser_el = item.css(".teaser")
            summary = teaser_el[0].get_all_text().strip() if teaser_el else None

            # Date and doc_type: embedded in title text (e.g. "Décret n° 2024-372 du 23 avril 2024")
            # No dedicated date element — leave as None; agent can parse from title
            date = None
            doc_type = None
            # Infer doc_type from title prefix
            title_lower = title.lower()
            if title_lower.startswith("décret") or title_lower.startswith("decret"):
                doc_type = "Décret"
            elif title_lower.startswith("arrêté") or title_lower.startswith("arrete"):
                doc_type = "Arrêté"
            elif title_lower.startswith("ordonnance"):
                doc_type = "Ordonnance"
            elif title_lower.startswith("loi"):
                doc_type = "Loi"
            elif title_lower.startswith("code"):
                doc_type = "Code"
            elif title_lower.startswith("délibération") or title_lower.startswith("deliberation"):
                doc_type = "Délibération"
            elif title_lower.startswith("circulaire"):
                doc_type = "Circulaire"

            documents.append(LegalDocument(
                title=title,
                url=href,
                date=date,
                doc_type=doc_type,
                source="legifrance",
                celex_or_id=doc_id,
                summary=summary,
            ))

        logger.info(f"[Legifrance] Found {len(documents)} results")
        return documents

    def get_document(self, doc_id: str) -> DocumentDetail:
        """
        Fetch a Legifrance document by its ID (LEGIARTI…, LEGITEXT…, or JORFTEXT…).
        Routes to the correct URL based on the ID prefix.
        """
        from scrapling.fetchers import StealthyFetcher

        # Determine the URL pattern from the ID prefix
        if doc_id.startswith("LEGIARTI"):
            url = f"{self.BASE_URL}/codes/article_lc/{doc_id}"
        elif doc_id.startswith("LEGITEXT"):
            url = f"{self.BASE_URL}/codes/texte_lc/{doc_id}"
        elif doc_id.startswith("JORFTEXT"):
            url = f"{self.BASE_URL}/jorf/id/{doc_id}"
        else:
            url = f"{self.BASE_URL}/loda/id/{doc_id}"

        logger.info(f"[Legifrance] Fetching document: {url}")

        try:
            page = StealthyFetcher.fetch(
                url,
                headless=True,
                disable_resources=False,
                network_idle=True,
                timeout=60_000,
            )
        except Exception as e:
            logger.error(f"[Legifrance] Fetch error: {e}")
            raise RuntimeError(f"Legifrance document fetch failed: {e}") from e

        # Title: <h1> is the most reliable selector on all Legifrance page types
        title_el = page.css("h1")
        title = title_el[0].get_all_text().strip() if title_el else doc_id

        # Body text strategy:
        # - JORF/LODA modifier decrees: tiny body (they only reference Code articles).
        #   Use .main-col which includes the modifier summary + article structure.
        # - LEGITEXT (codes): .page-content has the table of contents / article list.
        # - Self-contained arrêtés: .main-col has full article prose.
        body_text: Optional[str] = None
        main_col = page.css(".main-col")
        if main_col:
            body_text = main_col[0].get_all_text().strip()
        if not body_text:
            page_content = page.css(".page-content")
            if page_content:
                body_text = page_content[0].get_all_text().strip()

        # Metadata: extract NOR, ELI, JORF reference from .jo-subtitle / .top-page-jo
        metadata: dict = {}
        jo_subtitle = page.css(".jo-subtitle, .top-page-jo")
        if jo_subtitle:
            for line in jo_subtitle[0].get_all_text().splitlines():
                line = line.strip()
                if line.startswith("NOR"):
                    metadata["NOR"] = line.replace("NOR :", "").replace("NOR:", "").strip()
                elif line.startswith("ELI"):
                    metadata["ELI"] = line.replace("ELI :", "").replace("ELI:", "").strip()
                elif line.startswith("JORF"):
                    metadata["JORF"] = line.strip()
                elif line.startswith("Alias"):
                    metadata["Alias"] = line.replace("Alias :", "").replace("Alias:", "").strip()

        # For modifier decrees: extract the IDs of Code articles they reference.
        # Legifrance puts LEGIARTI IDs as query params: idArticle=LEGIARTI...
        # and LEGITEXT IDs as cidTexte=LEGITEXT... — parse both.
        import re as _re
        referenced_ids: list[str] = []
        seen_ids: set[str] = set()
        for a in page.css("a[href]"):
            href_a = a.attrib.get("href", "")
            for match in _re.finditer(r'(LEGIARTI\w+|LEGITEXT\w+)', href_a):
                id_val = match.group(1)
                if id_val not in seen_ids:
                    seen_ids.add(id_val)
                    referenced_ids.append(id_val)
        if referenced_ids:
            metadata["referenced_code_articles"] = referenced_ids

        date_el = page.css("time, .date-vigueur, .date-signature, .publication-date")
        date = date_el[0].get_all_text().strip() if date_el else None

        nature_el = page.css(".nature, .typeActe, .type-acte")
        doc_type = nature_el[0].get_all_text().strip() if nature_el else None

        return DocumentDetail(
            title=title,
            url=page.url or url,
            source="legifrance",
            celex_or_id=doc_id,
            date=date,
            doc_type=doc_type,
            body_text=body_text,
            metadata=metadata,
        )
