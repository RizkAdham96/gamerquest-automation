from social.config import (
    BRAND_NAME,
    WEBSITE_URL,
    CAROUSEL_MIN_SLIDES,
    CAROUSEL_MAX_SLIDES,
)


def clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def normalize_slides(slides):
    if not isinstance(slides, list):
        return []

    cleaned = []

    for slide in slides:
        if not isinstance(slide, dict):
            continue

        title = clean_text(slide.get("title"))
        body = clean_text(slide.get("body"))

        if not title and not body:
            continue

        cleaned.append(
            {
                "title": title,
                "body": body,
                "visual_prompt": clean_text(
                    slide.get("visual_prompt")
                ),
            }
        )

    return cleaned[:CAROUSEL_MAX_SLIDES]


def build_carousel(idea):
    if not isinstance(idea, dict):
        return None

    slides = normalize_slides(idea.get("slides", []))

    if len(slides) < CAROUSEL_MIN_SLIDES:
        return None

    carousel = {
        "topic": clean_text(idea.get("topic")),
        "angle": clean_text(idea.get("angle")),
        "format": clean_text(idea.get("format")),
        "hook": clean_text(idea.get("hook")),
        "score": idea.get("total_score", 0),
        "slides": slides,
        "caption": clean_text(idea.get("caption")),
        "cta": clean_text(idea.get("cta")),
        "website_url": WEBSITE_URL,
        "brand": BRAND_NAME,
    }

    if not carousel["cta"]:
        carousel["cta"] = f"Read more on {WEBSITE_URL}"

    return carousel
