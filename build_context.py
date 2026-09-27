from retriever import retrieve


# ============================================================
# CONFIG
# ============================================================

TOP_K = 5


# ============================================================
# RAG CONTEXT BUILDER
# ============================================================

print("=" * 70)
print("RAG CONTEXT BUILDER")
print("=" * 70)


# ============================================================
# BUILD CONTEXT
# ============================================================

def build_context(results):
    
    context_parts = []
 
    

    for index, result in enumerate(results, start=1):

        metadata = result.get(
            "metadata",
            {}
        )

        document = metadata.get(
            "document_id",
            "Unknown"
        )

        source = metadata.get(
            "source_file",
            "Unknown"
        )

        section = metadata.get(
            "section",
            "Unknown"
        )

        text = result.get(
            "text",
            ""
        )

        rrf_score = result.get(
            "rrf_score",
            0.0
        )

        context = f"""
SOURCE {index}

Document: {document}
Source File: {source}
Section: {section}
RRF Score: {rrf_score:.6f}

Content:
{text}
"""

        context_parts.append(
            context.strip()
        )

    return "\n\n".join(
        context_parts
    )


# ============================================================
# MAIN
# ============================================================

def main():

    question = input(
        "\nEnter cybersecurity question: "
    ).strip()

    if not question:

        print("❌ Question cannot be empty.")

        return


    # --------------------------------------------------------
    # Retrieval
    # --------------------------------------------------------

    print("\nRetrieving relevant documents...")

    results = retrieve(
        question,
        top_k=TOP_K
    )
    print("\nDEBUG FIRST RESULT:")
    print(results[0])


    # --------------------------------------------------------
    # Build context
    # --------------------------------------------------------

    print("\nBuilding context...")

    context = build_context(
        results
    )


    # --------------------------------------------------------
    # Display
    # --------------------------------------------------------

    print("\n")
    print("=" * 70)
    print("RETRIEVED CONTEXT")
    print("=" * 70)

    print(context)

    print("\n")
    print("=" * 70)
    print("CONTEXT BUILD COMPLETE")
    print("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()