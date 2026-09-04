import json
import re
import shutil
from pathlib import Path


DEFAULT_RENDERED_DIR = Path(
    "social-rendered"
)

DEFAULT_PUBLISHED_ROOT = Path(
    "social-published"
)


def _clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def _sanitize_folder_name(
    value,
):
    value = _clean_text(
        value
    )

    if not value:
        raise ValueError(
            "source_id is required."
        )

    value = value.lower()

    value = re.sub(
        r"[^a-z0-9_-]+",
        "-",
        value,
    )

    value = re.sub(
        r"-+",
        "-",
        value,
    )

    value = value.strip(
        "-_"
    )

    if not value:
        raise ValueError(
            "source_id produced an empty folder name."
        )

    return value


def _find_rendered_images(
    rendered_dir,
):
    rendered_dir = Path(
        rendered_dir
    )

    if not rendered_dir.exists():
        raise ValueError(
            "Rendered directory does not exist."
        )

    if not rendered_dir.is_dir():
        raise ValueError(
            "Rendered path is not a directory."
        )

    candidates = []

    for path in rendered_dir.iterdir():
        if not path.is_file():
            continue

        if path.suffix.lower() != ".png":
            continue

        candidates.append(
            path
        )

    candidates.sort(
        key=lambda path:
            path.name.lower()
    )

    if len(candidates) != 3:
        raise ValueError(
            "Exactly three rendered PNG images "
            "are required."
        )

    return candidates


def _relative_or_absolute(
    path,
    base_root,
):
    path = Path(
        path
    )

    base_root = Path(
        base_root
    )

    try:
        return str(
            path.relative_to(
                base_root
            )
        ).replace(
            "\\",
            "/",
        )

    except ValueError:
        return str(
            path
        ).replace(
            "\\",
            "/",
        )


def prepare_carousel_for_publish(
    source_id,
    rendered_dir=DEFAULT_RENDERED_DIR,
    published_root=DEFAULT_PUBLISHED_ROOT,
):
    source_id = _clean_text(
        source_id
    )

    if not source_id:
        raise ValueError(
            "source_id is required."
        )

    rendered_dir = Path(
        rendered_dir
    )

    published_root = Path(
        published_root
    )

    source_folder = (
        _sanitize_folder_name(
            source_id
        )
    )

    images = (
        _find_rendered_images(
            rendered_dir
        )
    )

    destination_dir = (
        published_root
        / source_folder
    )

    destination_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    copied_paths = []

    for index, source_image in enumerate(
        images,
        start=1,
    ):
        destination_path = (
            destination_dir
            / f"slide-{index}.png"
        )

        shutil.copy2(
            source_image,
            destination_path,
        )

        copied_paths.append(
            destination_path
        )

    base_root = (
        published_root.parent
    )

    image_paths = [
        _relative_or_absolute(
            path,
            base_root,
        )
        for path in copied_paths
    ]

    manifest_path = (
        destination_dir
        / "manifest.json"
    )

    manifest_payload = {
        "source_id":
            source_id,

        "folder_name":
            source_folder,

        "image_paths":
            image_paths,
    }

    with manifest_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            manifest_payload,
            file,
            ensure_ascii=False,
            indent=2,
        )

    manifest_value = (
        _relative_or_absolute(
            manifest_path,
            base_root,
        )
    )

    return {
        "source_id":
            source_id,

        "folder_name":
            source_folder,

        "image_paths":
            image_paths,

        "manifest":
            manifest_value,
    }
