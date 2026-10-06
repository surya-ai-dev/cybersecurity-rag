import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data" / "extracted_text"
OUTPUT_DIR = PROJECT_ROOT / "data" / "cleaned_text"


def clean_text(text):
    """
    Clean extracted PDF text while preserving useful content.
    """

    # Normalize line endings
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    # Remove page markers
    text = re.sub(
        r"---\s*PAGE\s*\d+\s*---",
        "\n",
        text,
        flags=re.IGNORECASE
    )

    # Remove excessive spaces
    text = re.sub(r"[ \t]+", " ", text)

    # Reduce excessive blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Remove spaces around newlines
    text = re.sub(r" *\n *", "\n", text)

    # Fix common PDF hyphenation
    # Example:
    # cyber-
    # security
    # →
    # cybersecurity
    text = re.sub(
        r"(\w)-\n(\w)",
        r"\1\2",
        text
    )

    # Remove leading/trailing whitespace
    text = text.strip()

    return text


def clean_file(input_path):
    """
    Clean one text file and save it to the matching category.
    """

    relative_path = input_path.relative_to(INPUT_DIR)

    output_path = OUTPUT_DIR / relative_path

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    try:

        text = input_path.read_text(
            encoding="utf-8",
            errors="ignore"
        )

        cleaned = clean_text(text)

        output_path.write_text(
            cleaned,
            encoding="utf-8"
        )

        print(f"✅ {input_path}")
        print(f"   → {output_path}")

        return True

    except Exception as error:

        print(f"❌ {input_path}")
        print(f"   Error: {error}")

        return False


def main():

    print("=" * 60)
    print("NIST TEXT CLEANING")
    print("=" * 60)

    txt_files = list(
        INPUT_DIR.rglob("*.txt")
    )

    print(f"\nFound {len(txt_files)} text files.\n")

    successful = 0
    failed = 0

    for file in txt_files:

        if clean_file(file):
            successful += 1
        else:
            failed += 1

    print("\n")
    print("=" * 60)
    print("TEXT CLEANING COMPLETE")
    print("=" * 60)

    print(f"Total files : {len(txt_files)}")
    print(f"Successful  : {successful}")
    print(f"Failed      : {failed}")

    print("\nOutput folder:")
    print(OUTPUT_DIR.absolute())

    print("=" * 60)


if __name__ == "__main__":
    main()