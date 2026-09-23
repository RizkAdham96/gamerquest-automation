import json
from pathlib import Path
from unittest.mock import patch

import pytest

import groq_budget


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
