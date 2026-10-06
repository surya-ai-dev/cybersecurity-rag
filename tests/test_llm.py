import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv(override=True)

MODEL_NAME = "openai/gpt-oss-20b"


def main():

    print("=" * 60)
    print("LLM CONNECTION TEST")
    print("=" * 60)

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        print("❌ GROQ_API_KEY is not set.")
        return

    client = Groq(
        api_key=api_key
    )

    print("✅ Groq client initialized")

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": (
                    "Explain what a firewall is "
                    "in simple cybersecurity terms."
                )
            }
        ],
        temperature=0.2,
    )

    answer = response.choices[0].message.content

    print("\nLLM RESPONSE")
    print("=" * 60)
    print(answer)

    print("\n")
    print("=" * 60)
    print("✅ LLM TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()