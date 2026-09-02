from social.config import SCORING_WEIGHTS


def clamp_score(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0

    return max(0.0, min(10.0, value))


def score_idea(idea):
    """
    Expected idea format:

    {
        "freshness": 0-10,
        "click_potential": 0-10,
        "curiosity": 0-10,
        "shareability": 0-10,
        "originality": 0-10,
        "gamerquest_relevance": 0-10
    }
    """

    total = 0.0
    max_weight = sum(SCORING_WEIGHTS.values())

    for criterion, weight in SCORING_WEIGHTS.items():
        raw_score = clamp_score(idea.get(criterion, 0))
        total += (raw_score / 10) * weight

    if max_weight == 0:
        return 0.0

    return round((total / max_weight) * 100, 2)


def rank_ideas(ideas):
    ranked = []

    for idea in ideas:
        if not isinstance(idea, dict):
            continue

        scored_idea = idea.copy()
        scored_idea["total_score"] = score_idea(idea)
        ranked.append(scored_idea)

    return sorted(
        ranked,
        key=lambda item: item.get("total_score", 0),
        reverse=True,
    )
