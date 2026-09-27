import os
from urllib import response

from dotenv import load_dotenv
from groq import Groq


# ============================================================
# CONFIG
# ============================================================

load_dotenv(override=True)
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
4. Answer ONLY the user's question.
5. Do not provide additional background, related concepts,
   examples, characteristics, advantages, disadvantages, or
   recommendations unless they are directly required to answer
   the question.
6. Be concise. Use the minimum amount of information needed to
   completely answer the question.
7. If the question asks for a definition, give the definition
   and only the essential clarification.
8. If the question asks for specific points, provide only those
   points.
9. Do not turn a simple question into a detailed report.
10. Do not add a summary or "Key Points" section unless it is
    necessary to answer the question.
11. Do not use tables unless the user explicitly asks for one.
12. Every factual claim must be supported by the retrieved
    context and include [Source X].
13. Do not introduce information simply because it appears in
    the retrieved context.

USER QUESTION:
{question}

RETRIEVED CONTEXT:
{context}

Now provide the answer.
"""

    stream = client.chat.completions.create(
    model=GROQ_MODEL,
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ],
    temperature=0,
    max_completion_tokens=8192,
    stream=True
)
    
    answer = ""

    for chunk in stream:
        content = chunk.choices[0].delta.content

        if content:
            print(content, end="", flush=True)
            answer += content

    return answer


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