import json
import os
from pathlib import Path


# =========================================================
# CONFIG
# =========================================================

GRAPH_API_VERSION = os.getenv(
    "META_GRAPH_API_VERSION",
    "v26.0",
).strip() or "v26.0"

INSTAGRAM_GRAPH_BASE_URL = (
    f"https://graph.instagram.com/"
    f"{GRAPH_API_VERSION}"
)

FACEBOOK_GRAPH_BASE_URL = (
    f"https://graph.facebook.com/"
    f"{GRAPH_API_VERSION}"
)

DEFAULT_TIMEOUT = 60

DEFAULT_PUBLISH_HISTORY_FILE = Path(
    "social/publish_history.json"
)


# =========================================================
# VALIDATION
# =========================================================

def _clean_text(value):
    if value is None:
        return ""

    return str(value).strip()


def _validate_three_images(
    image_urls,
):
    if not isinstance(
        image_urls,
        list,
    ):
        raise ValueError(
            "image_urls must be a list."
        )

    cleaned = [
        _clean_text(url)
        for url in image_urls
        if _clean_text(url)
    ]

    if len(cleaned) != 3:
        raise ValueError(
            "Exactly three image URLs "
            "are required."
        )

    for url in cleaned:
        if not (
            url.startswith("https://")
            or url.startswith("http://")
        ):
            raise ValueError(
                "Every image must use "
                "a public HTTP(S) URL."
            )

    return cleaned


def _require_value(
    value,
    name,
):
    cleaned = _clean_text(
        value
    )

    if not cleaned:
        raise ValueError(
            f"{name} is required."
        )

    return cleaned


# =========================================================
# REQUESTS
# =========================================================

def _get_requests_module(
    requests_module=None,
):
    if requests_module is not None:
        return requests_module

    try:
        import requests

        return requests

    except ImportError as error:
        raise RuntimeError(
            "The requests package is required "
            "for Meta publishing."
        ) from error


def _response_json(
    response,
):
    try:
        payload = response.json()

    except Exception as error:
        raise RuntimeError(
            "Meta returned an invalid "
            "JSON response."
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "Meta returned an unexpected "
            "response."
        )

    return payload


def _post(
    requests_module,
    url,
    data,
):
    response = requests_module.post(
        url,
        data=data,
        timeout=DEFAULT_TIMEOUT,
    )

    response.raise_for_status()

    payload = _response_json(
        response
    )

    if "error" in payload:
        error = payload.get(
            "error",
            {},
        )

        if isinstance(
            error,
            dict,
        ):
            message = (
                error.get(
                    "message"
                )
                or "Unknown Meta error"
            )

        else:
            message = str(
                error
            )

        raise RuntimeError(
            f"Meta API error: {message}"
        )

    return payload


# =========================================================
# GITHUB RAW URLS
# =========================================================

def build_raw_github_urls(
    image_paths,
    repository=(
        "RizkAdham96/"
        "gamerquest-automation"
    ),
    branch="main",
):
    """
    Convert repository file paths into
    public raw.githubusercontent.com URLs.
    """

    repository = _require_value(
        repository,
        "repository",
    )

    branch = _require_value(
        branch,
        "branch",
    )

    if not isinstance(
        image_paths,
        list,
    ):
        raise ValueError(
            "image_paths must be a list."
        )

    urls = []

    for path in image_paths:
        clean_path = (
            _clean_text(
                path
            )
            .replace("\\", "/")
            .lstrip("/")
        )

        if not clean_path:
            continue

        url = (
            "https://raw.githubusercontent.com/"
            f"{repository}/"
            f"{branch}/"
            f"{clean_path}"
        )

        urls.append(
            url
        )

    return urls


# =========================================================
# CAPTION
# =========================================================

def build_caption(
    caption,
    hashtags=None,
):
    caption = _clean_text(
        caption
    )

    if not isinstance(
        hashtags,
        list,
    ):
        hashtags = []

    clean_hashtags = []

    for hashtag in hashtags:
        hashtag = _clean_text(
            hashtag
        )

        if not hashtag:
            continue

        if not hashtag.startswith(
            "#"
        ):
            hashtag = (
                f"#{hashtag}"
            )

        clean_hashtags.append(
            hashtag
        )

    hashtag_text = " ".join(
        clean_hashtags
    )

    if (
        caption
        and hashtag_text
    ):
        return (
            f"{caption}\n\n"
            f"{hashtag_text}"
        )

    if caption:
        return caption

    return hashtag_text


# =========================================================
# PUBLISH HISTORY
# =========================================================

def load_publish_history(
    history_file=DEFAULT_PUBLISH_HISTORY_FILE,
):
    history_file = Path(
        history_file
    )

    if not history_file.exists():
        return {}

    try:
        with history_file.open(
            "r",
            encoding="utf-8",
        ) as file:
            payload = json.load(
                file
            )

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return {}

    if not isinstance(
        payload,
        dict,
    ):
        return {}

    return payload


def save_publish_history(
    history,
    history_file=DEFAULT_PUBLISH_HISTORY_FILE,
):
    if not isinstance(
        history,
        dict,
    ):
        raise ValueError(
            "Publish history must "
            "be a dictionary."
        )

    history_file = Path(
        history_file
    )

    history_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with history_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            history,
            file,
            ensure_ascii=False,
            indent=2,
        )


def pending_platforms(
    source_id,
    history,
):
    source_id = _require_value(
        source_id,
        "source_id",
    )

    if not isinstance(
        history,
        dict,
    ):
        history = {}

    source_history = history.get(
        source_id,
        {},
    )

    if not isinstance(
        source_history,
        dict,
    ):
        source_history = {}

    pending = []

    for platform in (
        "instagram",
        "facebook",
    ):
        platform_history = (
            source_history.get(
                platform,
                {},
            )
        )

        published = False

        if isinstance(
            platform_history,
            dict,
        ):
            published = (
                platform_history.get(
                    "published"
                )
                is True
            )

        if not published:
            pending.append(
                platform
            )

    return pending


def mark_platform_published(
    history,
    source_id,
    platform,
    post_id,
):
    if not isinstance(
        history,
        dict,
    ):
        history = {}

    source_id = _require_value(
        source_id,
        "source_id",
    )

    platform = _require_value(
        platform,
        "platform",
    )

    if platform not in (
        "instagram",
        "facebook",
    ):
        raise ValueError(
            "Unsupported platform."
        )

    source_history = history.setdefault(
        source_id,
        {},
    )

    source_history[
        platform
    ] = {
        "published": True,
        "post_id": _clean_text(
            post_id
        ),
    }

    return history


def mark_platform_failed(
    history,
    source_id,
    platform,
    error_message="",
):
    if not isinstance(
        history,
        dict,
    ):
        history = {}

    source_id = _require_value(
        source_id,
        "source_id",
    )

    platform = _require_value(
        platform,
        "platform",
    )

    if platform not in (
        "instagram",
        "facebook",
    ):
        raise ValueError(
            "Unsupported platform."
        )

    source_history = history.setdefault(
        source_id,
        {},
    )

    previous = source_history.get(
        platform,
        {},
    )

    post_id = ""

    if isinstance(
        previous,
        dict,
    ):
        post_id = _clean_text(
            previous.get(
                "post_id"
            )
        )

    source_history[
        platform
    ] = {
        "published": False,
        "post_id": post_id,
        "error": _clean_text(
            error_message
        ),
    }

    return history


# =========================================================
# INSTAGRAM
# =========================================================

def publish_instagram_carousel(
    image_urls,
    caption,
    ig_user_id,
    access_token,
    requests_module=None,
):
    """
    Publish exactly three images as
    an Instagram carousel.

    Instagram Login API uses:
    graph.instagram.com
    """

    image_urls = (
        _validate_three_images(
            image_urls
        )
    )

    ig_user_id = _require_value(
        ig_user_id,
        "ig_user_id",
    )

    access_token = _require_value(
        access_token,
        "access_token",
    )

    caption = _clean_text(
        caption
    )

    requests_module = (
        _get_requests_module(
            requests_module
        )
    )

    media_endpoint = (
        f"{INSTAGRAM_GRAPH_BASE_URL}/"
        f"{ig_user_id}/media"
    )

    publish_endpoint = (
        f"{INSTAGRAM_GRAPH_BASE_URL}/"
        f"{ig_user_id}/media_publish"
    )

    child_ids = []

    # -----------------------------------------------------
    # CREATE THREE CAROUSEL CHILDREN
    # -----------------------------------------------------

    for image_url in image_urls:
        payload = _post(
            requests_module,
            media_endpoint,
            {
                "image_url":
                    image_url,

                "is_carousel_item":
                    True,

                "access_token":
                    access_token,
            },
        )

        child_id = _clean_text(
            payload.get(
                "id"
            )
        )

        if not child_id:
            raise RuntimeError(
                "Instagram did not return "
                "a child media container ID."
            )

        child_ids.append(
            child_id
        )

    # -----------------------------------------------------
    # CREATE CAROUSEL PARENT
    # -----------------------------------------------------

    parent_payload = _post(
        requests_module,
        media_endpoint,
        {
            "media_type":
                "CAROUSEL",

            "children":
                ",".join(
                    child_ids
                ),

            "caption":
                caption,

            "access_token":
                access_token,
        },
    )

    creation_id = _clean_text(
        parent_payload.get(
            "id"
        )
    )

    if not creation_id:
        raise RuntimeError(
            "Instagram did not return "
            "a carousel creation ID."
        )

    # -----------------------------------------------------
    # PUBLISH
    # -----------------------------------------------------

    publish_payload = _post(
        requests_module,
        publish_endpoint,
        {
            "creation_id":
                creation_id,

            "access_token":
                access_token,
        },
    )

    post_id = _clean_text(
        publish_payload.get(
            "id"
        )
    )

    if not post_id:
        raise RuntimeError(
            "Instagram did not return "
            "a published media ID."
        )

    return {
        "published":
            True,

        "platform":
            "instagram",

        "post_id":
            post_id,

        "creation_id":
            creation_id,

        "children":
            child_ids,
    }


# =========================================================
# FACEBOOK
# =========================================================

def publish_facebook_carousel(
    image_urls,
    caption,
    page_id,
    access_token,
    requests_module=None,
):
    """
    Publish exactly three images as
    one Facebook Page multi-photo post.

    Facebook Page API uses:
    graph.facebook.com
    """

    image_urls = (
        _validate_three_images(
            image_urls
        )
    )

    page_id = _require_value(
        page_id,
        "page_id",
    )

    access_token = _require_value(
        access_token,
        "access_token",
    )

    caption = _clean_text(
        caption
    )

    requests_module = (
        _get_requests_module(
            requests_module
        )
    )

    photos_endpoint = (
        f"{FACEBOOK_GRAPH_BASE_URL}/"
        f"{page_id}/photos"
    )

    feed_endpoint = (
        f"{FACEBOOK_GRAPH_BASE_URL}/"
        f"{page_id}/feed"
    )

    photo_ids = []

    # -----------------------------------------------------
    # UPLOAD THREE UNPUBLISHED PHOTOS
    # -----------------------------------------------------

    for image_url in image_urls:
        payload = _post(
            requests_module,
            photos_endpoint,
            {
                "url":
                    image_url,

                "published":
                    False,

                "access_token":
                    access_token,
            },
        )

        photo_id = _clean_text(
            payload.get(
                "id"
            )
        )

        if not photo_id:
            raise RuntimeError(
                "Facebook did not return "
                "an uploaded photo ID."
            )

        photo_ids.append(
            photo_id
        )

    # -----------------------------------------------------
    # CREATE ONE MULTI-PHOTO PAGE POST
    # -----------------------------------------------------

    post_data = {
        "message":
            caption,

        "access_token":
            access_token,
    }

    for index, photo_id in enumerate(
        photo_ids
    ):
        post_data[
            f"attached_media[{index}]"
        ] = json.dumps(
            {
                "media_fbid":
                    photo_id
            }
        )

    payload = _post(
        requests_module,
        feed_endpoint,
        post_data,
    )

    post_id = _clean_text(
        payload.get(
            "id"
        )
    )

    if not post_id:
        raise RuntimeError(
            "Facebook did not return "
            "a Page post ID."
        )

    return {
        "published":
            True,

        "platform":
            "facebook",

        "post_id":
            post_id,

        "photo_ids":
            photo_ids,
    }
