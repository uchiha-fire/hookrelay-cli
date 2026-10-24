"""
Unit tests for HookRelay SQLite storage and models.
"""
import time
import pytest
from hookrelay.models import WebhookSession, WebhookEvent
from hookrelay.store import HookRelayStore


@pytest.fixture
def store():
    return HookRelayStore(db_path=":memory:")


def test_session_lifecycle(store):
    session = WebhookSession(
        id="wh_test_1",
        name="stripe",
        public_url="https://test.pinggy.link",
        local_target="http://localhost:8080/hook",
        local_port=9101,
        status="ACTIVE",
    )
    store.save_webhook(session)

    fetched = store.get_webhook("wh_test_1")
    assert fetched is not None
    assert fetched.name == "stripe"
    assert fetched.is_active is True
    assert fetched.is_paused is False

    # Pause
    store.update_webhook_status("wh_test_1", "PAUSED")
    paused = store.get_webhook("wh_test_1")
    assert paused.is_paused is True
    assert paused.is_active is False

    # Find by name
    found = store.find_webhook("stripe")
    assert found is not None
    assert found.id == "wh_test_1"

    # Terminate
    store.terminate_webhook("wh_test_1")
    assert store.get_webhook("wh_test_1").is_terminated is True
    # Should not show in default active list
    assert len(store.list_webhooks(include_terminated=False)) == 0
    # Shows in all list
    assert len(store.list_webhooks(include_terminated=True)) == 1


def test_events_recording_and_querying(store):
    session = WebhookSession(
        id="wh_test_2",
        name="hubspot",
        public_url="https://hubspot.pinggy.link",
        local_target="http://localhost:8081",
        local_port=9102,
    )
    store.save_webhook(session)

    evt = WebhookEvent(
        id="evt_101",
        webhook_id="wh_test_2",
        timestamp=time.time(),
        method="POST",
        path="/crm/lead",
        headers={"Content-Type": "application/json", "X-Hubspot-Signature": "abc123"},
        payload='{"type": "contact.created", "email": "test@example.com"}',
        fwd_status=200,
        fwd_latency_ms=45.2,
        fwd_response='{"success": true}',
    )
    store.save_event(evt)

    assert store.count_events("wh_test_2") == 1

    events = store.list_events(webhook_id="wh_test_2")
    assert len(events) == 1
    assert events[0].id == "evt_101"
    assert events[0].event_summary == "contact.created"
    assert events[0].is_success is True
    assert events[0].headers["X-Hubspot-Signature"] == "abc123"
    assert events[0].fwd_latency_ms == 45.2
