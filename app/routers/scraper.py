"""
FastAPI router for the legal scraper service.
Endpoints under prefix /scrape for EUR-Lex and Legifrance.
"""

from fastapi import APIRouter, HTTPException, Path
from app.schemas.scraper import SearchRequest, ScrapeResponse, DocumentDetail, LegalDocument
from app.services.legal_scraper_service import EurLexScraper, LegiFranceScraper

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
    try:
        documents = _eurlex.search(request.query, request.max_results)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

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
    try:
        return _eurlex.get_document(celex)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))


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
    try:
        documents = _legifrance.search(request.query, request.max_results)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

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
    try:
        return _legifrance.get_document(doc_id)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
