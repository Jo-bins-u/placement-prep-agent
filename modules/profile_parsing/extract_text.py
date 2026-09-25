"""
Step 1 of the pipeline: get raw text out of an uploaded resume file.
Handles PDF and DOCX — the two formats you're most likely to see (FR1.1).
"""

from pathlib import Path

# Limits for untrusted files (the parser also runs in a time/memory-limited child process).
MAX_PDF_PAGES = 10
MAX_TEXT_CHARS = 200_000
MAX_DOCX_UNCOMPRESSED = 30 * 1024 * 1024   # total size of the .docx zip entries
MAX_DOCX_ENTRIES = 500


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

    def read(**kwargs):
        text_parts = []
        total = 0
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages[:MAX_PDF_PAGES]:
                page_text = page.extract_text(**kwargs)
                if page_text:
                    text_parts.append(page_text)
                    total += len(page_text)
                    if total > MAX_TEXT_CHARS:
                        break
        return "\n".join(text_parts)[:MAX_TEXT_CHARS]

    text = read()
    # Some PDFs (tightly kerned templates) come out with spaces missing, in the
    # whole file or just a few lines: "Designedandimplementedasecurebackend".
    # Re-read with a tighter gap threshold and keep it if it un-glues words.
    glued = _glued_words(text)
    if glued:
        tight = read(x_tolerance=1.5)
        if _glued_words(tight) < glued:
            return tight
    return text


def _glued_words(text: str) -> int:
    """Count implausibly long letter runs (real words rarely exceed 18 letters)."""
    import re
    return sum(1 for w in re.findall(r"[A-Za-z]{19,}", text))


def _extract_docx(filepath: str) -> str:
    import zipfile

    import docx

    # Refuse zip bombs before python-docx inflates anything: check the declared sizes.
    with zipfile.ZipFile(filepath) as archive:
        entries = archive.infolist()
        if len(entries) > MAX_DOCX_ENTRIES or sum(e.file_size for e in entries) > MAX_DOCX_UNCOMPRESSED:
            raise ValueError("This .docx expands to more data than a resume should.")
    doc = docx.Document(filepath)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())[:MAX_TEXT_CHARS]
