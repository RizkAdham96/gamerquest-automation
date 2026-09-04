import json
import os
import re
import time
import urllib.error
import urllib.request


GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv(
    "SOCIAL_GROQ_MODEL",
    "openai/gpt-oss-120b",
)

# We retry a rate-limited request after Groq's requested wait.
MAX_RATE_LIMIT_RETRIES = 2

# Used only when Groq does not tell us how long to wait.
DEFAULT_RATE_LIMIT_WAIT_SECONDS = 60.0

# Small safety margin so we don't retry exactly on the limit boundary.
RATE_LIMIT_BUFFER_SECONDS = 3.0

# Do not let a GitHub Action sleep forever.
MAX_RATE_LIMIT_WAIT_SECONDS = 20 * 60


def _build_request(prompt, api_key):
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
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
    """
    Extract Groq's requested retry delay.

    Supported examples:
        "Please try again in 8.29s."
        "Please try again in 13m55.488s."
        "Please try again in 8m29.76s."
    """

    if not error_body:
        return DEFAULT_RATE_LIMIT_WAIT_SECONDS

    # Format: 13m55.488s
    minutes_seconds_match = re.search(
        r"try again in\s+"
        r"([0-9]+(?:\.[0-9]+)?)m"
        r"([0-9]+(?:\.[0-9]+)?)s",
        error_body,
        re.IGNORECASE,
    )

    if minutes_seconds_match:
        minutes = float(minutes_seconds_match.group(1))
        seconds = float(minutes_seconds_match.group(2))

        wait_seconds = (
            minutes * 60
            + seconds
            + RATE_LIMIT_BUFFER_SECONDS
        )

        return min(
            wait_seconds,
            MAX_RATE_LIMIT_WAIT_SECONDS,
        )

    # Format: 8.29s
    seconds_match = re.search(
        r"try again in\s+"
        r"([0-9]+(?:\.[0-9]+)?)s",
        error_body,
        re.IGNORECASE,
    )

    if seconds_match:
        wait_seconds = (
            float(seconds_match.group(1))
            + RATE_LIMIT_BUFFER_SECONDS
        )

        return min(
            wait_seconds,
            MAX_RATE_LIMIT_WAIT_SECONDS,
        )

    return DEFAULT_RATE_LIMIT_WAIT_SECONDS


def call_grok(prompt):
    """
    Backward-compatible function name used by the social pipeline.

    Requests are sent to Groq.

    When Groq returns HTTP 429:
    - read Groq's requested retry delay;
    - wait for that period;
    - retry automatically;
    - stop after a bounded number of retries.
    """

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Missing GROQ_API_KEY environment variable."
        )

    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):

        request = _build_request(
            prompt,
            api_key,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=60,
            ) as response:

                raw_response = (
                    response
                    .read()
                    .decode("utf-8")
                )

                data = json.loads(raw_response)

                return extract_text(data)

        except urllib.error.HTTPError as error:

            error_body = (
                error
                .read()
                .decode(
                    "utf-8",
                    errors="replace",
                )
            )

            if error.code == 429:

                if attempt >= MAX_RATE_LIMIT_RETRIES:
                    raise RuntimeError(
                        "Groq rate limit is still active "
                        "after automatic retries. "
                        f"Last response: {error_body}"
                    ) from error

                wait_seconds = (
                    _rate_limit_wait_seconds(
                        error_body
                    )
                )

                wait_minutes = (
                    wait_seconds / 60
                )

                print(
                    "Groq rate limit reached."
                )

                print(
                    "Groq requested a retry delay. "
                    f"Waiting {wait_seconds:.1f} seconds "
                    f"(~{wait_minutes:.1f} minutes)."
                )

                print(
                    f"Automatic retry "
                    f"{attempt + 1}/"
                    f"{MAX_RATE_LIMIT_RETRIES}."
                )

                time.sleep(wait_seconds)

                continue

            raise RuntimeError(
                f"Groq API error "
                f"{error.code}: "
                f"{error_body}"
            ) from error

        except urllib.error.URLError as error:
            raise RuntimeError(
                "Unable to connect to Groq API: "
                f"{error}"
            ) from error

    raise RuntimeError(
        "Groq request failed after "
        "rate-limit retries."
    )


def extract_text(data):
    if not isinstance(data, dict):
        raise RuntimeError(
            "Unexpected Groq API response."
        )

    choices = data.get(
        "choices",
        [],
    )

    for choice in choices:

        if not isinstance(
            choice,
            dict,
        ):
            continue

        message = choice.get(
            "message",
            {},
        )

        if not isinstance(
            message,
            dict,
        ):
            continue

        text = message.get(
            "content"
        )

        if text:
            return text.strip()

    raise RuntimeError(
        "Groq returned a response "
        "but no text could be extracted."
    )
