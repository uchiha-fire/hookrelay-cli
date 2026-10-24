"""
Data models for hookrelay-cli sessions, captured events, and replay responses.
"""
from dataclasses import dataclass, field
import json
import time
from typing import Dict, Optional, Any


@dataclass
class WebhookSession:
    id: str
    name: str
    public_url: str
    local_target: str
    local_port: int
    status: str = "ACTIVE"  # ACTIVE, PAUSED, TERMINATED
    created_at: float = field(default_factory=time.time)

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE"

    @property
    def is_paused(self) -> bool:
        return self.status == "PAUSED"

    @property
    def is_terminated(self) -> bool:
        return self.status == "TERMINATED"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "public_url": self.public_url,
            "local_target": self.local_target,
            "local_port": self.local_port,
            "status": self.status,
            "created_at": self.created_at,
        }


@dataclass
class WebhookEvent:
    id: str
    webhook_id: str
    timestamp: float
    method: str
    path: str
    headers: Dict[str, str]
    payload: str
    fwd_status: Optional[int] = None
    fwd_latency_ms: Optional[float] = None
    fwd_response: Optional[str] = None

    @property
    def event_summary(self) -> str:
        """Attempt to extract standard webhook event type (e.g. Stripe type, GitHub action)."""
        if not self.payload:
            return self.path
        try:
            data = json.loads(self.payload)
            if isinstance(data, dict):
                if "type" in data and isinstance(data["type"], str):
                    return data["type"]
                if "event" in data and isinstance(data["event"], str):
                    return data["event"]
                if "action" in data and isinstance(data["action"], str):
                    return f"{data.get('action')}"
        except Exception:
            pass
        return self.path

    @property
    def is_success(self) -> bool:
        return self.fwd_status is not None and 200 <= self.fwd_status < 300

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "webhook_id": self.webhook_id,
            "timestamp": self.timestamp,
            "method": self.method,
            "path": self.path,
            "headers": self.headers,
            "payload": self.payload,
            "event_summary": self.event_summary,
            "fwd_status": self.fwd_status,
            "fwd_latency_ms": self.fwd_latency_ms,
            "fwd_response": self.fwd_response,
        }


@dataclass
class ForwardResult:
    status_code: int
    latency_ms: float
    response_body: str
    error: Optional[str] = None
