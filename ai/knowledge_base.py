"""
knowledge_base.py — PDF ingestion, chunking, and indexing pipeline

Usage:
    python knowledge_base.py                          # index all PDFs in ./knowledge_base_docs/
    python knowledge_base.py --file path/to/doc.pdf  # index a single file
    python knowledge_base.py --stats                 # print DB stats
    python knowledge_base.py --reset                 # wipe and re-index
"""

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")

DOCS_DIR    = Path("./knowledge_base_docs")
CHUNK_SIZE  = 200    # target tokens per chunk (words as proxy)
CHUNK_OVER  = 40     # overlap words between chunks


# ── PDF extraction ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> list[dict]:
    """
    Extract text page-by-page from a PDF.
    Returns list of { page_number, text }.
    Falls back to pdfminer if PyMuPDF is unavailable.
    """
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(str(pdf_path))
        pages = []
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append({"page_number": i + 1, "text": text})
        doc.close()
        logger.info(f"Extracted {len(pages)} pages from {pdf_path.name} (PyMuPDF)")
        return pages

    except ImportError:
        logger.warning("PyMuPDF not found — falling back to pdfminer.six")
        try:
            from pdfminer.high_level import extract_pages
            from pdfminer.layout import LTTextContainer
            pages = []
            for page_num, layout in enumerate(extract_pages(str(pdf_path)), start=1):
                text = "\n".join(
                    el.get_text()
                    for el in layout
                    if isinstance(el, LTTextContainer)
                ).strip()
                if text:
                    pages.append({"page_number": page_num, "text": text})
            logger.info(f"Extracted {len(pages)} pages from {pdf_path.name} (pdfminer)")
            return pages
        except ImportError:
            logger.error("Neither PyMuPDF nor pdfminer.six is installed.")
            logger.error("Run: pip install pymupdf  OR  pip install pdfminer.six")
            sys.exit(1)


# ── Text cleaning ──────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove headers/footers noise, normalise whitespace."""
    # Remove common PDF artefacts
    text = re.sub(r"\x0c", " ", text)            # form feed
    text = re.sub(r"[ \t]+", " ", text)          # compress spaces
    text = re.sub(r"\n{3,}", "\n\n", text)       # max two blank lines
    text = re.sub(r"-\n", "", text)              # hyphenated line breaks
    return text.strip()


# ── Chunking ───────────────────────────────────────────────────────────────────

def chunk_page_text(text: str, page_number: int) -> list[dict]:
    """
    Split page text into overlapping chunks.
    Returns list of { chunk_index, text, start_word, end_word }.
    """
    words = text.split()
    chunks = []
    start = 0
    idx = 0

    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunk_text = " ".join(words[start:end])
        chunks.append({
            "chunk_index": idx,
            "text": chunk_text,
            "start_word": start,
            "end_word": end,
            "page_number": page_number,
        })
        start += CHUNK_SIZE - CHUNK_OVER
        idx += 1

    return chunks


# ── Chapter detection ──────────────────────────────────────────────────────────

CHAPTER_RE = re.compile(
    r"(chapter\s+\d+|section\s+\d+[\.\d]*|part\s+[ivxIVX\d]+)",
    re.IGNORECASE,
)

# Known page ranges for UCG 2023 only
UCG_CHAPTER_RANGES = [
    (1,   30,   "Front Matter"),
    (31,  80,   "Chapter 1: Primary Health Care"),
    (81,  150,  "Chapter 2: Communicable Diseases"),
    (151, 220,  "Chapter 3: HIV/AIDS"),
    (221, 290,  "Chapter 4: Malaria"),
    (291, 360,  "Chapter 5: Tuberculosis"),
    (361, 445,  "Chapter 6: Gastrointestinal and Hepatic Diseases"),
    (446, 485,  "Chapter 7: Renal and Urinary Diseases"),
    (486, 565,  "Chapter 9: Mental, Neurological and Substance Use"),
    (566, 620,  "Chapter 11: Blood Diseases"),
    (621, 700,  "Chapter 13: Palliative Care"),
    (701, 760,  "Chapter 14: Dermatology"),
    (761, 830,  "Chapter 15: Reproductive Health"),
    (831, 950,  "Chapter 17: Childhood Illness"),
    (951, 1035, "Chapter 23: Non-Communicable Diseases"),
    (1036,1100, "Chapter 24: Surgery and Anaesthesia"),
    (1101,1158, "Appendices and References"),
]

# Keywords that identify chapter topics in any PDF
TOPIC_KEYWORDS = [
    (["malaria", "plasmodium", "artemether", "artesunate", "rdt"],
     "Malaria"),
    (["hiv", "antiretroviral", "arv", "cd4", "viral load"],
     "HIV/AIDS"),
    (["tuberculosis", "tb ", "rifampicin", "isoniazid", "sputum"],
     "Tuberculosis"),
    (["diarrhoea", "diarrhea", "gastroenteritis", "vomiting", "dehydration", "ors"],
     "Gastrointestinal Diseases"),
    (["malnutrition", "nutrition", "stunting", "wasting", "breastfeeding"],
     "Nutrition"),
    (["pneumonia", "asthma", "respiratory", "wheeze", "cough"],
     "Respiratory Diseases"),
    (["hypertension", "cardiac", "heart failure", "blood pressure"],
     "Cardiovascular Diseases"),
    (["diabetes", "insulin", "glucose", "hyperglycaemia"],
     "Diabetes and Endocrine"),
    (["epilepsy", "seizure", "convulsion", "mental health", "depression"],
     "Mental and Neurological"),
    (["maternal", "antenatal", "obstetric", "labour", "delivery", "pregnancy"],
     "Reproductive and Maternal Health"),
    (["paediatric", "imci", "child", "infant", "neonatal", "newborn"],
     "Childhood Illness"),
    (["palliative", "cancer", "terminal", "pain management"],
     "Palliative Care"),
    (["surgery", "surgical", "anaesthesia", "wound", "fracture"],
     "Surgery and Anaesthesia"),
    (["skin", "dermatology", "rash", "eczema", "psoriasis"],
     "Dermatology"),
    (["eye", "vision", "ophthalm", "glaucoma", "cataract"],
     "Eye Conditions"),
    (["renal", "kidney", "urinary", "dialysis", "nephro"],
     "Renal and Urinary Diseases"),
]


def detect_chapter(
    text: str,
    prev_chapter: str = "General",
    page_number: int = 0,
    source_file: str = "",
) -> str:
    """
    Detect chapter using 3 strategies in order:

    1. Page range lookup — for UCG 2023 only (100% reliable)
    2. Topic keyword scan — works for any PDF automatically
    3. Carry forward — if nothing found, inherit from previous page
    """
    # Strategy 1: UCG page range lookup
    if "ucg" in source_file.lower() or "uganda clinical" in source_file.lower():
        for start, end, chapter in UCG_CHAPTER_RANGES:
            if start <= page_number <= end:
                return chapter

    # Strategy 2: Topic keyword scan (works for any PDF)
    text_lower = text[:800].lower()
    for keywords, chapter_name in TOPIC_KEYWORDS:
        matches = sum(1 for kw in keywords if kw in text_lower)
        if matches >= 2:  # require at least 2 keyword matches for confidence
            return chapter_name

    # Strategy 3: Carry forward
    return prev_chapter
 


# ── Metadata extraction ────────────────────────────────────────────────────────

DOCUMENT_NAMES = {
    "uganda clinical guidelines": "Uganda Clinical Guidelines 2023",
    "ucg":                        "Uganda Clinical Guidelines 2023",
    "imci":                       "Uganda IMCI Guidelines 2022",
    "essential medicines":        "Uganda Essential Medicines List",
    "who":                        "WHO Protocol",
    "moh":                        "MOH Treatment Manual",
}

def infer_document_name(filename: str) -> str:
    lower = filename.lower()
    for key, name in DOCUMENT_NAMES.items():
        if key in lower:
            return name
    return Path(filename).stem.replace("_", " ").replace("-", " ").title()


# ── Chunk ID ───────────────────────────────────────────────────────────────────

def make_chunk_id(source_file: str, page: int, chunk_index: int) -> str:
    """Stable, collision-resistant chunk identifier."""
    raw = f"{source_file}::p{page}::c{chunk_index}"
    h = hashlib.md5(raw.encode()).hexdigest()[:8]
    safe_stem = re.sub(r"[^a-zA-Z0-9]", "_", Path(source_file).stem)[:20]
    return f"{safe_stem}_p{page:04d}_c{chunk_index:03d}_{h}"


# ── Main ingestion pipeline ────────────────────────────────────────────────────

def ingest_pdf(pdf_path: Path, dry_run: bool = False) -> int:
    """
    Full pipeline: extract → clean → chunk → embed → store.
    Returns number of chunks added to the DB.
    """
    from database import add_chunks  # local import to avoid circular deps

    logger.info(f"Processing: {pdf_path.name}")
    pages = extract_text_from_pdf(pdf_path)
    if not pages:
        logger.warning(f"No text extracted from {pdf_path.name}")
        return 0

    doc_name = infer_document_name(pdf_path.name)
    all_chunks = []

    prev_chapter = "General"
    for page_data in pages:
        cleaned = clean_text(page_data["text"])
        if len(cleaned) < 80:
            continue
        chapter      = detect_chapter(cleaned, prev_chapter, page_number=page_data["page_number"], source_file=pdf_path.name)
        prev_chapter = chapter  # carry forward to next page

        page_chunks = chunk_page_text(cleaned, page_data["page_number"])
        for chunk in page_chunks:
            chunk_id = make_chunk_id(pdf_path.name, chunk["page_number"], chunk["chunk_index"])
            all_chunks.append({
                "id":   chunk_id,
                "text": chunk["text"],
                "metadata": {
                    "document":    doc_name,
                    "chapter":     chapter,
                    "page":        str(chunk["page_number"]),
                    "source_file": pdf_path.name,
                    "chunk_index": str(chunk["chunk_index"]),
                },
            })

    logger.info(f"  → {len(pages)} pages → {len(all_chunks)} chunks ready")

    if dry_run:
        logger.info(f"  → DRY RUN: skipping DB write")
        return 0

    added = add_chunks(all_chunks)
    logger.info(f"  → {added} new chunks written to ChromaDB")
    return added


def ingest_all(docs_dir: Path = DOCS_DIR, dry_run: bool = False) -> None:
    """Ingest every PDF found in docs_dir."""
    pdfs = list(docs_dir.glob("**/*.pdf"))
    if not pdfs:
        logger.warning(f"No PDFs found in {docs_dir}/")
        logger.info("Place your Uganda Clinical Guidelines PDFs in ./knowledge_base_docs/")
        logger.info("Then re-run:  python knowledge_base.py")
        return

    logger.info(f"Found {len(pdfs)} PDF(s)")
    total = 0
    for pdf in pdfs:
        total += ingest_pdf(pdf, dry_run=dry_run)

    logger.info(f"Done. {total} total new chunks indexed.")


def print_stats() -> None:
    from database import collection_stats
    stats = collection_stats()
    print(f"\n── ChromaDB Stats ──────────────────────────")
    print(f"Total chunks : {stats['total_chunks']}")
    print(f"Documents    : {len(stats['documents'])}")
    for doc in stats["documents"]:
        print(f"  • {doc['name']}  ({doc['chunks']} chunks)")
    print()


# ── CLI ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ClinAssist knowledge base ingestion")
    parser.add_argument("--file",    help="Path to a single PDF to ingest")
    parser.add_argument("--dir",     help="Directory of PDFs (default: ./knowledge_base_docs)")
    parser.add_argument("--stats",   action="store_true", help="Print DB stats and exit")
    parser.add_argument("--reset",   action="store_true", help="Wipe DB and re-ingest")
    parser.add_argument("--dry-run", action="store_true", help="Parse only, don't write to DB")
    args = parser.parse_args()

    if args.stats:
        print_stats()
        sys.exit(0)

    if args.reset:
        from database import delete_collection
        logger.warning("Wiping ChromaDB collection...")
        delete_collection()

    if args.file:
        p = Path(args.file)
        if not p.exists():
            logger.error(f"File not found: {p}")
            sys.exit(1)
        ingest_pdf(p, dry_run=args.dry_run)

    else:
        docs_dir = Path(args.dir) if args.dir else DOCS_DIR
        docs_dir.mkdir(parents=True, exist_ok=True)
        ingest_all(docs_dir, dry_run=args.dry_run)

    print_stats()