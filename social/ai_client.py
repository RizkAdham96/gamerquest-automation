import json
import os
import urllib.error
import urllib.request


XAI_API_URL = "https://api.x.ai/v1/responses"
XAI_MODEL = os.getenv("SOCIAL_XAI_MODEL", "grok-4.6")


def call_grok(prompt):
    api_key = os.getenv("SOCIAL_GROK_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing SOCIAL_GROK_API_KEY environment variable."
        )

    payload = {
        "model": XAI_MODEL,
        "input": prompt,
    }

    request = urllib.request.Request(
        XAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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
            f"Grok API error {error.code}: {error_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Unable to connect to Grok API: {error}"
        ) from error

    return extract_text(data)


def extract_text(data):
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Grok API response.")

    output = data.get("output", [])

    for item in output:
        if not isinstance(item, dict):
            continue

        content = item.get("content", [])

        for content_item in content:
            if not isinstance(content_item, dict):
                continue

            text = content_item.get("text")

            if text:
                return text.strip()

    raise RuntimeError(
        "Grok returned a response but no text could be extracted."
    )
