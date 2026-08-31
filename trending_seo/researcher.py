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
    "(compatible; GamerQuestFR-Research/7.0; "
    "+https://gamerquestfr.com/)"
)


# =========================================================
# DOMAINS WE NEVER WANT AS EVIDENCE
# =========================================================

GOOGLE_INFRASTRUCTURE_DOMAINS = {
    "google.com",
    "www.google.com",
    "news.google.com",
    "gstatic.com",
    "www.gstatic.com",
    "googleusercontent.com",
    "www.googleusercontent.com",
    "googleapis.com",
    "www.googleapis.com",
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


def build_verified_fact_pack(claims):

    confirmed_facts = []
    blocked_claims = []

    for claim in claims:

        if not isinstance(claim, dict):
            continue

        item = dict(claim)

        status = normalize_claim_status(
            item.get(
                "status",
                "UNKNOWN",
            )
        )

        sources = item.get(
            "sources",
            [],
        )

        if not isinstance(sources, list):
            sources = []

        item["status"] = status
        item["sources"] = sources

        # CONFIRMED is forbidden without evidence.
        if (
            status == "CONFIRMED"
            and not sources
        ):
            item["status"] = "UNKNOWN"
            status = "UNKNOWN"

        if should_allow_claim(status):

            confirmed_facts.append(item)

        else:

            blocked_claims.append(item)

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

    text = str(raw_html)

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

    text = html.unescape(text)

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

    if isinstance(value, dict):

        for key, child in value.items():

            if (
                key in USEFUL_JSON_KEYS
                and isinstance(child, str)
            ):

                cleaned = re.sub(
                    r"\s+",
                    " ",
                    html.unescape(child),
                ).strip()

                if cleaned:
                    collected.append(cleaned)

            if isinstance(
                child,
                (dict, list),
            ):

                _collect_json_text(
                    child,
                    collected,
                )

    elif isinstance(value, list):

        for child in value:

            _collect_json_text(
                child,
                collected,
            )


def _deduplicate_text_parts(parts):

    seen = set()
    output = []

    for part in parts:

        if not isinstance(part, str):
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
        output.append(cleaned)

    return " ".join(output)


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

            parsed = json.loads(block)

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            pass

        if parsed is None:

            try:

                parsed = json.loads(
                    html.unescape(block)
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


def extract_embedded_json_text(raw_html):

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

                parsed = json.loads(block)

            except (
                json.JSONDecodeError,
                TypeError,
            ):
                pass

            if parsed is None:

                try:

                    parsed = json.loads(
                        html.unescape(block)
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


def extract_best_page_text(raw_html):

    if not raw_html:
        return ""

    structured = extract_json_ld_text(
        raw_html
    )

    embedded = extract_embedded_json_text(
        raw_html
    )

    plain = clean_html_text(
        raw_html
    )

    parts = []

    if structured:
        parts.append(structured)

    if embedded:
        parts.append(embedded)

    if plain:
        parts.append(plain)

    return _deduplicate_text_parts(
        parts
    )[:MAX_EXTRACTED_CHARS]


# =========================================================
# URL SAFETY
# =========================================================

def _is_http_url(url):

    if not isinstance(url, str):
        return False

    try:

        parsed = urlparse(
            url.strip()
        )

    except Exception:
        return False

    return (
        parsed.scheme
        in {"http", "https"}
        and bool(parsed.netloc)
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

    if hostname.endswith(".local"):
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

    if not _is_http_url(url):
        return False

    try:

        parsed = urlparse(url)

    except Exception:
        return False

    hostname = parsed.hostname

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

        ip_text = address[4][0]

        if not _is_public_ip(
            ip_text
        ):
            return False

    return True


# =========================================================
# GOOGLE URL HELPERS
# =========================================================

def _hostname(url):

    try:

        return (
            urlparse(url).hostname
            or ""
        ).lower()

    except Exception:
        return ""


def is_google_news_url(url):

    hostname = _hostname(url)

    return (
        hostname == "news.google.com"
        or hostname.endswith(
            ".news.google.com"
        )
    )


def is_google_infrastructure_url(url):

    hostname = _hostname(url)

    if not hostname:
        return False

    if hostname in GOOGLE_INFRASTRUCTURE_DOMAINS:
        return True

    for domain in GOOGLE_INFRASTRUCTURE_DOMAINS:

        if hostname.endswith(
            "." + domain
        ):
            return True

    return False


# =========================================================
# V7 — NORMALIZE DISCOVERY URL
# =========================================================

def normalize_discovery_url(url):

    if not _is_http_url(url):
        return ""

    url = url.strip()

    # Google News wrapper is NOT evidence.
    if is_google_news_url(url):
        return ""

    if is_google_infrastructure_url(url):
        return ""

    return url


# =========================================================
# V7 — EVIDENCE CANDIDATE SCORING
# =========================================================

def score_evidence_candidate(candidate):

    if not isinstance(candidate, dict):
        return -1000

    url = str(
        candidate.get(
            "url",
            "",
        )
    ).strip()

    source_type = str(
        candidate.get(
            "source_type",
            "",
        )
    ).strip().lower()

    publisher = str(
        candidate.get(
            "publisher",
            "",
        )
    ).lower()

    title = str(
        candidate.get(
            "title",
            "",
        )
    ).lower()

    score = 0

    if source_type == "official":
        score += 100

    elif source_type == "publisher":
        score += 50

    elif source_type == "aggregator":
        score -= 20

    else:
        score += 5

    if is_google_news_url(url):
        score -= 150

    if is_google_infrastructure_url(url):
        score -= 150

    if not _is_http_url(url):
        score -= 100

    authority_words = {
        "official",
        "announcement",
        "announced",
        "publisher",
        "developer",
        "studio",
        "press release",
    }

    combined = (
        publisher
        + " "
        + title
    )

    for word in authority_words:

        if word in combined:
            score += 5

    return score


def rank_evidence_candidates(
    candidates,
):

    if not isinstance(
        candidates,
        list,
    ):
        return []

    seen_urls = set()
    ranked = []

    for candidate in candidates:

        if not isinstance(
            candidate,
            dict,
        ):
            continue

        url = str(
            candidate.get(
                "url",
                "",
            )
        ).strip()

        if not url:
            continue

        normalized_key = (
            url.rstrip("/")
            .lower()
        )

        if normalized_key in seen_urls:
            continue

        seen_urls.add(
            normalized_key
        )

        item = dict(candidate)

        item[
            "evidence_score"
        ] = score_evidence_candidate(
            item
        )

        ranked.append(item)

    ranked.sort(
        key=lambda item: item.get(
            "evidence_score",
            -1000,
        ),
        reverse=True,
    )

    return ranked


# =========================================================
# V7 — TOPIC / PAGE RELEVANCE
# =========================================================

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "wild",
    "hunt",
    "game",
    "games",
    "remaster",
    "remastered",
    "le",
    "la",
    "les",
    "des",
    "pour",
    "avec",
    "dans",
    "une",
    "un",
}


def _topic_keywords(topic):

    words = re.findall(
        r"[a-zA-ZÀ-ÿ0-9]+",
        str(topic).lower(),
    )

    return {
        word
        for word in words
        if (
            len(word) >= 3
            and word not in STOPWORDS
        )
    }


def classify_evidence_quality(
    text,
    topic,
    status_code,
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
        200 <= status_code < 300
    ):
        return "UNUSABLE"

    if not isinstance(text, str):
        return "UNUSABLE"

    cleaned = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if not cleaned:
        return "UNUSABLE"

    # Tiny page / JS shell.
    if len(cleaned) < 200:
        return "WEAK"

    topic_words = _topic_keywords(
        topic
    )

    if not topic_words:
        return "WEAK"

    page_words = set(
        re.findall(
            r"[a-zA-ZÀ-ÿ0-9]+",
            cleaned.lower(),
        )
    )

    matches = (
        topic_words
        & page_words
    )

    # Require meaningful topic overlap.
    minimum_matches = min(
        2,
        len(topic_words),
    )

    if len(matches) < minimum_matches:
        return "WEAK"

    return "USABLE"


# =========================================================
# BASIC FETCH RESULT
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
        200 <= status_code < 300
    ):
        return "UNUSABLE"

    if not isinstance(text, str):
        return "UNUSABLE"

    if not text.strip():
        return "UNUSABLE"

    return "USABLE"


# =========================================================
# RAW HTML FETCH
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
            "User-Agent": USER_AGENT,
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

            status_code = (
                response.getcode()
            )

            content_type = (
                response.headers.get(
                    "Content-Type",
                    "",
                )
            )

            result[
                "http_status"
            ] = status_code

            result[
                "final_url"
            ] = final_url

            result[
                "content_type"
            ] = content_type

            if (
                "text/html"
                not in content_type.lower()
                and
                "application/xhtml+xml"
                not in content_type.lower()
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

                raw_bytes = raw_bytes[
                    :MAX_PAGE_BYTES
                ]

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            result["html"] = (
                raw_bytes.decode(
                    charset,
                    errors="replace",
                )
            )

            result["status"] = (
                "USABLE"
            )

            return result

    except HTTPError as error:

        result[
            "http_status"
        ] = error.code

        result["error"] = (
            f"HTTP error: {error.code}"
        )

    except URLError as error:

        result["error"] = (
            "URL error: "
            f"{error.reason}"
        )

    except TimeoutError:

        result["error"] = (
            "Request timed out."
        )

    except Exception as error:

        result["error"] = (
            "Fetch error: "
            f"{type(error).__name__}"
        )

    return result


# =========================================================
# FETCH ARTICLE
# =========================================================

def fetch_public_page(
    url,
    topic="",
):

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

    raw = fetch_raw_html_page(
        url
    )

    result[
        "http_status"
    ] = raw.get(
        "http_status"
    )

    result[
        "content_type"
    ] = raw.get(
        "content_type",
        "",
    )

    result[
        "final_url"
    ] = raw.get(
        "final_url",
        "",
    )

    if raw.get("status") != "USABLE":

        result["error"] = (
            raw.get(
                "error",
                "",
            )
        )

        return result

    raw_html = raw.get(
        "html",
        "",
    )

    json_ld = extract_json_ld_text(
        raw_html
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

        extraction_method = (
            "JSON_LD"
        )

        if embedded:
            extraction_method += (
                "+EMBEDDED_JSON"
            )

    elif embedded:

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

    result["text"] = text

    if topic:

        result[
            "fetch_status"
        ] = classify_evidence_quality(
            text=text,
            topic=topic,
            status_code=result.get(
                "http_status"
            ),
        )

    else:

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
            ] == "USABLE"
            and len(text) < 80
        ):

            result[
                "fetch_status"
            ] = "WEAK"

    return result


# =========================================================
# V7 DISCOVERY QUERY
# =========================================================

def build_discovery_query(topic):

    # Tests can pass a string directly.
    if isinstance(topic, str):

        keyword = topic.strip()

    elif isinstance(topic, dict):

        seo = topic.get(
            "seo",
            {},
        )

        keyword = ""

        if isinstance(seo, dict):

            keyword = str(
                seo.get(
                    "primary_keyword",
                    "",
                )
            ).strip()

        if not keyword:

            keyword = str(
                topic.get(
                    "primary_keyword",
                    "",
                )
            ).strip()

        if not keyword:

            keyword = str(
                topic.get(
                    "topic",
                    "",
                )
            ).strip()

    else:

        keyword = ""

    if not keyword:
        return ""

    # v7 explicitly searches for authority signals.
    return (
        f'{keyword} official announcement news'
    )


# =========================================================
# GOOGLE NEWS RSS DISCOVERY
# =========================================================

def build_discovery_feed_url(query):

    if not query:
        return ""

    return (
        "https://news.google.com/"
        "rss/search"
        f"?q={quote_plus(query)}"
        "&hl=fr"
        "&gl=FR"
        "&ceid=FR:fr"
    )


def _element_text(
    element,
    tag,
):

    child = element.find(tag)

    if child is None:
        return ""

    return (
        child.text
        or ""
    ).strip()


def parse_discovery_feed(xml_text):

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
            item.find("source")
        )

        publisher = ""
        publisher_url = ""

        if source_element is not None:

            publisher = (
                source_element.text
                or ""
            ).strip()

            publisher_url = (
                source_element.attrib.get(
                    "url",
                    "",
                )
                or ""
            ).strip()

        if not _is_http_url(url):
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
                "source_type": (
                    "aggregator"
                    if is_google_news_url(url)
                    else "publisher"
                ),
            }
        )

    return articles


def fetch_discovery_feed(query):

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
        return result

    request = Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml,"
                "application/xml,"
                "text/xml"
            ),
        },
    )

    try:

        with urlopen(
            request,
            timeout=FETCH_TIMEOUT_SECONDS,
        ) as response:

            raw_bytes = response.read(
                MAX_PAGE_BYTES
            )

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            xml_text = raw_bytes.decode(
                charset,
                errors="replace",
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

            if result["articles"]:

                result["status"] = (
                    "USABLE"
                )

    except Exception as error:

        result["error"] = (
            "Discovery error: "
            f"{type(error).__name__}"
        )

    return result


# =========================================================
# V7 — GOOGLE NEWS PUBLISHER RESOLUTION
# =========================================================

def _extract_absolute_urls(raw_html):

    if not isinstance(
        raw_html,
        str,
    ):
        return []

    urls = re.findall(
        r'https?://[^"\'<>\\\s]+',
        raw_html,
        flags=re.IGNORECASE,
    )

    cleaned = []

    for url in urls:

        url = html.unescape(url)

        url = url.replace(
            "\\u0026",
            "&",
        )

        url = url.replace(
            "\\/",
            "/",
        )

        if url not in cleaned:
            cleaned.append(url)

    return cleaned


def extract_publisher_url_from_google_news_html(
    raw_html,
    google_url="",
    preferred_publisher_url="",
):

    candidates = []

    # Normal href links.
    hrefs = re.findall(
        r"""(?is)
        href\s*=\s*
        ["']
        (.*?)
        ["']
        """,
        str(raw_html),
        flags=re.VERBOSE,
    )

    for href in hrefs:

        candidate = urljoin(
            google_url,
            html.unescape(
                href.strip()
            ),
        )

        candidates.append(
            candidate
        )

    # Also inspect URLs hidden inside JS/data.
    candidates.extend(
        _extract_absolute_urls(
            raw_html
        )
    )

    preferred_host = _hostname(
        preferred_publisher_url
    )

    valid = []

    for candidate in candidates:

        candidate = normalize_discovery_url(
            candidate
        )

        if not candidate:
            continue

        if not _is_http_url(
            candidate
        ):
            continue

        if not is_safe_public_url(
            candidate
        ):
            continue

        valid.append(candidate)

    # Prefer publisher domain supplied in RSS.
    if preferred_host:

        for candidate in valid:

            candidate_host = (
                _hostname(
                    candidate
                )
            )

            if (
                candidate_host
                == preferred_host
                or candidate_host.endswith(
                    "." + preferred_host
                )
                or preferred_host.endswith(
                    "." + candidate_host
                )
            ):
                return candidate

    if valid:
        return valid[0]

    return ""


def resolve_discovery_url(
    url,
    wrapper_html="",
    preferred_publisher_url="",
):

    if not _is_http_url(url):

        return {
            "original_url": url,
            "resolved_url": "",
            "status": "INVALID",
            "can_fetch_as_evidence": False,
        }

    direct = normalize_discovery_url(
        url
    )

    if direct:

        return {
            "original_url": url,
            "resolved_url": direct,
            "status": "DIRECT",
            "can_fetch_as_evidence": True,
        }

    if not is_google_news_url(url):

        return {
            "original_url": url,
            "resolved_url": "",
            "status": "UNRESOLVED",
            "can_fetch_as_evidence": False,
        }

    publisher_url = (
        extract_publisher_url_from_google_news_html(
            wrapper_html,
            google_url=url,
            preferred_publisher_url=(
                preferred_publisher_url
            ),
        )
    )

    if not publisher_url:

        return {
            "original_url": url,
            "resolved_url": "",
            "status": "UNRESOLVED",
            "can_fetch_as_evidence": False,
        }

    return {
        "original_url": url,
        "resolved_url": publisher_url,
        "status": "RESOLVED",
        "can_fetch_as_evidence": True,
    }


# =========================================================
# DISCOVER TOPIC SOURCES
# =========================================================

def discover_topic_sources(
    scored_topic,
):

    query = build_discovery_query(
        scored_topic
    )

    print(
        f"Discovery query: {query}"
    )

    feed = fetch_discovery_feed(
        query
    )

    candidates = feed.get(
        "articles",
        [],
    )

    ranked = rank_evidence_candidates(
        candidates
    )

    return {
        "query": query,
        "feed_url": feed.get(
            "feed_url",
            "",
        ),
        "status": feed.get(
            "status",
            "UNUSABLE",
        ),
        "error": feed.get(
            "error",
            "",
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
    topic,
):

    fetched = []

    sources = discovery_result.get(
        "sources",
        [],
    )

    for source in sources[
        :MAX_DISCOVERED_SOURCES_TO_FETCH
    ]:

        original_url = source.get(
            "url",
            "",
        )

        print("")
        print(
            "Discovery candidate:"
        )
        print(original_url)

        wrapper_html = ""

        if is_google_news_url(
            original_url
        ):

            print(
                "Google News wrapper detected."
            )

            wrapper = fetch_raw_html_page(
                original_url
            )

            if (
                wrapper.get("status")
                == "USABLE"
            ):

                wrapper_html = (
                    wrapper.get(
                        "html",
                        "",
                    )
                )

        resolution = resolve_discovery_url(
            original_url,
            wrapper_html=wrapper_html,
            preferred_publisher_url=(
                source.get(
                    "publisher_url",
                    "",
                )
            ),
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
                    **source,
                    "original_url": (
                        original_url
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
                        "Could not resolve "
                        "publisher article."
                    ),
                }
            )

            continue

        print(
            "Resolved publisher URL: "
            f"{resolved_url}"
        )

        page = fetch_public_page(
            resolved_url,
            topic=topic,
        )

        fetched.append(
            {
                **source,
                "original_url": (
                    original_url
                ),
                "resolved_url": (
                    resolved_url
                ),
                "resolution_status": (
                    resolution.get(
                        "status"
                    )
                ),
                **page,
            }
        )

        print(
            "Publisher fetch result: "
            f"{page.get('fetch_status')}"
        )

        print(
            "Publisher extracted characters: "
            f"{len(page.get('text', ''))}"
        )

    return fetched


# =========================================================
# ORIGINAL INTEL SOURCES
# =========================================================

def extract_source_evidence(
    intel_topic,
):

    output = []

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

    topic_name = intel_topic.get(
        "topic",
        "",
    )

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
            source["url"],
            topic=topic_name,
        )

        fetched.append(
            {
                **source,
                **page,
            }
        )

        print(
            "Fetch result: "
            f"{page.get('fetch_status')}"
        )

        print(
            "Extracted characters: "
            f"{len(page.get('text', ''))}"
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

        claim = str(
            source.get(
                "evidence",
                "",
            )
        ).strip()

        if not claim:
            continue

        claims.append(
            {
                "claim": claim,
                "status": "UNKNOWN",
                "sources": [],
            }
        )

    return claims


# =========================================================
# V6/V7 — USABLE EVIDENCE
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

        url = normalize_discovery_url(
            url
        )

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        evidence.append(
            {
                "url": url,
                "text": text,
                "publisher": (
                    source.get(
                        "publisher",
                        "",
                    )
                ),
                "title": (
                    source.get(
                        "title",
                        "",
                    )
                ),
            }
        )

    return evidence


# =========================================================
# CLAIM VERIFICATION SELECTION
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

        claim_text = str(
            claim.get(
                "claim",
                "",
            )
        ).strip()

        if not claim_text:
            continue

        selected.append(claim)

        if (
            len(selected)
            >= max_claims
        ):
            break

    return selected


def normalize_verification_result(
    result,
    allowed_source_urls,
):

    if not isinstance(
        result,
        dict,
    ):
        result = {}

    allowed_source_urls = set(
        allowed_source_urls
        or []
    )

    status = normalize_claim_status(
        result.get(
            "status",
            "UNKNOWN",
        )
    )

    urls = result.get(
        "supporting_source_urls",
        [],
    )

    if not isinstance(urls, list):
        urls = []

    approved = []

    for url in urls:

        if (
            isinstance(url, str)
            and url in allowed_source_urls
            and url not in approved
        ):

            approved.append(url)

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
        "supporting_source_urls": (
            approved
        ),
        "reason": str(
            result.get(
                "reason",
                "",
            )
        ).strip(),
    }


# =========================================================
# GROQ HELPERS
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

        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if (
            start == -1
            or end == -1
        ):

            raise ValueError(
                "No JSON object found."
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
        "Groq verification failed."
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
You are GamerQuest FR's strict fact-verification engine.

You may use ONLY the supplied evidence.

Do not use memory.
Do not use general knowledge.
Do not infer dates.
Do not invent facts.
Do not treat search titles alone as proof.

Statuses:

CONFIRMED:
The evidence explicitly establishes the claim.

UNCONFIRMED:
The evidence directly contradicts the claim or clearly
shows the claim is not established.

UNKNOWN:
Evidence is insufficient, indirect, vague or unrelated.

CONFIRMED requires at least one exact URL supplied in
the evidence.

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
        item.get("url")
        for item in evidence
        if item.get("url")
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

    raw["claim"] = claim.get(
        "claim",
        "",
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
            MAX_CLAIMS_PER_RUN,
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
            "Verification skipped."
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
        print(claim_text)

        try:

            verification = (
                verify_claim_with_groq(
                    selected_claim,
                    evidence,
                )
            )

        except RateLimitError:

            print(
                "Groq free quota unavailable. "
                "Stopping safely."
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
                item.get("claim")
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
# SCORER / INTEL HELPERS
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
            topic.get("id")
            == topic_id
        ):

            return topic

    return None


def count_source_statuses(
    sources,
):

    counts = {
        "total": len(sources),
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

            counts["usable"] += 1

        elif status == "WEAK":

            counts["weak"] += 1

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
# BUILD V7 RESEARCH RECORD
# =========================================================

def build_research_record(
    scored_topic,
    intel_topic,
):

    topic_name = (
        scored_topic.get(
            "topic",
            "",
        )
        or intel_topic.get(
            "topic",
            "",
        )
    )

    claims = build_initial_claims(
        intel_topic
    )

    original_sources = (
        fetch_topic_sources(
            intel_topic
        )
    )

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
            discovery,
            topic_name,
        )
    )

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

    verified_claims = verify_claims(
        claims,
        usable_evidence,
    )

    fact_pack = (
        build_verified_fact_pack(
            verified_claims
        )
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
        "seo_score": scored_topic.get(
            "total_score"
        ),
        "seo_decision": scored_topic.get(
            "decision"
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
            "query": discovery.get(
                "query",
                "",
            ),
            "feed_url": discovery.get(
                "feed_url",
                "",
            ),
            "status": discovery.get(
                "status",
                "UNUSABLE",
            ),
            "error": discovery.get(
                "error",
                "",
            ),
            "candidate_count": len(
                discovery.get(
                    "sources",
                    [],
                )
            ),
            "candidates": discovery.get(
                "sources",
                [],
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
            "claims_total": len(
                verified_claims
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
        "GAMERQUEST RESEARCHER V7"
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
                "version": "7.0",
                "updated_at": None,
                "topics": [],
            }

    else:

        research_data = {
            "version": "7.0",
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
        topic.get("id")
        for topic in candidates
        if topic.get("id")
    }

    # Refresh current WRITE records
    # while researcher is under development.
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
            topic.get("id")
            not in candidate_ids
        )
    ]

    created = 0

    for scored_topic in candidates:

        topic_id = scored_topic.get(
            "id"
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
    ] = "7.0"

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
        "RESEARCHER V7 COMPLETE"
    )
    print(
        "==================================="
    )

    print(
        "Created/refreshed "
        f"{created} record(s)."
    )

    print(
        "Google wrappers and Google "
        "infrastructure are not evidence."
    )

    print(
        "Only relevant USABLE publisher "
        "content reaches verification."
    )

    print(
        "No paid fallback."
    )

    print(
        "No article publishing."
    )


if __name__ == "__main__":
    main()
