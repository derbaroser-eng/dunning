#!/usr/bin/env python3
"""
dunning.py — deterministic failed-payment recovery decision engine.

Reads JSON from stdin, writes JSON to stdout.
No external calls, no file I/O, no secrets in output.
"""
import json
import sys

RETRY_SCHEDULE = {
    1: {"retry_after_hours": 24, "email_template": "friendly_reminder", "escalate": False},
    2: {"retry_after_hours": 72, "email_template": "firm_reminder", "escalate": False},
    3: {"retry_after_hours": 168, "email_template": "final_notice", "escalate": True},
}

FAILURE_OVERRIDES = {
    "expired_card": {"action": "no_retry", "email_template": "update_payment_method", "escalate": True},
    "fraud_suspected": {"action": "no_retry", "email_template": None, "escalate": True},
}

REQUIRED_FIELDS = {"event", "amount", "currency", "customer_id", "attempt_count", "failure_code"}


def decide(payload: dict) -> dict:
    attempt = payload["attempt_count"]
    code = payload["failure_code"]
    amount = payload["amount"]

    # Failure code overrides
    if code in FAILURE_OVERRIDES:
        o = FAILURE_OVERRIDES[code]
        return {
            "action": o["action"],
            "retry_after_hours": None,
            "email_template": o["email_template"],
            "escalate": o["escalate"],
        }

    # Amount threshold: low amount + attempt >= 2 → no_retry
    if amount < 1000 and attempt >= 2:
        return {
            "action": "no_retry",
            "retry_after_hours": None,
            "email_template": "update_payment_method",
            "escalate": True,
        }

    # Standard retry schedule
    if attempt in RETRY_SCHEDULE:
        s = RETRY_SCHEDULE[attempt]
        return {
            "action": "retry",
            "retry_after_hours": s["retry_after_hours"],
            "email_template": s["email_template"],
            "escalate": s["escalate"],
        }

    # attempt >= 4 → no_retry, escalate
    return {
        "action": "no_retry",
        "retry_after_hours": None,
        "email_template": None,
        "escalate": True,
    }


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        print("error: invalid JSON", file=sys.stderr)
        return 1

    if not isinstance(data, dict):
        print("error: input must be a JSON object", file=sys.stderr)
        return 1

    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        print(f"error: missing fields: {sorted(missing)}", file=sys.stderr)
        return 1

    if not isinstance(data["attempt_count"], int):
        print("error: attempt_count must be an integer", file=sys.stderr)
        return 1

    if not isinstance(data["amount"], (int, float)):
        print("error: amount must be a number", file=sys.stderr)
        return 1

    if not isinstance(data["failure_code"], str):
        print("error: failure_code must be a string", file=sys.stderr)
        return 1

    result = decide(data)
    json.dump(result, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
