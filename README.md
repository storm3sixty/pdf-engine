# PDF Engine (FastAPI)

A simple PDF processing service for print SaaS workflows.

It provides three processing modes:

- **watermark**: add diagonal semi-transparent text on every page.
- **numbering**: add page numbers (`bottom-center` or `top-right`).
- **booklet**: reorder pages into booklet sequence and pad blanks if needed.

## Tech Stack

- Python 3.11
- FastAPI
- uvicorn
- pypdf
- reportlab
- python-multipart

## Project Structure

```text
.
├── main.py
├── requirements.txt
├── README.md
├── uploads/
├── output/
└── temp/
```

## Run Locally

1. Create and activate a virtual environment:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the API server:

```bash
uvicorn main:app --reload
```

Server runs at: `http://127.0.0.1:8000`

## API Endpoints

### 1) Health Check

- **GET** `/health`
- Response:

```json
{ "ok": true }
```

### 2) Process PDF

- **POST** `/process`
- Content type: `multipart/form-data`
- Fields:
  - `file` (required): PDF file
  - `mode` (required): `watermark`, `numbering`, `booklet`
  - `watermark_text` (optional): watermark text, default `SAMPLE`
  - `number_position` (optional): `bottom-center` or `top-right`, default `bottom-center`

Success response example:

```json
{
  "success": true,
  "mode": "watermark",
  "original_filename": "input.pdf",
  "output_filename": "input_watermark_a1b2c3d4.pdf",
  "download_path": "/download/input_watermark_a1b2c3d4.pdf"
}
```

### 3) Download Processed PDF

- **GET** `/download/{filename}`
- Returns PDF file if found, otherwise `404`.

## Example cURL Commands

### Health

```bash
curl http://127.0.0.1:8000/health
```

### Watermark

```bash
curl -X POST "http://127.0.0.1:8000/process" \
  -F "file=@sample.pdf" \
  -F "mode=watermark" \
  -F "watermark_text=PROOF"
```

### Numbering (top-right)

```bash
curl -X POST "http://127.0.0.1:8000/process" \
  -F "file=@sample.pdf" \
  -F "mode=numbering" \
  -F "number_position=top-right"
```

### Booklet

```bash
curl -X POST "http://127.0.0.1:8000/process" \
  -F "file=@sample.pdf" \
  -F "mode=booklet"
```

After processing, use the returned `download_path`:

```bash
curl -OJ "http://127.0.0.1:8000/download/<output_filename>.pdf"
```

## Notes

- Uploaded originals are saved in `uploads/`.
- Processed files are saved in `output/`.
- Temporary workspace folder `temp/` is created for future use.
- This version does **not** include auth, databases, Adobe/Fiery integrations, or 2-up/4-up imposition.
