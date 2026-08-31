import json
import html
import ipaddress
import os
import re
import socket
import time
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote_plus, urljoin
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from groq import Groq, RateLimitError


# =========================================================
# PATHS
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"
RESEARCH_FILE = BASE_DIR / "research_results.json"


# =========================================================
# CONFIGURATION
# =========================================================

ALLOWED_STATUSES = {
    "CONFIRMED",
    "UNCONFIRMED",
    "UNKNOWN",
}

FETCH_TIMEOUT_SECONDS = 12
MAX_PAGE_BYTES = 2_000_000
MAX_EXTRACTED_CHARS = 25_000

MAX_DISCOVERY_RESULTS = 8
MAX_DISCOVERED_SOURCES_TO_FETCH = 5

# Cost / quota protection
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
    "(compatible; GamerQuestFR-Research/6.0; "
    "+https://gamerquestfr.com/)"
)


# =========================================================
# GROQ CLIENT
# =========================================================

if GROQ_API_KEY:

    GROQ_CLIENT = Groq(
        api_key=GROQ_API_KEY,
        max_retries=0,
    )

else:

    GROQ_CLIENT = None


# =========================================================
# CLAIM SAFETY
# =========================================================

def normalize_claim_status(status):

    if not isinstance(
        status,
        str,
    ):
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
        normalize_claim_status(
            status
        )
        == "CONFIRMED"
    )


def build_verified_fact_pack(claims):

    confirmed_facts = []
    blocked_claims = []

    for claim in claims:

        if not isinstance(
            claim,
            dict,
        ):
            continue

        normalized_claim = dict(
            claim
        )

        status = (
            normalize_claim_status(
                normalized_claim.get(
                    "status",
                    "UNKNOWN",
                )
            )
        )

        normalized_claim[
            "status"
        ] = status

        sources = (
            normalized_claim.get(
                "sources",
                [],
            )
        )

        if not isinstance(
            sources,
            list,
        ):
            sources = []

        normalized_claim[
            "sources"
        ] = sources

        # CONFIRMED without evidence
        # must never pass.
        if (
            status == "CONFIRMED"
            and not sources
        ):

            normalized_claim[
                "status"
            ] = "UNKNOWN"

            status = "UNKNOWN"

        if should_allow_claim(
            status
        ):

            confirmed_facts.append(
                normalized_claim
            )

        else:

            blocked_claims.append(
                normalized_claim
            )

    return {
        "confirmed_facts": confirmed_facts,
        "blocked_claims": blocked_claims,
    }


# =========================================================
# BASIC HTML CLEANING
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


# =========================================================
# STRUCTURED DATA HELPERS
# =========================================================

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
    parent_key=None,
):

    if isinstance(
        value,
        dict,
    ):

        for key, child in (
            value.items()
        ):

            if key in USEFUL_JSON_KEYS:

                if isinstance(
                    child,
                    str,
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

                elif isinstance(
                    child,
                    (dict, list),
                ):

                    _collect_json_text(
                        child,
                        collected,
                        key,
                    )

            else:

                _collect_json_text(
                    child,
                    collected,
                    key,
                )

    elif isinstance(
        value,
        list,
    ):

        for item in value:

            _collect_json_text(
                item,
                collected,
                parent_key,
            )


def _deduplicate_text_parts(
    parts,
):

    seen = set()
    result = []

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

        normalized = (
            cleaned.lower()
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        result.append(
            cleaned
        )

    return " ".join(
        result
    )


# =========================================================
# JSON-LD EXTRACTION
# =========================================================

def extract_json_ld_text(
    raw_html,
):

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

    return (
        _deduplicate_text_parts(
            collected
        )
    )


# =========================================================
# EMBEDDED JSON EXTRACTION
# =========================================================

def extract_embedded_json_text(
    raw_html,
):

    if not raw_html:
        return ""

    text = str(
        raw_html
    )

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
            text,
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

    return (
        _deduplicate_text_parts(
            collected
        )
    )


# =========================================================
# BEST PAGE CONTENT
# =========================================================

def extract_best_page_text(
    raw_html,
):

    if not raw_html:
        return ""

    json_ld_text = (
        extract_json_ld_text(
            raw_html
        )
    )

    embedded_text = (
        extract_embedded_json_text(
            raw_html
        )
    )

    plain_text = (
        clean_html_text(
            raw_html
        )
    )

    parts = []

    if json_ld_text:

        parts.append(
            json_ld_text
        )

    if embedded_text:

        parts.append(
            embedded_text
        )

    if plain_text:

        parts.append(
            plain_text
        )

    combined = (
        _deduplicate_text_parts(
            parts
        )
    )

    return combined[
        :MAX_EXTRACTED_CHARS
    ]


# =========================================================
# URL HELPERS
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


def _is_public_ip(
    ip_text,
):

    try:

        ip = (
            ipaddress.ip_address(
                ip_text
            )
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


def _hostname_is_obviously_unsafe(
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

        return not (
            _is_public_ip(
                hostname
            )
        )

    except ValueError:
        return False


def is_safe_public_url(url):

    if not _is_http_url(
        url
    ):
        return False

    try:

        parsed = urlparse(
            url
        )

    except Exception:
        return False

    hostname = (
        parsed.hostname
    )

    if not hostname:
        return False

    if _hostname_is_obviously_unsafe(
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

        addresses = (
            socket.getaddrinfo(
                hostname,
                parsed.port
                or (
                    443
                    if parsed.scheme
                    == "https"
                    else 80
                ),
                type=socket.SOCK_STREAM,
            )
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
# GOOGLE NEWS URL DETECTION
# =========================================================

def is_google_news_url(url):

    if not _is_http_url(
        url
    ):
        return False

    try:

        parsed = urlparse(
            url
        )

    except Exception:
        return False

    hostname = (
        parsed.hostname
        or ""
    ).lower()

    return (
        hostname
        == "news.google.com"
        or hostname.endswith(
            ".news.google.com"
        )
    )


# =========================================================
# GOOGLE NEWS PUBLISHER EXTRACTION
# =========================================================

def extract_publisher_url_from_google_news_html(
    raw_html,
    google_url="",
):

    if not isinstance(
        raw_html,
        str,
    ):
        return ""

    if not raw_html.strip():
        return ""

    hrefs = re.findall(
        r"""(?is)
        href\s*=\s*
        ["']
        (.*?)
        ["']
        """,
        raw_html,
        flags=re.VERBOSE,
    )

    for href in hrefs:

        candidate = html.unescape(
            href.strip()
        )

        if not candidate:
            continue

        candidate = urljoin(
            google_url,
            candidate,
        )

        if not _is_http_url(
            candidate
        ):
            continue

        if is_google_news_url(
            candidate
        ):
            continue

        try:

            hostname = (
                urlparse(
                    candidate
                ).hostname
            )

        except Exception:
            continue

        if _hostname_is_obviously_unsafe(
            hostname
        ):
            continue

        return candidate

    return ""


def resolve_discovery_url(
    url,
    wrapper_html="",
):

    result = {
        "original_url": url,
        "resolved_url": "",
        "status": "UNRESOLVED",
        "can_fetch_as_evidence": False,
    }

    if not _is_http_url(
        url
    ):

        result[
            "status"
        ] = "INVALID"

        return result

    if not is_google_news_url(
        url
    ):

        try:

            hostname = (
                urlparse(
                    url
                ).hostname
            )

        except Exception:

            result[
                "status"
            ] = "INVALID"

            return result

        if _hostname_is_obviously_unsafe(
            hostname
        ):

            result[
                "status"
            ] = "UNSAFE"

            return result

        result[
            "resolved_url"
        ] = url

        result[
            "status"
        ] = "DIRECT"

        result[
            "can_fetch_as_evidence"
        ] = True

        return result

    publisher_url = (
        extract_publisher_url_from_google_news_html(
            wrapper_html,
            google_url=url,
        )
    )

    if not publisher_url:
        return result

    result[
        "resolved_url"
    ] = publisher_url

    result[
        "status"
    ] = "RESOLVED"

    result[
        "can_fetch_as_evidence"
    ] = True

    return result


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
# RAW PAGE FETCHER
# =========================================================

def fetch_raw_html_page(url):

    result = {
        "url": url,
        "status": "UNUSABLE",
        "http_status": None,
        "final_url": "",
        "content_type": "",
        "html": "",
        "error": "",
    }

    if not is_safe_public_url(
        url
    ):

        result["error"] = (
            "Unsafe or non-public URL."
        )

        return result

    request = Request(
        url,
        headers={
            "User-Agent": (
                USER_AGENT
            ),
            "Accept": (
                "text/html,"
                "application/xhtml+xml"
            ),
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
                    "Redirected to unsafe URL."
                )

                return result

            result[
                "http_status"
            ] = response.getcode()

            result[
                "final_url"
            ] = final_url

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            result[
                "content_type"
            ] = content_type

            content_type_lower = (
                content_type.lower()
            )

            if (
                "text/html"
                not in content_type_lower
                and
                "application/xhtml+xml"
                not in content_type_lower
            ):

                result["error"] = (
                    "Unsupported content type."
                )

                return result

            raw_bytes = response.read(
                MAX_PAGE_BYTES + 1
            )

            if (
                len(raw_bytes)
                > MAX_PAGE_BYTES
            ):

                raw_bytes = (
                    raw_bytes[
                        :MAX_PAGE_BYTES
                    ]
                )

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            result[
                "html"
            ] = raw_bytes.decode(
                charset,
                errors="replace",
            )

            result[
                "status"
            ] = "USABLE"

            return result

    except HTTPError as error:

        result[
            "http_status"
        ] = error.code

        result["error"] = (
            f"HTTP error: {error.code}"
        )

        return result

    except URLError as error:

        result["error"] = (
            "URL error: "
            f"{error.reason}"
        )

        return result

    except TimeoutError:

        result["error"] = (
            "Request timed out."
        )

        return result

    except Exception as error:

        result["error"] = (
            "Fetch error: "
            f"{type(error).__name__}"
        )

        return result


# =========================================================
# PUBLIC PAGE FETCHER
# =========================================================

def fetch_public_page(url):

    result = {
        "url": url,
        "fetch_status": "UNUSABLE",
        "http_status": None,
        "content_type": "",
        "final_url": "",
        "extraction_method": "",
        "text": "",
        "error": "",
    }

    raw_result = (
        fetch_raw_html_page(
            url
        )
    )

    result[
        "http_status"
    ] = raw_result.get(
        "http_status"
    )

    result[
        "content_type"
    ] = raw_result.get(
        "content_type",
        "",
    )

    result[
        "final_url"
    ] = raw_result.get(
        "final_url",
        "",
    )

    if (
        raw_result.get(
            "status"
        )
        != "USABLE"
    ):

        result["error"] = (
            raw_result.get(
                "error",
                "",
            )
        )

        return result

    raw_html = (
        raw_result.get(
            "html",
            "",
        )
    )

    json_ld_text = (
        extract_json_ld_text(
            raw_html
        )
    )

    embedded_text = (
        extract_embedded_json_text(
            raw_html
        )
    )

    extracted_text = (
        extract_best_page_text(
            raw_html
        )
    )

    if json_ld_text:

        extraction_method = (
            "JSON_LD"
        )

        if embedded_text:

            extraction_method += (
                "+EMBEDDED_JSON"
            )

    elif embedded_text:

        extraction_method = (
            "EMBEDDED_JSON"
        )

    else:

        extraction_method = (
            "HTML"
        )

    result[
        "extraction_method"
    ] = extraction_method

    result[
        "text"
    ] = extracted_text

    result[
        "fetch_status"
    ] = evaluate_fetch_result(
        result.get(
            "http_status"
        ),
        extracted_text,
    )

    if (
        result[
            "fetch_status"
        ]
        == "USABLE"
        and len(
            extracted_text
        ) < 80
    ):

        result[
            "fetch_status"
        ] = "WEAK"

    return result


# =========================================================
# DISCOVERY QUERY
# =========================================================

def build_discovery_query(
    scored_topic,
):

    if not isinstance(
        scored_topic,
        dict,
    ):
        return ""

    seo = scored_topic.get(
        "seo",
        {},
    )

    keyword = ""

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

    if not keyword:

        keyword = str(
            scored_topic.get(
                "primary_keyword",
                "",
            )
        ).strip()

    topic = str(
        scored_topic.get(
            "topic",
            "",
        )
    ).strip()

    if keyword:
        return keyword

    return topic


# =========================================================
# RSS DISCOVERY
# =========================================================

def _element_text(
    element,
    tag,
):

    child = element.find(
        tag
    )

    if child is None:
        return ""

    return (
        child.text
        or ""
    ).strip()


def parse_discovery_feed(
    xml_text,
):

    if not isinstance(
        xml_text,
        str,
    ):
        return []

    if not xml_text.strip():
        return []

    try:

        root = ET.fromstring(
            xml_text
        )

    except ET.ParseError:
        return []

    articles = []

    for item in root.findall(
        ".//item"
    ):

        title = _element_text(
            item,
            "title",
        )

        url = _element_text(
            item,
            "link",
        )

        published_at = (
            _element_text(
                item,
                "pubDate",
            )
        )

        source_element = (
            item.find(
                "source"
            )
        )

        publisher = ""
        publisher_url = ""

        if source_element is not None:

            publisher = (
                source_element.text
                or ""
            ).strip()

            publisher_url = (
                source_element
                .attrib
                .get(
                    "url",
                    "",
                )
                or ""
            ).strip()

        if not _is_http_url(
            url
        ):
            continue

        articles.append(
            {
                "title": title,
                "url": url,
                "published_at": (
                    published_at
                ),
                "publisher": (
                    publisher
                ),
                "publisher_url": (
                    publisher_url
                ),
            }
        )

    return articles


# =========================================================
# DISCOVERY RANKING
# =========================================================

def _normalize_words(text):

    if not isinstance(
        text,
        str,
    ):
        return set()

    words = re.findall(
        r"[a-zA-Z0-9À-ÿ]+",
        text.lower(),
    )

    ignored = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "for",
        "le",
        "la",
        "les",
        "de",
        "des",
        "du",
        "un",
        "une",
        "et",
        "en",
        "pour",
    }

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word not in ignored
        )
    }


def rank_discovered_sources(
    scored_topic,
    sources,
):

    if not isinstance(
        sources,
        list,
    ):
        return []

    query = (
        build_discovery_query(
            scored_topic
        )
    )

    topic = ""

    if isinstance(
        scored_topic,
        dict,
    ):

        topic = str(
            scored_topic.get(
                "topic",
                "",
            )
        )

    reference_words = (
        _normalize_words(
            query
        )
        |
        _normalize_words(
            topic
        )
    )

    seen_urls = set()
    ranked = []

    for source in sources:

        if not isinstance(
            source,
            dict,
        ):
            continue

        url = str(
            source.get(
                "url",
                "",
            )
        ).strip()

        if not _is_http_url(
            url
        ):
            continue

        normalized_url = (
            url.rstrip("/")
        )

        if normalized_url in seen_urls:
            continue

        seen_urls.add(
            normalized_url
        )

        title = str(
            source.get(
                "title",
                "",
            )
        )

        title_words = (
            _normalize_words(
                title
            )
        )

        matching_words = (
            reference_words
            & title_words
        )

        score = (
            len(
                matching_words
            )
            * 10
        )

        query_lower = (
            query
            .lower()
            .strip()
        )

        title_lower = (
            title.lower()
        )

        if (
            query_lower
            and query_lower
            in title_lower
        ):

            score += 50

        ranked_source = dict(
            source
        )

        ranked_source[
            "relevance_score"
        ] = score

        ranked.append(
            ranked_source
        )

    ranked.sort(
        key=lambda item: (
            item.get(
                "relevance_score",
                0,
            )
        ),
        reverse=True,
    )

    return ranked


# =========================================================
# GOOGLE NEWS RSS
# =========================================================

def build_discovery_feed_url(
    query,
):

    if not isinstance(
        query,
        str,
    ):

        query = ""

    query = query.strip()

    if not query:
        return ""

    encoded_query = (
        quote_plus(
            query
        )
    )

    return (
        "https://news.google.com/"
        "rss/search"
        f"?q={encoded_query}"
        "&hl=fr"
        "&gl=FR"
        "&ceid=FR:fr"
    )


def fetch_discovery_feed(
    query,
):

    result = {
        "query": query,
        "feed_url": "",
        "status": "UNUSABLE",
        "articles": [],
        "error": "",
    }

    feed_url = (
        build_discovery_feed_url(
            query
        )
    )

    result[
        "feed_url"
    ] = feed_url

    if not feed_url:

        result["error"] = (
            "Empty discovery query."
        )

        return result

    request = Request(
        feed_url,
        headers={
            "User-Agent": (
                USER_AGENT
            ),
            "Accept": (
                "application/rss+xml,"
                "application/xml,"
                "text/xml"
            ),
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

            status_code = (
                response.getcode()
            )

            if not (
                200
                <= status_code
                < 300
            ):

                result["error"] = (
                    "Discovery HTTP "
                    f"{status_code}"
                )

                return result

            raw_bytes = (
                response.read(
                    MAX_PAGE_BYTES
                )
            )

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            xml_text = (
                raw_bytes.decode(
                    charset,
                    errors="replace",
                )
            )

            articles = (
                parse_discovery_feed(
                    xml_text
                )
            )

            result[
                "articles"
            ] = articles[
                :MAX_DISCOVERY_RESULTS
            ]

            if result[
                "articles"
            ]:

                result[
                    "status"
                ] = "USABLE"

            return result

    except HTTPError as error:

        result["error"] = (
            "Discovery HTTP error: "
            f"{error.code}"
        )

        return result

    except URLError as error:

        result["error"] = (
            "Discovery URL error: "
            f"{error.reason}"
        )

        return result

    except TimeoutError:

        result["error"] = (
            "Discovery request timed out."
        )

        return result

    except Exception as error:

        result["error"] = (
            "Discovery error: "
            f"{type(error).__name__}"
        )

        return result


def discover_topic_sources(
    scored_topic,
):

    query = (
        build_discovery_query(
            scored_topic
        )
    )

    print(
        f"Discovery query: {query}"
    )

    feed_result = (
        fetch_discovery_feed(
            query
        )
    )

    articles = (
        feed_result.get(
            "articles",
            [],
        )
    )

    ranked = (
        rank_discovered_sources(
            scored_topic,
            articles,
        )
    )

    return {
        "query": query,
        "feed_url": (
            feed_result.get(
                "feed_url",
                "",
            )
        ),
        "status": (
            feed_result.get(
                "status",
                "UNUSABLE",
            )
        ),
        "error": (
            feed_result.get(
                "error",
                "",
            )
        ),
        "sources": ranked[
            :MAX_DISCOVERY_RESULTS
        ],
    }


# =========================================================
# FETCH DISCOVERED SOURCES
# =========================================================

def fetch_discovered_sources(
    discovery_result,
):

    fetched = []

    sources = (
        discovery_result.get(
            "sources",
            [],
        )
    )

    for source in sources[
        :MAX_DISCOVERED_SOURCES_TO_FETCH
    ]:

        discovery_url = (
            source.get(
                "url",
                "",
            )
        )

        print("")
        print(
            "Discovery candidate:"
        )
        print(
            discovery_url
        )

        wrapper_html = ""

        if is_google_news_url(
            discovery_url
        ):

            print(
                "Google News wrapper detected."
            )

            wrapper_fetch = (
                fetch_raw_html_page(
                    discovery_url
                )
            )

            if (
                wrapper_fetch.get(
                    "status"
                )
                == "USABLE"
            ):

                wrapper_html = (
                    wrapper_fetch.get(
                        "html",
                        "",
                    )
                )

        resolution = (
            resolve_discovery_url(
                discovery_url,
                wrapper_html=wrapper_html,
            )
        )

        print(
            "Resolution status: "
            f"{resolution.get('status')}"
        )

        resolved_url = (
            resolution.get(
                "resolved_url",
                "",
            )
        )

        if not resolution.get(
            "can_fetch_as_evidence"
        ):

            fetched.append(
                {
                    "discovery_title": (
                        source.get(
                            "title",
                            "",
                        )
                    ),
                    "publisher": (
                        source.get(
                            "publisher",
                            "",
                        )
                    ),
                    "published_at": (
                        source.get(
                            "published_at",
                            "",
                        )
                    ),
                    "original_url": (
                        discovery_url
                    ),
                    "resolved_url": "",
                    "resolution_status": (
                        resolution.get(
                            "status"
                        )
                    ),
                    "fetch_status": (
                        "UNRESOLVED"
                    ),
                    "text": "",
                    "error": (
                        "Discovery URL "
                        "could not be resolved."
                    ),
                }
            )

            print(
                "Skipping wrapper as evidence."
            )

            continue

        print(
            "Resolved publisher URL: "
            f"{resolved_url}"
        )

        fetch_result = (
            fetch_public_page(
                resolved_url
            )
        )

        fetched.append(
            {
                "discovery_title": (
                    source.get(
                        "title",
                        "",
                    )
                ),
                "publisher": (
                    source.get(
                        "publisher",
                        "",
                    )
                ),
                "published_at": (
                    source.get(
                        "published_at",
                        "",
                    )
                ),
                "original_url": (
                    discovery_url
                ),
                "resolved_url": (
                    resolved_url
                ),
                "resolution_status": (
                    resolution.get(
                        "status"
                    )
                ),
                **fetch_result,
            }
        )

        print(
            "Publisher fetch result: "
            f"{fetch_result.get('fetch_status')} "
            f"[{fetch_result.get('extraction_method', '')}]"
        )

        print(
            "Publisher extracted characters: "
            f"{len(fetch_result.get('text', ''))}"
        )

    return fetched


# =========================================================
# V6 — EVIDENCE COLLECTION
# =========================================================

def collect_usable_evidence(
    original_sources,
    discovered_sources,
):

    evidence = []
    seen_urls = set()

    all_sources = []

    if isinstance(
        original_sources,
        list,
    ):
        all_sources.extend(
            original_sources
        )

    if isinstance(
        discovered_sources,
        list,
    ):
        all_sources.extend(
            discovered_sources
        )

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

        url = str(
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
        ).strip()

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(
            url
        )

        evidence.append(
            {
                "url": url,
                "text": text,
                "publisher": (
                    source.get(
                        "publisher",
                        ""
                    )
                ),
                "title": (
                    source.get(
                        "discovery_title"
                    )
                    or source.get(
                        "title",
                        ""
                    )
                ),
            }
        )

    return evidence


# =========================================================
# V6 — CLAIM SELECTION
# =========================================================

def select_claims_for_verification(
    claims,
    max_claims=MAX_CLAIMS_PER_RUN,
):

    selected = []

    if not isinstance(
        claims,
        list,
    ):
        return selected

    try:

        max_claims = int(
            max_claims
        )

    except (
        TypeError,
        ValueError,
    ):

        max_claims = (
            MAX_CLAIMS_PER_RUN
        )

    max_claims = max(
        0,
        max_claims,
    )

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

        text = str(
            claim.get(
                "claim",
                "",
            )
        ).strip()

        if not text:
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
# V6 — VERIFICATION RESULT SAFETY
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

    if not isinstance(
        allowed_source_urls,
        set,
    ):

        try:

            allowed_source_urls = set(
                allowed_source_urls
            )

        except Exception:

            allowed_source_urls = set()

    claim = str(
        result.get(
            "claim",
            "",
        )
    ).strip()

    status = (
        normalize_claim_status(
            result.get(
                "status",
                "UNKNOWN",
            )
        )
    )

    reason = str(
        result.get(
            "reason",
            "",
        )
    ).strip()

    source_urls = (
        result.get(
            "supporting_source_urls",
            [],
        )
    )

    if not isinstance(
        source_urls,
        list,
    ):
        source_urls = []

    approved_urls = []

    for url in source_urls:

        if not isinstance(
            url,
            str,
        ):
            continue

        url = url.strip()

        if not url:
            continue

        if (
            url
            not in allowed_source_urls
        ):
            continue

        if url in approved_urls:
            continue

        approved_urls.append(
            url
        )

    # Critical safety gate:
    # AI cannot confirm a fact unless it cites
    # one of the exact evidence URLs we supplied.
    if (
        status == "CONFIRMED"
        and not approved_urls
    ):

        status = "UNKNOWN"
        approved_urls = []

    return {
        "claim": claim,
        "status": status,
        "supporting_source_urls": (
            approved_urls
        ),
        "reason": reason,
    }


# =========================================================
# V6 — JSON RESPONSE EXTRACTION
# =========================================================

def extract_ai_json(
    text,
):

    if not text:

        raise ValueError(
            "Empty AI response."
        )

    cleaned = (
        text.strip()
    )

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

        start = (
            cleaned.find(
                "{"
            )
        )

        end = (
            cleaned.rfind(
                "}"
            )
        )

        if (
            start == -1
            or end == -1
            or end <= start
        ):

            raise ValueError(
                "No JSON object found."
            )

        return json.loads(
            cleaned[
                start:end + 1
            ]
        )


# =========================================================
# V6 — GROQ FREE-TIER SAFE CALL
# =========================================================

def groq_chat(
    messages,
):

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

                retry_after = None

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

            print("")
            print(
                "GROQ FREE LIMIT REACHED"
            )

            print(
                "Verification attempt "
                f"{attempt}/"
                f"{GROQ_MAX_RETRIES}"
            )

            if (
                attempt
                >= GROQ_MAX_RETRIES
            ):
                raise

            print(
                "Waiting "
                f"{wait_seconds:.1f}s..."
            )

            time.sleep(
                wait_seconds
            )

    raise RuntimeError(
        "Groq verification failed."
    )


# =========================================================
# V6 — VERIFICATION PROMPT
# =========================================================

def build_verification_messages(
    claim,
    evidence,
):

    evidence_for_ai = []

    for item in evidence[
        :MAX_EVIDENCE_SOURCES_FOR_AI
    ]:

        text = str(
            item.get(
                "text",
                "",
            )
        )

        evidence_for_ai.append(
            {
                "url": (
                    item.get(
                        "url",
                        ""
                    )
                ),
                "title": (
                    item.get(
                        "title",
                        ""
                    )
                ),
                "publisher": (
                    item.get(
                        "publisher",
                        ""
                    )
                ),
                "text": (
                    text[
                        :MAX_EVIDENCE_CHARS_PER_SOURCE
                    ]
                ),
            }
        )

    system_prompt = """
You are the fact-verification engine for GamerQuest FR.

You are NOT allowed to use memory, general knowledge,
assumptions, rumours, or information outside the evidence
provided in this prompt.

Evaluate exactly one claim.

Allowed statuses:

CONFIRMED:
The supplied source text directly supports the claim.

UNCONFIRMED:
The supplied source text directly contradicts the claim
or clearly shows that the claim is not established.

UNKNOWN:
The available evidence is insufficient, vague, unrelated,
or does not explicitly establish the claim.

IMPORTANT RULES:

1. Do not infer a release date.
2. Do not invent facts.
3. Do not treat search-result titles as proof.
4. Only cite URLs supplied in EVIDENCE.
5. CONFIRMED requires at least one supporting source URL.
6. If uncertain, return UNKNOWN.
7. Never upgrade a claim merely because it sounds plausible.

Return ONLY valid JSON in this exact structure:

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
                ""
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
            "content": (
                system_prompt
            ),
        },
        {
            "role": "user",
            "content": (
                user_prompt
            ),
        },
    ]


# =========================================================
# V6 — VERIFY ONE CLAIM
# =========================================================

def verify_claim_with_groq(
    claim,
    evidence,
):

    allowed_source_urls = {
        item.get(
            "url"
        )
        for item in evidence
        if item.get(
            "url"
        )
    }

    response_text = groq_chat(
        build_verification_messages(
            claim,
            evidence,
        )
    )

    raw_result = (
        extract_ai_json(
            response_text
        )
    )

    raw_result[
        "claim"
    ] = claim.get(
        "claim",
        "",
    )

    return (
        normalize_verification_result(
            raw_result,
            allowed_source_urls,
        )
    )


# =========================================================
# V6 — VERIFY CLAIM SET
# =========================================================

def verify_claims(
    claims,
    evidence,
):

    selected = (
        select_claims_for_verification(
            claims,
            max_claims=MAX_CLAIMS_PER_RUN,
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

    updated_claims = [
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
                "Groq free limit unavailable."
            )

            print(
                "Stopping verification safely."
            )

            print(
                "No paid fallback."
            )

            break

        except Exception as error:

            print(
                "Verification failed:"
            )

            print(
                str(error)
            )

            continue

        print(
            "Verification result: "
            f"{verification.get('status')}"
        )

        for claim in updated_claims:

            if (
                claim.get(
                    "claim"
                )
                != claim_text
            ):
                continue

            claim[
                "status"
            ] = verification.get(
                "status",
                "UNKNOWN",
            )

            claim[
                "sources"
            ] = verification.get(
                "supporting_source_urls",
                [],
            )

            claim[
                "verification_reason"
            ] = verification.get(
                "reason",
                "",
            )

            claim[
                "verified_at"
            ] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )

            break

    return updated_claims


# =========================================================
# JSON HELPERS
# =========================================================

def load_json(path):

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(
            file
        )


def save_json(
    path,
    data,
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = (
        path.with_suffix(
            path.suffix
            + ".tmp"
        )
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

        file.write(
            "\n"
        )

    temporary_file.replace(
        path
    )


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

    for topic in intel_data.get(
        "topics",
        [],
    ):

        if (
            topic.get(
                "id"
            )
            == topic_id
        ):

            return topic

    return None


def extract_source_evidence(
    intel_topic,
):

    evidence = []

    for source in intel_topic.get(
        "sources",
        [],
    ):

        if not isinstance(
            source,
            dict,
        ):
            continue

        url = source.get(
            "url",
            "",
        )

        if not url:
            continue

        evidence.append(
            {
                "type": (
                    source.get(
                        "type",
                        "unknown",
                    )
                ),
                "url": url,
                "title": (
                    source.get(
                        "title",
                        "",
                    )
                ),
                "evidence": (
                    source.get(
                        "evidence",
                        "",
                    )
                ),
            }
        )

    return evidence


def fetch_topic_sources(
    intel_topic,
):

    fetched_sources = []

    for source in (
        extract_source_evidence(
            intel_topic
        )
    ):

        print(
            "Fetching original source: "
            f"{source['url']}"
        )

        result = (
            fetch_public_page(
                source["url"]
            )
        )

        fetched_sources.append(
            {
                "type": (
                    source.get(
                        "type",
                        "unknown",
                    )
                ),
                "title": (
                    source.get(
                        "title",
                        "",
                    )
                ),
                "expected_evidence": (
                    source.get(
                        "evidence",
                        "",
                    )
                ),
                **result,
            }
        )

        print(
            "Fetch result: "
            f"{result.get('fetch_status')} "
            f"[{result.get('extraction_method', '')}]"
        )

        print(
            "Extracted characters: "
            f"{len(result.get('text', ''))}"
        )

    return fetched_sources


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
# SOURCE COUNTERS
# =========================================================

def count_source_statuses(
    sources,
):

    usable = sum(
        1
        for source in sources
        if (
            source.get(
                "fetch_status"
            )
            == "USABLE"
        )
    )

    weak = sum(
        1
        for source in sources
        if (
            source.get(
                "fetch_status"
            )
            == "WEAK"
        )
    )

    unresolved = sum(
        1
        for source in sources
        if (
            source.get(
                "fetch_status"
            )
            == "UNRESOLVED"
        )
    )

    unusable = (
        len(sources)
        - usable
        - weak
        - unresolved
    )

    return {
        "total": (
            len(sources)
        ),
        "usable": usable,
        "weak": weak,
        "unresolved": (
            unresolved
        ),
        "unusable": (
            unusable
        ),
    }


# =========================================================
# RESEARCH RECORD V6
# =========================================================

def build_research_record(
    scored_topic,
    intel_topic,
):

    initial_claims = (
        build_initial_claims(
            intel_topic
        )
    )

    # Original source fetch
    original_sources = (
        fetch_topic_sources(
            intel_topic
        )
    )

    # Alternative discovery
    discovery = (
        discover_topic_sources(
            scored_topic
        )
    )

    print(
        "Discovered source candidates: "
        f"{len(discovery.get('sources', []))}"
    )

    discovered_sources = (
        fetch_discovered_sources(
            discovery
        )
    )

    # -----------------------------------------------------
    # V6: COLLECT ONLY USABLE EVIDENCE
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
    # V6: AUTOMATIC CLAIM VERIFICATION
    # -----------------------------------------------------

    verified_claims = (
        verify_claims(
            initial_claims,
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
        original_counts["unresolved"]
        + discovered_counts["unresolved"]
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
        "id": (
            scored_topic.get(
                "id"
            )
        ),
        "topic": (
            scored_topic.get(
                "topic"
            )
        ),
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
            "query": (
                discovery.get(
                    "query",
                    "",
                )
            ),
            "feed_url": (
                discovery.get(
                    "feed_url",
                    "",
                )
            ),
            "status": (
                discovery.get(
                    "status",
                    "UNUSABLE",
                )
            ),
            "error": (
                discovery.get(
                    "error",
                    "",
                )
            ),
            "candidate_count": (
                len(
                    discovery.get(
                        "sources",
                        [],
                    )
                )
            ),
            "candidates": (
                discovery.get(
                    "sources",
                    [],
                )
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
        "GAMERQUEST RESEARCHER V6"
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

    intel_data = (
        load_json(
            INTEL_FILE
        )
    )

    scored_data = (
        load_json(
            SCORED_FILE
        )
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
                "version": "6.0",
                "updated_at": None,
                "topics": [],
            }

    else:

        research_data = {
            "version": "6.0",
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
    # during Researcher development.
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
    ] = "6.0"

    research_data[
        "updated_at"
    ] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    save_json(
        RESEARCH_FILE,
        research_data,
    )

    print("")
    print(
        "==================================="
    )

    print(
        "RESEARCHER V6 COMPLETE"
    )

    print(
        "==================================="
    )

    print(
        "Created/refreshed "
        f"{created} research record(s)."
    )

    print(
        "Maximum AI verifications: "
        f"{MAX_CLAIMS_PER_RUN} claims per topic."
    )

    print(
        "No paid fallback."
    )

    print(
        "Only CONFIRMED claims enter "
        "the verified fact pack."
    )

    print(
        "No article publishing occurs "
        "in Researcher v6."
    )


if __name__ == "__main__":
    main()
