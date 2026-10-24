"""
Integration tests for WebhookManager orchestration.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import urllib.request
import pytest

from hookrelay.manager import WebhookManager


class MockLocalServer(BaseHTTPRequestHandler):
    recorded = []

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        MockLocalServer.recorded.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


@pytest.fixture(scope="module")
def local_app():
    server = HTTPServer(("127.0.0.1", 0), MockLocalServer)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_manager_multi_webhook_lifecycle(local_app):
    manager = WebhookManager(db_path=":memory:", force_mock_tunnel=True)

    try:
        # Create 2 webhooks
        wh1 = manager.create_webhook(name="stripe", local_target=local_app)
        wh2 = manager.create_webhook(name="hubspot", local_target=local_app)

        assert wh1.name == "stripe"
        assert wh2.name == "hubspot"
        assert wh1.public_url.startswith("https://")
        assert wh2.public_url.startswith("https://")

        active = manager.list_webhooks()
        assert len(active) == 2

        # Send event to wh1 sink
        req = urllib.request.Request(
            f"http://127.0.0.1:{wh1.local_port}/v1/charges",
            data=b'{"type": "charge.captured", "id": "ch_99"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

        assert manager.count_events(wh1.id) == 1
        events = manager.list_events(wh1.id)
        assert len(events) == 1
        assert events[0].event_summary == "charge.captured"

        # Replay event
        res = manager.replay_event(events[0].id)
        assert res.status_code == 200

        # Pause and resume wh1
        assert manager.pause_webhook("stripe") is True
        assert manager.get_webhook("stripe").is_paused is True
        assert manager.resume_webhook("stripe") is True
        assert manager.get_webhook("stripe").is_active is True

        # Terminate wh1
        assert manager.terminate_webhook("stripe") is True
        active_after = manager.list_webhooks()
        assert len(active_after) == 1
        assert active_after[0].name == "hubspot"

    finally:
        manager.shutdown_all()
