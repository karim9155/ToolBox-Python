import os
import shutil
import subprocess
from typing import Optional


class ConversionError(Exception):
    """Raised when a document cannot be converted to PDF."""


def _convert_with_libreoffice(input_path: str, output_dir: str) -> str:
    libreoffice_cmd = shutil.which("soffice")
    if not libreoffice_cmd:
        libreoffice_cmd = shutil.which("libreoffice")

    if not libreoffice_cmd:
        raise ConversionError("LibreOffice CLI is not available on PATH")

    command = [
        libreoffice_cmd,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        output_dir,
        input_path,
    ]

    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or completed.stdout.strip()
        raise ConversionError(f"LibreOffice conversion failed: {stderr}")

    basename = os.path.splitext(os.path.basename(input_path))[0]
    output_pdf = os.path.join(output_dir, f"{basename}.pdf")
    if not os.path.exists(output_pdf):
        raise ConversionError("LibreOffice did not produce a PDF output file")

    return output_pdf


def _convert_with_windows_com(input_path: str, output_pdf: str, extension: str) -> str:
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise ConversionError("Windows COM conversion is unavailable (pywin32 not installed)") from exc

    extension = extension.lower()

    if extension in {".doc", ".docx"}:
        pythoncom.CoInitialize()
        word_app = None
        doc = None
        try:
            word_app = win32com.client.Dispatch("Word.Application")
            word_app.Visible = False
            doc = word_app.Documents.Open(input_path)
            # 17 == wdExportFormatPDF
            doc.ExportAsFixedFormat(output_pdf, 17)
        except Exception as exc:
            raise ConversionError(f"Word COM conversion failed: {exc}") from exc
        finally:
            if doc is not None:
                doc.Close(False)
            if word_app is not None:
                word_app.Quit()
            pythoncom.CoUninitialize()

    elif extension in {".ppt", ".pptx"}:
        pythoncom.CoInitialize()
        powerpoint_app = None
        presentation = None
        try:
            powerpoint_app = win32com.client.Dispatch("PowerPoint.Application")
            presentation = powerpoint_app.Presentations.Open(input_path, WithWindow=False)
            # 32 == ppSaveAsPDF
            presentation.SaveAs(output_pdf, 32)
        except Exception as exc:
            raise ConversionError(f"PowerPoint COM conversion failed: {exc}") from exc
        finally:
            if presentation is not None:
                presentation.Close()
            if powerpoint_app is not None:
                powerpoint_app.Quit()
            pythoncom.CoUninitialize()
    else:
        raise ConversionError(f"Unsupported extension for COM conversion: {extension}")

    if not os.path.exists(output_pdf):
        raise ConversionError("Windows COM did not produce a PDF output file")

    return output_pdf


def convert_document_to_pdf(input_path: str, output_dir: str, extension: Optional[str] = None) -> str:
    """Convert DOC/DOCX/PPT/PPTX to PDF, trying LibreOffice first then Windows COM fallback."""
    if not extension:
        extension = os.path.splitext(input_path)[1].lower()

    if extension == ".pdf":
        return input_path

    output_pdf = os.path.join(output_dir, "converted.pdf")

    libreoffice_error = None
    try:
        return _convert_with_libreoffice(input_path, output_dir)
    except ConversionError as exc:
        libreoffice_error = str(exc)

    try:
        return _convert_with_windows_com(input_path, output_pdf, extension)
    except ConversionError as exc:
        raise ConversionError(
            "Document conversion failed. "
            f"LibreOffice error: {libreoffice_error}. "
            f"Windows COM error: {exc}"
        ) from exc
