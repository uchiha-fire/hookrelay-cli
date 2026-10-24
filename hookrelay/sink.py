"""
Embedded HTTP Sink and Forwarding Proxy for hookrelay-cli.
Receives incoming webhooks, transparently forwards them to a local target,
and records payloads, headers, latency, and responses.
"""
import io
import json
import logging
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
import socketserver
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
import urllib.request
from typing import Callable, Optional, Tuple

from hookrelay.models import WebhookSession, WebhookEvent, ForwardResult
from hookrelay.store import HookRelayStore

logger = logging.getLogger("hookrelay.sink")


def normalize_target_url(target: str) -> str:
    """Normalize port number or URL string into a full valid HTTP URL."""
    target = target.strip()
    if target.isdigit():
        return f"http://127.0.0.1:{target}"
    if not target.startswith("http://") and not target.startswith("https://"):
        return f"http://{target}"
    return target


def forward_request(
    target_url: str,
    method: str,
    headers: dict,
    body: bytes,
    timeout: float = 15.0,
) -> ForwardResult:
    """Forward an HTTP request to the target destination and measure latency."""
    t0 = time.perf_counter()
    filtered_headers = {}
    skip_headers = {"host", "content-length", "connection", "accept-encoding"}
    for k, v in headers.items():
        if k.lower() not in skip_headers:
            filtered_headers[k] = v

    req = urllib.request.Request(
        url=target_url,
        data=body if body and method not in ("GET", "HEAD") else None,
        headers=filtered_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            resp_body = response.read().decode("utf-8", errors="replace")
            return ForwardResult(
                status_code=response.status,
                latency_ms=latency_ms,
                response_body=resp_body,
            )
    except HTTPError as e:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        resp_body = e.read().decode("utf-8", errors="replace")
        return ForwardResult(
            status_code=e.code,
            latency_ms=latency_ms,
            response_body=resp_body,
            error=str(e),
        )
    except (URLError, ConnectionError, OSError) as e:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ForwardResult(
            status_code=502,
            latency_ms=latency_ms,
            response_body=f"Failed to connect to local target: {e}",
            error=str(e),
        )
    except Exception as e:
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return ForwardResult(
            status_code=500,
            latency_ms=latency_ms,
            response_body=f"Internal forward error: {e}",
            error=str(e),
        )


class ThreadingHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class WebhookSinkHandler(BaseHTTPRequestHandler):
    """Handles incoming webhook calls, logs them, and forwards them."""

    def log_message(self, format: str, *args) -> None:
        """Suppress default stderr logging."""
        pass

    def handle_incoming(self) -> None:
        session: WebhookSession = self.server.session
        store: HookRelayStore = self.server.store
        callback: Optional[Callable[[WebhookEvent], None]] = self.server.callback

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""
        payload_str = body.decode("utf-8", errors="replace")

        # Collect headers
        headers_dict = {k: v for k, v in self.headers.items()}

        # Check current status in store
        current_session = store.get_webhook(session.id) or session

        event_id = f"evt_{uuid.uuid4().hex[:10]}"
        timestamp = time.time()

        if current_session.is_paused:
            fwd_result = ForwardResult(
                status_code=200,
                latency_ms=0.0,
                response_body="[PAUSED: Webhook captured without forwarding]",
            )
        else:
            # Build full destination target URL
            base_target = normalize_target_url(current_session.local_target)
            parsed_target = urlparse(base_target)

            # If target has a path, use it; otherwise append incoming request path
            if parsed_target.path and parsed_target.path != "/":
                dest_url = base_target
                if self.path and self.path != "/":
                    dest_url = base_target.rstrip("/") + "/" + self.path.lstrip("/")
            else:
                dest_url = base_target.rstrip("/") + self.path

            fwd_result = forward_request(
                target_url=dest_url,
                method=self.command,
                headers=headers_dict,
                body=body,
            )

        event = WebhookEvent(
            id=event_id,
            webhook_id=session.id,
            timestamp=timestamp,
            method=self.command,
            path=self.path,
            headers=headers_dict,
            payload=payload_str,
            fwd_status=fwd_result.status_code,
            fwd_latency_ms=fwd_result.latency_ms,
            fwd_response=fwd_result.response_body,
        )

        store.save_event(event)

        if callback:
            try:
                callback(event)
            except Exception:
                pass

        # Respond to caller (e.g. Stripe)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-HookRelay-Event-Id", event_id)
        self.end_headers()
        response_data = json.dumps({
            "status": "received",
            "event_id": event_id,
            "forwarded_status": fwd_result.status_code,
        }).encode("utf-8")
        self.wfile.write(response_data)

    def do_POST(self):
        self.handle_incoming()

    def do_GET(self):
        self.handle_incoming()

    def do_PUT(self):
        self.handle_incoming()

    def do_PATCH(self):
        self.handle_incoming()

    def do_DELETE(self):
        self.handle_incoming()

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, PUT, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()


class WebhookSink:
    """Manages the background HTTP server for an active webhook session."""

    def __init__(
        self,
        session: WebhookSession,
        store: HookRelayStore,
        host: str = "127.0.0.1",
        port: int = 0,
        on_event_callback: Optional[Callable[[WebhookEvent], None]] = None,
    ):
        self.session = session
        self.store = store
        self.host = host
        self.port = port
        self.callback = on_event_callback
        self.server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._is_running = False

    def start(self) -> int:
        """Start listening. Returns the allocated port."""
        self.server = ThreadingHTTPServer((self.host, self.port), WebhookSinkHandler)
        self.server.session = self.session
        self.server.store = self.store
        self.server.callback = self.callback
        self.port = self.server.server_address[1]

        self._is_running = True
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self.port

    def stop(self) -> None:
        """Shut down the HTTP listener."""
        if self.server and self._is_running:
            self._is_running = False
            self.server.shutdown()
            self.server.server_close()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
