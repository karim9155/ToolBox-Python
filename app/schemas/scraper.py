from pydantic import BaseModel, Field
from typing import Optional


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search keywords")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of results to return")
    year_from: Optional[int] = Field(None, ge=1900, le=2200, description="Only return documents from this year onwards. Use 2023 to skip pre-training-cutoff documents.")
    language: Optional[str] = Field(None, description="Language code for EUR-Lex search (en, fr, de…). Defaults to en.")


class LegalDocument(BaseModel):
    title: str
    url: str
    date: Optional[str] = None
    doc_type: Optional[str] = None
    source: str  # "eurlex" or "legifrance"
    celex_or_id: Optional[str] = None
    summary: Optional[str] = None


class ScrapeResponse(BaseModel):
    source: str
    query: str
    total_found: int
    documents: list[LegalDocument]


class DocumentDetail(BaseModel):
    title: str
    url: str
    source: str
    celex_or_id: Optional[str] = None
    date: Optional[str] = None
    doc_type: Optional[str] = None
    body_text: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
