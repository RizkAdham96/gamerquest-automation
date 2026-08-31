import html
import ipaddress
import json
import os
import re
import socket
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import (
    parse_qsl,
    parse_qs,
    quote_plus,
    urlencode,
    urlparse,
    urlunparse,
)
from urllib.request import Request, urlopen

from groq import Groq, RateLimitError


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"
RESEARCH_FILE = BASE_DIR / "research_results.json"


# =========================================================
# CONFIG
# =========================================================

ALLOWED_STATUSES = {
    "CONFIRMED",
    "UNCONFIRMED",
    "UNKNOWN",
}

FETCH_TIMEOUT_SECONDS = 12
MAX_PAGE_BYTES = 2_000_000
MAX_EXTRACTED_CHARS = 25_000

MAX_DISCOVERY_RESULTS = 10
MAX_DISCOVERED_SOURCES_TO_FETCH = 6

MAX_CLAIMS_PER_RUN = 3
MAX_EVIDENCE_SOURCES_FOR_AI = 5
MAX_EVIDENCE_CHARS_PER_SOURCE = 6_000

GROQ_API_KEY = os.environ.get(
    "GROQ_API_KEY",
    "",
)

GROQ_MODEL = "openai/gpt-oss-120b"

GROQ_MAX_RETRIES = 3
GROQ_DEFAULT_WAIT_SECONDS = 10

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; GamerQuestFR-Research/8.0; "
    "+https://gamerquestfr.com/)"
)


# Free/public feeds only.
# Any feed that becomes unavailable simply fails safely.
PUBLIC_GAMING_FEEDS = [
    {
        "url": "https://www.pcgamer.com/rss/",
        "publisher": "PC Gamer",
        "source_type": "publisher",
    },
    {
        "url": "https://www.gamesradar.com/rss/",
        "publisher": "GamesRadar+",
        "source_type": "publisher",
    },
    {
        "url": "https://www.gamespot.com/feeds/mashup/",
        "publisher": "GameSpot",
        "source_type": "publisher",
    },
]


TRACKING_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "utm_id",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


SEARCH_HOSTS = {
    "google.com",
    "www.google.com",
    "news.google.com",
    "bing.com",
    "www.bing.com",
}


# =========================================================
# GROQ
# =========================================================

if GROQ_API_KEY:

    GROQ_CLIENT = Groq(
        api_key=GROQ_API_KEY,
        max_retries=0,
    )

else:

    GROQ_CLIENT = None


# =========================================================
# JSON FILE HELPERS
# =========================================================

def load_json(path):

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def save_json(path, data):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )

        file.write("\n")

    temporary_file.replace(path)


# =========================================================
# CLAIM SAFETY
# =========================================================

def normalize_claim_status(status):

    if not isinstance(status, str):
        return "UNKNOWN"

    normalized = (
        status
        .strip()
        .upper()
    )

    if normalized not in ALLOWED_STATUSES:
        return "UNKNOWN"

    return normalized


def should_allow_claim(status):

    return (
        normalize_claim_status(status)
        == "CONFIRMED"
    )


def _claim_sources(claim):

    sources = claim.get(
        "sources",
        [],
    )

    if not isinstance(sources, list):
        sources = []

    source_url = str(
        claim.get(
            "source_url",
            "",
        )
        or ""
    ).strip()

    if (
        source_url
        and source_url not in sources
    ):

        sources.append(
            source_url
        )

    return sources


def build_verified_fact_pack(claims):

    confirmed_facts = []
    blocked_claims = []

    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):
            continue

        item = dict(claim)

        status = normalize_claim_status(
            item.get(
                "status",
                "UNKNOWN",
            )
        )

        sources = _claim_sources(
            item
        )

        item["status"] = status
        item["sources"] = sources

        if (
            status == "CONFIRMED"
            and not sources
        ):

            status = "UNKNOWN"
            item["status"] = status

        if should_allow_claim(
            status
        ):

            confirmed_facts.append(
                item
            )

        else:

            blocked_claims.append(
                item
            )

    return {
        "confirmed_facts": confirmed_facts,
        "blocked_claims": blocked_claims,
    }


# =========================================================
# HTML EXTRACTION
# =========================================================

def clean_html_text(raw_html):

    if not raw_html:
        return ""

    text = str(
        raw_html
    )

    text = re.sub(
        r"(?is)<script[^>]*>.*?</script>",
        " ",
        text,
    )

    text = re.sub(
        r"(?is)<style[^>]*>.*?</style>",
        " ",
        text,
    )

    text = re.sub(
        r"(?is)<noscript[^>]*>.*?</noscript>",
        " ",
        text,
    )

    text = re.sub(
        r"(?is)<!--.*?-->",
        " ",
        text,
    )

    text = re.sub(
        r"(?s)<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


USEFUL_JSON_KEYS = {
    "headline",
    "name",
    "title",
    "description",
    "articleBody",
    "text",
    "content",
    "body",
    "summary",
    "excerpt",
}


def _collect_json_text(
    value,
    collected,
):

    if isinstance(
        value,
        dict,
    ):

        for key, child in value.items():

            if (
                key in USEFUL_JSON_KEYS
                and isinstance(
                    child,
                    str,
                )
            ):

                cleaned = re.sub(
                    r"\s+",
                    " ",
                    html.unescape(
                        child
                    ),
                ).strip()

                if cleaned:

                    collected.append(
                        cleaned
                    )

            if isinstance(
                child,
                (dict, list),
            ):

                _collect_json_text(
                    child,
                    collected,
                )

    elif isinstance(
        value,
        list,
    ):

        for child in value:

            _collect_json_text(
                child,
                collected,
            )


def _deduplicate_text_parts(parts):

    seen = set()
    output = []

    for part in parts:

        if not isinstance(
            part,
            str,
        ):
            continue

        cleaned = re.sub(
            r"\s+",
            " ",
            part,
        ).strip()

        if not cleaned:
            continue

        key = cleaned.lower()

        if key in seen:
            continue

        seen.add(key)

        output.append(
            cleaned
        )

    return " ".join(
        output
    )


def extract_json_ld_text(raw_html):

    if not raw_html:
        return ""

    blocks = re.findall(
        r"""(?is)
        <script
        [^>]*type\s*=\s*
        ["']application/ld\+json["']
        [^>]*>
        (.*?)
        </script>
        """,
        str(raw_html),
        flags=re.VERBOSE,
    )

    collected = []

    for block in blocks:

        block = block.strip()

        if not block:
            continue

        parsed = None

        try:

            parsed = json.loads(
                block
            )

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            pass

        if parsed is None:

            try:

                parsed = json.loads(
                    html.unescape(
                        block
                    )
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):

                continue

        _collect_json_text(
            parsed,
            collected,
        )

    return _deduplicate_text_parts(
        collected
    )


def extract_embedded_json_text(
    raw_html,
):

    if not raw_html:
        return ""

    patterns = [
        r"""(?is)
        <script
        [^>]*id\s*=\s*["']__NEXT_DATA__["']
        [^>]*>
        (.*?)
        </script>
        """,

        r"""(?is)
        <script
        [^>]*id\s*=\s*["']__NUXT_DATA__["']
        [^>]*>
        (.*?)
        </script>
        """,

        r"""(?is)
        <script
        [^>]*type\s*=\s*["']application/json["']
        [^>]*>
        (.*?)
        </script>
        """,
    ]

    collected = []

    for pattern in patterns:

        blocks = re.findall(
            pattern,
            str(raw_html),
            flags=re.VERBOSE,
        )

        for block in blocks:

            block = block.strip()

            if not block:
                continue

            parsed = None

            try:

                parsed = json.loads(
                    block
                )

            except (
                json.JSONDecodeError,
                TypeError,
            ):
                pass

            if parsed is None:

                try:

                    parsed = json.loads(
                        html.unescape(
                            block
                        )
                    )

                except (
                    json.JSONDecodeError,
                    TypeError,
                ):

                    continue

            _collect_json_text(
                parsed,
                collected,
            )

    return _deduplicate_text_parts(
        collected
    )


def extract_best_page_text(
    raw_html,
):

    if not raw_html:
        return ""

    structured = (
        extract_json_ld_text(
            raw_html
        )
    )

    embedded = (
        extract_embedded_json_text(
            raw_html
        )
    )

    plain = clean_html_text(
        raw_html
    )

    parts = []

    if structured:
        parts.append(
            structured
        )

    if embedded:
        parts.append(
            embedded
        )

    if plain:
        parts.append(
            plain
        )

    return (
        _deduplicate_text_parts(
            parts
        )
        [:MAX_EXTRACTED_CHARS]
    )


# =========================================================
# URL SAFETY
# =========================================================

def _is_http_url(url):

    if not isinstance(
        url,
        str,
    ):
        return False

    try:

        parsed = urlparse(
            url.strip()
        )

    except Exception:
        return False

    return (
        parsed.scheme
        in {
            "http",
            "https",
        }
        and bool(
            parsed.netloc
        )
    )


def _is_public_ip(ip_text):

    try:

        ip = ipaddress.ip_address(
            ip_text
        )

    except ValueError:

        return False

    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _hostname_is_unsafe(
    hostname,
):

    if not hostname:
        return True

    hostname = (
        hostname
        .lower()
        .strip(".")
    )

    if hostname in {
        "localhost",
        "localhost.localdomain",
    }:

        return True

    if hostname.endswith(
        ".local"
    ):

        return True

    try:

        ipaddress.ip_address(
            hostname
        )

        return not _is_public_ip(
            hostname
        )

    except ValueError:

        return False


def is_safe_public_url(url):

    if not _is_http_url(
        url
    ):

        return False

    parsed = urlparse(
        url
    )

    hostname = (
        parsed.hostname
    )

    if _hostname_is_unsafe(
        hostname
    ):

        return False

    try:

        ipaddress.ip_address(
            hostname
        )

        return True

    except ValueError:
        pass

    try:

        addresses = socket.getaddrinfo(
            hostname,
            parsed.port
            or (
                443
                if parsed.scheme == "https"
                else 80
            ),
            type=socket.SOCK_STREAM,
        )

    except Exception:

        return False

    if not addresses:

        return False

    for address in addresses:

        ip_text = (
            address[4][0]
        )

        if not _is_public_ip(
            ip_text
        ):

            return False

    return True


# =========================================================
# V8 URL NORMALIZATION
# =========================================================

def normalize_discovery_url(url):

    if not isinstance(
        url,
        str,
    ):

        return ""

    url = url.strip()

    if not _is_http_url(
        url
    ):

        return ""

    parsed = urlparse(
        url
    )

    filtered_query = []

    for key, value in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):

        if (
            key.lower()
            in TRACKING_QUERY_KEYS
        ):

            continue

        filtered_query.append(
            (key, value)
        )

    normalized = parsed._replace(
        query=urlencode(
            filtered_query,
            doseq=True,
        ),
        fragment="",
    )

    return urlunparse(
        normalized
    )


# =========================================================
# V8 SEARCH RESULT PROTECTION
# =========================================================

def is_search_result_url(url):

    normalized = (
        normalize_discovery_url(
            url
        )
    )

    if not normalized:

        return False

    parsed = urlparse(
        normalized
    )

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    path = (
        parsed.path
        or ""
    ).lower()

    if hostname in {
        "google.com",
        "www.google.com",
    }:

        if (
            path.startswith(
                "/search"
            )
            or path.startswith(
                "/url"
            )
        ):

            return True

    if hostname == "news.google.com":

        return True

    if hostname in {
        "bing.com",
        "www.bing.com",
    }:

        if path.startswith(
            "/search"
        ):

            return True

    return False


def resolve_discovery_url(url):

    normalized = (
        normalize_discovery_url(
            url
        )
    )

    if not normalized:

        return ""

    parsed = urlparse(
        normalized
    )

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    path = (
        parsed.path
        or ""
    )

    # Google redirect:
    # /url?q=https://publisher/article
    if (
        hostname
        in {
            "google.com",
            "www.google.com",
        }
        and path == "/url"
    ):

        params = parse_qs(
            parsed.query
        )

        targets = (
            params.get("q")
            or params.get("url")
            or []
        )

        if not targets:

            return ""

        target = (
            normalize_discovery_url(
                targets[0]
            )
        )

        if (
            target
            and not is_search_result_url(
                target
            )
        ):

            return target

        return ""

    # Search-result pages themselves
    # are never evidence.
    if is_search_result_url(
        normalized
    ):

        return ""

    return normalized


# =========================================================
# V8 DISCOVERY QUERY
# =========================================================

def build_discovery_query(
    topic,
    claim="",
):

    if isinstance(
        topic,
        dict,
    ):

        topic_name = str(
            topic.get(
                "topic",
                "",
            )
        ).strip()

        seo = topic.get(
            "seo",
            {},
        )

        if isinstance(
            seo,
            dict,
        ):

            keyword = str(
                seo.get(
                    "primary_keyword",
                    "",
                )
            ).strip()

            if keyword:
                topic_name = keyword

    else:

        topic_name = str(
            topic
            or ""
        ).strip()

    claim = str(
        claim
        or ""
    ).strip()

    if claim:

        return (
            f"{topic_name} {claim}"
        ).strip()

    return (
        f"{topic_name} official announcement news"
    ).strip()


# =========================================================
# V8 FEED PARSING
# =========================================================

def _local_name(tag):

    if not isinstance(
        tag,
        str,
    ):

        return ""

    if "}" in tag:

        return tag.split(
            "}",
            1,
        )[1]

    return tag


def _element_clean_text(
    element,
):

    if element is None:

        return ""

    text = " ".join(
        element.itertext()
    )

    return re.sub(
        r"\s+",
        " ",
        html.unescape(
            text
        ),
    ).strip()


def extract_feed_entries(
    feed_text,
):

    if not isinstance(
        feed_text,
        str,
    ):

        return []

    if not feed_text.strip():

        return []

    try:

        root = ET.fromstring(
            feed_text
        )

    except ET.ParseError:

        return []

    entries = []

    # RSS
    for item in root.iter():

        if (
            _local_name(
                item.tag
            )
            != "item"
        ):

            continue

        title = ""
        url = ""
        description = ""

        for child in list(
            item
        ):

            name = _local_name(
                child.tag
            )

            if name == "title":

                title = (
                    _element_clean_text(
                        child
                    )
                )

            elif name == "link":

                url = (
                    _element_clean_text(
                        child
                    )
                )

            elif name in {
                "description",
                "summary",
                "content",
                "encoded",
            }:

                description = (
                    _element_clean_text(
                        child
                    )
                )

        url = normalize_discovery_url(
            url
        )

        if (
            title
            and url
        ):

            entries.append(
                {
                    "title": title,
                    "url": url,
                    "description": (
                        description
                    ),
                }
            )

    # Atom
    for entry in root.iter():

        if (
            _local_name(
                entry.tag
            )
            != "entry"
        ):

            continue

        title = ""
        url = ""
        description = ""

        for child in list(
            entry
        ):

            name = _local_name(
                child.tag
            )

            if name == "title":

                title = (
                    _element_clean_text(
                        child
                    )
                )

            elif name == "link":

                rel = (
                    child.attrib.get(
                        "rel",
                        "alternate",
                    )
                )

                href = (
                    child.attrib.get(
                        "href",
                        "",
                    )
                )

                if (
                    href
                    and rel
                    in {
                        "",
                        "alternate",
                    }
                ):

                    url = href

            elif name in {
                "summary",
                "content",
                "description",
            }:

                description = (
                    _element_clean_text(
                        child
                    )
                )

        url = normalize_discovery_url(
            url
        )

        if (
            title
            and url
        ):

            entries.append(
                {
                    "title": title,
                    "url": url,
                    "description": (
                        description
                    ),
                }
            )

    return deduplicate_candidates(
        entries
    )


# =========================================================
# V8 FEED TOPIC MATCHING
# =========================================================

DISCOVERY_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "game",
    "games",
    "news",
    "official",
    "le",
    "la",
    "les",
    "de",
    "des",
    "du",
    "une",
    "un",
    "et",
}


def _topic_words(text):

    words = re.findall(
        r"[a-zA-ZÀ-ÿ0-9]+",
        str(
            text
            or ""
        ).lower(),
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word
            not in DISCOVERY_STOPWORDS
        )
    }


def discover_feed_candidates(
    feed_text,
    topic,
):

    entries = (
        extract_feed_entries(
            feed_text
        )
    )

    topic_words = (
        _topic_words(
            topic
        )
    )

    if not topic_words:

        return []

    candidates = []

    for entry in entries:

        searchable = (
            str(
                entry.get(
                    "title",
                    "",
                )
            )
            + " "
            + str(
                entry.get(
                    "description",
                    "",
                )
            )
        )

        entry_words = (
            _topic_words(
                searchable
            )
        )

        matches = (
            topic_words
            & entry_words
        )

        required_matches = min(
            2,
            len(topic_words),
        )

        if (
            len(matches)
            < required_matches
        ):

            continue

        candidate = dict(
            entry
        )

        candidate[
            "source_type"
        ] = "rss"

        candidate[
            "publisher_match"
        ] = True

        candidate[
            "usable"
        ] = True

        candidates.append(
            candidate
        )

    return candidates


# =========================================================
# V8 CANDIDATE DEDUPLICATION
# =========================================================

def deduplicate_candidates(
    candidates,
):

    if not isinstance(
        candidates,
        list,
    ):

        return []

    seen = set()
    output = []

    for candidate in candidates:

        if not isinstance(
            candidate,
            dict,
        ):

            continue

        url = (
            normalize_discovery_url(
                candidate.get(
                    "url",
                    "",
                )
            )
        )

        if not url:

            continue

        key = (
            url.rstrip("/")
            .lower()
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        item = dict(
            candidate
        )

        item["url"] = url

        output.append(
            item
        )

    return output


# =========================================================
# V8 EVIDENCE RANKING
# =========================================================

def rank_evidence_candidate(
    candidate,
):

    if not isinstance(
        candidate,
        dict,
    ):

        return 0

    url = (
        normalize_discovery_url(
            candidate.get(
                "url",
                "",
            )
        )
    )

    if not url:

        return 0

    if is_search_result_url(
        url
    ):

        return 0

    source_type = str(
        candidate.get(
            "source_type",
            "",
        )
    ).lower()

    publisher_match = bool(
        candidate.get(
            "publisher_match",
            False,
        )
    )

    usable = bool(
        candidate.get(
            "usable",
            False,
        )
    )

    score = 10

    source_scores = {
        "official": 100,
        "publisher": 70,
        "rss": 60,
        "search": 20,
        "aggregator": 10,
    }

    score += source_scores.get(
        source_type,
        0,
    )

    if publisher_match:

        score += 25

    if usable:

        score += 30

    else:

        score -= 40

    return max(
        score,
        0,
    )


def build_evidence_candidate_pool(
    candidates,
):

    candidates = (
        deduplicate_candidates(
            candidates
        )
    )

    output = []

    for candidate in candidates:

        if is_search_result_url(
            candidate.get(
                "url",
                "",
            )
        ):

            continue

        score = (
            rank_evidence_candidate(
                candidate
            )
        )

        if score <= 0:

            continue

        item = dict(
            candidate
        )

        item[
            "evidence_rank"
        ] = score

        output.append(
            item
        )

    output.sort(
        key=lambda item: (
            item.get(
                "evidence_rank",
                0,
            )
        ),
        reverse=True,
    )

    return output


# =========================================================
# FETCH RESULT
# =========================================================

def evaluate_fetch_result(
    status_code,
    text,
):

    try:

        status_code = int(
            status_code
        )

    except (
        TypeError,
        ValueError,
    ):

        return "UNUSABLE"

    if not (
        200
        <= status_code
        < 300
    ):

        return "UNUSABLE"

    if not isinstance(
        text,
        str,
    ):

        return "UNUSABLE"

    if not text.strip():

        return "UNUSABLE"

    return "USABLE"


# =========================================================
# HTTP FETCH
# =========================================================

def fetch_url_bytes(
    url,
    accept,
):

    result = {
        "status": "UNUSABLE",
        "http_status": None,
        "final_url": "",
        "content_type": "",
        "body": b"",
        "error": "",
    }

    if not is_safe_public_url(
        url
    ):

        result["error"] = (
            "Unsafe URL."
        )

        return result

    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": (
                "fr-FR,fr;q=0.9,"
                "en;q=0.8"
            ),
        },
    )

    try:

        with urlopen(
            request,
            timeout=FETCH_TIMEOUT_SECONDS,
        ) as response:

            final_url = (
                response.geturl()
            )

            if not is_safe_public_url(
                final_url
            ):

                result["error"] = (
                    "Unsafe redirect."
                )

                return result

            body = response.read(
                MAX_PAGE_BYTES + 1
            )

            if (
                len(body)
                > MAX_PAGE_BYTES
            ):

                body = body[
                    :MAX_PAGE_BYTES
                ]

            result[
                "status"
            ] = "USABLE"

            result[
                "http_status"
            ] = response.getcode()

            result[
                "final_url"
            ] = final_url

            result[
                "content_type"
            ] = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            result["body"] = body

            result[
                "charset"
            ] = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

    except HTTPError as error:

        result[
            "http_status"
        ] = error.code

        result["error"] = (
            f"HTTP error: {error.code}"
        )

    except URLError as error:

        result["error"] = (
            f"URL error: {error.reason}"
        )

    except Exception as error:

        result["error"] = (
            "Fetch error: "
            f"{type(error).__name__}"
        )

    return result


def fetch_public_page(
    url,
):

    result = {
        "url": url,
        "fetch_status": "UNUSABLE",
        "http_status": None,
        "final_url": "",
        "content_type": "",
        "text": "",
        "extraction_method": "",
        "error": "",
    }

    fetched = fetch_url_bytes(
        url,
        (
            "text/html,"
            "application/xhtml+xml"
        ),
    )

    result[
        "http_status"
    ] = fetched.get(
        "http_status"
    )

    result[
        "final_url"
    ] = fetched.get(
        "final_url",
        "",
    )

    result[
        "content_type"
    ] = fetched.get(
        "content_type",
        "",
    )

    if (
        fetched.get(
            "status"
        )
        != "USABLE"
    ):

        result["error"] = (
            fetched.get(
                "error",
                "",
            )
        )

        return result

    content_type = (
        fetched.get(
            "content_type",
            ""
        ).lower()
    )

    if (
        "html"
        not in content_type
        and "xhtml"
        not in content_type
    ):

        result["error"] = (
            "Not HTML."
        )

        return result

    raw_html = (
        fetched.get(
            "body",
            b"",
        )
        .decode(
            fetched.get(
                "charset",
                "utf-8",
            ),
            errors="replace",
        )
    )

    json_ld = (
        extract_json_ld_text(
            raw_html
        )
    )

    embedded = (
        extract_embedded_json_text(
            raw_html
        )
    )

    text = extract_best_page_text(
        raw_html
    )

    if json_ld:

        method = "JSON_LD"

        if embedded:

            method += (
                "+EMBEDDED_JSON"
            )

    elif embedded:

        method = (
            "EMBEDDED_JSON"
        )

    else:

        method = "HTML"

    result[
        "extraction_method"
    ] = method

    result["text"] = text

    result[
        "fetch_status"
    ] = evaluate_fetch_result(
        result.get(
            "http_status"
        ),
        text,
    )

    if (
        result[
            "fetch_status"
        ]
        == "USABLE"
        and len(text) < 200
    ):

        result[
            "fetch_status"
        ] = "WEAK"

    return result


# =========================================================
# FETCH PUBLIC FEED
# =========================================================

def fetch_feed(
    url,
):

    fetched = fetch_url_bytes(
        url,
        (
            "application/rss+xml,"
            "application/atom+xml,"
            "application/xml,"
            "text/xml"
        ),
    )

    if (
        fetched.get(
            "status"
        )
        != "USABLE"
    ):

        return ""

    return (
        fetched.get(
            "body",
            b"",
        )
        .decode(
            fetched.get(
                "charset",
                "utf-8",
            ),
            errors="replace",
        )
    )


# =========================================================
# V8 MULTI-FEED DISCOVERY
# =========================================================

def discover_public_feed_sources(
    topic,
):

    candidates = []

    for feed in PUBLIC_GAMING_FEEDS:

        feed_url = (
            feed.get(
                "url",
                "",
            )
        )

        print(
            "Checking feed: "
            f"{feed_url}"
        )

        feed_text = fetch_feed(
            feed_url
        )

        if not feed_text:

            continue

        matches = (
            discover_feed_candidates(
                feed_text=feed_text,
                topic=topic,
            )
        )

        for match in matches:

            match[
                "publisher"
            ] = feed.get(
                "publisher",
                "",
            )

            match[
                "source_type"
            ] = feed.get(
                "source_type",
                "rss",
            )

            candidates.append(
                match
            )

    return (
        deduplicate_candidates(
            candidates
        )
    )


# =========================================================
# ORIGINAL INTEL
# =========================================================

def extract_source_evidence(
    intel_topic,
):

    output = []

    for source in (
        intel_topic.get(
            "sources",
            [],
        )
    ):

        if not isinstance(
            source,
            dict,
        ):

            continue

        url = (
            normalize_discovery_url(
                source.get(
                    "url",
                    "",
                )
            )
        )

        if not url:

            continue

        output.append(
            {
                "type": source.get(
                    "type",
                    "unknown",
                ),
                "url": url,
                "title": source.get(
                    "title",
                    "",
                ),
                "evidence": source.get(
                    "evidence",
                    "",
                ),
            }
        )

    return output


def fetch_topic_sources(
    intel_topic,
):

    fetched = []

    for source in (
        extract_source_evidence(
            intel_topic
        )
    ):

        print(
            "Fetching original source: "
            f"{source['url']}"
        )

        page = fetch_public_page(
            source["url"]
        )

        fetched.append(
            {
                **source,
                **page,
            }
        )

    return fetched


def build_initial_claims(
    intel_topic,
):

    claims = []

    for source in (
        extract_source_evidence(
            intel_topic
        )
    ):

        evidence = str(
            source.get(
                "evidence",
                "",
            )
        ).strip()

        if not evidence:

            continue

        claims.append(
            {
                "claim": evidence,
                "status": "UNKNOWN",
                "sources": [],
            }
        )

    return claims


# =========================================================
# FETCH V8 DISCOVERED ARTICLES
# =========================================================

def fetch_v8_candidates(
    candidates,
):

    fetched = []

    pool = (
        build_evidence_candidate_pool(
            candidates
        )
    )

    for candidate in pool[
        :MAX_DISCOVERED_SOURCES_TO_FETCH
    ]:

        url = (
            resolve_discovery_url(
                candidate.get(
                    "url",
                    "",
                )
            )
        )

        if not url:

            continue

        if is_search_result_url(
            url
        ):

            continue

        print(
            "Fetching direct candidate: "
            f"{url}"
        )

        page = fetch_public_page(
            url
        )

        fetched.append(
            {
                **candidate,
                **page,
                "resolved_url": url,
            }
        )

    return fetched


# =========================================================
# COLLECT USABLE EVIDENCE
# =========================================================

def collect_usable_evidence(
    original_sources,
    discovered_sources,
):

    all_sources = []

    all_sources.extend(
        original_sources
        if isinstance(
            original_sources,
            list,
        )
        else []
    )

    all_sources.extend(
        discovered_sources
        if isinstance(
            discovered_sources,
            list,
        )
        else []
    )

    evidence = []
    seen = set()

    for source in all_sources:

        if not isinstance(
            source,
            dict,
        ):

            continue

        if (
            source.get(
                "fetch_status"
            )
            != "USABLE"
        ):

            continue

        text = str(
            source.get(
                "text",
                "",
            )
        ).strip()

        if not text:

            continue

        url = (
            source.get(
                "resolved_url"
            )
            or source.get(
                "final_url"
            )
            or source.get(
                "url"
            )
            or ""
        )

        url = resolve_discovery_url(
            url
        )

        if not url:

            continue

        if is_search_result_url(
            url
        ):

            continue

        if url in seen:

            continue

        seen.add(
            url
        )

        evidence.append(
            {
                "url": url,
                "text": text,
                "title": source.get(
                    "title",
                    "",
                ),
                "publisher": source.get(
                    "publisher",
                    "",
                ),
            }
        )

    return evidence


# =========================================================
# CLAIM SELECTION
# =========================================================

def select_claims_for_verification(
    claims,
    max_claims=MAX_CLAIMS_PER_RUN,
):

    selected = []

    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):

            continue

        if (
            normalize_claim_status(
                claim.get(
                    "status",
                    "UNKNOWN",
                )
            )
            != "UNKNOWN"
        ):

            continue

        if not str(
            claim.get(
                "claim",
                "",
            )
        ).strip():

            continue

        selected.append(
            claim
        )

        if (
            len(selected)
            >= max_claims
        ):

            break

    return selected


# =========================================================
# VERIFICATION RESULT SAFETY
# =========================================================

def normalize_verification_result(
    result,
    allowed_source_urls,
):

    if not isinstance(
        result,
        dict,
    ):

        result = {}

    allowed = set(
        allowed_source_urls
        or []
    )

    status = (
        normalize_claim_status(
            result.get(
                "status",
                "UNKNOWN",
            )
        )
    )

    supplied_urls = (
        result.get(
            "supporting_source_urls",
            [],
        )
    )

    if not isinstance(
        supplied_urls,
        list,
    ):

        supplied_urls = []

    approved = []

    for url in supplied_urls:

        if (
            isinstance(
                url,
                str,
            )
            and url in allowed
            and url not in approved
        ):

            approved.append(
                url
            )

    if (
        status == "CONFIRMED"
        and not approved
    ):

        status = "UNKNOWN"

    return {
        "claim": str(
            result.get(
                "claim",
                "",
            )
        ).strip(),
        "status": status,
        "supporting_source_urls": approved,
        "reason": str(
            result.get(
                "reason",
                "",
            )
        ).strip(),
    }


# =========================================================
# GROQ SAFE CALL
# =========================================================

def extract_ai_json(text):

    if not text:

        raise ValueError(
            "Empty AI response."
        )

    cleaned = text.strip()

    cleaned = re.sub(
        r"^```(?:json)?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
    )

    try:

        return json.loads(
            cleaned
        )

    except json.JSONDecodeError:

        start = cleaned.find(
            "{"
        )

        end = cleaned.rfind(
            "}"
        )

        if (
            start == -1
            or end == -1
        ):

            raise ValueError(
                "No JSON found."
            )

        return json.loads(
            cleaned[
                start:end + 1
            ]
        )


def groq_chat(messages):

    if GROQ_CLIENT is None:

        raise RuntimeError(
            "GROQ_API_KEY is missing."
        )

    for attempt in range(
        1,
        GROQ_MAX_RETRIES + 1,
    ):

        try:

            response = (
                GROQ_CLIENT
                .chat
                .completions
                .create(
                    model=GROQ_MODEL,
                    messages=messages,
                    temperature=0,
                )
            )

            return (
                response
                .choices[0]
                .message
                .content
            )

        except RateLimitError as error:

            retry_after = None

            try:

                retry_after = (
                    error
                    .response
                    .headers
                    .get(
                        "retry-after"
                    )
                )

            except Exception:
                pass

            try:

                wait_seconds = float(
                    retry_after
                )

            except Exception:

                wait_seconds = (
                    GROQ_DEFAULT_WAIT_SECONDS
                    * attempt
                )

            wait_seconds += 2

            if (
                attempt
                >= GROQ_MAX_RETRIES
            ):

                raise

            print(
                "Groq free limit reached. "
                f"Waiting {wait_seconds}s."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "Groq request failed."
    )


def build_verification_messages(
    claim,
    evidence,
):

    evidence_for_ai = []

    for item in evidence[
        :MAX_EVIDENCE_SOURCES_FOR_AI
    ]:

        evidence_for_ai.append(
            {
                "url": item.get(
                    "url",
                    "",
                ),
                "title": item.get(
                    "title",
                    "",
                ),
                "publisher": item.get(
                    "publisher",
                    "",
                ),
                "text": str(
                    item.get(
                        "text",
                        "",
                    )
                )[
                    :MAX_EVIDENCE_CHARS_PER_SOURCE
                ],
            }
        )

    system_prompt = """
You are the strict fact-verification engine for GamerQuest FR.

Use ONLY the supplied evidence.

Never use memory or outside knowledge.
Never infer a release date.
Never invent a fact.
Never treat a search result as evidence.

Return CONFIRMED only when the supplied text explicitly
supports the claim.

Return UNCONFIRMED when supplied evidence explicitly
contradicts the claim.

Otherwise return UNKNOWN.

A CONFIRMED result must cite at least one exact evidence URL.

Return ONLY valid JSON:

{
  "claim": "",
  "status": "CONFIRMED|UNCONFIRMED|UNKNOWN",
  "supporting_source_urls": [],
  "reason": ""
}
""".strip()

    user_prompt = (
        "CLAIM:\n"
        + str(
            claim.get(
                "claim",
                "",
            )
        )
        + "\n\nEVIDENCE:\n"
        + json.dumps(
            evidence_for_ai,
            ensure_ascii=False,
            indent=2,
        )
    )

    return [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]


def verify_claim_with_groq(
    claim,
    evidence,
):

    allowed_urls = {
        item.get(
            "url"
        )
        for item in evidence
        if item.get(
            "url"
        )
    }

    response = groq_chat(
        build_verification_messages(
            claim,
            evidence,
        )
    )

    raw = extract_ai_json(
        response
    )

    raw["claim"] = (
        claim.get(
            "claim",
            "",
        )
    )

    return (
        normalize_verification_result(
            raw,
            allowed_urls,
        )
    )


def verify_claims(
    claims,
    evidence,
):

    selected = (
        select_claims_for_verification(
            claims,
        )
    )

    if not selected:

        return claims

    if not evidence:

        print(
            "No USABLE evidence. "
            "Claims remain UNKNOWN."
        )

        return claims

    if GROQ_CLIENT is None:

        print(
            "GROQ_API_KEY missing. "
            "Verification skipped safely."
        )

        return claims

    updated = [
        dict(claim)
        for claim in claims
    ]

    for selected_claim in selected:

        claim_text = (
            selected_claim.get(
                "claim",
                "",
            )
        )

        print("")
        print(
            "Verifying claim:"
        )

        print(
            claim_text
        )

        try:

            verification = (
                verify_claim_with_groq(
                    selected_claim,
                    evidence,
                )
            )

        except RateLimitError:

            print(
                "Groq free quota unavailable."
            )

            print(
                "Stopping safely. "
                "No paid fallback."
            )

            break

        except Exception as error:

            print(
                "Verification failed: "
                f"{error}"
            )

            continue

        print(
            "Verification result: "
            f"{verification.get('status')}"
        )

        for item in updated:

            if (
                item.get(
                    "claim"
                )
                != claim_text
            ):

                continue

            item["status"] = (
                verification.get(
                    "status",
                    "UNKNOWN",
                )
            )

            item["sources"] = (
                verification.get(
                    "supporting_source_urls",
                    [],
                )
            )

            item[
                "verification_reason"
            ] = verification.get(
                "reason",
                "",
            )

            item[
                "verified_at"
            ] = datetime.now(
                timezone.utc
            ).isoformat()

            break

    return updated


# =========================================================
# PIPELINE HELPERS
# =========================================================

def get_write_candidates(
    scored_data,
):

    return [
        topic
        for topic
        in scored_data.get(
            "topics",
            [],
        )
        if (
            isinstance(
                topic,
                dict,
            )
            and str(
                topic.get(
                    "decision",
                    "",
                )
            ).upper()
            == "WRITE"
        )
    ]


def find_intel_topic(
    intel_data,
    topic_id,
):

    for topic in (
        intel_data.get(
            "topics",
            [],
        )
    ):

        if (
            topic.get(
                "id"
            )
            == topic_id
        ):

            return topic

    return None


def count_source_statuses(
    sources,
):

    counts = {
        "total": len(
            sources
        ),
        "usable": 0,
        "weak": 0,
        "unresolved": 0,
        "unusable": 0,
    }

    for source in sources:

        status = source.get(
            "fetch_status",
            "UNUSABLE",
        )

        if status == "USABLE":

            counts[
                "usable"
            ] += 1

        elif status == "WEAK":

            counts[
                "weak"
            ] += 1

        elif status == "UNRESOLVED":

            counts[
                "unresolved"
            ] += 1

        else:

            counts[
                "unusable"
            ] += 1

    return counts


# =========================================================
# V8 RESEARCH RECORD
# =========================================================

def build_research_record(
    scored_topic,
    intel_topic,
):

    topic_name = str(
        scored_topic.get(
            "topic",
            "",
        )
        or intel_topic.get(
            "topic",
            "",
        )
    ).strip()

    claims = (
        build_initial_claims(
            intel_topic
        )
    )

    # -----------------------------------------------------
    # 1. ORIGINAL SOURCES
    # -----------------------------------------------------

    original_sources = (
        fetch_topic_sources(
            intel_topic
        )
    )

    # -----------------------------------------------------
    # 2. FREE DIRECT RSS / ATOM DISCOVERY
    # -----------------------------------------------------

    feed_candidates = (
        discover_public_feed_sources(
            topic_name
        )
    )

    print(
        "DIRECT FEED CANDIDATES: "
        f"{len(feed_candidates)}"
    )

    # -----------------------------------------------------
    # 3. DIRECT ARTICLE FETCH
    # -----------------------------------------------------

    discovered_sources = (
        fetch_v8_candidates(
            feed_candidates
        )
    )

    # -----------------------------------------------------
    # 4. USABLE EVIDENCE ONLY
    # -----------------------------------------------------

    usable_evidence = (
        collect_usable_evidence(
            original_sources,
            discovered_sources,
        )
    )

    print("")
    print(
        "USABLE EVIDENCE SOURCES: "
        f"{len(usable_evidence)}"
    )

    # -----------------------------------------------------
    # 5. CLAIM VERIFICATION
    # -----------------------------------------------------

    verified_claims = (
        verify_claims(
            claims,
            usable_evidence,
        )
    )

    fact_pack = (
        build_verified_fact_pack(
            verified_claims
        )
    )

    confirmed_count = len(
        fact_pack[
            "confirmed_facts"
        ]
    )

    blocked_count = len(
        fact_pack[
            "blocked_claims"
        ]
    )

    original_counts = (
        count_source_statuses(
            original_sources
        )
    )

    discovered_counts = (
        count_source_statuses(
            discovered_sources
        )
    )

    total_sources = (
        original_counts["total"]
        + discovered_counts["total"]
    )

    usable_sources = (
        original_counts["usable"]
        + discovered_counts["usable"]
    )

    weak_sources = (
        original_counts["weak"]
        + discovered_counts["weak"]
    )

    unresolved_sources = (
        original_counts[
            "unresolved"
        ]
        + discovered_counts[
            "unresolved"
        ]
    )

    unusable_sources = (
        original_counts["unusable"]
        + discovered_counts["unusable"]
    )

    if confirmed_count > 0:

        research_status = (
            "VERIFIED_FACTS_READY"
        )

    elif usable_evidence:

        research_status = (
            "VERIFICATION_COMPLETE_NO_CONFIRMED_FACTS"
        )

    else:

        research_status = (
            "PENDING_VERIFICATION"
        )

    return {
        "id": scored_topic.get(
            "id"
        ),
        "topic": topic_name,
        "seo_score": (
            scored_topic.get(
                "total_score"
            )
        ),
        "seo_decision": (
            scored_topic.get(
                "decision"
            )
        ),
        "created_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "sources": (
            extract_source_evidence(
                intel_topic
            )
        ),

        "fetched_sources": (
            original_sources
        ),

        "discovery": {
            "version": "8.0",
            "strategy": (
                "original + public RSS/Atom"
            ),
            "feed_candidate_count": (
                len(
                    feed_candidates
                )
            ),
            "candidates": (
                feed_candidates
            ),
        },

        "discovered_sources": (
            discovered_sources
        ),

        "usable_evidence": (
            usable_evidence
        ),

        "source_summary": {
            "total_sources": (
                total_sources
            ),
            "usable_sources": (
                usable_sources
            ),
            "weak_sources": (
                weak_sources
            ),
            "unresolved_sources": (
                unresolved_sources
            ),
            "unusable_sources": (
                unusable_sources
            ),
            "original": (
                original_counts
            ),
            "discovered": (
                discovered_counts
            ),
        },

        "verification_summary": {
            "max_claims_per_run": (
                MAX_CLAIMS_PER_RUN
            ),
            "claims_total": (
                len(
                    verified_claims
                )
            ),
            "confirmed": (
                confirmed_count
            ),
            "blocked": (
                blocked_count
            ),
            "usable_evidence_sources": (
                len(
                    usable_evidence
                )
            ),
        },

        "claims": (
            verified_claims
        ),

        "fact_pack": (
            fact_pack
        ),

        "research_status": (
            research_status
        ),
    }


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "==================================="
    )
    print(
        "GAMERQUEST RESEARCHER V8"
    )
    print(
        "==================================="
    )

    if not INTEL_FILE.exists():

        print(
            "Intel file not found."
        )

        return

    if not SCORED_FILE.exists():

        print(
            "Scored topics file not found."
        )

        return

    intel_data = load_json(
        INTEL_FILE
    )

    scored_data = load_json(
        SCORED_FILE
    )

    if RESEARCH_FILE.exists():

        try:

            research_data = (
                load_json(
                    RESEARCH_FILE
                )
            )

        except Exception:

            research_data = {
                "version": "8.0",
                "updated_at": None,
                "topics": [],
            }

    else:

        research_data = {
            "version": "8.0",
            "updated_at": None,
            "topics": [],
        }

    candidates = (
        get_write_candidates(
            scored_data
        )
    )

    print(
        "WRITE candidates: "
        f"{len(candidates)}"
    )

    candidate_ids = {
        topic.get(
            "id"
        )
        for topic in candidates
        if topic.get(
            "id"
        )
    }

    # Refresh current WRITE records
    # while Researcher is being developed.
    research_data[
        "topics"
    ] = [
        topic
        for topic
        in research_data.get(
            "topics",
            [],
        )
        if (
            topic.get(
                "id"
            )
            not in candidate_ids
        )
    ]

    created = 0

    for scored_topic in candidates:

        topic_id = (
            scored_topic.get(
                "id"
            )
        )

        if not topic_id:

            continue

        intel_topic = (
            find_intel_topic(
                intel_data,
                topic_id,
            )
        )

        if intel_topic is None:

            print(
                "Intel missing: "
                f"{topic_id}"
            )

            continue

        print("")
        print(
            "==================================="
        )
        print(
            "Researching: "
            f"{scored_topic.get('topic')}"
        )
        print(
            "==================================="
        )

        record = (
            build_research_record(
                scored_topic,
                intel_topic,
            )
        )

        research_data[
            "topics"
        ].append(
            record
        )

        summary = record.get(
            "source_summary",
            {},
        )

        verification = record.get(
            "verification_summary",
            {},
        )

        print("")
        print(
            "Research result:"
        )

        print(
            "TOTAL SOURCES: "
            f"{summary.get('total_sources', 0)}"
        )

        print(
            "USABLE: "
            f"{summary.get('usable_sources', 0)}"
        )

        print(
            "WEAK: "
            f"{summary.get('weak_sources', 0)}"
        )

        print(
            "UNRESOLVED: "
            f"{summary.get('unresolved_sources', 0)}"
        )

        print(
            "UNUSABLE: "
            f"{summary.get('unusable_sources', 0)}"
        )

        print(
            "CONFIRMED CLAIMS: "
            f"{verification.get('confirmed', 0)}"
        )

        print(
            "BLOCKED CLAIMS: "
            f"{verification.get('blocked', 0)}"
        )

        print(
            "STATUS: "
            f"{record.get('research_status')}"
        )

        created += 1

    research_data[
        "version"
    ] = "8.0"

    research_data[
        "updated_at"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    save_json(
        RESEARCH_FILE,
        research_data,
    )

    print("")
    print(
        "==================================="
    )
    print(
        "RESEARCHER V8 COMPLETE"
    )
    print(
        "==================================="
    )

    print(
        "Created/refreshed "
        f"{created} record(s)."
    )

    print(
        "Search-result pages are never evidence."
    )

    print(
        "Direct RSS/Atom publisher URLs "
        "are preferred."
    )

    print(
        "Only USABLE evidence reaches Groq."
    )

    print(
        "No paid fallback."
    )

    print(
        "No article publishing."
    )


if __name__ == "__main__":
    main()
