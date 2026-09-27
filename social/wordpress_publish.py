"""Prepare, recover and clean temporary WordPress-backed Meta packages."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from social.master_carousel import (
    MASTER_REFERENCE_POST,
    MASTER_SPEC_VERSION,
    validate_master_copy,
    validate_master_package,
)
from social.prepare_publish import _carousel_version
from social.wordpress_media import cleanup_media, stage_carousel_media


OUTPUT_FILE = Path("social-output.json")
READY_FILE = Path("social-publish-ready.json")
PENDING_FILE = Path("social/pending_publish.json")
RENDERED_DIR = Path("social-rendered")


def _load_json(path: Path, *, required: bool = True):
    if not path.exists():
        if required:
            raise RuntimeError(f"Required file does not exist: {path}")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"Invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} must contain a JSON object.")
    return value


def _source_id(payload: dict) -> str:
    source_id = str(payload.get("source_id", "")).strip()
    if not source_id and isinstance(payload.get("selected"), dict):
        source_id = str(payload["selected"].get("source_id", "")).strip()
    if not source_id:
        raise RuntimeError("No source_id found in social-output.json.")
    return source_id


def _credentials():
    values = {
        "wp_url": str(os.getenv("WP_URL", "")).strip(),
        "username": str(os.getenv("WP_USERNAME", "")).strip(),
        "app_password": str(os.getenv("WP_APP_PASSWORD", "")).strip(),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Missing WordPress media staging configuration: " + ", ".join(missing)
        )
    return values


def stage_publish_package(
    *,
    social_output: dict,
    rendered_dir: Path = RENDERED_DIR,
    ready_file: Path = READY_FILE,
    pending_file: Path = PENDING_FILE,
    wp_url: str,
    username: str,
    app_password: str,
    session=None,
) -> dict:
    if social_output.get("status") != "ready":
        raise RuntimeError("Social output is not ready for publishing.")
    source_id = _source_id(social_output)
    image_paths = sorted(Path(rendered_dir).glob("slide-*.png"))
    if len(image_paths) != 3:
        raise RuntimeError("Exactly three rendered PNGs are required for staging.")

    # Permanent fail-closed quality gate.  If copy would be truncated, if the
    # canvas is not the approved 1080x1920 format, or if the rendered slides
    # are duplicated/malformed, nothing is uploaded to WordPress or Meta.
    validate_master_package(
        social_output=social_output,
        image_paths=image_paths,
    )

    kwargs = {
        "wp_url": wp_url,
        "username": username,
        "app_password": app_password,
    }
    if session is not None:
        kwargs["session"] = session
    staged = stage_carousel_media(image_paths, **kwargs)
    version = _carousel_version(image_paths)
    ready = {
        "source_id": source_id,
        "carousel_version": version,
        "image_urls": staged["image_urls"],
        "master_spec_version": MASTER_SPEC_VERSION,
    }
    pending = {
        **ready,
        "master_reference_post": MASTER_REFERENCE_POST,
        "media_ids": staged["media_ids"],
        "prepared_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "social_output": social_output,
    }
    ready_file.parent.mkdir(parents=True, exist_ok=True)
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    ready_file.write_text(
        json.dumps(ready, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    pending_file.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return pending


def recover_publish_package(
    *,
    pending_file: Path = PENDING_FILE,
    output_file: Path = OUTPUT_FILE,
    ready_file: Path = READY_FILE,
) -> dict:
    pending = _load_json(pending_file, required=False)
    if not pending:
        return {"ready": False, "reason": "no pending WordPress carousel found"}
    source_id = str(pending.get("source_id", "")).strip()
    version = str(pending.get("carousel_version", "")).strip()
    spec_version = str(pending.get("master_spec_version", "")).strip()
    image_urls = [
        str(url).strip()
        for url in pending.get("image_urls", [])
        if str(url).strip()
    ]
    social_output = pending.get("social_output")
    if (
        not source_id
        or not version
        or spec_version != MASTER_SPEC_VERSION
        or len(image_urls) != 3
        or len(set(image_urls)) != 3
        or not isinstance(social_output, dict)
        or social_output.get("status") != "ready"
    ):
        raise RuntimeError("Pending WordPress publish package is invalid or pre-master-spec.")

    # Recovery is allowed only for copy that still satisfies the current
    # master contract.  Requiring the spec version above prevents old pending
    # packages created before this gate from slipping through after deployment.
    validate_master_copy(social_output)

    social_output = dict(social_output)
    social_output["source_id"] = source_id
    ready = {
        "source_id": source_id,
        "carousel_version": version,
        "image_urls": image_urls,
        "master_spec_version": MASTER_SPEC_VERSION,
    }
    output_file.write_text(
        json.dumps(social_output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ready_file.write_text(
        json.dumps(ready, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "ready": True,
        "reason": "pending WordPress carousel restored",
        "source_id": source_id,
        "carousel_version": version,
    }


def cleanup_publish_package(
    *,
    pending_file: Path = PENDING_FILE,
    wp_url: str,
    username: str,
    app_password: str,
    session=None,
) -> dict:
    pending = _load_json(pending_file, required=False)
    if not pending:
        return {"cleaned": False, "reason": "no pending package"}
    media_ids = pending.get("media_ids", [])
    kwargs = {
        "wp_url": wp_url,
        "username": username,
        "app_password": app_password,
    }
    if session is not None:
        kwargs["session"] = session
    cleanup_media(media_ids, **kwargs)
    pending_file.unlink(missing_ok=True)
    return {
        "cleaned": True,
        "reason": "temporary WordPress media deleted",
        "media_ids": media_ids,
    }


def _write_outputs(result: dict) -> None:
    output_path = str(os.getenv("GITHUB_OUTPUT", "")).strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as output:
        for key in ("ready", "reason", "source_id", "carousel_version", "cleaned"):
            if key not in result:
                continue
            value = result[key]
            if isinstance(value, bool):
                value = "true" if value else "false"
            output.write(f"{key}={str(value).replace(chr(10), ' ')}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="GamerQuest WordPress social staging")
    parser.add_argument("command", choices=("stage", "recover", "cleanup"))
    args = parser.parse_args()

    if args.command == "stage":
        credentials = _credentials()
        result = stage_publish_package(
            social_output=_load_json(OUTPUT_FILE),
            **credentials,
        )
        print(f"Staged carousel {result['carousel_version']} in WordPress media.")
        print("Public image URLs:")
        for url in result["image_urls"]:
            print(f"- {url}")
        return 0

    if args.command == "recover":
        result = recover_publish_package()
        _write_outputs(result)
        print(f"SOCIAL RECOVERY READY: {result['ready']}")
        print(f"SOCIAL RECOVERY REASON: {result['reason']}")
        return 0

    credentials = _credentials()
    result = cleanup_publish_package(**credentials)
    _write_outputs(result)
    print(f"SOCIAL MEDIA CLEANED: {result['cleaned']}")
    print(f"SOCIAL MEDIA CLEANUP REASON: {result['reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
