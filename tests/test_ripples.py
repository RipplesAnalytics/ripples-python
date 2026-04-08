from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from ripples import Ripples, RipplesError


class TestInit:
    def test_missing_key_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(RipplesError, match="Missing secret key"):
                Ripples()

    def test_key_from_env(self):
        with patch.dict("os.environ", {"RIPPLES_SECRET_KEY": "priv_test"}):
            r = Ripples()
            assert r._secret_key == "priv_test"

    def test_key_from_constructor(self):
        r = Ripples("priv_explicit")
        assert r._secret_key == "priv_explicit"

    def test_custom_base_url(self):
        r = Ripples("priv_test", base_url="https://custom.example.com/api/")
        assert r._base_url == "https://custom.example.com/api"

    def test_base_url_from_env(self):
        with patch.dict("os.environ", {"RIPPLES_URL": "https://env.example.com"}):
            r = Ripples("priv_test")
            assert r._base_url == "https://env.example.com"


class TestEnqueue:
    def setup_method(self):
        self.ripples = Ripples("priv_test")

    def test_revenue_enqueues(self):
        self.ripples.revenue(49.99, "user_1", currency="EUR")
        assert len(self.ripples._queue) == 1
        event = self.ripples._queue[0]
        assert event["type"] == "revenue"
        assert event["amount"] == 49.99
        assert event["user_id"] == "user_1"
        assert event["currency"] == "EUR"
        assert "sent_at" in event

    def test_signup_enqueues(self):
        self.ripples.signup("user_1", email="jane@example.com")
        event = self.ripples._queue[0]
        assert event["type"] == "signup"
        assert event["user_id"] == "user_1"
        assert event["email"] == "jane@example.com"

    def test_track_enqueues(self):
        self.ripples.track("created a budget", "user_1", area="budgets")
        event = self.ripples._queue[0]
        assert event["type"] == "track"
        assert event["name"] == "created a budget"
        assert event["user_id"] == "user_1"
        assert event["area"] == "budgets"

    def test_identify_enqueues(self):
        self.ripples.identify("user_1", email="jane@example.com", role="admin")
        event = self.ripples._queue[0]
        assert event["type"] == "identify"
        assert event["user_id"] == "user_1"
        assert event["email"] == "jane@example.com"
        assert event["role"] == "admin"

    def test_negative_revenue_for_refunds(self):
        self.ripples.revenue(-29.99, "user_1", transaction_id="txn_abc")
        event = self.ripples._queue[0]
        assert event["amount"] == -29.99


class TestFlush:
    def setup_method(self):
        self.ripples = Ripples("priv_test")

    @patch.object(Ripples, "_post")
    def test_flush_sends_batch(self, mock_post):
        self.ripples.revenue(10.0, "user_1")
        self.ripples.signup("user_2")
        self.ripples.flush()

        mock_post.assert_called_once()
        path, data = mock_post.call_args[0]
        assert path == "/v1/ingest/batch"
        assert len(data["events"]) == 2
        assert self.ripples._queue == []

    @patch.object(Ripples, "_post")
    def test_flush_noop_when_empty(self, mock_post):
        self.ripples.flush()
        mock_post.assert_not_called()

    @patch.object(Ripples, "_post")
    def test_auto_flush_on_max_queue(self, mock_post):
        r = Ripples("priv_test", max_queue_size=3)
        r.revenue(1.0, "u1")
        r.revenue(2.0, "u2")
        mock_post.assert_not_called()
        r.revenue(3.0, "u3")  # triggers auto-flush
        mock_post.assert_called_once()


class TestErrorHandling:
    @patch.object(Ripples, "_post", side_effect=RipplesError("fail"))
    def test_errors_swallowed(self, mock_post):
        r = Ripples("priv_test")
        r.revenue(10.0, "user_1")
        r.flush()  # should not raise

    @patch.object(Ripples, "_post", side_effect=RipplesError("fail"))
    def test_on_error_callback(self, mock_post):
        callback = MagicMock()
        r = Ripples("priv_test", on_error=callback)
        r.revenue(10.0, "user_1")
        r.flush()
        callback.assert_called_once()
        assert isinstance(callback.call_args[0][0], RipplesError)


class TestPost:
    def setup_method(self):
        self.ripples = Ripples("priv_test")

    @patch("ripples.client.requests.Session.post")
    def test_post_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        self.ripples._post("/v1/ingest/batch", {"events": []})
        mock_post.assert_called_once()

    @patch("ripples.client.requests.Session.post")
    def test_post_raises_on_4xx(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 422
        mock_resp.content = b'{"error": "validation failed"}'
        mock_resp.json.return_value = {"error": "validation failed"}
        mock_post.return_value = mock_resp

        with pytest.raises(RipplesError, match="validation failed"):
            self.ripples._post("/v1/ingest/batch", {"events": []})
