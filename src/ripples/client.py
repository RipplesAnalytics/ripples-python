from __future__ import annotations

import atexit
import os
from datetime import datetime, timezone
from typing import Any, Callable

import requests

from .errors import RipplesError


class Ripples:
    """Official Python SDK for Ripples.sh — server-side event tracking.

    Events are queued in memory and sent as a single batch on flush().
    flush() is called automatically at interpreter exit via atexit.
    """

    def __init__(
        self,
        secret_key: str | None = None,
        *,
        base_url: str | None = None,
        timeout: int = 3,
        connect_timeout: int = 2,
        on_error: Callable[[Exception], None] | None = None,
        max_queue_size: int = 100,
    ) -> None:
        self._secret_key = secret_key or os.environ.get("RIPPLES_SECRET_KEY", "")
        if not self._secret_key:
            raise RipplesError(
                "Missing secret key. Set RIPPLES_SECRET_KEY in your environment "
                "or pass it to the constructor."
            )

        self._base_url = (
            (base_url or os.environ.get("RIPPLES_URL", "https://api.ripples.sh"))
            .rstrip("/")
        )
        self._timeout = (connect_timeout, timeout)
        self._on_error = on_error
        self._max_queue_size = max_queue_size
        self._queue: list[dict[str, Any]] = []

        self._session = requests.Session()
        self._session.headers.update(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {self._secret_key}",
            }
        )

        atexit.register(self.flush)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def revenue(self, amount: float, user_id: str, **attributes: Any) -> None:
        """Track revenue. Use negative amounts for refunds."""
        self._enqueue("revenue", {"amount": amount, "user_id": user_id, **attributes})

    def signup(self, user_id: str, **attributes: Any) -> None:
        """Track a signup."""
        self._enqueue("signup", {"user_id": user_id, **attributes})

    def track(self, action_name: str, user_id: str, **attributes: Any) -> None:
        """Track significant product usage only.

        Use for actions that prove a user got real value (created a budget,
        sent a message, invited a teammate). NOT a generic event log like
        PostHog or Mixpanel — do not send pageviews, banner impressions,
        button clicks, or "viewed X" events. Every track() call feeds the
        Activation dashboard; noise pollutes your funnel.

        Ripples auto-detects activation (first per user per action).
        Pass area= to group into product areas.
        Pass activated=True to flag this specific occurrence as the
        activation moment (not every occurrence of the event type).
        """
        self._enqueue("track", {"name": action_name, "user_id": user_id, **attributes})

    def subscription(
        self,
        subscription_id: str,
        user_id: str,
        status: str,
        amount: float,
        interval: str = "month",
        **attributes: Any,
    ) -> None:
        """Track a subscription state change for MRR calculation.

        Call when a subscription is created, upgraded/downgraded, or canceled.
        For Stripe/Paddle users with a native integration, MRR is tracked
        automatically — only use this for other payment providers.

        Args:
            subscription_id: Your subscription ID (must be stable across updates).
            user_id: The user who owns the subscription.
            status: active, canceled, past_due, trialing, or paused.
            amount: Amount per billing cycle (e.g. 29.00), in your currency.
            interval: Billing interval: month, year, week, or day.
            **attributes: Optional: currency, name/plan, interval_count.
        """
        event: dict[str, Any] = {
            "amount": 0,
            "user_id": user_id,
            "subscription_id": subscription_id,
            "subscription_status": status,
            "subscription_amount": str(round(amount * 100)),
            "billing_interval": interval,
            "billing_interval_count": str(attributes.pop("interval_count", 1)),
        }
        currency = attributes.pop("currency", None)
        if currency is not None:
            event["currency"] = currency
        name = attributes.pop("name", attributes.pop("plan", None))
        if name is not None:
            event["name"] = name
        event.update(attributes)
        self._enqueue("revenue", event)

    def identify(self, user_id: str, **attributes: Any) -> None:
        """Identify a user (set or update traits)."""
        self._enqueue("identify", {"user_id": user_id, **attributes})

    def flush(self) -> None:
        """Send all queued events in a single batch request.

        Called automatically at interpreter exit. Call explicitly when you
        need to guarantee delivery before a process ends.
        """
        if not self._queue:
            return

        batch, self._queue = self._queue, []
        self._send("/v1/ingest/batch", {"events": batch})

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _enqueue(self, event_type: str, data: dict[str, Any]) -> None:
        self._queue.append(
            {
                "type": event_type,
                "sent_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                **data,
            }
        )
        if len(self._queue) >= self._max_queue_size:
            self.flush()

    def _send(self, path: str, data: dict[str, Any]) -> None:
        """Dispatch a request, swallowing errors so the host app is never
        disrupted by a Ripples outage."""
        try:
            self._post(path, data)
        except Exception as exc:
            if self._on_error is not None:
                self._on_error(exc)

    def _post(self, path: str, data: dict[str, Any]) -> None:
        """Send a POST request. Override in a subclass to swap HTTP clients."""
        url = f"{self._base_url}{path}"
        resp = self._session.post(url, json=data, timeout=self._timeout)

        if resp.status_code >= 400:
            body = resp.json() if resp.content else {}
            message = body.get("error", f"HTTP {resp.status_code}")
            raise RipplesError(message, status_code=resp.status_code)
