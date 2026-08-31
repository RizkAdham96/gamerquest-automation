# =========================================================
# V9 CLAIM-TARGETED EVIDENCE DISCOVERY
# =========================================================

MAX_CLAIM_DISCOVERY_QUERIES = 3


CLAIM_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "in",
    "on",
    "at",
    "for",
    "with",
    "from",
    "by",
    "is",
    "was",
    "were",
    "be",
    "been",
    "has",
    "have",
    "had",
    "this",
    "that",
    "its",
    "it",
    "as",
    "official",
    "officially",
    "game",
    "games",
    "news",

    "le",
    "la",
    "les",
    "un",
    "une",
    "des",
    "du",
    "de",
    "et",
    "ou",
    "dans",
    "sur",
    "avec",
    "pour",
    "par",
}


def _normalize_claim_text(text):

    return re.sub(
        r"\s+",
        " ",
        str(
            text
            or ""
        ),
    ).strip()


def _claim_words(text):

    words = re.findall(
        r"[a-zA-ZÀ-ÿ0-9]+",
        _normalize_claim_text(
            text
        ).lower(),
    )

    return [
        word
        for word in words
        if (
            len(word) >= 3
            and word
            not in CLAIM_STOPWORDS
        )
    ]


def _unique_words(words):

    seen = set()
    output = []

    for word in words:

        key = word.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            word
        )

    return output


def _important_claim_words(
    topic,
    claim,
):

    topic_words = _claim_words(
        topic
    )

    claim_words = _claim_words(
        claim
    )

    combined = _unique_words(
        topic_words
        + claim_words
    )

    return combined


def build_claim_discovery_queries(
    topic,
    claim,
):

    topic = _normalize_claim_text(
        topic
    )

    claim = _normalize_claim_text(
        claim
    )

    if not topic:
        return []

    if not claim:

        return [
            topic
        ]

    important_words = (
        _important_claim_words(
            topic,
            claim,
        )
    )

    claim_specific_words = []

    topic_word_set = {
        word.lower()
        for word
        in _claim_words(
            topic
        )
    }

    for word in important_words:

        if (
            word.lower()
            not in topic_word_set
        ):

            claim_specific_words.append(
                word
            )

    distinctive = " ".join(
        claim_specific_words[
            :8
        ]
    )

    queries = [
        (
            f'"{topic}" '
            f'{distinctive}'
        ).strip(),

        (
            f'{topic} '
            f'{claim}'
        ).strip(),

        (
            f'"{topic}" '
            f'{claim}'
        ).strip(),
    ]

    output = []
    seen = set()

    for query in queries:

        query = _normalize_claim_text(
            query
        )

        if not query:
            continue

        key = query.lower()

        if key in seen:
            continue

        seen.add(
            key
        )

        output.append(
            query
        )

        if (
            len(output)
            >= MAX_CLAIM_DISCOVERY_QUERIES
        ):
            break

    return output


def _entry_search_text(entry):

    if not isinstance(
        entry,
        dict,
    ):
        return ""

    return _normalize_claim_text(
        " ".join(
            [
                str(
                    entry.get(
                        "title",
                        "",
                    )
                ),
                str(
                    entry.get(
                        "description",
                        "",
                    )
                ),
            ]
        )
    )


def match_claim_to_feed_entry(
    entry,
    topic,
    claim,
):

    if not isinstance(
        entry,
        dict,
    ):
        return False

    searchable = (
        _entry_search_text(
            entry
        )
    )

    if not searchable:
        return False

    searchable_words = set(
        _claim_words(
            searchable
        )
    )

    topic_words = set(
        _claim_words(
            topic
        )
    )

    claim_words = set(
        _claim_words(
            claim
        )
    )

    if not topic_words:
        return False

    topic_matches = (
        topic_words
        & searchable_words
    )

    required_topic_matches = min(
        2,
        len(topic_words),
    )

    if (
        len(topic_matches)
        < required_topic_matches
    ):
        return False

    claim_specific_words = (
        claim_words
        - topic_words
    )

    if not claim_specific_words:

        return True

    claim_matches = (
        claim_specific_words
        & searchable_words
    )

    # Require meaningful claim-specific evidence.
    #
    # One generic shared word is not enough.
    required_claim_matches = min(
        2,
        len(claim_specific_words),
    )

    if (
        len(claim_matches)
        < required_claim_matches
    ):

        return False

    return True


def discover_claim_feed_candidates(
    feed_text,
    topic,
    claim,
):

    entries = extract_feed_entries(
        feed_text
    )

    candidates = []

    for entry in entries:

        if not match_claim_to_feed_entry(
            entry=entry,
            topic=topic,
            claim=claim,
        ):

            continue

        url = normalize_discovery_url(
            entry.get(
                "url",
                "",
            )
        )

        if not url:
            continue

        if is_search_result_url(
            url
        ):
            continue

        candidate = dict(
            entry
        )

        candidate[
            "url"
        ] = url

        candidate[
            "target_claim"
        ] = claim

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

    return deduplicate_candidates(
        candidates
    )


def merge_claim_evidence(
    general_evidence,
    claim_evidence,
):

    combined = []

    if isinstance(
        claim_evidence,
        list,
    ):

        # Claim-specific evidence comes first.
        combined.extend(
            claim_evidence
        )

    if isinstance(
        general_evidence,
        list,
    ):

        combined.extend(
            general_evidence
        )

    output = []
    seen = set()

    for evidence in combined:

        if not isinstance(
            evidence,
            dict,
        ):
            continue

        url = (
            evidence.get(
                "resolved_url"
            )
            or evidence.get(
                "final_url"
            )
            or evidence.get(
                "url"
            )
            or ""
        )

        url = normalize_discovery_url(
            url
        )

        if not url:
            continue

        if is_search_result_url(
            url
        ):
            continue

        key = (
            url
            .rstrip("/")
            .lower()
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        item = dict(
            evidence
        )

        item[
            "url"
        ] = url

        output.append(
            item
        )

    return output


def discover_public_feed_sources_for_claim(
    topic,
    claim,
):

    candidates = []

    queries = (
        build_claim_discovery_queries(
            topic,
            claim,
        )
    )

    print("")
    print(
        "V9 claim discovery:"
    )

    print(
        claim
    )

    for query in queries:

        print(
            "Target query: "
            f"{query}"
        )

    for feed in PUBLIC_GAMING_FEEDS:

        feed_url = feed.get(
            "url",
            "",
        )

        print(
            "Checking claim feed: "
            f"{feed_url}"
        )

        feed_text = fetch_feed(
            feed_url
        )

        if not feed_text:
            continue

        matches = (
            discover_claim_feed_candidates(
                feed_text=feed_text,
                topic=topic,
                claim=claim,
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

            match[
                "target_claim"
            ] = claim

            candidates.append(
                match
            )

    candidates = (
        deduplicate_candidates(
            candidates
        )
    )

    print(
        "CLAIM-TARGETED CANDIDATES: "
        f"{len(candidates)}"
    )

    return candidates


def fetch_claim_candidates(
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
            "Fetching claim candidate: "
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


def collect_claim_specific_evidence(
    topic,
    claims,
):

    evidence_by_claim = {}

    selected_claims = (
        select_claims_for_verification(
            claims
        )
    )

    for claim in selected_claims:

        claim_text = (
            _normalize_claim_text(
                claim.get(
                    "claim",
                    "",
                )
            )
        )

        if not claim_text:
            continue

        candidates = (
            discover_public_feed_sources_for_claim(
                topic=topic,
                claim=claim_text,
            )
        )

        fetched = (
            fetch_claim_candidates(
                candidates
            )
        )

        usable = (
            collect_usable_evidence(
                [],
                fetched,
            )
        )

        for item in usable:

            item[
                "target_claim"
            ] = claim_text

        evidence_by_claim[
            claim_text
        ] = usable

        print(
            "CLAIM-SPECIFIC USABLE EVIDENCE: "
            f"{len(usable)}"
        )

    return evidence_by_claim


def verify_claims_v9(
    claims,
    general_evidence,
    claim_evidence_map,
):

    selected = (
        select_claims_for_verification(
            claims
        )
    )

    if not selected:
        return claims

    if GROQ_CLIENT is None:

        print(
            "GROQ_API_KEY missing. "
            "Verification skipped safely."
        )

        return claims

    updated = [
        dict(
            claim
        )
        for claim in claims
    ]

    for selected_claim in selected:

        claim_text = (
            _normalize_claim_text(
                selected_claim.get(
                    "claim",
                    "",
                )
            )
        )

        specific = []

        if isinstance(
            claim_evidence_map,
            dict,
        ):

            specific = (
                claim_evidence_map.get(
                    claim_text,
                    [],
                )
            )

        evidence = (
            merge_claim_evidence(
                general_evidence,
                specific,
            )
        )

        if not evidence:

            print("")
            print(
                "No evidence for claim:"
            )

            print(
                claim_text
            )

            continue

        print("")
        print(
            "V9 verifying claim:"
        )

        print(
            claim_text
        )

        print(
            "Evidence sources supplied: "
            f"{len(evidence)}"
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
                _normalize_claim_text(
                    item.get(
                        "claim",
                        "",
                    )
                )
                != claim_text
            ):

                continue

            item[
                "status"
            ] = verification.get(
                "status",
                "UNKNOWN",
            )

            item[
                "sources"
            ] = verification.get(
                "supporting_source_urls",
                [],
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

            item[
                "verification_version"
            ] = "9.0"

            break

    return updated
