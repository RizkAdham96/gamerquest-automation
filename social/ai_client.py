import json
import os
import urllib.error
import urllib.request


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("SOCIAL_GROQ_MODEL", "openai/gpt-oss-120b")


def call_grok(prompt):
    """Backward-compatible function name used by the social pipeline.

    The request is sent to Groq, not xAI/Grok.
    """
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing GROQ_API_KEY environment variable."
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }

    request = urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "GamerQuest-Social/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw_response = response.read().decode("utf-8")
            data = json.loads(raw_response)

    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="replace")

        raise RuntimeError(
            f"Groq API error {error.code}: {error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Unable to connect to Groq API: {error}"
        ) from error

    return extract_text(data)


def extract_text(data):
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Groq API response.")

    choices = data.get("choices", [])

    for choice in choices:
        if not isinstance(choice, dict):
            continue

        message = choice.get("message", {})
        if not isinstance(message, dict):
            continue

        text = message.get("content")
        if text:
            return text.strip()

    raise RuntimeError(
        "Groq returned a response but no text could be extracted."
    )
