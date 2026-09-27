import os

from dotenv import load_dotenv
from groq import Groq


load_dotenv(override=True)

GROQ_MODEL = "openai/gpt-oss-20b"

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise ValueError("GROQ_API_KEY not found in .env")

client = Groq(api_key=api_key)


def rewrite_question(question, conversation_history):
    history_text = ""

    for message in conversation_history:
        history_text += f"""
User: {message["user"]}
Assistant: {message["assistant"]}
"""

    prompt = f"""
You are a question rewriting component in a cybersecurity RAG system.

Your task is to rewrite the user's latest question into a standalone
question that can be understood without the previous conversation.

Conversation history:
{history_text}

Latest user question:
{question}

Rules:
1. Preserve the original meaning.
2. Use conversation history only when necessary.
3. If the question is already standalone, return it unchanged.
4. Do not answer the question.
5. Return ONLY the rewritten question.
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        temperature=0,
        max_completion_tokens=512
    )

    return response.choices[0].message.content.strip()


if __name__ == "__main__":
    history = [
        {
            "user": "What is least privilege?",
            "assistant": "Least privilege limits actions to the minimum necessary."
        }
    ]

    question = "Why is it important?"

    rewritten = rewrite_question(question, history)

    print("\nOriginal:", question)
    print("Rewritten:", rewritten)