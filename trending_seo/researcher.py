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
from urllib.parse import parse_qsl, parse_qs, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from groq import Groq, RateLimitError

BASE_DIR = Path(__file__).resolve().parent
INTEL_FILE = BASE_DIR / "intel" / "topics.json"
SCORED_FILE = BASE_DIR / "scored_topics.json"
RESEARCH_FILE = BASE_DIR / "research_results.json"

ALLOWED_STATUSES = {"CONFIRMED", "UNCONFIRMED", "UNKNOWN"}
FETCH_TIMEOUT_SECONDS = 12
MAX_PAGE_BYTES = 2_000_000
MAX_EXTRACTED_CHARS = 25_000
MAX_DISCOVERED_SOURCES_TO_FETCH = 6
MAX_CLAIMS_PER_RUN = 3
MAX_EVIDENCE_SOURCES_FOR_AI = 5
MAX_EVIDENCE_CHARS_PER_SOURCE = 6_000
MAX_CLAIM_DISCOVERY_QUERIES = 3

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_MAX_RETRIES = 3
GROQ_DEFAULT_WAIT_SECONDS = 10

USER_AGENT = (
    "Mozilla/5.0 "
    "(compatible; GamerQuestFR-Research/9.0; +https://gamerquestfr.com/)"
)

PUBLIC_GAMING_FEEDS = [
    {"url": "https://www.pcgamer.com/rss/", "publisher": "PC Gamer", "source_type": "publisher"},
    {"url": "https://www.gamesradar.com/rss/", "publisher": "GamesRadar+", "source_type": "publisher"},
    {"url": "https://www.gamespot.com/feeds/mashup/", "publisher": "GameSpot", "source_type": "publisher"},
]

TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid",
}

GROQ_CLIENT = Groq(api_key=GROQ_API_KEY, max_retries=0) if GROQ_API_KEY else None


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp.replace(path)


# =========================================================
# CLAIM SAFETY
# =========================================================

def normalize_claim_status(status):
    if not isinstance(status, str):
        return "UNKNOWN"
    status = status.strip().upper()
    return status if status in ALLOWED_STATUSES else "UNKNOWN"


def should_allow_claim(status):
    return normalize_claim_status(status) == "CONFIRMED"


def _claim_sources(claim):
    sources = claim.get("sources", [])
    if not isinstance(sources, list):
        sources = []
    source_url = str(claim.get("source_url", "") or "").strip()
    if source_url and source_url not in sources:
        sources.append(source_url)
    return sources


def build_verified_fact_pack(claims):
    confirmed_facts = []
    blocked_claims = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        item = dict(claim)
        item["status"] = normalize_claim_status(item.get("status", "UNKNOWN"))
        item["sources"] = _claim_sources(item)
        if item["status"] == "CONFIRMED" and not item["sources"]:
            item["status"] = "UNKNOWN"
        if should_allow_claim(item["status"]):
            confirmed_facts.append(item)
        else:
            blocked_claims.append(item)
    return {"confirmed_facts": confirmed_facts, "blocked_claims": blocked_claims}


# =========================================================
# HTML EXTRACTION
# =========================================================

def clean_html_text(raw_html):
    if not raw_html:
        return ""
    text = str(raw_html)
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


USEFUL_JSON_KEYS = {
    "headline", "name", "title", "description", "articleBody",
    "text", "content", "body", "summary", "excerpt",
}


def _collect_json_text(value, collected):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in USEFUL_JSON_KEYS and isinstance(child, str):
                cleaned = re.sub(r"\s+", " ", html.unescape(child)).strip()
                if cleaned:
                    collected.append(cleaned)
            if isinstance(child, (dict, list)):
                _collect_json_text(child, collected)
    elif isinstance(value, list):
        for child in value:
            _collect_json_text(child, collected)


def _deduplicate_text_parts(parts):
    seen = set()
    out = []
    for part in parts:
        if not isinstance(part, str):
            continue
        cleaned = re.sub(r"\s+", " ", part).strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return " ".join(out)


def extract_json_ld_text(raw_html):
    if not raw_html:
        return ""
    blocks = re.findall(
        r'''(?is)<script[^>]*type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>''',
        str(raw_html),
    )
    collected = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        parsed = None
        try:
            parsed = json.loads(block)
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = json.loads(html.unescape(block))
            except (json.JSONDecodeError, TypeError):
                continue
        _collect_json_text(parsed, collected)
    return _deduplicate_text_parts(collected)


def extract_embedded_json_text(raw_html):
    if not raw_html:
        return ""
    patterns = [
        r'''(?is)<script[^>]*id\s*=\s*["']__NEXT_DATA__["'][^>]*>(.*?)</script>''',
        r'''(?is)<script[^>]*id\s*=\s*["']__NUXT_DATA__["'][^>]*>(.*?)</script>''',
        r'''(?is)<script[^>]*type\s*=\s*["']application/json["'][^>]*>(.*?)</script>''',
    ]
    collected = []
    for pattern in patterns:
        for block in re.findall(pattern, str(raw_html)):
            block = block.strip()
            if not block:
                continue
            parsed = None
            try:
                parsed = json.loads(block)
            except (json.JSONDecodeError, TypeError):
                try:
                    parsed = json.loads(html.unescape(block))
                except (json.JSONDecodeError, TypeError):
                    continue
            _collect_json_text(parsed, collected)
    return _deduplicate_text_parts(collected)


def extract_best_page_text(raw_html):
    if not raw_html:
        return ""
    return _deduplicate_text_parts([
        extract_json_ld_text(raw_html),
        extract_embedded_json_text(raw_html),
        clean_html_text(raw_html),
    ])[:MAX_EXTRACTED_CHARS]


# =========================================================
# URL SAFETY / NORMALIZATION
# =========================================================

def _is_http_url(url):
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_public_ip(ip_text):
    try:
        ip = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
        or ip.is_reserved or ip.is_unspecified
    )


def _hostname_is_unsafe(hostname):
    if not hostname:
        return True
    hostname = hostname.lower().strip(".")
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return True
    try:
        ipaddress.ip_address(hostname)
        return not _is_public_ip(hostname)
    except ValueError:
        return False


def is_safe_public_url(url):
    if not _is_http_url(url):
        return False
    parsed = urlparse(url)
    hostname = parsed.hostname
    if _hostname_is_unsafe(hostname):
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        pass
    try:
        addresses = socket.getaddrinfo(
            hostname,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except Exception:
        return False
    if not addresses:
        return False
    return all(_is_public_ip(address[4][0]) for address in addresses)


def normalize_discovery_url(url):
    if not isinstance(url, str):
        return ""
    url = url.strip()
    if not _is_http_url(url):
        return ""
    parsed = urlparse(url)
    filtered_query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    normalized = parsed._replace(
        query=urlencode(filtered_query, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def is_search_result_url(url):
    normalized = normalize_discovery_url(url)
    if not normalized:
        return False
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    path = (parsed.path or "").lower()
    if hostname in {"google.com", "www.google.com"} and (
        path.startswith("/search") or path.startswith("/url")
    ):
        return True
    if hostname == "news.google.com":
        return True
    if hostname in {"bing.com", "www.bing.com"} and path.startswith("/search"):
        return True
    return False


def resolve_discovery_url(url):
    normalized = normalize_discovery_url(url)
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"google.com", "www.google.com"} and parsed.path == "/url":
        params = parse_qs(parsed.query)
        targets = params.get("q") or params.get("url") or []
        if not targets:
            return ""
        target = normalize_discovery_url(targets[0])
        return target if target and not is_search_result_url(target) else ""
    if is_search_result_url(normalized):
        return ""
    return normalized


# =========================================================
# DISCOVERY QUERY / FEEDS
# =========================================================

def build_discovery_query(topic, claim=""):
    if isinstance(topic, dict):
        topic_name = str(topic.get("topic", "")).strip()
        seo = topic.get("seo", {})
        if isinstance(seo, dict):
            keyword = str(seo.get("primary_keyword", "")).strip()
            if keyword:
                topic_name = keyword
    else:
        topic_name = str(topic or "").strip()
    claim = str(claim or "").strip()
    return f"{topic_name} {claim}".strip() if claim else f"{topic_name} official announcement news".strip()


def _local_name(tag):
    if not isinstance(tag, str):
        return ""
    return tag.split("}", 1)[1] if "}" in tag else tag


def _element_clean_text(element):
    if element is None:
        return ""
    return re.sub(r"\s+", " ", html.unescape(" ".join(element.itertext()))).strip()


def extract_feed_entries(feed_text):
    if not isinstance(feed_text, str) or not feed_text.strip():
        return []
    try:
        root = ET.fromstring(feed_text)
    except ET.ParseError:
        return []

    entries = []
    for item in root.iter():
        if _local_name(item.tag) != "item":
            continue
        title = url = description = ""
        for child in list(item):
            name = _local_name(child.tag)
            if name == "title":
                title = _element_clean_text(child)
            elif name == "link":
                url = _element_clean_text(child)
            elif name in {"description", "summary", "content", "encoded"}:
                description = _element_clean_text(child)
        url = normalize_discovery_url(url)
        if title and url:
            entries.append({"title": title, "url": url, "description": description})

    for entry in root.iter():
        if _local_name(entry.tag) != "entry":
            continue
        title = url = description = ""
        for child in list(entry):
            name = _local_name(child.tag)
            if name == "title":
                title = _element_clean_text(child)
            elif name == "link":
                rel = child.attrib.get("rel", "alternate")
                href = child.attrib.get("href", "")
                if href and rel in {"", "alternate"}:
                    url = href
            elif name in {"summary", "content", "description"}:
                description = _element_clean_text(child)
        url = normalize_discovery_url(url)
        if title and url:
            entries.append({"title": title, "url": url, "description": description})

    return deduplicate_candidates(entries)


DISCOVERY_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "game", "games",
    "news", "official", "le", "la", "les", "de", "des", "du", "une", "un", "et",
}


def _topic_words(text):
    return {
        word for word in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", str(text or "").lower())
        if len(word) >= 3 and word not in DISCOVERY_STOPWORDS
    }


def discover_feed_candidates(feed_text, topic):
    entries = extract_feed_entries(feed_text)
    topic_words = _topic_words(topic)
    if not topic_words:
        return []
    candidates = []
    for entry in entries:
        searchable = f"{entry.get('title', '')} {entry.get('description', '')}"
        matches = topic_words & _topic_words(searchable)
        if len(matches) < min(2, len(topic_words)):
            continue
        candidate = dict(entry)
        candidate.update({"source_type": "rss", "publisher_match": True, "usable": True})
        candidates.append(candidate)
    return candidates


def deduplicate_candidates(candidates):
    if not isinstance(candidates, list):
        return []
    seen = set()
    output = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = normalize_discovery_url(candidate.get("url", ""))
        if not url:
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        item = dict(candidate)
        item["url"] = url
        output.append(item)
    return output


def rank_evidence_candidate(candidate):
    if not isinstance(candidate, dict):
        return 0
    url = normalize_discovery_url(candidate.get("url", ""))
    if not url or is_search_result_url(url):
        return 0
    source_type = str(candidate.get("source_type", "")).lower()
    score = 10 + {
        "official": 100,
        "publisher": 70,
        "rss": 60,
        "search": 20,
        "aggregator": 10,
    }.get(source_type, 0)
    if candidate.get("publisher_match", False):
        score += 25
    score += 30 if candidate.get("usable", False) else -40
    return max(score, 0)


def build_evidence_candidate_pool(candidates):
    output = []
    for candidate in deduplicate_candidates(candidates):
        if is_search_result_url(candidate.get("url", "")):
            continue
        score = rank_evidence_candidate(candidate)
        if score <= 0:
            continue
        item = dict(candidate)
        item["evidence_rank"] = score
        output.append(item)
    return sorted(output, key=lambda item: item.get("evidence_rank", 0), reverse=True)


# =========================================================
# V9 CLAIM-TARGETED DISCOVERY
# =========================================================

CLAIM_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "for", "with",
    "from", "by", "is", "was", "were", "be", "been", "has", "have", "had", "this",
    "that", "its", "it", "as", "official", "officially", "game", "games", "news",
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "dans", "sur",
    "avec", "pour", "par",
}


def _normalize_claim_text(text):
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _claim_words(text):
    return [
        word for word in re.findall(r"[a-zA-ZÀ-ÿ0-9]+", _normalize_claim_text(text).lower())
        if len(word) >= 3 and word not in CLAIM_STOPWORDS
    ]


def build_claim_discovery_queries(topic, claim):
    topic = _normalize_claim_text(topic)
    claim = _normalize_claim_text(claim)
    if not topic:
        return []
    if not claim:
        return [topic]
    topic_words = set(_claim_words(topic))
    distinctive = []
    seen = set()
    for word in _claim_words(claim):
        if word not in topic_words and word not in seen:
            seen.add(word)
            distinctive.append(word)
    distinctive_text = " ".join(distinctive[:8])
    raw = [
        f'"{topic}" {distinctive_text}'.strip(),
        f'{topic} {claim}'.strip(),
        f'"{topic}" {claim}'.strip(),
    ]
    output = []
    seen_q = set()
    for query in raw:
        key = query.lower()
        if query and key not in seen_q:
            seen_q.add(key)
            output.append(query)
        if len(output) >= MAX_CLAIM_DISCOVERY_QUERIES:
            break
    return output


def match_claim_to_feed_entry(entry, topic, claim):
    if not isinstance(entry, dict):
        return False
    searchable = _normalize_claim_text(
        f"{entry.get('title', '')} {entry.get('description', '')}"
    )
    if not searchable:
        return False
    searchable_words = set(_claim_words(searchable))
    topic_words = set(_claim_words(topic))
    claim_words = set(_claim_words(claim))
    if not topic_words:
        return False
    if len(topic_words & searchable_words) < min(2, len(topic_words)):
        return False
    claim_specific = claim_words - topic_words
    if not claim_specific:
        return True
    return len(claim_specific & searchable_words) >= min(2, len(claim_specific))


def discover_claim_feed_candidates(feed_text, topic, claim):
    candidates = []
    for entry in extract_feed_entries(feed_text):
        if not match_claim_to_feed_entry(entry, topic, claim):
            continue
        url = normalize_discovery_url(entry.get("url", ""))
        if not url or is_search_result_url(url):
            continue
        candidate = dict(entry)
        candidate.update({
            "url": url,
            "target_claim": claim,
            "source_type": "rss",
            "publisher_match": True,
            "usable": True,
        })
        candidates.append(candidate)
    return deduplicate_candidates(candidates)


def merge_claim_evidence(general_evidence, claim_evidence):
    combined = []
    if isinstance(claim_evidence, list):
        combined.extend(claim_evidence)
    if isinstance(general_evidence, list):
        combined.extend(general_evidence)
    output = []
    seen = set()
    for evidence in combined:
        if not isinstance(evidence, dict):
            continue
        url = evidence.get("resolved_url") or evidence.get("final_url") or evidence.get("url") or ""
        url = normalize_discovery_url(url)
        if not url or is_search_result_url(url):
            continue
        key = url.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        item = dict(evidence)
        item["url"] = url
        output.append(item)
    return output


# =========================================================
# FETCH / EVIDENCE
# =========================================================

def evaluate_fetch_result(status_code, text):
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        return "UNUSABLE"
    if not 200 <= status_code < 300 or not isinstance(text, str) or not text.strip():
        return "UNUSABLE"
    return "USABLE"


def fetch_url_bytes(url, accept):
    result = {"status": "UNUSABLE", "http_status": None, "final_url": "", "content_type": "", "body": b"", "error": ""}
    if not is_safe_public_url(url):
        result["error"] = "Unsafe URL."
        return result
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept, "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"})
    try:
        with urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            final_url = response.geturl()
            if not is_safe_public_url(final_url):
                result["error"] = "Unsafe redirect."
                return result
            body = response.read(MAX_PAGE_BYTES + 1)[:MAX_PAGE_BYTES]
            result.update({
                "status": "USABLE",
                "http_status": response.getcode(),
                "final_url": final_url,
                "content_type": response.headers.get("Content-Type", ""),
                "body": body,
                "charset": response.headers.get_content_charset() or "utf-8",
            })
    except HTTPError as error:
        result["http_status"] = error.code
        result["error"] = f"HTTP error: {error.code}"
    except URLError as error:
        result["error"] = f"URL error: {error.reason}"
    except Exception as error:
        result["error"] = f"Fetch error: {type(error).__name__}"
    return result


def fetch_public_page(url):
    result = {"url": url, "fetch_status": "UNUSABLE", "http_status": None, "final_url": "", "content_type": "", "text": "", "extraction_method": "", "error": ""}
    fetched = fetch_url_bytes(url, "text/html,application/xhtml+xml")
    result["http_status"] = fetched.get("http_status")
    result["final_url"] = fetched.get("final_url", "")
    result["content_type"] = fetched.get("content_type", "")
    if fetched.get("status") != "USABLE":
        result["error"] = fetched.get("error", "")
        return result
    content_type = fetched.get("content_type", "").lower()
    if "html" not in content_type and "xhtml" not in content_type:
        result["error"] = "Not HTML."
        return result
    raw_html = fetched.get("body", b"").decode(fetched.get("charset", "utf-8"), errors="replace")
    text = extract_best_page_text(raw_html)
    result["text"] = text
    result["extraction_method"] = "JSON_LD" if extract_json_ld_text(raw_html) else ("EMBEDDED_JSON" if extract_embedded_json_text(raw_html) else "HTML")
    result["fetch_status"] = evaluate_fetch_result(result["http_status"], text)
    if result["fetch_status"] == "USABLE" and len(text) < 200:
        result["fetch_status"] = "WEAK"
    return result


def fetch_feed(url):
    fetched = fetch_url_bytes(url, "application/rss+xml,application/atom+xml,application/xml,text/xml")
    if fetched.get("status") != "USABLE":
        return ""
    return fetched.get("body", b"").decode(fetched.get("charset", "utf-8"), errors="replace")


def discover_public_feed_sources(topic):
    candidates = []
    for feed in PUBLIC_GAMING_FEEDS:
        feed_text = fetch_feed(feed["url"])
        if not feed_text:
            continue
        for match in discover_feed_candidates(feed_text, topic):
            match["publisher"] = feed["publisher"]
            match["source_type"] = feed["source_type"]
            candidates.append(match)
    return deduplicate_candidates(candidates)


def discover_public_feed_sources_for_claim(topic, claim):
    candidates = []
    for feed in PUBLIC_GAMING_FEEDS:
        feed_text = fetch_feed(feed["url"])
        if not feed_text:
            continue
        for match in discover_claim_feed_candidates(feed_text, topic, claim):
            match["publisher"] = feed["publisher"]
            match["source_type"] = feed["source_type"]
            match["target_claim"] = claim
            candidates.append(match)
    return deduplicate_candidates(candidates)


def extract_source_evidence(intel_topic):
    output = []
    for source in intel_topic.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = normalize_discovery_url(source.get("url", ""))
        if url:
            output.append({
                "type": source.get("type", "unknown"),
                "url": url,
                "title": source.get("title", ""),
                "evidence": source.get("evidence", ""),
            })
    return output


def fetch_topic_sources(intel_topic):
    fetched = []
    for source in extract_source_evidence(intel_topic):
        page = fetch_public_page(source["url"])
        fetched.append({**source, **page})
    return fetched


def build_initial_claims(intel_topic):
    return [
        {"claim": str(source.get("evidence", "")).strip(), "status": "UNKNOWN", "sources": []}
        for source in extract_source_evidence(intel_topic)
        if str(source.get("evidence", "")).strip()
    ]


def fetch_candidates(candidates):
    fetched = []
    for candidate in build_evidence_candidate_pool(candidates)[:MAX_DISCOVERED_SOURCES_TO_FETCH]:
        url = resolve_discovery_url(candidate.get("url", ""))
        if not url or is_search_result_url(url):
            continue
        page = fetch_public_page(url)
        fetched.append({**candidate, **page, "resolved_url": url})
    return fetched


fetch_v8_candidates = fetch_candidates
fetch_claim_candidates = fetch_candidates


def collect_usable_evidence(original_sources, discovered_sources):
    evidence = []
    seen = set()
    for source in (original_sources if isinstance(original_sources, list) else []) + (discovered_sources if isinstance(discovered_sources, list) else []):
        if not isinstance(source, dict) or source.get("fetch_status") != "USABLE":
            continue
        text = str(source.get("text", "")).strip()
        if not text:
            continue
        url = source.get("resolved_url") or source.get("final_url") or source.get("url") or ""
        url = resolve_discovery_url(url)
        if not url or is_search_result_url(url) or url in seen:
            continue
        seen.add(url)
        evidence.append({
            "url": url,
            "text": text,
            "title": source.get("title", ""),
            "publisher": source.get("publisher", ""),
            "target_claim": source.get("target_claim", ""),
        })
    return evidence


def select_claims_for_verification(claims, max_claims=MAX_CLAIMS_PER_RUN):
    selected = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        if normalize_claim_status(claim.get("status", "UNKNOWN")) != "UNKNOWN":
            continue
        if not str(claim.get("claim", "")).strip():
            continue
        selected.append(claim)
        if len(selected) >= max_claims:
            break
    return selected


def collect_claim_specific_evidence(topic, claims):
    result = {}
    for claim in select_claims_for_verification(claims):
        claim_text = _normalize_claim_text(claim.get("claim", ""))
        candidates = discover_public_feed_sources_for_claim(topic, claim_text)
        usable = collect_usable_evidence([], fetch_claim_candidates(candidates))
        for item in usable:
            item["target_claim"] = claim_text
        result[claim_text] = usable
    return result


# =========================================================
# GROQ VERIFICATION
# =========================================================

def normalize_verification_result(result, allowed_source_urls):
    if not isinstance(result, dict):
        result = {}
    allowed = set(allowed_source_urls or [])
    status = normalize_claim_status(result.get("status", "UNKNOWN"))
    supplied = result.get("supporting_source_urls", [])
    if not isinstance(supplied, list):
        supplied = []
    approved = [url for url in supplied if isinstance(url, str) and url in allowed]
    approved = list(dict.fromkeys(approved))
    if status == "CONFIRMED" and not approved:
        status = "UNKNOWN"
    return {
        "claim": str(result.get("claim", "")).strip(),
        "status": status,
        "supporting_source_urls": approved,
        "reason": str(result.get("reason", "")).strip(),
    }


def extract_ai_json(text):
    if not text:
        raise ValueError("Empty AI response.")
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON found.")
        return json.loads(cleaned[start:end + 1])


def groq_chat(messages):
    if GROQ_CLIENT is None:
        raise RuntimeError("GROQ_API_KEY is missing.")
    for attempt in range(1, GROQ_MAX_RETRIES + 1):
        try:
            response = GROQ_CLIENT.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages,
                temperature=0,
            )
            return response.choices[0].message.content
        except RateLimitError as error:
            retry_after = None
            try:
                retry_after = error.response.headers.get("retry-after")
            except Exception:
                pass
            try:
                wait_seconds = float(retry_after)
            except Exception:
                wait_seconds = GROQ_DEFAULT_WAIT_SECONDS * attempt
            wait_seconds += 2
            if attempt >= GROQ_MAX_RETRIES:
                raise
            time.sleep(wait_seconds)
    raise RuntimeError("Groq request failed.")


def build_verification_messages(claim, evidence):
    evidence_for_ai = [
        {
            "url": item.get("url", ""),
            "title": item.get("title", ""),
            "publisher": item.get("publisher", ""),
            "text": str(item.get("text", ""))[:MAX_EVIDENCE_CHARS_PER_SOURCE],
        }
        for item in evidence[:MAX_EVIDENCE_SOURCES_FOR_AI]
    ]
    system_prompt = (
        "You are the strict fact-verification engine for GamerQuest FR. "
        "Use ONLY the supplied evidence. Never use memory or outside knowledge. "
        "Never infer a release date. Never invent a fact. Never treat a search result as evidence. "
        "Return CONFIRMED only when supplied text explicitly supports the claim. "
        "Return UNCONFIRMED only when supplied evidence explicitly contradicts the claim. "
        "Otherwise return UNKNOWN. A CONFIRMED result must cite at least one exact evidence URL. "
        "Return ONLY valid JSON with keys claim, status, supporting_source_urls, reason."
    )
    user_prompt = "CLAIM:\n" + str(claim.get("claim", "")) + "\n\nEVIDENCE:\n" + json.dumps(evidence_for_ai, ensure_ascii=False, indent=2)
    return [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]


def verify_claim_with_groq(claim, evidence):
    allowed_urls = {item.get("url") for item in evidence if item.get("url")}
    raw = extract_ai_json(groq_chat(build_verification_messages(claim, evidence)))
    raw["claim"] = claim.get("claim", "")
    return normalize_verification_result(raw, allowed_urls)


def verify_claims_v9(claims, general_evidence, claim_evidence_map):
    if GROQ_CLIENT is None:
        print("GROQ_API_KEY missing. Verification skipped safely.")
        return claims
    updated = [dict(claim) for claim in claims]
    for selected_claim in select_claims_for_verification(claims):
        claim_text = _normalize_claim_text(selected_claim.get("claim", ""))
        specific = claim_evidence_map.get(claim_text, []) if isinstance(claim_evidence_map, dict) else []
        evidence = merge_claim_evidence(general_evidence, specific)
        if not evidence:
            continue
        try:
            verification = verify_claim_with_groq(selected_claim, evidence)
        except RateLimitError:
            print("Groq free quota unavailable. Stopping safely. No paid fallback.")
            break
        except Exception as error:
            print(f"Verification failed: {error}")
            continue
        for item in updated:
            if _normalize_claim_text(item.get("claim", "")) != claim_text:
                continue
            item["status"] = verification.get("status", "UNKNOWN")
            item["sources"] = verification.get("supporting_source_urls", [])
            item["verification_reason"] = verification.get("reason", "")
            item["verified_at"] = datetime.now(timezone.utc).isoformat()
            item["verification_version"] = "9.0"
            break
    return updated


def verify_claims(claims, evidence):
    return verify_claims_v9(claims, evidence, {})


# =========================================================
# PIPELINE
# =========================================================

def get_write_candidates(scored_data):
    return [
        topic for topic in scored_data.get("topics", [])
        if isinstance(topic, dict) and str(topic.get("decision", "")).upper() == "WRITE"
    ]


def find_intel_topic(intel_data, topic_id):
    for topic in intel_data.get("topics", []):
        if topic.get("id") == topic_id:
            return topic
    return None


def count_source_statuses(sources):
    counts = {"total": len(sources), "usable": 0, "weak": 0, "unresolved": 0, "unusable": 0}
    for source in sources:
        status = source.get("fetch_status", "UNUSABLE")
        if status == "USABLE":
            counts["usable"] += 1
        elif status == "WEAK":
            counts["weak"] += 1
        elif status == "UNRESOLVED":
            counts["unresolved"] += 1
        else:
            counts["unusable"] += 1
    return counts


def build_research_record(scored_topic, intel_topic):
    topic_name = str(scored_topic.get("topic", "") or intel_topic.get("topic", "")).strip()
    claims = build_initial_claims(intel_topic)
    original_sources = fetch_topic_sources(intel_topic)
    feed_candidates = discover_public_feed_sources(topic_name)
    discovered_sources = fetch_v8_candidates(feed_candidates)
    general_evidence = collect_usable_evidence(original_sources, discovered_sources)
    claim_evidence_map = collect_claim_specific_evidence(topic_name, claims)
    verified_claims = verify_claims_v9(claims, general_evidence, claim_evidence_map)
    fact_pack = build_verified_fact_pack(verified_claims)
    confirmed = len(fact_pack["confirmed_facts"])
    blocked = len(fact_pack["blocked_claims"])
    all_specific = [item for items in claim_evidence_map.values() for item in items]
    all_evidence = merge_claim_evidence(general_evidence, all_specific)
    if confirmed > 0:
        status = "VERIFIED_FACTS_READY"
    elif all_evidence:
        status = "VERIFICATION_COMPLETE_NO_CONFIRMED_FACTS"
    else:
        status = "PENDING_VERIFICATION"
    return {
        "id": scored_topic.get("id"),
        "topic": topic_name,
        "seo_score": scored_topic.get("total_score"),
        "seo_decision": scored_topic.get("decision"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "sources": extract_source_evidence(intel_topic),
        "fetched_sources": original_sources,
        "discovered_sources": discovered_sources,
        "usable_evidence": general_evidence,
        "claim_specific_evidence": claim_evidence_map,
        "discovery": {
            "version": "9.0",
            "strategy": "original + public RSS/Atom + claim-targeted evidence",
            "feed_candidate_count": len(feed_candidates),
            "candidates": feed_candidates,
            "claim_queries": {
                claim.get("claim", ""): build_claim_discovery_queries(topic_name, claim.get("claim", ""))
                for claim in claims
            },
        },
        "verification_summary": {
            "version": "9.0",
            "max_claims_per_run": MAX_CLAIMS_PER_RUN,
            "claims_total": len(verified_claims),
            "confirmed": confirmed,
            "blocked": blocked,
            "general_usable_evidence_sources": len(general_evidence),
            "claim_specific_usable_evidence_sources": len(all_specific),
        },
        "claims": verified_claims,
        "fact_pack": fact_pack,
        "research_status": status,
    }


def main():
    print("\n===================================")
    print("GAMERQUEST RESEARCHER V9")
    print("===================================")
    if not INTEL_FILE.exists() or not SCORED_FILE.exists():
        print("Required input file missing.")
        return
    intel_data = load_json(INTEL_FILE)
    scored_data = load_json(SCORED_FILE)
    try:
        research_data = load_json(RESEARCH_FILE) if RESEARCH_FILE.exists() else {"version": "9.0", "updated_at": None, "topics": []}
    except Exception:
        research_data = {"version": "9.0", "updated_at": None, "topics": []}
    candidates = get_write_candidates(scored_data)
    candidate_ids = {topic.get("id") for topic in candidates if topic.get("id")}
    research_data["topics"] = [topic for topic in research_data.get("topics", []) if topic.get("id") not in candidate_ids]
    created = 0
    for scored_topic in candidates:
        topic_id = scored_topic.get("id")
        intel_topic = find_intel_topic(intel_data, topic_id)
        if not topic_id or intel_topic is None:
            continue
        record = build_research_record(scored_topic, intel_topic)
        research_data["topics"].append(record)
        print(f"STATUS: {record.get('research_status')}")
        created += 1
    research_data["version"] = "9.0"
    research_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(RESEARCH_FILE, research_data)
    print("===================================")
    print("RESEARCHER V9 COMPLETE")
    print("===================================")
    print(f"Created/refreshed {created} record(s).")
    print("No paid fallback. No article publishing.")


if __name__ == "__main__":
    main()
