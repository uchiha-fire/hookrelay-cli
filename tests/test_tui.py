"""
Tests for HookRelay interactive TUI navigation and state transitions.
"""
import pytest
from hookrelay.manager import WebhookManager
from hookrelay.models import WebhookEvent
from hookrelay.tui import HookRelayTUI


@pytest.fixture
def tui_env():
    manager = WebhookManager(db_path=":memory:", force_mock_tunnel=True)
    wh = manager.create_webhook(name="stripe", local_target="http://localhost:8080")

    # Add dummy event
    evt = WebhookEvent(
        id="evt_test_tui",
        webhook_id=wh.id,
        timestamp=1000.0,
        method="POST",
        path="/api/stripe",
        headers={"Content-Type": "application/json"},
        payload='{"type": "invoice.paid"}',
        fwd_status=200,
        fwd_latency_ms=25.0,
        fwd_response='{"ok": true}',
    )
    manager.store.save_event(evt)

    tui = HookRelayTUI(manager)
    return tui, manager, wh


def test_tui_initial_state_and_render(tui_env):
    tui, manager, wh = tui_env
    assert tui.screen == "HUB"
    rendered = tui.render()
    assert "HOOKRELAY — Active Webhook Manager" in rendered
    assert "stripe" in rendered
    assert wh.id in rendered
    assert wh.public_url[:20] in rendered


def test_tui_navigation_flow(tui_env):
    tui, manager, wh = tui_env

    # 1. From HUB, press ENTER to open Workspace
    assert tui.handle_key("ENTER") is True
    assert tui.screen == "WORKSPACE"
    assert tui.active_webhook_id == wh.id
    ws_rendered = tui.render()
    assert "HOOKRELAY » stripe" in ws_rendered
    assert "invoice.paid" in ws_rendered

    # 2. From WORKSPACE, press ENTER to inspect event
    assert tui.handle_key("ENTER") is True
    assert tui.screen == "INSPECTOR"
    assert tui.active_event_id == "evt_test_tui"
    insp_rendered = tui.render()
    assert "EVENT INSPECTOR" in insp_rendered
    assert "invoice.paid" in insp_rendered

    # 3. Back button 'b' returns to WORKSPACE
    assert tui.handle_key("b") is True
    assert tui.screen == "WORKSPACE"

    # 4. Back button 'ESC' returns to HUB
    assert tui.handle_key("ESC") is True
    assert tui.screen == "HUB"


def test_tui_wizard_creation_and_cancel(tui_env):
    tui, manager, wh = tui_env

    # Open wizard
    assert tui.handle_key("n") is True
    assert tui.screen == "WIZARD"

    # Cancel with ESC
    assert tui.handle_key("ESC") is True
    assert tui.screen == "HUB"

    # Open wizard again and submit
    assert tui.handle_key("n") is True
    assert tui.screen == "WIZARD"
    tui.wizard_data = {"name": "hubspot", "target": "http://localhost:3000"}
    assert tui.handle_key("ENTER") is True
    assert tui.screen == "HUB"

    active_webhooks = manager.list_webhooks()
    assert len(active_webhooks) == 2
    assert any(w.name == "hubspot" for w in active_webhooks)


def test_tui_termination_flow(tui_env):
    tui, manager, wh = tui_env

    # Press 'd' to terminate
    assert tui.handle_key("d") is True
    assert tui.screen == "CONFIRM_KILL"
    rendered = tui.render()
    assert "CONFIRM TERMINATION" in rendered

    # Confirm with 'y'
    assert tui.handle_key("y") is True
    assert tui.screen == "HUB"
    assert len(manager.list_webhooks(include_terminated=False)) == 0


def test_tui_quit(tui_env):
    tui, manager, wh = tui_env
    assert tui.handle_key("q") is False
