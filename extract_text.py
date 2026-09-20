from pathlib import Path
import fitz  # PyMuPDF


DOCUMENTS_DIR = Path("documents")
OUTPUT_DIR = Path("data/extracted_text")


def extract_pdf(pdf_path):
    """
    Extract text from one PDF and save it as .txt
    """

    # Find category name
    category = pdf_path.parent.name

    # Create matching output folder
    category_output = OUTPUT_DIR / category
    category_output.mkdir(parents=True, exist_ok=True)

    # Output text filename
    txt_path = category_output / f"{pdf_path.stem}.txt"

    print("=" * 60)
    print(f"Reading: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)

        all_text = []

        for page_number, page in enumerate(doc, start=1):

            text = page.get_text()

            all_text.append(
                f"\n\n--- PAGE {page_number} ---\n\n{text}"
            )

        final_text = "".join(all_text)

        # Save extracted text
        txt_path.write_text(
            final_text,
            encoding="utf-8"
        )

        print(f"Pages: {len(doc)}")
        print(f"Characters extracted: {len(final_text):,}")
        print(f"Saved: {txt_path}")

        doc.close()

        return True

    except Exception as error:

        print(f"ERROR: {error}")

        return False


def main():

    print("=" * 60)
    print("NIST PDF TEXT EXTRACTION")
    print("=" * 60)

    # Find every PDF recursively
    pdf_files = list(DOCUMENTS_DIR.rglob("*.pdf"))

    print(f"\nFound {len(pdf_files)} PDF files.\n")

    successful = 0
    failed = 0

    for index, pdf_path in enumerate(pdf_files, start=1):

        print(f"\n[{index}/{len(pdf_files)}]")

        success = extract_pdf(pdf_path)

        if success:
            successful += 1
        else:
            failed += 1

    print("\n")
    print("=" * 60)
    print("TEXT EXTRACTION COMPLETE")
    print("=" * 60)

    print(f"Total PDFs : {len(pdf_files)}")
    print(f"Successful : {successful}")
    print(f"Failed     : {failed}")

    print(f"\nOutput folder:")
    print(OUTPUT_DIR.absolute())

    print("=" * 60)


if __name__ == "__main__":
    main()