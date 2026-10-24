"""
Tests for WebhookSink, request capture, and forwarding proxy.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
import urllib.request
import pytest

from hookrelay.models import WebhookSession
from hookrelay.store import HookRelayStore
from hookrelay.sink import WebhookSink


class MockLocalBackendHandler(BaseHTTPRequestHandler):
    last_request = None

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        MockLocalBackendHandler.last_request = {
            "path": self.path,
            "headers": dict(self.headers),
            "body": body,
        }

        if "/fail" in self.path:
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"error": "internal crash"}')
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "processed": true}')


@pytest.fixture(scope="module")
def mock_backend():
    server = HTTPServer(("127.0.0.1", 0), MockLocalBackendHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


def test_sink_receives_and_forwards(mock_backend):
    store = HookRelayStore(db_path=":memory:")
    session = WebhookSession(
        id="wh_sink_1",
        name="stripe",
        public_url="https://fake.pinggy.link",
        local_target=mock_backend,
        local_port=0,
        status="ACTIVE",
    )
    store.save_webhook(session)

    events_captured = []
    sink = WebhookSink(
        session=session,
        store=store,
        port=0,
        on_event_callback=lambda evt: events_captured.append(evt),
    )
    port = sink.start()

    try:
        # Send a webhook to the sink
        sink_url = f"http://127.0.0.1:{port}/stripe/webhook"
        payload = json.dumps({"type": "payment_intent.succeeded", "amount": 5000}).encode("utf-8")
        req = urllib.request.Request(
            sink_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Stripe-Signature": "t=123,v1=sig_xyz",
            },
            method="POST",
        )

        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["status"] == "received"
            assert data["forwarded_status"] == 200

        # Verify callback and store
        assert len(events_captured) == 1
        stored_events = store.list_events("wh_sink_1")
        assert len(stored_events) == 1

        evt = stored_events[0]
        assert evt.method == "POST"
        assert evt.path == "/stripe/webhook"
        assert evt.headers["Stripe-Signature"] == "t=123,v1=sig_xyz"
        assert "payment_intent.succeeded" in evt.payload
        assert evt.fwd_status == 200
        assert "processed" in evt.fwd_response
        assert evt.fwd_latency_ms is not None and evt.fwd_latency_ms >= 0

        # Verify backend received exact forwarded payload
        assert MockLocalBackendHandler.last_request["body"] == json.dumps({"type": "payment_intent.succeeded", "amount": 5000})
        assert MockLocalBackendHandler.last_request["headers"]["Stripe-Signature"] == "t=123,v1=sig_xyz"

    finally:
        sink.stop()


def test_sink_paused_mode_does_not_forward(mock_backend):
    store = HookRelayStore(db_path=":memory:")
    session = WebhookSession(
        id="wh_sink_2",
        name="hubspot",
        public_url="https://hubspot.pinggy.link",
        local_target=mock_backend,
        local_port=0,
        status="PAUSED",
    )
    store.save_webhook(session)

    MockLocalBackendHandler.last_request = None
    sink = WebhookSink(session=session, store=store, port=0)
    port = sink.start()

    try:
        sink_url = f"http://127.0.0.1:{port}/hubspot/lead"
        req = urllib.request.Request(
            sink_url,
            data=b'{"lead_id": 99}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200

        # The local backend should NOT have received this request
        assert MockLocalBackendHandler.last_request is None

        # But store should have logged it as PAUSED
        events = store.list_events("wh_sink_2")
        assert len(events) == 1
        assert "PAUSED" in events[0].fwd_response

    finally:
        sink.stop()
