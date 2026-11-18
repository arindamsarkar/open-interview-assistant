from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


def read_cv(filename):
    path = Path(filename)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from pypdf import PdfReader
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    elif suffix == ".docx":
        with ZipFile(path) as archive:
            root = ElementTree.fromstring(archive.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        text = "\n".join("".join(t.text or "" for t in p.iter(ns + "t"))
                         for p in root.iter(ns + "p"))
    elif suffix == ".txt":
        text = path.read_text(encoding="utf-8-sig")
    else:
        raise ValueError("Choose a PDF, DOCX or UTF-8 TXT file.")
    text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not text:
        raise ValueError("No readable text found. Try a DOCX or text-based PDF.")
    return text
