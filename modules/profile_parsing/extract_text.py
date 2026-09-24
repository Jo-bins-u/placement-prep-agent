"""
Step 1 of the pipeline: get raw text out of an uploaded resume file.
Handles PDF and DOCX — the two formats you're most likely to see (FR1.1).
"""

from pathlib import Path


def extract_text(filepath: str) -> str:
    """Return raw text from a .pdf or .docx resume. Raises ValueError
    for unsupported formats so the caller can show a clear error to
    the user rather than failing silently."""
    ext = Path(filepath).suffix.lower()

    if ext == ".pdf":
        return _extract_pdf(filepath)
    elif ext == ".docx":
        return _extract_docx(filepath)
    else:
        raise ValueError(
            f"Unsupported resume format: '{ext}'. Only .pdf and .docx are supported."
        )


def _extract_pdf(filepath: str) -> str:
    import pdfplumber

    text_parts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
    return "\n".join(text_parts)


def _extract_docx(filepath: str) -> str:
    import docx

    doc = docx.Document(filepath)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
