import json
from pathlib import Path
from unittest.mock import patch

import pytest

import groq_budget


def test_two_daily_carousels_fit_even_after_other_lanes_use_their_caps(tmp_path):
    state = tmp_path / "groq.json"
    day = "2026-10-02"
    for lane in ("news", "seo", "manual"):
        result = groq_budget.reserve_run(
            lane, groq_budget.lane_ceiling(lane), f"all-{lane}", path=state, day=day,
        )
        assert result["allowed"] is True
    for slot in ("12:30", "18:30"):
        result = groq_budget.reserve_run(
            "social", 17000, f"carousel-{slot}", path=state, day=day,
        )
        assert result["allowed"] is True, result["reason"]
    saved = json.loads(state.read_text())
    assert saved["lanes"]["social"] == 34000
    assert saved["global_reserved"] <= groq_budget.global_daily_ceiling()


def test_minimum_other_daily_allocations_preserve_full_quality_runs(tmp_path):
    state = tmp_path / "groq.json"
    day = "2026-10-02"
    result = groq_budget.reserve_run("news", 11000, "news", path=state, day=day)
    assert result["allowed"] is True
    for index in range(2):
        result = groq_budget.reserve_run("seo", 10000, f"seo-{index}", path=state, day=day)
        assert result["allowed"] is True
    for index in range(2):
        result = groq_budget.reserve_run("social", 17000, f"social-{index}", path=state, day=day)
        assert result["allowed"] is True


def test_shared_daily_reservations_stop_before_global_ceiling(tmp_path):
    state = tmp_path / "groq.json"

    first = groq_budget.reserve_run(
        "news",
        7000,
        "news-1",
        path=state,
        day="2026-09-22",
        global_cap=10000,
        lane_cap=10000,
    )
    second = groq_budget.reserve_run(
        "seo",
        4000,
        "seo-1",
        path=state,
        day="2026-09-22",
        global_cap=10000,
        lane_cap=10000,
    )

    assert first["allowed"] is True
    assert second["allowed"] is False
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["global_reserved"] == 7000


def test_lane_ceiling_prevents_one_automation_from_starving_others(tmp_path):
    state = tmp_path / "groq.json"

    first = groq_budget.reserve_run(
        "news",
        7000,
        "news-1",
        path=state,
        day="2026-09-22",
        global_cap=70000,
        lane_cap=7000,
    )
    second = groq_budget.reserve_run(
        "news",
        7000,
        "news-2",
        path=state,
        day="2026-09-22",
        global_cap=70000,
        lane_cap=7000,
    )

    assert first["allowed"] is True
    assert second["allowed"] is False
    assert "news daily ceiling" in second["reason"]


def test_new_utc_day_resets_shared_budget(tmp_path):
    state = tmp_path / "groq.json"
    groq_budget.reserve_run(
        "news",
        7000,
        "old-day",
        path=state,
        day="2026-09-21",
        global_cap=70000,
        lane_cap=42000,
    )

    new_state = groq_budget.load_state(
        state,
        day="2026-09-22",
    )

    assert new_state["global_reserved"] == 0
    assert new_state["lanes"]["news"] == 0


def test_local_run_budget_blocks_before_api_call():
    groq_budget.reset_local_counters()

    with patch.dict(
        "os.environ",
        {
            "GROQ_RUN_TOKEN_BUDGET": "2000",
            "GROQ_TPM_CEILING": "6000",
        },
        clear=False,
    ):
        with pytest.raises(groq_budget.GroqBudgetExhausted):
            groq_budget.consume_run_budget(
                "x" * 4500,
                800,
                lane="news",
                operation="unit-test",
                sleep_fn=lambda _seconds: None,
                monotonic_fn=lambda: 0.0,
            )


def test_tpm_guard_paces_without_reducing_output_cap():
    groq_budget.reset_local_counters()
    waits = []
    ticks = iter([0.0, 0.0, 66.0])

    with patch.dict(
        "os.environ",
        {
            "GROQ_RUN_TOKEN_BUDGET": "10000",
            "GROQ_TPM_CEILING": "3000",
        },
        clear=False,
    ):
        first = groq_budget.consume_run_budget(
            "a" * 1500,
            500,
            lane="social",
            operation="first",
            sleep_fn=waits.append,
            monotonic_fn=lambda: next(ticks),
        )
        second = groq_budget.consume_run_budget(
            "b" * 4503,
            500,
            lane="social",
            operation="second",
            sleep_fn=waits.append,
            monotonic_fn=lambda: next(ticks),
        )

    assert first == 1000
    assert second == 2001
    assert waits
    assert waits[0] >= 65.0


def test_news_quality_window_allows_two_calls_with_tpm_pacing():
    groq_budget.reset_local_counters()
    waits = []
    ticks = iter([0.0, 0.0, 66.0])

    with patch.dict(
        "os.environ",
        {
            "GROQ_RUN_TOKEN_BUDGET": "11000",
            "GROQ_TPM_CEILING": "6000",
        },
        clear=False,
    ):
        first = groq_budget.consume_run_budget(
            "a" * 7761,
            1700,
            lane="news",
            operation="news:draft",
            sleep_fn=waits.append,
            monotonic_fn=lambda: next(ticks),
        )
        second = groq_budget.consume_run_budget(
            "b" * 9711,
            1300,
            lane="news",
            operation="news:verify",
            sleep_fn=waits.append,
            monotonic_fn=lambda: next(ticks),
        )

    assert first == 4287
    assert second == 4537
    assert waits and waits[0] >= 65.0


def test_full_scheduled_day_fits_under_global_ceiling_with_headroom(tmp_path):
    state = tmp_path / "groq.json"
    day = "2026-09-22"

    for index in range(4):
        result = groq_budget.reserve_run(
            "news",
            11000,
            f"news-{index}",
            path=state,
            day=day,
            global_cap=70000,
            lane_cap=44000,
        )
        assert result["allowed"] is True

    result = groq_budget.reserve_run(
        "seo",
        10000,
        "seo-0",
        path=state,
        day=day,
        global_cap=70000,
        lane_cap=10000,
    )
    assert result["allowed"] is True

    primary = groq_budget.reserve_run(
        "social",
        8000,
        "social-primary",
        path=state,
        day=day,
        global_cap=70000,
        lane_cap=14000,
    )
    recovery = groq_budget.reserve_run(
        "social",
        6000,
        "social-recovery",
        path=state,
        day=day,
        global_cap=70000,
        lane_cap=14000,
    )

    assert primary["allowed"] is True
    assert recovery["allowed"] is True

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["global_reserved"] == 68000
    assert saved["lanes"] == {
        "news": 44000,
        "seo": 10000,
        "social": 14000,
        "manual": 0,
    }

    blocked = groq_budget.reserve_run(
        "manual",
        2001,
        "over-global-headroom",
        path=state,
        day=day,
        global_cap=70000,
        lane_cap=4000,
    )
    assert blocked["allowed"] is False
    assert "global daily ceiling" in blocked["reason"]


def test_release_run_returns_unused_reservation_to_budget(tmp_path):
    state = tmp_path / "groq.json"
    groq_budget.reserve_run(
        "seo",
        10000,
        "seo-failed-before-ai",
        path=state,
        day="2026-09-22",
        global_cap=70000,
        lane_cap=10000,
    )

    result = groq_budget.release_run(
        "seo-failed-before-ai",
        path=state,
        day="2026-09-22",
    )

    assert result["released"] is True
    assert result["tokens"] == 10000
    assert result["lane"] == "seo"

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["global_reserved"] == 0
    assert saved["lanes"]["seo"] == 0
    assert saved["reservations"] == []


def test_release_run_is_idempotent_when_reservation_is_missing(tmp_path):
    state = tmp_path / "groq.json"
    result = groq_budget.release_run(
        "missing",
        path=state,
        day="2026-09-22",
    )

    assert result["released"] is False
    assert result["reason"] == "not_found"


def test_reconcile_run_returns_unused_tokens_to_shared_budget(tmp_path):
    state = tmp_path / "groq.json"
    groq_budget.reserve_run(
        "seo",
        10000,
        "seo-run",
        path=state,
        day="2026-09-22",
        global_cap=70000,
        lane_cap=10000,
    )

    result = groq_budget.reconcile_run(
        "seo-run",
        used_tokens=3800,
        path=state,
        day="2026-09-22",
    )

    assert result["reconciled"] is True
    assert result["used_tokens"] == 3800
    assert result["released_tokens"] == 6200

    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["global_reserved"] == 3800
    assert saved["lanes"]["seo"] == 3800
    assert saved["reservations"][0]["tokens"] == 3800


def test_consume_run_budget_persists_estimated_usage_for_reconciliation(tmp_path):
    usage_file = tmp_path / "groq-usage.json"
    groq_budget.reset_local_counters()

    with patch.dict(
        "os.environ",
        {
            "GROQ_RUN_TOKEN_BUDGET": "10000",
            "GROQ_TPM_CEILING": "6000",
            "GROQ_USAGE_FILE": str(usage_file),
        },
        clear=False,
    ):
        estimate = groq_budget.consume_run_budget(
            "x" * 3000,
            500,
            lane="news",
            operation="usage-test",
            sleep_fn=lambda _seconds: None,
            monotonic_fn=lambda: 0.0,
        )

    payload = json.loads(usage_file.read_text(encoding="utf-8"))
    assert payload["estimated_tokens"] == estimate
    assert payload["calls"] == 1
