# SPEC — Failed Payment Recovery (Dunning)

## What it does

Takes a Stripe webhook event for a failed payment and decides:
- Whether to retry the charge
- When to retry (hours from now)
- Which email template to send

Outputs a JSON decision ready for a worker to execute.

## What it does NOT do

- Does not send emails
- Does not modify Stripe (no retry execution, no customer update)
- Does not store customer data
- Does not use an LLM

## Input

```json
{
  "event": "invoice.payment_failed",
  "amount": 2900,
  "currency": "eur",
  "customer_id": "cus_123",
  "attempt_count": 1,
  "failure_code": "card_declined"
}
```

## Output

```json
{
  "action": "retry",
  "retry_after_hours": 24,
  "email_template": "friendly_reminder",
  "escalate": false
}
```

## Exit codes

- `0` — success, decision made
- `1` — invalid input (missing required fields, wrong types)
- `2` — unrecognized failure code

## Rules (deterministic, no ML)

### Retry schedule by attempt_count

| attempt_count | retry_after_hours | email_template | escalate |
|---|---|---|---|
| 1 | 24 | friendly_reminder | false |
| 2 | 72 | firm_reminder | false |
| 3 | 168 | final_notice | true |
| 4+ | null | null | true |

### Failure code overrides

- `insufficient_funds` → retry as scheduled
- `card_declined` → retry as scheduled
- `expired_card` → `action: "no_retry"`, `email_template: "update_payment_method"`, `escalate: true`
- `fraud_suspected` → `action: "no_retry"`, `email_template: null`, `escalate: true`
- any other code → `action: "retry"`, `retry_after_hours: 24`, `email_template: "friendly_reminder"`, `escalate: false`

### Amount threshold

- If `amount < 1000` (i.e. < $10 / < €10) and `attempt_count >= 2` → `action: "no_retry"`, `email_template: "update_payment_method"`, `escalate: true`

## Constraints

- No external API calls
- No file I/O beyond reading stdin and writing stdout
- No secrets in output
- Deterministic: same input → same output
