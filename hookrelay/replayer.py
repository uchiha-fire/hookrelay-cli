"""
Event Replay Engine for hookrelay-cli.
Allows resending captured webhook events to local services or custom targets.
"""
import json
import time
from typing import Optional
from hookrelay.models import WebhookEvent, ForwardResult
from hookrelay.sink import forward_request, normalize_target_url


class EventReplayer:
    """Retransmits stored webhook events to specified destinations."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def replay(
        self,
        event: WebhookEvent,
        target_url: str,
        modified_payload: Optional[str] = None,
    ) -> ForwardResult:
        """
        Replays a stored event to target_url.
        Uses modified_payload if provided, otherwise uses the original payload.
        """
        dest_url = normalize_target_url(target_url)

        payload_to_send = modified_payload if modified_payload is not None else event.payload
        body_bytes = payload_to_send.encode("utf-8") if payload_to_send else b""

        # Clone and enrich headers
        headers = dict(event.headers)
        headers["X-HookRelay-Replay"] = "true"
        headers["X-HookRelay-Original-Event"] = event.id

        return forward_request(
            target_url=dest_url,
            method=event.method,
            headers=headers,
            body=body_bytes,
            timeout=self.timeout,
        )
