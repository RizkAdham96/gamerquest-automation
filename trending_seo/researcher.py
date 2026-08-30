import json
from datetime import datetime, timezone
from pathlib import Path


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


# =========================================================
# CLAIM STATUS SAFETY
# =========================================================

def normalize_claim_status(status):
    """
    Normalize claim status.

    Any unexpected value automatically becomes UNKNOWN.

    This prevents values such as:
    - probably
    - likely
    - maybe
    - assumed

    from being treated as verified facts.
    """

    if not isinstance(status, str):
        return "UNKNOWN"

    normalized = status.strip().upper()

    if normalized not in ALLOWED_STATUSES:
        return "UNKNOWN"

    return normalized


def should_allow_claim(status):
    """
    Only CONFIRMED claims are allowed into the
    article fact pack.

    UNCONFIRMED and UNKNOWN claims are blocked.
    """

    return (
        normalize_claim_status(status)
        == "CONFIRMED"
    )


# =========================================================
# VERIFIED FACT PACK
# =========================================================

def build_verified_fact_pack(claims):
    """
    Separate verified facts from blocked claims.

    The future article writer will receive
    confirmed_facts as its factual source.

    Unsupported claims remain visible in
    blocked_claims for auditing, but they are
    NOT authorized for article generation.
    """

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

        # A claim cannot be CONFIRMED without
        # at least one supporting source.
        if (
            status == "CONFIRMED"
            and not sources
        ):
            normalized_claim[
                "status"
            ] = "UNKNOWN"

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
# JSON HELPERS
# =========================================================

def load_json(path):
    """
    Load JSON safely from disk.
    """

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:

        return json.load(file)


def save_json(path, data):
    """
    Save formatted UTF-8 JSON.
    """

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

    temporary_file.replace(
        path
    )


# =========================================================
# GET WRITE CANDIDATES
# =========================================================

def get_write_candidates(scored_data):
    """
    Only topics approved as WRITE are allowed
    to enter the research stage.

    REVIEW and REJECT topics stop here.
    """

    candidates = []

    for topic in scored_data.get(
        "topics",
        [],
    ):

        if not isinstance(topic, dict):
            continue

        decision = str(
            topic.get(
                "decision",
                "",
            )
        ).upper()

        if decision != "WRITE":
            continue

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
    """
    Find the original raw Intel entry.

    Research must always be connected back to
    the original evidence.
    """

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
# SOURCE EXTRACTION
# =========================================================

def extract_source_evidence(
    intel_topic,
):
    """
    Convert Intel sources into structured
    research evidence.

    IMPORTANT:

    This does NOT claim that every sentence in
    the source is verified.

    It simply preserves the evidence already
    collected in Intel.

    A later research stage can fetch and inspect
    the actual pages.
    """

    evidence = []

    for source in intel_topic.get(
        "sources",
        [],
    ):

        if not isinstance(source, dict):
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
# INITIAL CLAIM CREATION
# =========================================================

def build_initial_claims(
    intel_topic,
):
    """
    Build conservative claims from explicit
    Intel evidence.

    These claims are NOT automatically confirmed.

    They remain UNKNOWN until the research stage
    actually validates them against source
    content.
    """

    claims = []

    for source in extract_source_evidence(
        intel_topic
    ):

        evidence = source.get(
            "evidence",
            "",
        ).strip()

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
# BUILD RESEARCH RECORD
# =========================================================

def build_research_record(
    scored_topic,
    intel_topic,
):
    """
    Build the initial research record.

    No claim is automatically considered true
    merely because AI or Intel mentioned it.
    """

    initial_claims = (
        build_initial_claims(
            intel_topic
        )
    )

    fact_pack = (
        build_verified_fact_pack(
            initial_claims
        )
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
    """
    Prevent repeated research records.
    """

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
    """
    Research Gate v1.

    Current responsibility:

    Scored WRITE topic
        ↓
    Original Intel evidence
        ↓
    Structured claims
        ↓
    Everything begins UNKNOWN
        ↓
    Future verifier confirms evidence

    This version intentionally does NOT publish
    articles and does NOT invent facts.
    """

    print("")
    print(
        "==================================="
    )
    print(
        "GAMERQUEST RESEARCH GATE"
    )
    print(
        "==================================="
    )

    if not INTEL_FILE.exists():

        print(
            "Intel file not found:"
        )

        print(
            INTEL_FILE
        )

        return

    if not SCORED_FILE.exists():

        print(
            "Scored topics file not found:"
        )

        print(
            SCORED_FILE
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
            "version": "1.0",
            "updated_at": None,
            "topics": [],
        }

    write_candidates = (
        get_write_candidates(
            scored_data
        )
    )

    if not write_candidates:

        print(
            "No WRITE topics waiting for research."
        )

        return

    existing_ids = (
        get_existing_research_ids(
            research_data
        )
    )

    created = 0

    for scored_topic in write_candidates:

        topic_id = scored_topic.get(
            "id"
        )

        if not topic_id:
            continue

        if topic_id in existing_ids:

            print(
                f"Skipping existing research: "
                f"{topic_id}"
            )

            continue

        intel_topic = find_intel_topic(
            intel_data,
            topic_id,
        )

        if intel_topic is None:

            print(
                f"Original Intel missing: "
                f"{topic_id}"
            )

            continue

        record = build_research_record(
            scored_topic,
            intel_topic,
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

        print(
            f"Research record created: "
            f"{topic_id}"
        )

    if created == 0:

        print(
            "No new research records created."
        )

        return

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
        "All claims remain blocked "
        "until verified."
    )


if __name__ == "__main__":
    main()
