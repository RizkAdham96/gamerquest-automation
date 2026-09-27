"""Temporary public media staging for Meta carousel publishing.

Images are uploaded to the existing GamerQuest WordPress media library so Meta
can fetch them immediately without committing binary files to Git.  Callers
keep the returned attachment IDs until publishing succeeds, then delete them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import requests


DEFAULT_TIMEOUT = 30


def _clean(value):
    return "" if value is None else str(value).strip()


def _media_endpoint(wp_url: str) -> str:
    base = _clean(wp_url).rstrip("/")
    if not base:
        raise ValueError("wp_url is required.")
    return f"{base}/wp-json/wp/v2/media"


def _auth(username: str, app_password: str):
    username = _clean(username)
    app_password = _clean(app_password)
    if not username or not app_password:
        raise ValueError("WordPress username and application password are required.")
    return username, app_password


def cleanup_media(
    media_ids: Iterable[int],
    *,
    wp_url: str,
    username: str,
    app_password: str,
    session=requests,
    timeout: int = DEFAULT_TIMEOUT,
) -> None:
    """Delete temporary WordPress attachments after Meta has consumed them."""
    endpoint = _media_endpoint(wp_url)
    auth = _auth(username, app_password)
    errors = []
    for raw_id in media_ids:
        try:
            media_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if media_id <= 0:
            continue
        try:
            response = session.delete(
                f"{endpoint}/{media_id}?force=true",
                auth=auth,
                timeout=timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            errors.append(f"{media_id}: {exc}")
    if errors:
        raise RuntimeError(
            "Unable to clean up some temporary WordPress media: "
            + " | ".join(errors)
        )


def stage_carousel_media(
    image_paths: Iterable[Path | str],
    *,
    wp_url: str,
    username: str,
    app_password: str,
    session=requests,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Upload exactly three PNGs and return their public URLs + attachment IDs.

    A partial upload is rolled back if a later image fails, preventing orphaned
    media from accumulating on the site.
    """
    paths = [Path(path) for path in image_paths]
    if len(paths) != 3:
        raise ValueError("Exactly three carousel images are required.")
    if len({path.name for path in paths}) != 3:
        raise ValueError("Carousel image names must be distinct.")
    for path in paths:
        if not path.is_file() or path.suffix.lower() != ".png":
            raise ValueError(f"Carousel image is missing or not PNG: {path}")

    endpoint = _media_endpoint(wp_url)
    auth = _auth(username, app_password)
    media_ids = []
    image_urls = []

    try:
        for index, path in enumerate(paths, start=1):
            response = session.post(
                endpoint,
                data=path.read_bytes(),
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="gamerquest-social-{index}-{path.name}"'
                    ),
                    "Content-Type": "image/png",
                },
                auth=auth,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()
            media_id = int(payload.get("id", 0) or 0)
            source_url = _clean(payload.get("source_url"))
            if media_id <= 0 or not source_url.startswith(("https://", "http://")):
                raise RuntimeError(
                    "WordPress media upload returned no usable id/source_url."
                )
            media_ids.append(media_id)
            image_urls.append(source_url)
    except Exception:
        if media_ids:
            try:
                cleanup_media(
                    media_ids,
                    wp_url=wp_url,
                    username=username,
                    app_password=app_password,
                    session=session,
                    timeout=timeout,
                )
            except Exception:
                pass
        raise

    if len(set(image_urls)) != 3:
        try:
            cleanup_media(
                media_ids,
                wp_url=wp_url,
                username=username,
                app_password=app_password,
                session=session,
                timeout=timeout,
            )
        finally:
            raise RuntimeError("WordPress returned duplicate public image URLs.")

    return {
        "media_ids": media_ids,
        "image_urls": image_urls,
    }
