import re


TARGET_WORDS = 400
MAX_WORDS = 500
OVERLAP_WORDS = 50


def _split_words(text):
    """Split text by word count with overlap when sentences cannot be used."""
    words = text.split()
    pieces = []
    start = 0
    while start < len(words):
        end = min(start + TARGET_WORDS, len(words))
        pieces.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = end - OVERLAP_WORDS
    return pieces


def split_text(text):
    """Split long text at sentence boundaries, with a word-based fallback."""
    words = text.split()
    if not words:
        return []
    if len(words) <= MAX_WORDS:
        return [text.strip()]

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sentences) == 1:
        # Unpunctuated text still needs predictable chunks below the size limit.
        return _split_words(text)

    pieces = []
    current = []
    current_words = 0

    for sentence_index, sentence in enumerate(sentences):
        sentence_words = len(sentence.split())
        if sentence_words > MAX_WORDS:
            if current:
                pieces.append(" ".join(current))
                current = []
                current_words = 0
            pieces.extend(_split_words(sentence))
            continue

        if current and current_words + sentence_words > MAX_WORDS:
            pieces.append(" ".join(current))
            # Repeat a few complete sentences to preserve context between chunks.
            overlap = []
            overlap_words = 0
            for previous in reversed(current):
                count = len(previous.split())
                if overlap_words + count > OVERLAP_WORDS:
                    break
                overlap.insert(0, previous)
                overlap_words += count
            current = overlap
            current_words = overlap_words

        current.append(sentence)
        current_words += sentence_words
        if current_words >= TARGET_WORDS:
            pieces.append(" ".join(current))
            if sentence_index == len(sentences) - 1:
                current = []
                current_words = 0
                continue
            overlap = []
            overlap_words = 0
            for previous in reversed(current):
                count = len(previous.split())
                if overlap_words + count > OVERLAP_WORDS:
                    break
                overlap.insert(0, previous)
                overlap_words += count
            current = overlap
            current_words = overlap_words

    if current:
        pieces.append(" ".join(current))
    return pieces


def make_chunk(document_id, index, content, page=None, slide=None, sheet=None):
    """Create one chunk in the common format."""
    return {
        "chunk_id": f"{document_id}_{index}",
        "chunk_index": index,
        "content": content,
        "page": page,
        "slide": slide,
        "sheet": sheet,
    }


def create_document_chunks(document_id, file_type, content, content_units=None):
    """Create ordered chunks while keeping page, slide, or sheet metadata."""
    units = content_units or [{"content": content or ""}]
    chunks = []

    if file_type in {".pdf", ".pptx"}:
        for unit in units:
            # Split long units without losing their original page or slide number.
            for piece in split_text(unit.get("content", "")):
                chunk = make_chunk(
                    document_id, len(chunks), piece,
                    page=unit.get("page"), slide=unit.get("slide"),
                )
                chunks.append(chunk)
        return chunks

    if file_type == ".xlsx":
        current_sheet = None
        current_rows = []
        word_count = 0

        for unit in units:
            row_text = unit.get("content", "").strip()
            sheet = unit.get("sheet")
            if not row_text:
                continue

            row_words = len(row_text.split())
            if current_rows and (sheet != current_sheet or word_count + row_words > TARGET_WORDS):
                text = "\n".join(current_rows)
                chunks.append(make_chunk(document_id, len(chunks), text, sheet=current_sheet))
                current_rows = []
                word_count = 0

            if row_words > MAX_WORDS:
                for piece in split_text(row_text):
                    chunks.append(make_chunk(document_id, len(chunks), piece, sheet=sheet))
                current_sheet = sheet
                continue

            # Keep nearby rows together without mixing content from different sheets.
            current_sheet = sheet
            current_rows.append(row_text)
            word_count += row_words

        if current_rows:
            text = "\n".join(current_rows)
            chunks.append(make_chunk(document_id, len(chunks), text, sheet=current_sheet))
        return chunks

    if file_type == ".docx":
        paragraphs = []
        word_count = 0

        for unit in units:
            paragraph = unit.get("content", "").strip()
            if not paragraph:
                continue

            paragraph_words = len(paragraph.split())
            if paragraphs and word_count + paragraph_words > TARGET_WORDS:
                text = "\n".join(paragraphs)
                chunks.append(make_chunk(document_id, len(chunks), text))
                paragraphs = []
                word_count = 0

            if paragraph_words > MAX_WORDS:
                for piece in split_text(paragraph):
                    chunks.append(make_chunk(document_id, len(chunks), piece))
                continue

            paragraphs.append(paragraph)
            word_count += paragraph_words

        if paragraphs:
            text = "\n".join(paragraphs)
            chunks.append(make_chunk(document_id, len(chunks), text))
        return chunks

    for piece in split_text(content or ""):
        chunks.append(make_chunk(document_id, len(chunks), piece))
    return chunks
