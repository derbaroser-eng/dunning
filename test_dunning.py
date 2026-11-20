#!/usr/bin/env python3
"""
test_dunning.py — failing tests for dunning.

Run: python workspace/products/dunning/test_dunning.py
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SCRIPT = HERE / "dunning.py"

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    results.append((name, cond, detail))


def run_dunning(payload: dict) -> dict:
    """Run dunning.py with the given payload and return parsed output."""
    r = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if r.returncode != 0:
        return {"error": f"exit={r.returncode}", "stderr": r.stderr[:200]}
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"error": "invalid_json", "stdout": r.stdout[:200]}


def base_payload(**overrides):
    p = {
        "event": "invoice.payment_failed",
        "amount": 2900,
        "currency": "eur",
        "customer_id": "cus_123",
        "attempt_count": 1,
        "failure_code": "card_declined",
    }
    p.update(overrides)
    return p


# --- test 1: attempt 1 → retry in 24h, friendly_reminder ---
out = run_dunning(base_payload())
check("attempt1: classified", isinstance(out, dict) and "action" in out, str(out)[:100])
if isinstance(out, dict) and "action" in out:
    check("attempt1: action is retry", out.get("action") == "retry", str(out))
    check("attempt1: retry_after_hours is 24", out.get("retry_after_hours") == 24, str(out))
    check("attempt1: email_template is friendly_reminder", out.get("email_template") == "friendly_reminder", str(out))
    check("attempt1: escalate is false", out.get("escalate") is False, str(out))

# --- test 2: attempt 2 → retry in 72h, firm_reminder ---
out = run_dunning(base_payload(attempt_count=2))
check("attempt2: action is retry", out.get("action") == "retry", str(out))
check("attempt2: retry_after_hours is 72", out.get("retry_after_hours") == 72, str(out))
check("attempt2: email_template is firm_reminder", out.get("email_template") == "firm_reminder", str(out))
check("attempt2: escalate is false", out.get("escalate") is False, str(out))

# --- test 3: attempt 3 → retry in 168h, final_notice, escalate ---
out = run_dunning(base_payload(attempt_count=3))
check("attempt3: action is retry", out.get("action") == "retry", str(out))
check("attempt3: retry_after_hours is 168", out.get("retry_after_hours") == 168, str(out))
check("attempt3: email_template is final_notice", out.get("email_template") == "final_notice", str(out))
check("attempt3: escalate is true", out.get("escalate") is True, str(out))

# --- test 4: attempt 4+ → no_retry, escalate ---
out = run_dunning(base_payload(attempt_count=4))
check("attempt4: action is no_retry", out.get("action") == "no_retry", str(out))
check("attempt4: retry_after_hours is null", out.get("retry_after_hours") is None, str(out))
check("attempt4: email_template is null", out.get("email_template") is None, str(out))
check("attempt4: escalate is true", out.get("escalate") is True, str(out))

# --- test 5: expired_card → no_retry, update_payment_method ---
out = run_dunning(base_payload(failure_code="expired_card"))
check("expired: action is no_retry", out.get("action") == "no_retry", str(out))
check("expired: email_template is update_payment_method", out.get("email_template") == "update_payment_method", str(out))
check("expired: escalate is true", out.get("escalate") is True, str(out))

# --- test 6: fraud_suspected → no_retry, no email, escalate ---
out = run_dunning(base_payload(failure_code="fraud_suspected"))
check("fraud: action is no_retry", out.get("action") == "no_retry", str(out))
check("fraud: email_template is null", out.get("email_template") is None, str(out))
check("fraud: escalate is true", out.get("escalate") is True, str(out))

# --- test 7: insufficient_funds → retry as scheduled ---
out = run_dunning(base_payload(failure_code="insufficient_funds"))
check("insufficient: action is retry", out.get("action") == "retry", str(out))
check("insufficient: retry_after_hours is 24", out.get("retry_after_hours") == 24, str(out))

# --- test 8: unknown failure code → retry in 24h, friendly_reminder ---
out = run_dunning(base_payload(failure_code="some_new_code"))
check("unknown: action is retry", out.get("action") == "retry", str(out))
check("unknown: retry_after_hours is 24", out.get("retry_after_hours") == 24, str(out))
check("unknown: email_template is friendly_reminder", out.get("email_template") == "friendly_reminder", str(out))

# --- test 9: low amount + attempt 2 → no_retry, update_payment_method ---
out = run_dunning(base_payload(amount=500, attempt_count=2))
check("low_amount: action is no_retry", out.get("action") == "no_retry", str(out))
check("low_amount: email_template is update_payment_method", out.get("email_template") == "update_payment_method", str(out))
check("low_amount: escalate is true", out.get("escalate") is True, str(out))

# --- test 10: low amount + attempt 1 → still retry ---
out = run_dunning(base_payload(amount=500, attempt_count=1))
check("low_amount_attempt1: action is retry", out.get("action") == "retry", str(out))

# --- test 11: invalid input (missing fields) ---
r = subprocess.run(
    [sys.executable, str(SCRIPT)],
    input=json.dumps({"foo": "bar"}),
    capture_output=True,
    text=True,
    timeout=10,
)
check("invalid: exit code 1", r.returncode == 1, f"rc={r.returncode}")

# --- test 12: invalid input (wrong type) ---
r = subprocess.run(
    [sys.executable, str(SCRIPT)],
    input=json.dumps(base_payload(attempt_count="one")),
    capture_output=True,
    text=True,
    timeout=10,
)
check("wrong_type: exit code 1", r.returncode == 1, f"rc={r.returncode}")

# --- test 13: no secrets in output ---
out = run_dunning(base_payload(customer_id="cus_SECRET123"))
if isinstance(out, dict):
    check("no secrets: customer_id not in output", "cus_SECRET123" not in json.dumps(out), str(out))

# --- test 14: deterministic ---
out1 = run_dunning(base_payload())
out2 = run_dunning(base_payload())
check("deterministic: same output", out1 == out2, f"{out1} vs {out2}")

# --- report ----------------------------------------------------------------
passed = sum(1 for _, ok, _ in results if ok)
failed = [(n, d) for n, ok, d in results if not ok]
print(f"\n{passed}/{len(results)} assertions passed")
if failed:
    print("\nFAILED:")
    for n, d in failed:
        print(f"  {n}  ({d})")
    sys.exit(1)
print("ALL TESTS GREEN")
