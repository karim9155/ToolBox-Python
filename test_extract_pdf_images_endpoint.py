from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import pdf as pdf_router
from app.utils.document_converter import ConversionError


app = FastAPI()
app.include_router(pdf_router.router)
client = TestClient(app)


def _multipart(filename: str, payload: bytes = b"dummy"):
    return {"file": (filename, payload, "application/octet-stream")}


def test_extract_pdf_images_accepts_pdf_without_conversion(monkeypatch):
    seen = {}

    def fake_extract(path, output_dir=None, return_base64=False):
        seen["path"] = path
        seen["return_base64"] = return_base64
        return {"success": True, "totalImages": 0, "totalPages": 0, "images": [], "texts": []}

    def fake_convert(*args, **kwargs):
        raise AssertionError("Conversion should not be called for .pdf files")

    monkeypatch.setattr(pdf_router, "extract_images_from_pdf", fake_extract)
    monkeypatch.setattr(pdf_router, "convert_document_to_pdf", fake_convert)

    response = client.post("/extract/pdf-images?include_base64=false", files=_multipart("sample.pdf", b"%PDF-1.4"))

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert seen["path"].endswith(".pdf")
    assert seen["return_base64"] is False


def test_extract_pdf_images_converts_docx_before_extraction(monkeypatch):
    seen = {}

    def fake_convert(path, output_dir, extension=None):
        seen["input_path"] = path
        seen["extension"] = extension
        return f"{output_dir}/converted-from-docx.pdf"

    def fake_extract(path, output_dir=None, return_base64=False):
        seen["extract_path"] = path
        seen["return_base64"] = return_base64
        return {"success": True, "totalImages": 1, "totalPages": 1, "images": [], "texts": []}

    monkeypatch.setattr(pdf_router, "convert_document_to_pdf", fake_convert)
    monkeypatch.setattr(pdf_router, "extract_images_from_pdf", fake_extract)

    response = client.post("/extract/pdf-images", files=_multipart("deck.docx"))

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert seen["extension"] == ".docx"
    assert seen["extract_path"].endswith("converted-from-docx.pdf")
    assert seen["return_base64"] is True


def test_extract_pdf_images_rejects_unsupported_extension():
    response = client.post("/extract/pdf-images", files=_multipart("notes.txt", b"hello"))

    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_extract_pdf_images_returns_422_when_conversion_fails(monkeypatch):
    def fake_convert(*args, **kwargs):
        raise ConversionError("converter unavailable")

    monkeypatch.setattr(pdf_router, "convert_document_to_pdf", fake_convert)

    response = client.post("/extract/pdf-images", files=_multipart("slides.pptx"))

    assert response.status_code == 422
    assert "converter unavailable" in response.json()["detail"]
