# Ripples Python SDK

Server-side Python SDK for [Ripples.sh](https://ripples.sh) analytics.

## Install

```bash
pip install ripples
```

Set your secret key:

```
RIPPLES_SECRET_KEY=priv_your_secret_key
```

## Usage

```python
from ripples import Ripples

ripples = Ripples()

ripples.revenue(49.99, "user_123")
ripples.signup("user_123", email="jane@example.com")
ripples.track("created a budget", "user_123", area="budgets")
ripples.identify("user_123", email="jane@example.com")
```

That's it. Events are batched and sent automatically when the process exits.

## Track product usage

Call `track()` **only** for significant product usage — actions that prove a user got real value (created a budget, sent a message, invited a teammate). This is not a generic event log like PostHog or Mixpanel: do **not** send pageviews, banner impressions, button clicks, or "viewed X" events. Every `track()` call feeds the Activation dashboard, so noise here pollutes your funnel. Ripples auto-detects activation (first occurrence per user), computes adoption rates, and correlates with retention and payment.

```python
ripples.track("created a budget", "user_123", area="budgets")
ripples.track("shared a list", "user_123", area="sharing", via="link")
ripples.track("exported report", "user_123", area="reports", format="csv")
```

Use `area` to group actions into product areas. Use `activated=True` to mark the specific moment a user activates:

```python
ripples.track("added transaction", "user_123", area="transactions", activated=True)
```

## Track subscriptions (MRR)

Call `subscription()` when a subscription is created, upgraded, downgraded, or canceled. This powers the MRR metric on your dashboard.

> **Stripe / Paddle users:** MRR is tracked automatically via the integration. Only use this method if you use a payment provider without a native Ripples integration.

```python
# User subscribes to Pro Monthly ($29/mo)
ripples.subscription("sub_123", "user_456", "active", 29.00, "month",
    name="Pro", currency="EUR")

# User upgrades to Business Annual ($499/yr)
ripples.subscription("sub_123", "user_456", "active", 499.00, "year",
    name="Business")

# User cancels
ripples.subscription("sub_123", "user_456", "canceled", 0)
```

Parameters:

- `subscription_id` (str, required) — stable identifier for the subscription
- `user_id` (str, required) — your internal user ID
- `status` (str, required) — one of: `active`, `canceled`, `past_due`, `trialing`, `paused`
- `amount` (float, required) — amount per billing cycle (e.g. `29.00`), pass `0` when canceling
- `interval` (str, optional) — `"month"` (default), `"year"`, `"week"`, or `"day"`
- `currency` (str, optional) — 3-letter currency code
- `name` / `plan` (str, optional) — plan name shown in the dashboard
- `interval_count` (int, optional) — billing frequency multiplier (e.g. `3` for quarterly)

## Track revenue

```python
ripples.revenue(49.99, "user_123")
```

Any extra keyword argument becomes a custom property:

```python
ripples.revenue(49.99, "user_123",
    email="jane@example.com",
    currency="EUR",
    transaction_id="txn_abc123",
    plan="annual",
    coupon="WELCOME20",
)
```

Refunds are negative revenue:

```python
ripples.revenue(-29.99, "user_123", transaction_id="txn_abc123")
```

## Track signups

```python
ripples.signup("user_123",
    email="jane@example.com",
    name="Jane Smith",
    referral="twitter",
    plan="free",
)
```

## Identify users

Update user traits at any time:

```python
ripples.identify("user_123",
    email="jane@example.com",
    name="Jane Smith",
    company="Acme Inc",
    role="admin",
)
```

## Error handling

```python
from ripples import RipplesError

try:
    ripples.revenue(49.99, "user_123")
except RipplesError as e:
    print(e)
```

By default, errors during flush are swallowed so your app is never disrupted. Use `on_error` to log them:

```python
ripples = Ripples(on_error=lambda e: print(f"Ripples error: {e}"))
```

## Configuration

```python
ripples = Ripples(
    "priv_explicit_key",
    base_url="https://your-domain.com/api",
    timeout=10,
    max_queue_size=50,
)
```

Or via environment variables:

```
RIPPLES_SECRET_KEY=priv_your_secret_key
RIPPLES_URL=https://your-domain.com/api
```

## Flush manually

Events are flushed automatically at exit. For long-running processes or CLI scripts, call `flush()` explicitly:

```python
ripples.flush()
```

## Custom HTTP client

Subclass and override `_post()`:

```python
class MyRipples(Ripples):
    def _post(self, path, data):
        # your custom implementation
        pass
```

## Requirements

- Python 3.9+
- requests

## License

MIT
