from pathlib import Path

path = Path(__file__).resolve().parents[1] / "trending_seo" / "pipeline.py"
text = path.read_text(encoding="utf-8")

start = text.index("def find_relevant_source_image(")
end = text.index("\ndef upload_featured_image", start)

replacement = r'''def build_featured_image_sources(
    topic: Dict[str, Any],
    research_context: Dict[str, Any] | None = None,
) -> list[Dict[str, Any]]:
    """Build a deduplicated image-source list from original and verified research pages."""
    collected = []

    original_sources = topic.get("sources", []) if isinstance(topic, dict) else []
    if isinstance(original_sources, list):
        collected.extend(item for item in original_sources if isinstance(item, dict))

    context = research_context if isinstance(research_context, dict) else {}

    usable_evidence = context.get("usable_evidence", [])
    if isinstance(usable_evidence, list):
        collected.extend(item for item in usable_evidence if isinstance(item, dict))

    claim_specific = context.get("claim_specific_evidence", {})
    if isinstance(claim_specific, dict):
        for items in claim_specific.values():
            if isinstance(items, list):
                collected.extend(item for item in items if isinstance(item, dict))

    for key in ("discovered_sources", "fetched_sources"):
        items = context.get(key, [])
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            status = safe_string(item.get("fetch_status")).upper()
            if status == "USABLE":
                collected.append(item)

    deduped = []
    seen = set()
    for source in collected:
        source_url = safe_string(source.get("url"))
        if urlparse(source_url).scheme not in {"http", "https"}:
            continue
        normalized_url = source_url.rstrip("/")
        if normalized_url in seen:
            continue
        seen.add(normalized_url)
        deduped.append(source)

    return deduped


def find_relevant_source_image(
    topic: Dict[str, Any],
    research_context: Dict[str, Any] | None = None,
    client=None,
) -> str:
    """Inspect original plus verified research source pages for a relevant image."""
    if client is None:
        client = requests

    topic_name = safe_string(topic.get("topic"))
    if not topic_name:
        return ""

    sources = build_featured_image_sources(topic, research_context)

    for source in sources:
        source_url = safe_string(source.get("url"))
        try:
            response = client.get(
                source_url,
                timeout=25,
                headers={
                    "Accept": "text/html,application/xhtml+xml",
                    "User-Agent": "GamerQuest-Trending-SEO/2.0",
                },
            )
        except Exception:
            continue
        if getattr(response, "status_code", 0) != 200:
            continue
        image_url = extract_relevant_image_url(
            safe_string(getattr(response, "text", "")),
            source_url,
            topic_name,
        )
        if image_url:
            return image_url

    return ""
'''

text = text[:start] + replacement + text[end:]
text = text.replace(
    "    image_url = find_relevant_source_image(topic)\n",
    "    image_url = find_relevant_source_image(\n        topic,\n        research_context=research_context,\n    )\n",
    1,
)
path.write_text(text, encoding="utf-8")
print("Verified research image-source path patched.")
# trigger after apply workflow exists
