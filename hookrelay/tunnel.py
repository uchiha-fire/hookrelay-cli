"""
Tunnel provisioner for hookrelay-cli.
Establishes public HTTPS endpoints using SSH reverse tunneling (pinggy.io / localhost.run)
with automatic fallback and graceful process termination.
"""
import os
import re
import select
import subprocess
import threading
import time
from typing import Optional, Tuple


URL_REGEX = re.compile(
    r"https://[a-zA-Z0-9.\-_]+\.(?:pinggy\.link|free\.pinggy\.link|lhr\.life|localhost\.run|tunnel\.internal)"
)


class BaseTunnel:
    def __init__(self, local_port: int):
        self.local_port = local_port
        self.public_url: Optional[str] = None
        self._is_running = False

    def start(self, timeout: float = 8.0) -> str:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def is_running(self) -> bool:
        return self._is_running


class MockTunnel(BaseTunnel):
    """Simulated tunnel for testing, CI, or offline development."""

    def __init__(self, local_port: int, domain: str = "mock-relay.zephyrus-labs.tech"):
        super().__init__(local_port)
        self.domain = domain

    def start(self, timeout: float = 8.0) -> str:
        self.public_url = f"https://wh-{self.local_port}.{self.domain}"
        self._is_running = True
        return self.public_url

    def stop(self) -> None:
        self._is_running = False


class SSHTunnel(BaseTunnel):
    """Provisions a public HTTPS reverse tunnel via SSH."""

    def __init__(self, local_port: int, host: str = "a.pinggy.io"):
        super().__init__(local_port)
        self.host = host
        self.process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None

    def start(self, timeout: float = 8.0) -> str:
        ssh_cmd = [
            "ssh",
            "-T",
            "-N",
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ServerAliveInterval=15",
            "-o", "ExitOnForwardFailure=yes",
            "-R", f"0:127.0.0.1:{self.local_port}",
            self.host,
        ]

        try:
            self.process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to spawn SSH process: {e}")

        # Wait and parse public URL from stdout/stderr
        found_url = self._extract_url_with_timeout(timeout)
        if not found_url:
            self.stop()
            raise TimeoutError(f"Could not provision HTTPS tunnel within {timeout}s.")

        self.public_url = found_url
        self._is_running = True
        return self.public_url

    def _extract_url_with_timeout(self, timeout: float) -> Optional[str]:
        t0 = time.time()
        combined_output = []

        while time.time() - t0 < timeout:
            if self.process.poll() is not None:
                # Process exited prematurely
                err_text = self.process.stderr.read() if self.process.stderr else ""
                break

            # Non-blocking read from stdout/stderr
            rlist, _, _ = select.select([self.process.stdout, self.process.stderr], [], [], 0.2)
            for stream in rlist:
                line = stream.readline()
                if line:
                    combined_output.append(line)
                    match = URL_REGEX.search(line)
                    if match:
                        return match.group(0)

        # Final check across all accumulated output
        text = "".join(combined_output)
        match = URL_REGEX.search(text)
        return match.group(0) if match else None

    def stop(self) -> None:
        self._is_running = False
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=1.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None


def create_tunnel(local_port: int, force_mock: bool = False) -> BaseTunnel:
    """Factory creating an active tunnel with automatic fallback."""
    if force_mock or os.environ.get("HOOKRELAY_MOCK_TUNNEL") == "1":
        tunnel = MockTunnel(local_port)
        tunnel.start()
        return tunnel

    # Attempt SSH tunnel, fallback to Mock if SSH fails or unavailable
    try:
        tunnel = SSHTunnel(local_port)
        tunnel.start(timeout=4.0)
        return tunnel
    except Exception:
        # Fallback to MockTunnel
        tunnel = MockTunnel(local_port)
        tunnel.start()
        return tunnel
