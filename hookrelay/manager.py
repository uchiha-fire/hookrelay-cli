"""
Central Orchestrator for hookrelay-cli.
Coordinates local HTTP sinks, public HTTPS tunnels, SQLite persistence, and event replay.
"""
import atexit
import logging
import threading
import uuid
from typing import Callable, Dict, List, Optional

from hookrelay.models import WebhookSession, WebhookEvent, ForwardResult
from hookrelay.sink import WebhookSink, normalize_target_url
from hookrelay.store import HookRelayStore
from hookrelay.tunnel import BaseTunnel, create_tunnel
from hookrelay.replayer import EventReplayer

logger = logging.getLogger("hookrelay.manager")


class WebhookManager:
    """Manages multi-webhook lifecycles, active sinks, tunnels, and events."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        force_mock_tunnel: bool = False,
        on_event: Optional[Callable[[WebhookEvent], None]] = None,
    ):
        self.store = HookRelayStore(db_path=db_path)
        self.force_mock_tunnel = force_mock_tunnel
        self.on_event = on_event
        self.replayer = EventReplayer()

        self._sinks: Dict[str, WebhookSink] = {}
        self._tunnels: Dict[str, BaseTunnel] = {}
        self._lock = threading.Lock()

        atexit.register(self.shutdown_all)

    def create_webhook(
        self,
        name: str,
        local_target: str,
        local_port: int = 0,
    ) -> WebhookSession:
        """Create a new webhook session, spin up local sink and public tunnel."""
        normalized_target = normalize_target_url(local_target)
        session_id = f"wh_{uuid.uuid4().hex[:6]}"

        session = WebhookSession(
            id=session_id,
            name=name.strip(),
            public_url="",
            local_target=normalized_target,
            local_port=local_port,
            status="ACTIVE",
        )

        with self._lock:
            # 1. Start HTTP sink
            sink = WebhookSink(
                session=session,
                store=self.store,
                port=local_port,
                on_event_callback=self._handle_event,
            )
            allocated_port = sink.start()
            session.local_port = allocated_port
            self._sinks[session_id] = sink

            # 2. Provision Tunnel
            tunnel = create_tunnel(allocated_port, force_mock=self.force_mock_tunnel)
            session.public_url = tunnel.public_url or f"http://127.0.0.1:{allocated_port}"
            self._tunnels[session_id] = tunnel

            # 3. Persist session
            self.store.save_webhook(session)

        return session

    def _handle_event(self, event: WebhookEvent) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    def list_webhooks(self, include_terminated: bool = False) -> List[WebhookSession]:
        return self.store.list_webhooks(include_terminated=include_terminated)

    def get_webhook(self, id_or_name: str) -> Optional[WebhookSession]:
        found = self.store.get_webhook(id_or_name)
        if not found:
            found = self.store.find_webhook(id_or_name)
        return found

    def pause_webhook(self, id_or_name: str) -> bool:
        session = self.get_webhook(id_or_name)
        if not session:
            return False
        return self.store.update_webhook_status(session.id, "PAUSED")

    def resume_webhook(self, id_or_name: str) -> bool:
        session = self.get_webhook(id_or_name)
        if not session:
            return False
        return self.store.update_webhook_status(session.id, "ACTIVE")

    def terminate_webhook(self, id_or_name: str) -> bool:
        """Stops sink, kills tunnel, and marks webhook as TERMINATED."""
        session = self.get_webhook(id_or_name)
        if not session:
            return False

        with self._lock:
            if session.id in self._sinks:
                try:
                    self._sinks[session.id].stop()
                except Exception:
                    pass
                del self._sinks[session.id]

            if session.id in self._tunnels:
                try:
                    self._tunnels[session.id].stop()
                except Exception:
                    pass
                del self._tunnels[session.id]

            return self.store.terminate_webhook(session.id)

    def list_events(self, webhook_id: Optional[str] = None, limit: int = 50) -> List[WebhookEvent]:
        return self.store.list_events(webhook_id=webhook_id, limit=limit)

    def get_event(self, event_id: str) -> Optional[WebhookEvent]:
        return self.store.get_event(event_id)

    def count_events(self, webhook_id: str) -> int:
        return self.store.count_events(webhook_id)

    def replay_event(
        self,
        event_id: str,
        target_override: Optional[str] = None,
        modified_payload: Optional[str] = None,
    ) -> ForwardResult:
        """Replay a recorded event to original target or an override."""
        event = self.get_event(event_id)
        if not event:
            raise ValueError(f"Event '{event_id}' not found.")

        target = target_override
        if not target:
            session = self.store.get_webhook(event.webhook_id)
            if not session:
                raise ValueError(f"Webhook session '{event.webhook_id}' for event '{event_id}' not found.")
            target = session.local_target

        return self.replayer.replay(
            event=event,
            target_url=target,
            modified_payload=modified_payload,
        )

    def shutdown_all(self) -> None:
        """Gracefully stop all running sinks and tunnels."""
        with self._lock:
            for session_id, sink in list(self._sinks.items()):
                try:
                    sink.stop()
                except Exception:
                    pass
            self._sinks.clear()

            for session_id, tunnel in list(self._tunnels.items()):
                try:
                    tunnel.stop()
                except Exception:
                    pass
            self._tunnels.clear()
