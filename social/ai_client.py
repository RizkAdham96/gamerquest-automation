import json
import os
import re
import time
import urllib.error
import urllib.request

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("SOCIAL_GROQ_MODEL", "openai/gpt-oss-120b")
MAX_RATE_LIMIT_RETRIES = 1
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 5.0
RATE_LIMIT_BUFFER_SECONDS = 1.0


def _build_request(prompt, api_key):
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }
    return urllib.request.Request(
        GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "GamerQuest-Social/1.0",
        },
        method="POST",
    )


def _rate_limit_wait_seconds(error_body):
    match = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", error_body, re.IGNORECASE)
    if match:
        return float(match.group(1)) + RATE_LIMIT_BUFFER_SECONDS
    return DEFAULT_RATE_LIMIT_WAIT_SECONDS


def call_grok(prompt):
    """Backward-compatible function name used by the social pipeline.

    The request is sent to Groq, not xAI/Grok. A 429 is retried once after
    the wait time reported by Groq so the free TPM window can recover.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("Missing GROQ_API_KEY environment variable.")

    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        request = _build_request(prompt, api_key)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw_response = response.read().decode("utf-8")
                data = json.loads(raw_response)
                return extract_text(data)
        except urllib.error.HTTPError as error:
            error_body = error.read().decode("utf-8", errors="replace")
            if error.code == 429 and attempt < MAX_RATE_LIMIT_RETRIES:
                wait_seconds = _rate_limit_wait_seconds(error_body)
                print(f"Groq rate limit reached; retrying once in {wait_seconds:.1f}s.")
                time.sleep(wait_seconds)
                continue
            raise RuntimeError(f"Groq API error {error.code}: {error_body}") from error
        except urllib.error.URLError as error:
            raise RuntimeError(f"Unable to connect to Groq API: {error}") from error

    raise RuntimeError("Groq request failed after rate-limit retry.")


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
    raise RuntimeError("Groq returned a response but no text could be extracted.")
