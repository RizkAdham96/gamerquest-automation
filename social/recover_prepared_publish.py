import json
import os
from datetime import datetime
from pathlib import Path

from social.meta_publisher import build_raw_github_urls
from social.publish_run import pending_platforms


PUBLISHED_ROOT = Path("social-published")
HISTORY_FILE = Path("social/publish_history.json")
OUTPUT_FILE = Path("social-output.json")
READY_FILE = Path("social-publish-ready.json")


def _load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return value


def _prepared_timestamp(manifest):
    raw = str(manifest.get("prepared_at_utc", "")).strip()
    if not raw:
        return datetime.min
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return datetime.min


def find_latest_pending_package():
    history = _load_json(HISTORY_FILE, {})
    if not isinstance(history, dict):
        history = {}

    candidates = []
    for manifest_path in PUBLISHED_ROOT.glob("*/manifest.json"):
        manifest = _load_json(manifest_path, {})
        if not isinstance(manifest, dict):
            continue
        social_output = manifest.get("social_output")
        if not isinstance(social_output, dict) or social_output.get("status") != "ready":
            continue
        source_id = str(manifest.get("source_id", "")).strip()
        version = str(manifest.get("carousel_version", "")).strip()
        image_paths = manifest.get("image_paths", [])
        if not source_id or not version or not isinstance(image_paths, list) or len(image_paths) != 3:
            continue
        if not pending_platforms(source_id, history, version):
            continue
        candidates.append((_prepared_timestamp(manifest), manifest_path, manifest))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][2]


def prepare_recovery_files(repository="RizkAdham96/gamerquest-automation", branch="main"):
    manifest = find_latest_pending_package()
    if manifest is None:
        return {"ready": False, "reason": "no prepared unpublished carousel found"}

    social_output = dict(manifest["social_output"])
    source_id = str(manifest["source_id"]).strip()
    social_output["source_id"] = source_id
    social_output["status"] = "ready"

    image_urls = build_raw_github_urls(
        image_paths=manifest["image_paths"],
        repository=repository,
        branch=branch,
    )
    if len(image_urls) != 3 or len(set(image_urls)) != 3:
        raise RuntimeError("Recovery package does not contain three distinct public images.")

    ready = {
        "source_id": source_id,
        "carousel_version": str(manifest["carousel_version"]).strip(),
        "image_urls": image_urls,
    }
    OUTPUT_FILE.write_text(json.dumps(social_output, ensure_ascii=False, indent=2), encoding="utf-8")
    READY_FILE.write_text(json.dumps(ready, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "ready": True,
        "reason": "prepared unpublished carousel restored",
        "source_id": source_id,
        "carousel_version": ready["carousel_version"],
    }


def main():
    result = prepare_recovery_files(
        repository=os.getenv("GITHUB_REPOSITORY", "RizkAdham96/gamerquest-automation"),
        branch=os.getenv("GITHUB_REF_NAME", "main"),
    )
    print(f"SOCIAL RECOVERY READY: {result['ready']}")
    print(f"SOCIAL RECOVERY REASON: {result['reason']}")
    output_path = os.getenv("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"ready={'true' if result['ready'] else 'false'}\n")
            output.write(f"reason={result['reason']}\n")
            if result.get("source_id"):
                output.write(f"source_id={result['source_id']}\n")


if __name__ == "__main__":
    main()
