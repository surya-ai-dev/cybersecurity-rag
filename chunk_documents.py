import re
import json
from pathlib import Path

import tiktoken


# ============================================================
# CONFIGURATION
# ============================================================

INPUT_DIR = Path("data/cleaned_text")
OUTPUT_DIR = Path("data/chunks")

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80

TOKENIZER = tiktoken.get_encoding("cl100k_base")


# ============================================================
# TOKEN FUNCTIONS
# ============================================================

def count_tokens(text):
    """Return approximate token count."""

    return len(
        TOKENIZER.encode(
            text,
            disallowed_special=()
        )
    )


def split_by_tokens(text, max_tokens):
    """Split text into token-sized pieces."""

    tokens = TOKENIZER.encode(
        text,
        disallowed_special=()
    )

    chunks = []

    start = 0

    while start < len(tokens):

        end = min(
            start + max_tokens,
            len(tokens)
        )

        chunk_tokens = tokens[start:end]

        chunk_text = TOKENIZER.decode(
            chunk_tokens
        )

        chunks.append(chunk_text)

        start = end

    return chunks


# ============================================================
# SECTION DETECTION
# ============================================================

def detect_section(line):
    """
    Try to identify common NIST section headings.

    Examples:
        1. Introduction
        2.1 Purpose
        3.2.1 Detection
        APPENDIX A
    """

    line = line.strip()

    if not line:
        return None

    # Numbered headings
    numbered_pattern = re.match(
        r"^(\d+(?:\.\d+){0,4})\s+(.+)$",
        line
    )

    if numbered_pattern:

        number = numbered_pattern.group(1)

        title = numbered_pattern.group(2).strip()

        # Avoid treating very long sentences as headings
        if len(line) <= 150:

            return f"{number} {title}"

    # Appendix headings
    appendix_pattern = re.match(
        r"^(APPENDIX\s+[A-Z0-9]+.*)$",
        line,
        re.IGNORECASE
    )

    if appendix_pattern:

        return appendix_pattern.group(1).strip()

    return None


# ============================================================
# STRUCTURE-AWARE SPLITTING
# ============================================================

def create_sections(text):
    """
    Divide a document into logical sections.
    """

    lines = text.splitlines()

    sections = []

    current_section = "Introduction"

    current_lines = []

    for line in lines:

        detected = detect_section(line)

        if detected:

            if current_lines:

                sections.append({
                    "section": current_section,
                    "text": "\n".join(
                        current_lines
                    ).strip()
                })

            current_section = detected

            current_lines = []

        else:

            current_lines.append(line)

    # Last section
    if current_lines:

        sections.append({
            "section": current_section,
            "text": "\n".join(
                current_lines
            ).strip()
        })

    return sections


# ============================================================
# PARAGRAPH SPLITTING
# ============================================================

def split_into_paragraphs(text):

    paragraphs = re.split(
        r"\n\s*\n",
        text
    )

    return [
        paragraph.strip()
        for paragraph in paragraphs
        if paragraph.strip()
    ]


# ============================================================
# BUILD CHUNKS
# ============================================================

def build_chunks(
    text,
    document_id,
    category,
    source_file
):

    sections = create_sections(text)

    chunks = []

    chunk_id = 0

    for section in sections:

        section_name = section["section"]

        paragraphs = split_into_paragraphs(
            section["text"]
        )

        current_text = ""

        for paragraph in paragraphs:

            candidate = (
                f"{current_text}\n\n{paragraph}"
                if current_text
                else paragraph
            )

            candidate_tokens = count_tokens(
                candidate
            )

            # ------------------------------------------
            # Paragraph fits inside chunk
            # ------------------------------------------

            if candidate_tokens <= CHUNK_SIZE:

                current_text = candidate

                continue

            # ------------------------------------------
            # Save current chunk
            # ------------------------------------------

            if current_text:

                chunk_id += 1

                chunks.append(
                    create_chunk(
                        chunk_id,
                        document_id,
                        category,
                        source_file,
                        section_name,
                        current_text
                    )
                )

            # ------------------------------------------
            # Large paragraph
            # ------------------------------------------

            if count_tokens(paragraph) > CHUNK_SIZE:

                small_chunks = split_by_tokens(
                    paragraph,
                    CHUNK_SIZE
                )

                for small_chunk in small_chunks:

                    chunk_id += 1

                    chunks.append(
                        create_chunk(
                            chunk_id,
                            document_id,
                            category,
                            source_file,
                            section_name,
                            small_chunk
                        )
                    )

                current_text = ""

            else:

                current_text = paragraph

        # ----------------------------------------------
        # Save remaining section text
        # ----------------------------------------------

        if current_text:

            chunk_id += 1

            chunks.append(
                create_chunk(
                    chunk_id,
                    document_id,
                    category,
                    source_file,
                    section_name,
                    current_text
                )
            )

    return chunks


# ============================================================
# CREATE CHUNK METADATA
# ============================================================

def create_chunk(
    chunk_id,
    document_id,
    category,
    source_file,
    section,
    text
):

    return {

        "chunk_id": (
            f"{document_id}_"
            f"{chunk_id:05d}"
        ),

        "document_id": document_id,

        "category": category,

        "source_file": source_file,

        "section": section,

        "text": text,

        "token_count": count_tokens(
            text
        )
    }


# ============================================================
# PROCESS ONE DOCUMENT
# ============================================================

def process_document(file_path):

    relative_path = file_path.relative_to(
        INPUT_DIR
    )

    category = relative_path.parts[0]

    document_id = file_path.stem

    source_file = file_path.name

    print("\n" + "=" * 70)

    print(
        f"Processing: {source_file}"
    )

    print(
        f"Category: {category}"
    )

    text = file_path.read_text(
        encoding="utf-8",
        errors="ignore"
    )

    chunks = build_chunks(
        text=text,
        document_id=document_id,
        category=category,
        source_file=source_file
    )

    # ----------------------------------------------
    # Output directory
    # ----------------------------------------------

    output_dir = (
        OUTPUT_DIR /
        category
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    output_file = (
        output_dir /
        f"{document_id}.json"
    )

    # ----------------------------------------------
    # Save JSON
    # ----------------------------------------------

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            chunks,
            file,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"Chunks created: {len(chunks)}"
    )

    print(
        f"Saved: {output_file}"
    )

    return len(chunks)


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)

    print(
        "NIST STRUCTURE-AWARE CHUNKING"
    )

    print("=" * 70)

    print()

    files = list(
        INPUT_DIR.rglob("*.txt")
    )

    print(
        f"Found {len(files)} cleaned documents."
    )

    print(
        f"Chunk size: {CHUNK_SIZE} tokens"
    )

    print(
        f"Overlap: {CHUNK_OVERLAP} tokens"
    )

    total_chunks = 0

    for index, file_path in enumerate(
        files,
        start=1
    ):

        print(
            f"\n[{index}/{len(files)}]"
        )

        total_chunks += process_document(
            file_path
        )

    print("\n")

    print("=" * 70)

    print("CHUNKING COMPLETE")

    print("=" * 70)

    print(
        f"Documents processed: {len(files)}"
    )

    print(
        f"Total chunks: {total_chunks}"
    )

    print(
        f"Output: {OUTPUT_DIR.absolute()}"
    )

    print("=" * 70)


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    main()