import re

PLATFORM_PATTERNS = {
    "Nintendo": [
        r"\bnintendo\b",
        r"\bswitch(?:\s*2)?\b",
        r"\bnintendo\s+direct\b",
    ],
    "PlayStation": [
        r"\bplaystation\b",
        r"\bps5\b",
        r"\bps4\b",
        r"\bstate\s+of\s+play\b",
        r"\bps\s*plus\b",
    ],
    "Xbox": [
        r"\bxbox\b",
        r"\bgame\s+pass\b",
        r"\bseries\s+x\b",
        r"\bseries\s+s\b",
        r"\bxbox\s+one\b",
    ],
}


def classify_platforms(text):
    normalized = str(text or "").lower()
    platforms = []

    for platform, patterns in PLATFORM_PATTERNS.items():
        if any(
            re.search(pattern, normalized, flags=re.IGNORECASE)
            for pattern in patterns
        ):
            platforms.append(platform)

    return platforms


def merge_platform_tags(existing_tags, platforms):
    merged = []
    seen = set()

    for tag in list(existing_tags or []) + list(platforms or []):
        value = str(tag).strip()

        if not value:
            continue

        key = value.casefold()

        if key in seen:
            continue

        seen.add(key)
        merged.append(value)

    return merged
