import json
import html
import ipaddress
import re
import socket
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, quote_plus
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


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

USER_AGENT = (
    "Mozilla/5.0 (compatible; GamerQuestFR-Research/4.0; "
    "+https://gamerquestfr.com/)"
)


# =========================================================
# CLAIM SAFETY
# =========================================================

def normalize_claim_status(status):

    if not isinstance(status, str):
        return "UNKNOWN"

    normalized = status.strip().upper()

    if normalized not in ALLOWED_STATUSES:
        return "UNKNOWN"

    return normalized


def should_allow_claim(status):

    return normalize_claim_status(status) == "CONFIRMED"


def build_verified_fact_pack(claims):

    confirmed_facts = []
    blocked_claims = []

    for claim in claims:

        if not isinstance(claim, dict):
            continue

        normalized_claim = dict(claim)

        status = normalize_claim_status(
            normalized_claim.get(
                "status",
                "UNKNOWN",
            )
        )

        normalized_claim["status"] = status

        sources = normalized_claim.get(
            "sources",
            [],
        )

        if not isinstance(sources, list):
            sources = []

        normalized_claim["sources"] = sources

        # CONFIRMED without evidence must never pass.
        if (
            status == "CONFIRMED"
            and not sources
        ):
            status = "UNKNOWN"
            normalized_claim["status"] = status

        if should_allow_claim(status):

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

    if isinstance(value, dict):

        for key, child in value.items():

            if key in USEFUL_JSON_KEYS:

                if isinstance(child, str):

                    cleaned = re.sub(
                        r"\s+",
                        " ",
                        html.unescape(child),
                    ).strip()

                    if cleaned:
                        collected.append(cleaned)

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

    elif isinstance(value, list):

        for item in value:

            _collect_json_text(
                item,
                collected,
                parent_key,
            )


def _deduplicate_text_parts(parts):

    seen = set()
    result = []

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

        normalized = cleaned.lower()

        if normalized in seen:
            continue

        seen.add(normalized)
        result.append(cleaned)

    return " ".join(result)


# =========================================================
# JSON-LD EXTRACTION
# =========================================================

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

        # First try raw JSON.
        try:
            parsed = json.loads(block)

        except (
            json.JSONDecodeError,
            TypeError,
        ):
            pass

        # Then try HTML-decoded JSON.
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


# =========================================================
# EMBEDDED JSON EXTRACTION
# =========================================================

def extract_embedded_json_text(raw_html):

    if not raw_html:
        return ""

    text = str(raw_html)

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


# =========================================================
# BEST PAGE CONTENT
# =========================================================

def extract_best_page_text(raw_html):

    if not raw_html:
        return ""

    json_ld_text = extract_json_ld_text(
        raw_html
    )

    embedded_text = (
        extract_embedded_json_text(
            raw_html
        )
    )

    plain_text = clean_html_text(
        raw_html
    )

    parts = []

    # Structured content comes first.
    if json_ld_text:
        parts.append(json_ld_text)

    if embedded_text:
        parts.append(embedded_text)

    if plain_text:
        parts.append(plain_text)

    combined = _deduplicate_text_parts(
        parts
    )

    return combined[
        :MAX_EXTRACTED_CHARS
    ]


# =========================================================
# URL HELPERS
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
        parsed.scheme in {
            "http",
            "https",
        }
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

    hostname = (
        hostname
        .lower()
        .strip(".")
    )

    if hostname in {
        "localhost",
        "localhost.localdomain",
    }:
        return False

    if hostname.endswith(
        ".local"
    ):
        return False

    try:

        ipaddress.ip_address(
            hostname
        )

        return _is_public_ip(
            hostname
        )

    except ValueError:
        pass

    try:

        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or (
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
        200 <= status_code < 300
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

            result["http_status"] = (
                status_code
            )

            result["content_type"] = (
                content_type
            )

            result["final_url"] = (
                final_url
            )

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

                raw_bytes = raw_bytes[
                    :MAX_PAGE_BYTES
                ]

            charset = (
                response.headers
                .get_content_charset()
                or "utf-8"
            )

            raw_html = raw_bytes.decode(
                charset,
                errors="replace",
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

            result["text"] = (
                extracted_text
            )

            result["fetch_status"] = (
                evaluate_fetch_result(
                    status_code,
                    extracted_text,
                )
            )

            # Tiny HTML shells are not
            # strong enough for evidence.
            if (
                result["fetch_status"]
                == "USABLE"
                and len(
                    extracted_text
                ) < 80
            ):

                result["fetch_status"] = (
                    "WEAK"
                )

            return result

    except HTTPError as error:

        result["http_status"] = (
            error.code
        )

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
# V4 — DISCOVERY QUERY
# =========================================================

def build_discovery_query(
    scored_topic,
):
    """
    Build the search phrase used for
    source discovery.

    Preference:
    1. seo.primary_keyword
    2. top-level primary_keyword
    3. topic
    """

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

    if isinstance(seo, dict):

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
# V4 — RSS PARSER
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
        child.text or ""
    ).strip()


def parse_discovery_feed(
    xml_text,
):
    """
    Parse an RSS discovery feed.

    Discovery results are candidates only.
    They are NOT automatically trusted.
    """

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

        published_at = _element_text(
            item,
            "pubDate",
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

        # RSS results only need syntactic
        # HTTP validation here.
        #
        # Network/public-IP validation happens
        # later when the actual page is fetched.
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
# V4 — SOURCE RANKING
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
    """
    Rank discovery results according to
    title relevance.

    This ranking does NOT determine factual
    trustworthiness. It only decides which
    candidate pages we inspect first.
    """

    if not isinstance(
        sources,
        list,
    ):
        return []

    query = build_discovery_query(
        scored_topic
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
        _normalize_words(query)
        | _normalize_words(topic)
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
            len(matching_words)
            * 10
        )

        query_lower = (
            query.lower().strip()
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
# V4 — FREE DISCOVERY FEED
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
        quote_plus(query)
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

    result["feed_url"] = (
        feed_url
    )

    if not feed_url:

        result["error"] = (
            "Empty discovery query."
        )

        return result

    if not is_safe_public_url(
        feed_url
    ):

        result["error"] = (
            "Unsafe discovery URL."
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

            final_url = (
                response.geturl()
            )

            if not is_safe_public_url(
                final_url
            ):

                result["error"] = (
                    "Discovery redirected "
                    "to unsafe URL."
                )

                return result

            status_code = (
                response.getcode()
            )

            if not (
                200 <= status_code < 300
            ):

                result["error"] = (
                    "Discovery HTTP "
                    f"{status_code}"
                )

                return result

            raw_bytes = response.read(
                MAX_PAGE_BYTES
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

            result["articles"] = (
                articles[
                    :MAX_DISCOVERY_RESULTS
                ]
            )

            if result["articles"]:

                result["status"] = (
                    "USABLE"
                )

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


# =========================================================
# V4 — DISCOVER SOURCES
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

    feed_result = (
        fetch_discovery_feed(
            query
        )
    )

    articles = feed_result.get(
        "articles",
        [],
    )

    ranked = rank_discovered_sources(
        scored_topic,
        articles,
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
# V4 — FETCH DISCOVERED SOURCES
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

        url = source.get(
            "url",
            "",
        )

        print(
            "Fetching discovered source: "
            f"{url}"
        )

        fetch_result = (
            fetch_public_page(
                url
            )
        )

        combined = {
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
            "publisher_url": (
                source.get(
                    "publisher_url",
                    "",
                )
            ),
            "published_at": (
                source.get(
                    "published_at",
                    "",
                )
            ),
            "relevance_score": (
                source.get(
                    "relevance_score",
                    0,
                )
            ),
            **fetch_result,
        }

        fetched.append(
            combined
        )

        print(
            "Discovery fetch result: "
            f"{fetch_result.get('fetch_status')} "
            f"[{fetch_result.get('extraction_method', '')}]"
        )

        print(
            "Discovery extracted characters: "
            f"{len(fetch_result.get('text', ''))}"
        )

    return fetched


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
            path.suffix + ".tmp"
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

        file.write("\n")

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
        if isinstance(topic, dict)
        and str(
            topic.get(
                "decision",
                "",
            )
        ).upper() == "WRITE"
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
            f"{result['fetch_status']} "
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

        # IMPORTANT:
        #
        # Intel evidence is NEVER automatically
        # considered confirmed.
        claims.append(
            {
                "claim": evidence,
                "status": "UNKNOWN",
                "sources": [
                    source["url"]
                ],
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
        if source.get(
            "fetch_status"
        ) == "USABLE"
    )

    weak = sum(
        1
        for source in sources
        if source.get(
            "fetch_status"
        ) == "WEAK"
    )

    unusable = (
        len(sources)
        - usable
        - weak
    )

    return {
        "total": len(sources),
        "usable": usable,
        "weak": weak,
        "unusable": unusable,
    }


# =========================================================
# RESEARCH RECORD V4
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

    # -----------------------------------------------------
    # 1. Fetch original Intel sources
    # -----------------------------------------------------

    original_sources = (
        fetch_topic_sources(
            intel_topic
        )
    )

    original_counts = (
        count_source_statuses(
            original_sources
        )
    )

    # -----------------------------------------------------
    # 2. Discover alternative sources
    # -----------------------------------------------------

    discovery = (
        discover_topic_sources(
            scored_topic
        )
    )

    print(
        "Discovered source candidates: "
        f"{len(discovery.get('sources', []))}"
    )

    # -----------------------------------------------------
    # 3. Fetch discovered pages
    # -----------------------------------------------------

    discovered_sources = (
        fetch_discovered_sources(
            discovery
        )
    )

    discovered_counts = (
        count_source_statuses(
            discovered_sources
        )
    )

    # -----------------------------------------------------
    # 4. Combine source statistics
    # -----------------------------------------------------

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

    unusable_sources = (
        original_counts["unusable"]
        + discovered_counts["unusable"]
    )

    # -----------------------------------------------------
    # 5. Fact safety gate
    # -----------------------------------------------------

    # V4 discovers additional evidence,
    # but it STILL does not automatically
    # mark claims CONFIRMED.
    #
    # Claim verification comes next.
    fact_pack = (
        build_verified_fact_pack(
            initial_claims
        )
    )

    if usable_sources > 0:

        research_status = (
            "SOURCES_FOUND_PENDING_VERIFICATION"
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

        # Original Intel evidence
        "sources": (
            extract_source_evidence(
                intel_topic
            )
        ),

        # Original fetched pages
        "fetched_sources": (
            original_sources
        ),

        # V4 discovery data
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

        # Pages actually inspected
        "discovered_sources": (
            discovered_sources
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

        "claims": (
            initial_claims
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
        "GAMERQUEST RESEARCHER V4"
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
                "version": "4.0",
                "updated_at": None,
                "topics": [],
            }

    else:

        research_data = {
            "version": "4.0",
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

    # -----------------------------------------------------
    # Refresh WRITE candidates.
    #
    # This is intentional while the Researcher
    # architecture is still being developed.
    # -----------------------------------------------------

    research_data["topics"] = [
        topic
        for topic
        in research_data.get(
            "topics",
            [],
        )
        if topic.get("id")
        not in candidate_ids
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

        summary = (
            record.get(
                "source_summary",
                {},
            )
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
            "UNUSABLE: "
            f"{summary.get('unusable_sources', 0)}"
        )

        print(
            "STATUS: "
            f"{record.get('research_status')}"
        )

        created += 1

    research_data[
        "version"
    ] = "4.0"

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
        "RESEARCHER V4 COMPLETE"
    )

    print(
        "==================================="
    )

    print(
        "Created/refreshed "
        f"{created} research record(s)."
    )

    print(
        "Discovery sources are candidates only."
    )

    print(
        "Claims remain UNKNOWN until verification."
    )


if __name__ == "__main__":
    main()
