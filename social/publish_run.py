import json
import os
import time
import urllib.request
from pathlib import Path

from social.meta_publisher import (
    build_caption,
    load_publish_history,
    save_publish_history,
    publish_instagram_carousel,
    publish_facebook_carousel,
)

DEFAULT_OUTPUT_FILE = Path("social-output.json")
DEFAULT_READY_FILE = Path("social-publish-ready.json")
DEFAULT_HISTORY_FILE = Path("social/publish_history.json")
PUBLIC_URL_ATTEMPTS = 6
PUBLIC_URL_WAIT_SECONDS = 10
PUBLISH_ATTEMPTS = 3


def _clean(value):
    return "" if value is None else str(value).strip()


def _require_env(name):
    value = _clean(os.getenv(name))
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _load_json(path):
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"Required file does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Invalid JSON file: {path}") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a JSON object.")
    return payload


def extract_publish_package(social_output, publish_ready):
    if not isinstance(social_output, dict) or not isinstance(publish_ready, dict):
        raise RuntimeError("Social publish payload is invalid.")
    if social_output.get("status") != "ready":
        raise RuntimeError("Social output is not ready for publishing.")
    output_source_id = _clean(social_output.get("source_id"))
    ready_source_id = _clean(publish_ready.get("source_id"))
    if not output_source_id or not ready_source_id:
        raise RuntimeError("Missing source_id in publish package.")
    if output_source_id != ready_source_id:
        raise RuntimeError("Source ID mismatch between social output and prepared images.")
    image_urls = [_clean(url) for url in publish_ready.get("image_urls", []) if _clean(url)]
    if len(image_urls) != 3 or len(set(image_urls)) != 3:
        raise RuntimeError("Exactly three distinct prepared image URLs are required.")
    carousel_version = _clean(publish_ready.get("carousel_version"))
    if not carousel_version:
        raise RuntimeError("carousel_version is required for safe publishing.")
    return {
        "source_id": output_source_id,
        "carousel_version": carousel_version,
        "image_urls": image_urls,
        "caption": build_caption(
            social_output.get("caption", ""),
            social_output.get("hashtags", []),
        ),
    }


def pending_platforms(source_id, history, carousel_version=""):
    source_id = _clean(source_id)
    carousel_version = _clean(carousel_version)
    if not source_id:
        raise ValueError("source_id is required.")
    if not isinstance(history, dict):
        history = {}
    source_history = history.get(source_id, {})
    if not isinstance(source_history, dict):
        source_history = {}
    pending = []
    for platform in ("instagram", "facebook"):
        item = source_history.get(platform, {})
        if not isinstance(item, dict) or item.get("published") is not True:
            pending.append(platform)
            continue
        stored_version = _clean(item.get("carousel_version"))
        if not stored_version:
            continue
        if carousel_version and stored_version != carousel_version:
            pending.append(platform)
    return pending


def _mark_platform(history, source_id, platform, published, post_id="", error="", carousel_version=""):
    if not isinstance(history, dict):
        history = {}
    source_history = history.setdefault(source_id, {})
    payload = {"published": bool(published), "post_id": _clean(post_id)}
    if carousel_version:
        payload["carousel_version"] = _clean(carousel_version)
    if error:
        payload["error"] = _clean(error)
    source_history[platform] = payload
    return history


def _backfill_legacy_versions(history, source_id, version):
    changed = False
    source_history = history.get(source_id, {}) if isinstance(history, dict) else {}
    if not isinstance(source_history, dict):
        return False
    for platform in ("instagram", "facebook"):
        item = source_history.get(platform)
        if isinstance(item, dict) and item.get("published") is True and not _clean(item.get("carousel_version")):
            item["carousel_version"] = version
            changed = True
    return changed


def _url_is_public(url):
    try:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "GamerQuest-Social-Publisher/1.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            return 200 <= response.status < 400
    except Exception:
        return False


def wait_for_public_urls(image_urls, attempts=PUBLIC_URL_ATTEMPTS, wait_seconds=PUBLIC_URL_WAIT_SECONDS):
    print("Checking that Meta can access the three public carousel images...")
    for attempt in range(1, attempts + 1):
        unavailable = [url for url in image_urls if not _url_is_public(url)]
        if not unavailable:
            print("All three carousel images are publicly available.")
            return True
        print(f"Public image check {attempt}/{attempts}: {len(unavailable)} unavailable.")
        if attempt < attempts:
            time.sleep(wait_seconds)
    raise RuntimeError("Prepared carousel images are not publicly available; publishing stopped.")


def _is_transient(error):
    text = str(error).lower()
    return any(token in text for token in (
        "http status: 429", "http status: 500", "http status: 502", "http status: 503",
        "http status: 504", "temporar", "timeout", "timed out", "connection reset", "connection aborted",
    ))


def _publish_with_retry(label, fn):
    last_error = None
    for attempt in range(1, PUBLISH_ATTEMPTS + 1):
        try:
            return fn()
        except Exception as error:
            last_error = error
            if attempt >= PUBLISH_ATTEMPTS or not _is_transient(error):
                raise
            wait = attempt * 5
            print(f"{label} transient failure {attempt}/{PUBLISH_ATTEMPTS}; retrying in {wait}s: {error}")
            time.sleep(wait)
    raise last_error


def run_publish(output_file=DEFAULT_OUTPUT_FILE, ready_file=DEFAULT_READY_FILE, history_file=DEFAULT_HISTORY_FILE, wait_for_urls=True):
    print("\n======================================")
    print("GAMERQUEST META PUBLISHER")
    print("======================================")
    package = extract_publish_package(_load_json(output_file), _load_json(ready_file))
    source_id = package["source_id"]
    version = package["carousel_version"]
    image_urls = package["image_urls"]
    caption = package["caption"]
    history = load_publish_history(history_file)
    pending = pending_platforms(source_id, history, version)
    print(f"Source ID: {source_id}")
    print(f"Carousel version: {version}")
    print("Pending platforms: " + (", ".join(pending) if pending else "none"))
    if not pending:
        if _backfill_legacy_versions(history, source_id, version):
            save_publish_history(history, history_file)
            print("Legacy publish history baselined to this carousel version.")
        print("This exact carousel version has already been published.")
        return {"status": "already_published", "source_id": source_id, "carousel_version": version}
    if wait_for_urls:
        wait_for_public_urls(image_urls)

    results = {"status": "publishing", "source_id": source_id, "carousel_version": version}
    errors = []

    if "instagram" in pending:
        print("\nPublishing to Instagram...")
        try:
            token = _require_env("META_IG_ACCESS_TOKEN")
            ig_user_id = _require_env("META_IG_USER_ID")
            result = _publish_with_retry("Instagram", lambda: publish_instagram_carousel(
                image_urls=image_urls, caption=caption, ig_user_id=ig_user_id, access_token=token
            ))
            post_id = _clean(result.get("post_id"))
            if not post_id:
                raise RuntimeError("Instagram publish returned no media ID.")
            history = _mark_platform(history, source_id, "instagram", True, post_id=post_id, carousel_version=version)
            save_publish_history(history, history_file)
            results["instagram"] = result
            print(f"Instagram published successfully. Media ID: {post_id}")
        except Exception as error:
            history = _mark_platform(history, source_id, "instagram", False, error=str(error), carousel_version=version)
            save_publish_history(history, history_file)
            errors.append(f"Instagram failed: {error}")
    else:
        print("Instagram exact version already published. Skipping.")

    if "facebook" in pending:
        print("\nPublishing to Facebook...")
        try:
            token = _require_env("META_FB_PAGE_ACCESS_TOKEN")
            page_id = _require_env("META_PAGE_ID")
            result = _publish_with_retry("Facebook", lambda: publish_facebook_carousel(
                image_urls=image_urls, caption=caption, page_id=page_id, access_token=token
            ))
            post_id = _clean(result.get("post_id"))
            if not post_id:
                raise RuntimeError("Facebook publish returned no post ID.")
            history = _mark_platform(history, source_id, "facebook", True, post_id=post_id, carousel_version=version)
            save_publish_history(history, history_file)
            results["facebook"] = result
            print(f"Facebook published successfully. Post ID: {post_id}")
        except Exception as error:
            history = _mark_platform(history, source_id, "facebook", False, error=str(error), carousel_version=version)
            save_publish_history(history, history_file)
            errors.append(f"Facebook failed: {error}")
    else:
        print("Facebook exact version already published. Skipping.")

    if errors:
        results["status"] = "partial_failure"
        results["errors"] = errors
        raise RuntimeError(" | ".join(errors))
    results["status"] = "published"
    print("\n======================================")
    print("META PUBLISHING SUCCESS")
    print("======================================")
    return results


def main():
    run_publish()


if __name__ == "__main__":
    main()
