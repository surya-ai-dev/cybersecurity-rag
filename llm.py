import os

from dotenv import load_dotenv
from groq import Groq


# ============================================================
# CONFIG
# ============================================================

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-20b"


# ============================================================
# INITIALIZE GROQ
# ============================================================

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError(
        "GROQ_API_KEY not found in .env"
    )

client = Groq(
    api_key=api_key
)


# ============================================================
# GENERATE ANSWER
# ============================================================

def generate_answer(
    question: str,
    context: str
):

    prompt = f"""
You are a cybersecurity assistant for a Retrieval-Augmented
Generation (RAG) system.

Your task is to answer the user's question using ONLY the
retrieved context provided below.

IMPORTANT RULES:

1. Do not use information that is not supported by the context.
2. Do not invent facts.
3. If the context does not contain enough information, clearly
   say that the available context is insufficient.
4. Keep the answer clear and technically accurate.
5. Organize the answer using headings or bullet points when useful.
6. Every important factual claim must include a source reference
   such as [Source 1], [Source 2], etc.
7. Use only source numbers that actually exist in the retrieved
   context.
8. Do not create new source numbers.
9. At the end, include a "Sources Used" section listing only the
   sources actually referenced in the answer.
10. Do not copy large passages from the context. Summarize them.

USER QUESTION:
{question}

RETRIEVED CONTEXT:
{context}

Now provide the answer.
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0
    )

    return response.choices[0].message.content


# ============================================================
# TEST
# ============================================================

def main():

    question = (
        "What are the security risks of public cloud computing?"
    )

    context = """
SOURCE 1

Document: NIST_SP_800-144
Source File: NIST_SP_800-144.txt
Section: Conclusion

Content:
Public cloud computing creates security and privacy concerns.
Organizations remain accountable for security and privacy even
when infrastructure is managed by a cloud provider. Continuous
monitoring can be challenging because significant portions of
the environment may be under the provider's control.


SOURCE 2

Document: NIST_SP_800-144
Source File: NIST_SP_800-144.txt
Section: Executive Summary

Content:
Public cloud infrastructure and computational resources are
owned and operated by an outside party and delivered through
a multi-tenant platform. The report discusses threats,
technology risks, and safeguards surrounding public cloud
environments.


SOURCE 3

Document: NIST_SP_800-144
Source File: NIST_SP_800-144.txt
Section: Security

Content:
Social engineering attacks and malware on client devices can
negatively affect the security and privacy of public cloud
services.
"""

    print("=" * 70)
    print("LLM TEST")
    print("=" * 70)

    print("\nGenerating answer...")

    answer = generate_answer(
        question,
        context
    )

    print("\nAnswer:")
    print(answer)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()