import sys
from pathlib import Path

# Windows console UTF-8 fix for special symbols in chunk texts
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


# ============================================================
# CONFIG
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_PATH = PROJECT_ROOT / "data" / "qdrant"

COLLECTION_NAME = "cybersecurity_chunks_bge_m3"
MODEL_NAME = "BAAI/bge-m3"
VECTOR_DIMENSION = 1024

TOP_K = 30
TEXT_PREVIEW_LENGTH = 800


# ============================================================
# MAIN SEARCH ROUTINE
# ============================================================

def main():
    print("=" * 70)
    print("QDRANT VECTOR SEARCH TEST (BGE-M3)")
    print("=" * 70)

    # --------------------------------------------------------
    # 1. LOAD EMBEDDING MODEL
    # --------------------------------------------------------
    print(f"\nLoading {MODEL_NAME}...")
    try:
        try:
            model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            model = SentenceTransformer(MODEL_NAME)
        print("✅ Model loaded")
    except Exception as exc:
        print(f"❌ Failed to load embedding model '{MODEL_NAME}': {exc}")
        sys.exit(1)

    # --------------------------------------------------------
    # 2. CONNECT TO QDRANT
    # --------------------------------------------------------
    print("\nConnecting to Qdrant...")
    client = None

    try:
        client = QdrantClient(path=str(QDRANT_PATH))
        print("✅ Qdrant connected")

        # ----------------------------------------------------
        # 3. VERIFY COLLECTION & VECTOR DIMENSION
        # ----------------------------------------------------
        collection_info = client.get_collection(COLLECTION_NAME)
        vectors_config = collection_info.config.params.vectors

        collection_dim = (
            vectors_config.size
            if hasattr(vectors_config, "size")
            else getattr(vectors_config, "get", lambda k: None)("size")
        )

        distance_metric = (
            vectors_config.distance
            if hasattr(vectors_config, "distance")
            else getattr(vectors_config, "get", lambda k: None)("distance")
        )

        print("\nCollection:")
        print(f"Name      : {COLLECTION_NAME}")
        print(f"Vectors   : {collection_info.points_count:,}")
        print(f"Dimension : {collection_dim}")
        print(f"Distance  : {distance_metric}")

        if collection_dim != VECTOR_DIMENSION:
            raise ValueError(
                f"Collection vector dimension ({collection_dim}) does not match "
                f"expected dimension ({VECTOR_DIMENSION})."
            )

        # ----------------------------------------------------
        # 4. USER QUERY
        # ----------------------------------------------------
        query = input("\nEnter cybersecurity question: ").strip()

        if not query:
            print("\n⚠️ Query is empty. Please enter a valid cybersecurity question.")
            return

        print("\nQuery:")
        print(query)

        # ----------------------------------------------------
        # 5. CREATE QUERY EMBEDDING
        # ----------------------------------------------------
        print("\nGenerating query embedding...")
        query_embedding = model.encode(
            query,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        print("✅ Query embedding generated")
        print(f"Dimension : {query_embedding.shape[0]}")

        # Dimension match check
        if query_embedding.shape[0] != collection_dim:
            raise ValueError(
                f"Query embedding dimension ({query_embedding.shape[0]}) does not match "
                f"collection vector dimension ({collection_dim})."
            )

        # ----------------------------------------------------
        # 6. SEARCH QDRANT
        # ----------------------------------------------------
        print(f"\nSearching Qdrant (Top-{TOP_K})...")
        results = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding.tolist(),
            limit=TOP_K,
            with_payload=True,
        ).points

        # ----------------------------------------------------
        # 7. DISPLAY RESULTS
        # ----------------------------------------------------
        print("\n" + "=" * 70)
        print("SEARCH RESULTS")
        print("=" * 70)

        if not results:
            print("\n⚠️ No matching chunks found in the collection.")
        else:
            for rank, result in enumerate(results, start=1):
                payload = result.payload or {}

                print("\n" + "-" * 70)
                print(f"Rank           : {rank}")
                print(f"Score          : {result.score:.4f}")
                print(f"Chunk ID       : {payload.get('chunk_id', 'N/A')}")
                print(f"Document       : {payload.get('document_id', 'N/A')}")
                print(f"Category       : {payload.get('category', 'N/A')}")

                section = (
                    payload.get("section")
                    or payload.get("section_heading")
                    or "N/A"
                )
                print(f"Section        : {section}")
                print(f"Citation Label : {payload.get('citation_label', 'N/A')}")

                text = payload.get("text", "")
                print("\nText Preview:")
                if text:
                    preview = text[:TEXT_PREVIEW_LENGTH]
                    print(preview)
                    if len(text) > TEXT_PREVIEW_LENGTH:
                        print("\n... [truncated]")
                else:
                    print("[No text found in payload]")

        print("\n" + "=" * 70)
        print("VECTOR SEARCH COMPLETE")
        print("=" * 70)

    except Exception as exc:
        print(f"\n❌ ERROR during vector search: {exc}")
        raise

    finally:
        # ----------------------------------------------------
        # 8. CLEANUP QDRANT CONNECTION
        # ----------------------------------------------------
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()