"""Search-provider pages and their logo images must never reach the site.

Regression: Tavily started returning its own company-profile pages
(tavily.com/knowledge/company/...) for a "Steam" query. They were published
as News with tavily.com/opengraph-image.png as the featured image.
"""

import os

os.environ.setdefault("TAVILY_API_KEY", "test-key")
os.environ.setdefault("GROQ_API_KEY", "test-key")

import news_quality


def test_tavily_pages_are_blocked_sources():
    assert news_quality.is_blocked_source(
        "https://tavily.com/knowledge/company/WhqALBQP3wDk"
    )
    assert news_quality.is_blocked_source("https://www.tavily.com/x")
    assert news_quality.is_blocked_source("https://app.tavily.com/x")
    assert not news_quality.is_blocked_source("https://www.ign.com/articles/x")
    assert not news_quality.is_blocked_source("https://nottavily.com/x")


def test_provider_and_site_wide_images_are_rejected():
    assert news_quality.is_site_default_image(
        "https://tavily.com/opengraph-image.png"
    )
    assert news_quality.is_site_default_image("https://example.com/og-image.jpg")
    assert not news_quality.is_site_default_image(
        "https://example.com/news/game/opengraph-image.png"
    )
    assert not news_quality.is_site_default_image(
        "https://assets-prd.ignimgs.com/2026/11/08/soooo.jpg"
    )
    assert not news_quality.is_site_default_image("")


def test_automation_image_filter_rejects_tavily_logo():
    import automation

    assert automation.image_url_looks_bad(
        "https://tavily.com/opengraph-image.png"
    )
    assert not automation.image_url_looks_bad(
        "https://images.nintendolife.com/18e28c0a27fab/1280x720.jpg"
    )
