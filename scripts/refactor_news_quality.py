from pathlib import Path


AUTOMATION = Path("automation.py")
MODULE = Path("news_quality.py")

START_MARKER = "# =========================================================\n# OFFICIAL SOURCE DOMAINS\n# =========================================================\n"
END_MARKER = "# =========================================================\n# NEWS FEATURED IMAGES\n# =========================================================\n"
DISCOVERY_MARKER = "\ndef discovery_story_is_duplicate("
SOURCE_IMAGE_MARKER = "\ndef source_image_matches_article("

IMPORT_BLOCK = '''from news_quality import (\n    NEWS_STORY_ANGLES,\n    NEWS_TOPIC_GENERIC_TERMS,\n    OFFICIAL_DOMAIN_KEYWORDS,\n    TRUSTED_MEDIA_DOMAINS,\n    claimed_platforms,\n    get_domain,\n    has_conflicting_news_claims,\n    is_duplicate_news_topic,\n    is_exclusive_claim,\n    looks_official,\n    looks_trusted_media,\n    news_story_angles,\n    news_topic_terms,\n    normalize_words,\n    normalized_news_terms,\n    release_years,\n    result_content_length,\n    same_news_subject,\n    sanitize_article_html,\n    slugify,\n    source_image_matches_article,\n    source_tier,\n    strip_code_fences,\n)\n\n'''

MODULE_HEADER = '''"""Pure source and News-quality helpers for GamerQuest.\n\nThis module deliberately contains no API clients, environment-secret access,\nfilesystem state, or publishing side effects.  Keeping these rules separate\nmakes the News pipeline easier to test and safer to maintain.\n"""\n\nimport re\nfrom urllib.parse import urlparse\n\nfrom bs4 import BeautifulSoup\n\n'''


def main() -> None:
    if MODULE.exists():
        raise SystemExit("news_quality.py already exists; refusing a second extraction")

    text = AUTOMATION.read_text(encoding="utf-8")
    try:
        start = text.index(START_MARKER)
        end = text.index(END_MARKER, start)
    except ValueError as exc:
        raise SystemExit(f"Could not locate News quality block: {exc}") from exc

    block = text[start:end]
    discovery_start = block.index(DISCOVERY_MARKER)
    source_image_start = block.index(SOURCE_IMAGE_MARKER, discovery_start)

    # discovery_story_is_duplicate depends on repository-backed history that
    # intentionally remains in automation.py. Everything around it is pure.
    discovery_func = block[discovery_start:source_image_start].strip("\n")
    pure_block = (block[:discovery_start] + block[source_image_start:]).strip("\n")

    module_text = MODULE_HEADER + pure_block + "\n"
    replacement = IMPORT_BLOCK + discovery_func + "\n\n\n"
    new_text = text[:start] + replacement + text[end:]

    MODULE.write_text(module_text, encoding="utf-8")
    AUTOMATION.write_text(new_text, encoding="utf-8")

    old_size = len(text.encode("utf-8"))
    new_size = len(new_text.encode("utf-8"))
    print(f"automation.py: {old_size} -> {new_size} bytes")
    print(f"news_quality.py: {len(module_text.encode('utf-8'))} bytes")
    print(f"extracted: {old_size - new_size} bytes from the monolith")


if __name__ == "__main__":
    main()
