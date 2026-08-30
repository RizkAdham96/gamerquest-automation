import json
import html
import ipaddress
import re
import socket
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
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

USER_AGENT = (
    "Mozilla/5.0 (compatible; GamerQuestFR-Research/1.0; "
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

        # CONFIRMED without evidence is impossible.
        if (
            status == "CONFIRMED"
            and not sources
        ):
            normalized_claim["status"] = "UNKNOWN"
            status = "UNKNOWN"

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
# HTML CLEANING
# =========================================================

def clean_html_text(raw_html):
    """
    Convert a basic HTML page into readable text.

    Scripts/styles are removed completely.
    HTML tags are stripped.

    This is intentionally simple and dependency-free.
    """

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
# URL SAFETY
# =========================================================

def _is_public_ip(ip_text):

    try:
        ip = ipaddress.ip_address(ip_text)

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
    """
    Only public HTTP/HTTPS URLs are accepted.

    Blocks:
    - localhost
    - loopback
    - private networks
    - file://
    - ftp://
    - malformed URLs

    This prevents the research system from being
    used to access internal services.
    """

    if not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url)

    except Exception:
        return False

    if parsed.scheme not in {
        "http",
        "https",
    }:
        return False

    hostname = parsed.hostname

    if not hostname:
        return False

    hostname = hostname.lower().strip(".")

    if hostname in {
        "localhost",
        "localhost.localdomain",
    }:
        return False

    if hostname.endswith(".local"):
        return False

    # Direct IP address.
    try:
        ipaddress.ip_address(hostname)

        return _is_public_ip(hostname)

    except ValueError:
        pass

    # Resolve hostname and make sure it doesn't
    # point to a private/internal network.
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

    except socket.gaierror:
        # DNS failure means we don't fetch it.
        return False

    except Exception:
        return False

    if not addresses:
        return False

    for address in addresses:

        ip_text = address[4][0]

        if not _is_public_ip(ip_text):
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

    except (TypeError, ValueError):
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
# PAGE FETCHER
# =========================================================

def fetch_public_page(url):
    """
    Fetch one public webpage.

    Cost: €0.

    Failure does NOT confirm or deny a claim.
    It simply makes the source unavailable.
    """

    result = {
        "url": url,
        "fetch_status": "UNUSABLE",
        "http_status": None,
        "content_type": "",
        "final_url": "",
        "text": "",
        "error": "",
    }

    if not is_safe_public_url(url):

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

            final_url = response.geturl()

            # Redirect protection:
            # validate destination too.
            if not is_safe_public_url(
                final_url
            ):

                result["error"] = (
                    "Redirected to unsafe URL."
                )

                return result

            status_code = response.getcode()

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

            raw_html = raw_bytes.decode(
                charset,
                errors="replace",
            )

            cleaned_text = (
                clean_html_text(
                    raw_html
                )
            )

            cleaned_text = (
                cleaned_text[
                    :MAX_EXTRACTED_CHARS
                ]
            )

            result["text"] = (
                cleaned_text
            )

            result["fetch_status"] = (
                evaluate_fetch_result(
                    status_code,
                    cleaned_text,
                )
            )

            return result

    except HTTPError as error:

        result["http_status"] = (
            error.code
        )

        result["error"] = (
            f"HTTP error: "
            f"{error.code}"
        )

        return result

    except URLError as error:

        result["error"] = (
            f"URL error: "
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
            f"Fetch error: "
            f"{type(error).__name__}"
        )

        return result


# =========================================================
# JSON HELPERS
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
# WRITE CANDIDATES
# =========================================================

def get_write_candidates(
    scored_data,
):

    candidates = []

    for topic in scored_data.get(
        "topics",
        [],
    ):

        if not isinstance(
            topic,
            dict,
        ):
            continue

        decision = str(
            topic.get(
                "decision",
                "",
            )
        ).upper()

        if decision == "WRITE":

            candidates.append(
                topic
            )

    return candidates


# =========================================================
# INTEL LOOKUP
# =========================================================

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


# =========================================================
# SOURCE EVIDENCE
# =========================================================

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

    return evidence


# =========================================================
# FETCH ALL SOURCES
# =========================================================

def fetch_topic_sources(
    intel_topic,
):
    """
    Fetch every Intel source.

    One inaccessible website does not stop
    the entire research process.
    """

    fetched_sources = []

    for source in extract_source_evidence(
        intel_topic
    ):

        url = source["url"]

        print(
            f"Fetching source: {url}"
        )

        fetch_result = (
            fetch_public_page(
                url
            )
        )

        fetched_sources.append(
            {
                "type": source.get(
                    "type",
                    "unknown",
                ),
                "title": source.get(
                    "title",
                    "",
                ),
                "expected_evidence": (
                    source.get(
                        "evidence",
                        "",
                    )
                ),
                **fetch_result,
            }
        )

        print(
            "Fetch result: "
            f"{fetch_result['fetch_status']}"
        )

    return fetched_sources


# =========================================================
# INITIAL CLAIMS
# =========================================================

def build_initial_claims(
    intel_topic,
):

    claims = []

    for source in extract_source_evidence(
        intel_topic
    ):

        evidence = (
            source.get(
                "evidence",
                "",
            )
            .strip()
        )

        if not evidence:
            continue

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
# RESEARCH RECORD
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

    fetched_sources = (
        fetch_topic_sources(
            intel_topic
        )
    )

    fact_pack = (
        build_verified_fact_pack(
            initial_claims
        )
    )

    usable_sources = sum(
        1
        for source
        in fetched_sources
        if source.get(
            "fetch_status"
        ) == "USABLE"
    )

    return {
        "id": scored_topic.get(
            "id"
        ),
        "topic": scored_topic.get(
            "topic"
        ),
        "seo_score": scored_topic.get(
            "total_score"
        ),
        "seo_decision": scored_topic.get(
            "decision"
        ),
        "created_at": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
        ),
        "sources": (
            extract_source_evidence(
                intel_topic
            )
        ),
        "fetched_sources": (
            fetched_sources
        ),
        "source_summary": {
            "total_sources": (
                len(fetched_sources)
            ),
            "usable_sources": (
                usable_sources
            ),
            "unusable_sources": (
                len(fetched_sources)
                - usable_sources
            ),
        },
        "claims": initial_claims,
        "fact_pack": fact_pack,
        "research_status": (
            "PENDING_VERIFICATION"
        ),
    }


# =========================================================
# DUPLICATE PROTECTION
# =========================================================

def get_existing_research_ids(
    research_data,
):

    existing = set()

    for topic in research_data.get(
        "topics",
        [],
    ):

        topic_id = topic.get(
            "id"
        )

        if topic_id:

            existing.add(
                topic_id
            )

    return existing


# =========================================================
# MAIN
# =========================================================

def main():

    print("")
    print(
        "==================================="
    )
    print(
        "GAMERQUEST RESEARCHER V2"
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

        research_data = load_json(
            RESEARCH_FILE
        )

    else:

        research_data = {
            "version": "2.0",
            "updated_at": None,
            "topics": [],
        }

    candidates = (
        get_write_candidates(
            scored_data
        )
    )

    existing_ids = (
        get_existing_research_ids(
            research_data
        )
    )

    created = 0

    for scored_topic in candidates:

        topic_id = scored_topic.get(
            "id"
        )

        if not topic_id:
            continue

        if topic_id in existing_ids:

            print(
                f"Already researched: "
                f"{topic_id}"
            )

            continue

        intel_topic = (
            find_intel_topic(
                intel_data,
                topic_id,
            )
        )

        if intel_topic is None:

            print(
                f"Intel missing: "
                f"{topic_id}"
            )

            continue

        print("")
        print(
            f"Researching: "
            f"{scored_topic.get('topic')}"
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

        existing_ids.add(
            topic_id
        )

        created += 1

    if created == 0:

        print(
            "No new WRITE topics "
            "require research."
        )

        return

    research_data[
        "version"
    ] = "2.0"

    research_data[
        "updated_at"
    ] = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    save_json(
        RESEARCH_FILE,
        research_data,
    )

    print("")
    print(
        f"Created {created} "
        f"research record(s)."
    )

    print(
        "Source fetching complete."
    )

    print(
        "Claims remain UNKNOWN until "
        "verification is performed."
    )


if __name__ == "__main__":
    main()
