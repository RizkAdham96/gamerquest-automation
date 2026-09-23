"""Shared Groq budget guard for every GamerQuest automation.

The goal is to stop BEFORE the external provider limit is reached. Production
workflows reserve a conservative daily allowance in state/groq_budget.json,
then every individual Groq call consumes from that run allowance and from a
local TPM safety window.

Quality is never reduced dynamically: when there is not enough budget for the
configured prompt + output size, the automation skips/defer the AI task.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = Path("state/groq_budget.json")

DEFAULT_GLOBAL_DAILY_CEILING = 70_000
DEFAULT_LANE_CEILINGS = {
    # Four 11k News windows + one 10k SEO window + an 8k primary Social
    # window and a 6k recovery window reserve at most 68k/day. This keeps
    # full-quality multi-call jobs viable while staying below the 70k guard.
    "news": 44_000,
    "seo": 10_000,
    "social": 14_000,
    "manual": 4_000,
}

# The account previously exposed an 8k TPM boundary. We stay materially below
# it so prompt-estimation error and provider-side token accounting have room.
DEFAULT_TPM_CEILING = 6_000
TOKEN_CHAR_DIVISOR = 3.0
MINUTE_WINDOW_SECONDS = 65.0


class GroqBudgetExhausted(RuntimeError):
    """Raised before an API call when GamerQuest's own ceiling is exhausted."""


_LOCAL_RUN_USED = 0
_LOCAL_MINUTE_USED = 0
_LOCAL_MINUTE_STARTED = None


def _int_env(name: str, default: int) -> int:
    try:
        value = int(str(os.getenv(name, default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(0, value)


def global_daily_ceiling() -> int:
    return _int_env(
        "GROQ_GLOBAL_DAILY_CEILING",
        DEFAULT_GLOBAL_DAILY_CEILING,
    )


def lane_ceiling(lane: str) -> int:
    lane = str(lane or "").strip().lower()
    default = DEFAULT_LANE_CEILINGS.get(lane, 0)
    return _int_env(
        f"GROQ_LANE_{lane.upper()}_CEILING",
        default,
    )


def tpm_ceiling() -> int:
    return _int_env("GROQ_TPM_CEILING", DEFAULT_TPM_CEILING)


def run_budget() -> int:
    # Missing/zero budget means "no production allocation". There is no
    # production bypass: every real Groq caller must receive a reserved budget.
    return _int_env("GROQ_RUN_TOKEN_BUDGET", 0)


def utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _default_state(day: str | None = None) -> dict[str, Any]:
    day = day or utc_day()
    return {
        "date_utc": day,
        "global_reserved": 0,
        "lanes": {
            lane: 0
            for lane in DEFAULT_LANE_CEILINGS
        },
        "reservations": [],
    }


def load_state(
    path: Path | str = DEFAULT_STATE_PATH,
    *,
    day: str | None = None,
) -> dict[str, Any]:
    path = Path(path)
    day = day or utc_day()
    if not path.exists():
        return _default_state(day)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _default_state(day)

    if not isinstance(data, dict) or data.get("date_utc") != day:
        return _default_state(day)

    data.setdefault("global_reserved", 0)
    data.setdefault("lanes", {})
    data.setdefault("reservations", [])
    for lane in DEFAULT_LANE_CEILINGS:
        data["lanes"].setdefault(lane, 0)
    return data


def save_state(
    state: dict[str, Any],
    path: Path | str = DEFAULT_STATE_PATH,
) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def reserve_run(
    lane: str,
    tokens: int,
    reservation_id: str,
    *,
    path: Path | str = DEFAULT_STATE_PATH,
    day: str | None = None,
    global_cap: int | None = None,
    lane_cap: int | None = None,
) -> dict[str, Any]:
    lane = str(lane or "").strip().lower()
    tokens = max(0, int(tokens))
    reservation_id = str(reservation_id or "").strip()
    if lane not in DEFAULT_LANE_CEILINGS:
        raise ValueError(f"Unknown Groq budget lane: {lane}")
    if tokens <= 0:
        raise ValueError("Reservation tokens must be positive.")
    if not reservation_id:
        raise ValueError("reservation_id is required.")

    day = day or utc_day()
    state = load_state(path, day=day)
    global_cap = global_daily_ceiling() if global_cap is None else int(global_cap)
    lane_cap = lane_ceiling(lane) if lane_cap is None else int(lane_cap)

    for existing in state.get("reservations", []):
        if existing.get("id") == reservation_id:
            return {
                "allowed": True,
                "tokens": int(existing.get("tokens", tokens)),
                "reason": "already_reserved",
                "state": state,
            }

    global_used = int(state.get("global_reserved", 0) or 0)
    lane_used = int(state.get("lanes", {}).get(lane, 0) or 0)

    if global_used + tokens > global_cap:
        return {
            "allowed": False,
            "tokens": 0,
            "reason": (
                f"global daily ceiling: {global_used}/{global_cap} already reserved"
            ),
            "state": state,
        }

    if lane_used + tokens > lane_cap:
        return {
            "allowed": False,
            "tokens": 0,
            "reason": (
                f"{lane} daily ceiling: {lane_used}/{lane_cap} already reserved"
            ),
            "state": state,
        }

    stamp = datetime.now(timezone.utc).isoformat()
    state["global_reserved"] = global_used + tokens
    state["lanes"][lane] = lane_used + tokens
    state["reservations"].append(
        {
            "id": reservation_id,
            "lane": lane,
            "tokens": tokens,
            "reserved_at": stamp,
        }
    )
    state["reservations"] = state["reservations"][-120:]
    save_state(state, path)

    return {
        "allowed": True,
        "tokens": tokens,
        "reason": "reserved",
        "state": state,
    }


def estimate_request_tokens(
    prompt_or_messages: Any,
    max_output_tokens: int,
) -> int:
    if isinstance(prompt_or_messages, str):
        text = prompt_or_messages
    else:
        try:
            text = json.dumps(
                prompt_or_messages,
                ensure_ascii=False,
                separators=(",", ":"),
            )
        except Exception:
            text = str(prompt_or_messages)

    # /3 is intentionally more conservative than the common /4 heuristic.
    input_estimate = math.ceil(len(text) / TOKEN_CHAR_DIVISOR)
    output = max(0, int(max_output_tokens))
    return input_estimate + output


def reset_local_counters() -> None:
    global _LOCAL_RUN_USED, _LOCAL_MINUTE_USED, _LOCAL_MINUTE_STARTED
    _LOCAL_RUN_USED = 0
    _LOCAL_MINUTE_USED = 0
    _LOCAL_MINUTE_STARTED = None


def consume_run_budget(
    prompt_or_messages: Any,
    max_output_tokens: int,
    *,
    lane: str,
    operation: str = "",
    sleep_fn=time.sleep,
    monotonic_fn=time.monotonic,
) -> int:
    """Reserve estimated tokens locally BEFORE one Groq API call.

    This is the second safety layer after workflow-level daily reservation.
    It also paces requests below the local TPM ceiling. No model/prompt quality
    is changed: an unaffordable call is skipped instead.
    """

    global _LOCAL_RUN_USED, _LOCAL_MINUTE_USED, _LOCAL_MINUTE_STARTED

    estimate = estimate_request_tokens(
        prompt_or_messages,
        max_output_tokens,
    )
    run_cap = run_budget()
    minute_cap = tpm_ceiling()

    if run_cap <= 0:
        raise GroqBudgetExhausted(
            f"No Groq run budget was allocated for {lane}."
        )

    if estimate > minute_cap:
        raise GroqBudgetExhausted(
            f"One {lane} request needs ~{estimate} tokens, above the "
            f"{minute_cap} TPM safety ceiling. Operation={operation or 'unknown'}"
        )

    if _LOCAL_RUN_USED + estimate > run_cap:
        raise GroqBudgetExhausted(
            f"{lane} run budget would exceed {run_cap} tokens "
            f"({_LOCAL_RUN_USED}+{estimate}). Operation={operation or 'unknown'}"
        )

    now = monotonic_fn()
    if _LOCAL_MINUTE_STARTED is None:
        _LOCAL_MINUTE_STARTED = now

    elapsed = now - _LOCAL_MINUTE_STARTED
    if elapsed >= MINUTE_WINDOW_SECONDS:
        _LOCAL_MINUTE_STARTED = now
        _LOCAL_MINUTE_USED = 0
        elapsed = 0

    if _LOCAL_MINUTE_USED + estimate > minute_cap:
        wait_seconds = max(
            0.0,
            MINUTE_WINDOW_SECONDS - elapsed,
        )
        if wait_seconds:
            print(
                "Shared Groq TPM guard: waiting "
                f"{wait_seconds:.1f}s before the next AI request."
            )
            sleep_fn(wait_seconds)

        _LOCAL_MINUTE_STARTED = monotonic_fn()
        _LOCAL_MINUTE_USED = 0

    _LOCAL_RUN_USED += estimate
    _LOCAL_MINUTE_USED += estimate

    print(
        "Groq budget reservation: "
        f"lane={lane} operation={operation or 'unknown'} "
        f"estimated={estimate} run={_LOCAL_RUN_USED}/{run_cap} "
        f"minute={_LOCAL_MINUTE_USED}/{minute_cap}"
    )
    return estimate


def _write_github_output(
    output_path: str | None,
    result: dict[str, Any],
) -> None:
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as handle:
        handle.write(
            f"allowed={'true' if result['allowed'] else 'false'}\n"
        )
        handle.write(f"tokens={int(result.get('tokens', 0))}\n")
        handle.write(
            "reason="
            + str(result.get("reason", "")).replace("\n", " ")
            + "\n"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="GamerQuest shared Groq budget manager"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reserve = subparsers.add_parser("reserve-run")
    reserve.add_argument("--lane", required=True, choices=sorted(DEFAULT_LANE_CEILINGS))
    reserve.add_argument("--tokens", type=int, required=True)
    reserve.add_argument("--reservation-id", required=True)
    reserve.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))
    reserve.add_argument("--github-output", default="")

    status = subparsers.add_parser("status")
    status.add_argument("--state-file", default=str(DEFAULT_STATE_PATH))

    args = parser.parse_args()

    if args.command == "reserve-run":
        github_ref = str(os.getenv("GITHUB_REF_NAME", "")).strip()
        in_actions = str(os.getenv("GITHUB_ACTIONS", "")).lower() == "true"
        allow_non_main = os.getenv("GROQ_ALLOW_NON_MAIN") == "1"

        if in_actions and github_ref and github_ref != "main" and not allow_non_main:
            result = {
                "allowed": False,
                "tokens": 0,
                "reason": (
                    f"Groq production is disabled on non-main branch: {github_ref}"
                ),
                "state": load_state(args.state_file),
            }
        else:
            result = reserve_run(
                args.lane,
                args.tokens,
                args.reservation_id,
                path=args.state_file,
            )
        _write_github_output(args.github_output, result)
        state = result["state"]
        print(
            "Groq shared budget: "
            f"allowed={result['allowed']} lane={args.lane} "
            f"reserved={result.get('tokens', 0)} "
            f"global={state.get('global_reserved', 0)}/{global_daily_ceiling()} "
            f"reason={result.get('reason', '')}"
        )
        return 0

    state = load_state(args.state_file)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
