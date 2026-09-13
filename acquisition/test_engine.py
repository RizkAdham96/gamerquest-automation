import json
from pathlib import Path

from acquisition.engine import build_shadow_queue, collect_candidates, score_candidate


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_specific_long_tail_beats_broad_head_term():
    covered = []
    specific = {
        "id": "space-marine-2-performance-ps5",
        "title": "Space Marine 2 performance PS5 Pro patch problème FPS",
        "source_type": "seo_intel",
        "keywords": ["Space Marine 2 performance PS5 Pro", "Space Marine 2 problème FPS"],
        "freshness": "fresh",
        "existing_score": 0,
        "sources": [{"type": "official"}],
    }
    broad = {
        "id": "gta-6-news",
        "title": "GTA 6 news",
        "source_type": "seo_intel",
        "keywords": ["GTA 6"],
        "freshness": "fresh",
        "existing_score": 0,
        "sources": [{"type": "news"}],
    }

    specific_result = score_candidate(specific, covered)
    broad_result = score_candidate(broad, covered)

    assert specific_result["score"] > broad_result["score"]
    assert specific_result["decision"] in {"PRIORITIZE", "WATCH"}


def test_historical_duplicate_is_blocked():
    candidate = {
        "id": "warlock-release-platforms",
        "title": "Warlock date de sortie plateformes gameplay",
        "source_type": "seo_intel",
        "keywords": ["Warlock date de sortie"],
        "freshness": "fresh",
        "existing_score": 80,
        "sources": [{"type": "official"}],
    }
    covered = [
        {
            "title": "Warlock (2027) : date de sortie, plateformes et aperçu du gameplay",
            "slug": "warlock-date-de-sortie",
            "seo": {"primary_keyword": "Warlock date de sortie"},
            "tags": [],
        }
    ]

    result = score_candidate(candidate, covered)

    assert result["decision"] == "SKIP"
    assert result["duplicate_risk"] is True


def test_missing_optional_inputs_are_safe(tmp_path):
    queue = build_shadow_queue(tmp_path)

    assert queue["count"] == 0
    assert queue["opportunities"] == []


def test_deal_free_window_gets_freshness_credit():
    candidate = {
        "id": "astral-ascent-free-epic",
        "title": "Astral Ascent gratuit Epic Games Store jusqu'au 17 septembre",
        "source_type": "deal",
        "keywords": ["Astral Ascent gratuit Epic Games Store"],
        "freshness": "urgent",
        "existing_score": 0,
        "sources": [{"type": "epic"}],
    }

    result = score_candidate(candidate, [])

    assert result["breakdown"]["freshness"] >= 12
    assert result["score"] >= 55


def test_collect_and_queue_are_sorted_by_score_descending(tmp_path):
    _write_json(
        tmp_path / "trending_seo" / "intel" / "topics.json",
        {
            "topics": [
                {
                    "id": "generic",
                    "topic": "Gaming news",
                    "keywords": ["gaming"],
                    "status": "new",
                    "sources": [],
                },
                {
                    "id": "specific",
                    "topic": "Monster Hunter Wilds erreur sauvegarde PC comment corriger",
                    "keywords": ["Monster Hunter Wilds erreur sauvegarde PC"],
                    "status": "new",
                    "sources": [{"type": "official"}],
                },
            ]
        },
    )

    candidates = collect_candidates(tmp_path)
    queue = build_shadow_queue(tmp_path)

    assert len(candidates) == 2
    assert queue["count"] == 2
    assert queue["opportunities"][0]["score"] >= queue["opportunities"][1]["score"]
    assert queue["opportunities"][0]["id"] == "specific"
