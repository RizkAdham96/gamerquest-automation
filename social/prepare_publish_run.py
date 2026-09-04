import json
from pathlib import Path

from social.prepare_publish import (
    prepare_carousel_for_publish,
)
from social.meta_publisher import (
    build_raw_github_urls,
)


OUTPUT_FILE = Path("social-output.json")
RENDERED_DIR = Path("social-rendered")
PUBLISHED_ROOT = Path("social-published")
READY_FILE = Path("social-publish-ready.json")


def load_social_output():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "social-output.json does not exist."
        )

    with OUTPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise RuntimeError(
            "social-output.json must contain "
            "a JSON object."
        )

    return payload


def get_source_id(payload):
    source_id = str(
        payload.get("source_id", "")
    ).strip()

    if source_id:
        return source_id

    selected = payload.get(
        "selected",
        {},
    )

    if isinstance(selected, dict):
        source_id = str(
            selected.get(
                "source_id",
                "",
            )
        ).strip()

    if not source_id:
        raise RuntimeError(
            "No source_id found in "
            "social-output.json."
        )

    return source_id


def write_publish_ready_file(
    source_id,
    image_paths,
):
    image_urls = build_raw_github_urls(
        image_paths=image_paths,
        repository=(
            "RizkAdham96/"
            "gamerquest-automation"
        ),
        branch="main",
    )

    if len(image_urls) != 3:
        raise RuntimeError(
            "Exactly three public image URLs "
            "are required."
        )

    payload = {
        "source_id": source_id,
        "image_urls": image_urls,
    }

    with READY_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return payload


def main():
    payload = load_social_output()

    source_id = get_source_id(
        payload
    )

    result = prepare_carousel_for_publish(
        source_id=source_id,
        rendered_dir=RENDERED_DIR,
        published_root=PUBLISHED_ROOT,
    )

    ready_payload = write_publish_ready_file(
        source_id=result["source_id"],
        image_paths=result["image_paths"],
    )

    print(
        "Carousel prepared for publishing."
    )

    print(
        f"Source ID: {result['source_id']}"
    )

    print(
        f"Folder: {result['folder_name']}"
    )

    print("Images:")

    for image_path in result[
        "image_paths"
    ]:
        print(
            f"- {image_path}"
        )

    print(
        f"Manifest: {result['manifest']}"
    )

    print(
        f"Publish-ready file: {READY_FILE}"
    )

    print(
        "Public image URLs:"
    )

    for image_url in ready_payload[
        "image_urls"
    ]:
        print(
            f"- {image_url}"
        )


if __name__ == "__main__":
    main()
