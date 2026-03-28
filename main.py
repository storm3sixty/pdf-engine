"""FastAPI PDF processing service.

This service accepts uploaded PDFs and can:
1) add a text watermark,
2) add page numbers, or
3) reorder pages into booklet order.
"""

from __future__ import annotations

import re
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.pdfgen import canvas

# --- App and paths ---------------------------------------------------------

app = FastAPI(title="PDF Engine", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp"


# Create required folders on startup and when module is imported.
for directory in (UPLOAD_DIR, OUTPUT_DIR, TEMP_DIR):
    directory.mkdir(parents=True, exist_ok=True)


# --- Utility helpers -------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Create a safe filename stem (letters, numbers, dot, dash, underscore)."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return cleaned[:120] if cleaned else "file"


def make_output_filename(original_name: str, mode: str) -> str:
    """Generate a unique output filename for processed files."""
    stem = Path(original_name).stem or "document"
    safe_stem = sanitize_filename(stem)
    suffix = uuid.uuid4().hex[:8]
    return f"{safe_stem}_{mode}_{suffix}.pdf"


def create_watermark_overlay(width: float, height: float, text: str) -> BytesIO:
    """Create a one-page watermark overlay PDF in memory."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))

    # Semi-transparent gray text, diagonally across the page.
    c.saveState()
    c.translate(width / 2, height / 2)
    c.rotate(45)
    c.setFillColor(Color(0.5, 0.5, 0.5, alpha=0.25))
    c.setFont("Helvetica-Bold", max(24, int(min(width, height) * 0.08)))
    c.drawCentredString(0, 0, text)
    c.restoreState()

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def create_number_overlay(
    width: float,
    height: float,
    page_number: int,
    position: str,
) -> BytesIO:
    """Create a one-page page-number overlay PDF in memory."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    c.setFont("Helvetica", 11)

    label = str(page_number)

    if position == "top-right":
        x, y = width - 36, height - 24
        c.drawRightString(x, y, label)
    else:
        # Default: bottom-center
        x, y = width / 2, 20
        c.drawCentredString(x, y, label)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def process_watermark(input_path: Path, output_path: Path, watermark_text: str) -> None:
    """Apply watermark text to every page in the PDF."""
    reader = PdfReader(str(input_path))
    writer = PdfWriter()

    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        overlay_pdf = create_watermark_overlay(width, height, watermark_text)
        overlay_page = PdfReader(overlay_pdf).pages[0]

        page.merge_page(overlay_page)
        writer.add_page(page)

    with output_path.open("wb") as f:
        writer.write(f)


def process_numbering(input_path: Path, output_path: Path, number_position: str) -> None:
    """Add page numbers to every page in the PDF."""
    reader = PdfReader(str(input_path))
    writer = PdfWriter()

    for idx, page in enumerate(reader.pages, start=1):
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)

        overlay_pdf = create_number_overlay(width, height, idx, number_position)
        overlay_page = PdfReader(overlay_pdf).pages[0]

        page.merge_page(overlay_page)
        writer.add_page(page)

    with output_path.open("wb") as f:
        writer.write(f)


def process_booklet(input_path: Path, output_path: Path) -> None:
    """Reorder pages into booklet sequence and pad with blanks to /4 pages."""
    reader = PdfReader(str(input_path))
    writer = PdfWriter()

    pages = list(reader.pages)
    total = len(pages)

    if total == 0:
        # Produce an empty output for an empty input.
        with output_path.open("wb") as f:
            writer.write(f)
        return

    # Use first page size for blank padding pages.
    base_width = float(pages[0].mediabox.width)
    base_height = float(pages[0].mediabox.height)

    # Pad until total is divisible by 4.
    while len(pages) % 4 != 0:
        blank = writer.add_blank_page(width=base_width, height=base_height)
        pages.append(blank)

    n = len(pages)
    ordered_pages = []

    # For each sheet group in booklet ordering:
    # [last, first, second, second-last], then continue inward.
    for i in range(n // 4):
        ordered_pages.extend(
            [
                pages[n - 1 - (2 * i)],
                pages[2 * i],
                pages[(2 * i) + 1],
                pages[n - 2 - (2 * i)],
            ]
        )

    for page in ordered_pages:
        writer.add_page(page)

    with output_path.open("wb") as f:
        writer.write(f)


def is_pdf_upload(upload: UploadFile) -> bool:
    """Basic PDF validation based on metadata and extension."""
    content_type_ok = upload.content_type in {"application/pdf", "application/x-pdf"}
    extension_ok = upload.filename.lower().endswith(".pdf") if upload.filename else False
    return content_type_ok or extension_ok


# --- API endpoints ---------------------------------------------------------

@app.get("/health")
def health() -> dict[str, bool]:
    """Health check endpoint."""
    return {"ok": True}


@app.post("/process")
async def process_pdf(
    file: UploadFile = File(...),
    mode: str = Form(...),
    watermark_text: str | None = Form(default=None),
    number_position: str | None = Form(default="bottom-center"),
) -> dict[str, str | bool]:
    """Process uploaded PDF using watermark, numbering, or booklet mode."""
    allowed_modes = {"watermark", "numbering", "booklet"}
    if mode not in allowed_modes:
        raise HTTPException(status_code=400, detail="Invalid mode")

    if not file.filename:
        raise HTTPException(status_code=400, detail="File must have a filename")

    if not is_pdf_upload(file):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    safe_input_name = sanitize_filename(Path(file.filename).name)
    input_path = UPLOAD_DIR / f"{uuid.uuid4().hex[:8]}_{safe_input_name}"
    output_filename = make_output_filename(file.filename, mode)
    output_path = OUTPUT_DIR / output_filename

    # Save upload to disk.
    data = await file.read()
    input_path.write_bytes(data)

    # Validate by actually parsing with pypdf.
    try:
        PdfReader(str(input_path))
    except Exception as exc:  # noqa: BLE001 - Keep error handling beginner-friendly.
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PDF") from exc

    # Optional field validation/defaults.
    effective_watermark = watermark_text or "SAMPLE"
    effective_position = number_position or "bottom-center"
    if effective_position not in {"bottom-center", "top-right"}:
        raise HTTPException(status_code=400, detail="Invalid number_position")

    # Route to processing mode.
    if mode == "watermark":
        process_watermark(input_path, output_path, effective_watermark)
    elif mode == "numbering":
        process_numbering(input_path, output_path, effective_position)
    else:
        process_booklet(input_path, output_path)

    return {
        "success": True,
        "mode": mode,
        "original_filename": file.filename,
        "output_filename": output_filename,
        "download_path": f"/download/{output_filename}",
    }


@app.get("/download/{filename}")
def download_file(filename: str) -> FileResponse:
    """Download a processed file by filename."""
    safe_name = sanitize_filename(filename)
    target = OUTPUT_DIR / safe_name

    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(path=target, media_type="application/pdf", filename=safe_name)
