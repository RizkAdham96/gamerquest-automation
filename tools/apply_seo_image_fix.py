from pathlib import Path

path = Path(__file__).resolve().parents[1] / "trending_seo" / "pipeline.py"
text = path.read_text(encoding="utf-8")
start = text.index("def extract_relevant_image_url(")
end = text.index("\ndef find_relevant_source_image", start)

replacement = r'''def extract_relevant_image_url(
    html: str,
    page_url: str,
    topic: str,
) -> str:
    """Select a relevant image from a source page without trusting unrelated social cards."""
    if not safe_string(html) or not safe_string(page_url):
        return ""

    topic_terms = image_match_terms(topic)
    if len(topic_terms) < 2:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    page_context_parts = []
    if soup.title:
        page_context_parts.append(safe_string(soup.title.get_text(" ", strip=True)))
    for tag in soup.find_all("meta"):
        marker = safe_string(tag.get("property") or tag.get("name")).lower()
        if marker in {"og:title", "twitter:title"}:
            page_context_parts.append(safe_string(tag.get("content")))
    first_h1 = soup.find("h1")
    if first_h1:
        page_context_parts.append(safe_string(first_h1.get_text(" ", strip=True)))

    page_terms = image_match_terms(" ".join(page_context_parts))
    page_relevance = len(topic_terms & page_terms)
    page_is_relevant = page_relevance >= 2

    social_alt = ""
    for tag in soup.find_all("meta"):
        marker = safe_string(tag.get("property") or tag.get("name")).lower()
        if marker in {"og:image:alt", "twitter:image:alt"}:
            social_alt = safe_string(tag.get("content"))
            if social_alt:
                break

    candidates = []
    for tag in soup.find_all("meta"):
        marker = safe_string(tag.get("property") or tag.get("name")).lower()
        if marker not in {"og:image", "og:image:secure_url", "twitter:image"}:
            continue
        candidates.append((safe_string(tag.get("content")), social_alt, "social"))

    for tag in soup.find_all("img", limit=80):
        image_url = safe_string(
            tag.get("src")
            or tag.get("data-src")
            or tag.get("data-lazy-src")
        )
        description = " ".join([
            safe_string(tag.get("alt")),
            safe_string(tag.get("title")),
        ])
        candidates.append((image_url, description, "inline"))

    obvious_generic_markers = (
        "logo", "banner", "default", "placeholder", "avatar", "icon",
        "sprite", "header", "gamescom-logo", "site-logo",
    )

    ranked = []
    for image_url, description, kind in candidates:
        absolute_url = urljoin(page_url, image_url)
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue

        raw_context = f"{absolute_url} {description}".lower()
        if any(marker in raw_context for marker in obvious_generic_markers):
            continue

        context_terms = image_match_terms(f"{absolute_url} {description}")
        direct_score = len(topic_terms & context_terms)

        if direct_score >= 2:
            ranked.append((10 + direct_score, absolute_url))
            continue

        # Publisher social-card URLs are often opaque CDN hashes. Accept them only
        # when the page itself is clearly about the topic; unrelated pages remain blocked.
        if kind == "social" and page_is_relevant:
            ranked.append((page_relevance, absolute_url))

    if not ranked:
        return ""

    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]
'''

path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("SEO featured-image selector patched.")
# Triggered intentionally after the workflow was present on the branch.
