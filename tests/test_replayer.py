"""
Unit tests for EventReplayer.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import pytest

from hookrelay.models import WebhookEvent
from hookrelay.replayer import EventReplayer


class MockReplayTargetHandler(BaseHTTPRequestHandler):
    received = []

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        MockReplayTargetHandler.received.append({
            "path": self.path,
            "headers": dict(self.headers),
            "body": body,
        })
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"replayed": true}')


@pytest.fixture(scope="module")
def mock_target():
    server = HTTPServer(("127.0.0.1", 0), MockReplayTargetHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_replayer_sends_exact_event(mock_target):
    MockReplayTargetHandler.received.clear()
    replayer = EventReplayer()

    evt = WebhookEvent(
        id="evt_test_replay_1",
        webhook_id="wh_1",
        timestamp=1234567.0,
        method="POST",
        path="/api/stripe",
        headers={"Content-Type": "application/json", "Stripe-Signature": "t=1,v1=sig"},
        payload='{"amount": 4200, "currency": "usd"}',
    )

    result = replayer.replay(evt, target_url=mock_target + "/api/stripe")

    assert result.status_code == 200
    assert "replayed" in result.response_body
    assert len(MockReplayTargetHandler.received) == 1

    last = MockReplayTargetHandler.received[0]
    assert last["headers"]["Stripe-Signature"] == "t=1,v1=sig"
    assert last["headers"]["X-Hookrelay-Replay"] == "true"
    assert last["headers"]["X-Hookrelay-Original-Event"] == "evt_test_replay_1"
    assert json.loads(last["body"])["amount"] == 4200


def test_replayer_modified_payload(mock_target):
    MockReplayTargetHandler.received.clear()
    replayer = EventReplayer()

    evt = WebhookEvent(
        id="evt_test_replay_2",
        webhook_id="wh_1",
        timestamp=1234567.0,
        method="POST",
        path="/api/stripe",
        headers={"Content-Type": "application/json"},
        payload='{"status": "pending"}',
    )

    result = replayer.replay(
        evt,
        target_url=mock_target + "/api/stripe",
        modified_payload='{"status": "settled"}',
    )

    assert result.status_code == 200
    assert len(MockReplayTargetHandler.received) == 1
    assert json.loads(MockReplayTargetHandler.received[0]["body"])["status"] == "settled"
