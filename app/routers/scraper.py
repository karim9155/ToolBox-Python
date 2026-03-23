"""
FastAPI router for the legal scraper service.
Endpoints under prefix /scrape for EUR-Lex and Legifrance.
"""

import logging
import time

from fastapi import APIRouter, HTTPException, Path
from app.schemas.scraper import SearchRequest, ScrapeResponse, DocumentDetail, LegalDocument
from app.services.legal_scraper_service import EurLexScraper, LegiFranceScraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scrape", tags=["Legal Scraper"])

_eurlex = EurLexScraper()
_legifrance = LegiFranceScraper()


# ---------------------------------------------------------------------------
# EUR-LEX endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/eurlex/search",
    response_model=ScrapeResponse,
    summary="Search EUR-Lex documents",
    description=(
        "Search the EUR-Lex database for EU legal documents. "
        "Uses a fast HTTP fetcher (no browser required) since EUR-Lex is publicly accessible."
    ),
)
def search_eurlex(request: SearchRequest) -> ScrapeResponse:
    """Search EUR-Lex for documents matching the given query."""
    logger.info("[EUR-Lex] 🔍 Search request — query=%r  max_results=%d  year_from=%s  language=%s", request.query, request.max_results, request.year_from, request.language or 'en')
    t0 = time.perf_counter()
    try:
        documents = _eurlex.search(request.query, request.max_results, request.year_from, request.language)
    except RuntimeError as e:
        elapsed = time.perf_counter() - t0
        logger.error("[EUR-Lex] ❌ Search failed after %.2fs — %s", elapsed, e)
        raise HTTPException(status_code=502, detail=str(e))

    elapsed = time.perf_counter() - t0
    logger.info("[EUR-Lex] ✅ Search done in %.2fs — %d/%d results returned", elapsed, len(documents), request.max_results)
    return ScrapeResponse(
        source="eurlex",
        query=request.query,
        total_found=len(documents),
        documents=documents,
    )


@router.get(
    "/eurlex/document/{celex}",
    response_model=DocumentDetail,
    summary="Fetch EUR-Lex document by CELEX number",
    description=(
        "Retrieve the full content of an EU legal document using its CELEX number. "
        "Example CELEX numbers: `32016R0679` (GDPR), `32018L2001` (Renewable Energy Directive)."
    ),
)
def get_eurlex_document(
    celex: str = Path(..., description="CELEX number, e.g. 32016R0679"),
) -> DocumentDetail:
    """Fetch a single EUR-Lex document by its CELEX identifier."""
    logger.info("[EUR-Lex] 📄 Document request — CELEX=%r", celex)
    t0 = time.perf_counter()
    try:
        doc = _eurlex.get_document(celex)
    except RuntimeError as e:
        elapsed = time.perf_counter() - t0
        logger.error("[EUR-Lex] ❌ Document fetch failed after %.2fs — %s", elapsed, e)
        raise HTTPException(status_code=502, detail=str(e))
    elapsed = time.perf_counter() - t0
    logger.info("[EUR-Lex] ✅ Document fetched in %.2fs — title=%r", elapsed, doc.title[:80] if doc.title else "(none)")
    return doc


# ---------------------------------------------------------------------------
# Legifrance endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/legifrance/search",
    response_model=ScrapeResponse,
    summary="Search Legifrance legal texts",
    description=(
        "Search the Legifrance database for French legal texts. "
        "Uses a **stealth headless browser** to bypass bot protection (Legifrance returns 403 to plain HTTP). "
        "Expect the first request to be slower (~10–30s) as the browser launches."
    ),
)
def search_legifrance(request: SearchRequest) -> ScrapeResponse:
    """Search Legifrance for legal texts matching the given query (stealth mode)."""
    logger.info("[Legifrance] 🔍 Search request — query=%r  max_results=%d", request.query, request.max_results)
    t0 = time.perf_counter()
    try:
        documents = _legifrance.search(request.query, request.max_results)
    except RuntimeError as e:
        elapsed = time.perf_counter() - t0
        logger.error("[Legifrance] ❌ Search failed after %.2fs — %s", elapsed, e)
        raise HTTPException(status_code=502, detail=str(e))

    elapsed = time.perf_counter() - t0
    logger.info("[Legifrance] ✅ Search done in %.2fs — %d/%d results returned", elapsed, len(documents), request.max_results)
    return ScrapeResponse(
        source="legifrance",
        query=request.query,
        total_found=len(documents),
        documents=documents,
    )


@router.get(
    "/legifrance/document/{doc_id}",
    response_model=DocumentDetail,
    summary="Fetch a Legifrance document by ID",
    description=(
        "Retrieve a French legal document by its Legifrance identifier. "
        "Supported prefixes: `LEGIARTI…` (article), `LEGITEXT…` (full law text), `JORFTEXT…` (JORF act). "
        "Example: `LEGITEXT000006070719` (Code Civil)."
    ),
)
def get_legifrance_document(
    doc_id: str = Path(
        ...,
        description="Legifrance document ID (LEGIARTI…, LEGITEXT…, or JORFTEXT…)",
    ),
) -> DocumentDetail:
    """Fetch a single Legifrance document by its identifier (stealth mode)."""
    logger.info("[Legifrance] 📄 Document request — doc_id=%r", doc_id)
    t0 = time.perf_counter()
    try:
        doc = _legifrance.get_document(doc_id)
    except RuntimeError as e:
        elapsed = time.perf_counter() - t0
        logger.error("[Legifrance] ❌ Document fetch failed after %.2fs — %s", elapsed, e)
        raise HTTPException(status_code=502, detail=str(e))
    elapsed = time.perf_counter() - t0
    logger.info("[Legifrance] ✅ Document fetched in %.2fs — title=%r", elapsed, doc.title[:80] if doc.title else "(none)")
    return doc
