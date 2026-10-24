"""
Interactive Terminal UI (TUI) for hookrelay-cli.
Provides multi-screen interactive navigation:
- Webhook Hub (Active webhooks list, termination, new webhook wizard)
- Webhook Workspace (Live event feed, pause, inspect)
- Event Deep Inspector (Headers, JSON payload, response, replay)
"""
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from hookrelay.manager import WebhookManager
from hookrelay.models import WebhookSession, WebhookEvent


# ANSI Color & Style Codes
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"
BG_BLUE = "\033[44m"
BG_DARK = "\033[48;5;236m"
CLEAR_SCREEN = "\033[2J\033[H"


class HookRelayTUI:
    """Multi-screen state machine for interactive webhook operations."""

    def __init__(self, manager: WebhookManager):
        self.manager = manager
        self.screen = "HUB"  # "HUB", "WORKSPACE", "INSPECTOR", "WIZARD", "CONFIRM_KILL"
        self.selected_webhook_idx = 0
        self.selected_event_idx = 0
        self.active_webhook_id: Optional[str] = None
        self.active_event_id: Optional[str] = None
        self.status_message: Optional[str] = None
        self.status_color: str = GREEN

        # Wizard state
        self.wizard_step = 0
        self.wizard_data = {"name": "", "target": ""}

    def set_status(self, message: str, color: str = GREEN) -> None:
        self.status_message = message
        self.status_color = color

    # -------------------------------------------------------------------------
    # Screen Renderers
    # -------------------------------------------------------------------------

    def render(self) -> str:
        """Render the current screen to a string for display."""
        if self.screen == "HUB":
            return self._render_hub()
        elif self.screen == "WORKSPACE":
            return self._render_workspace()
        elif self.screen == "INSPECTOR":
            return self._render_inspector()
        elif self.screen == "WIZARD":
            return self._render_wizard()
        elif self.screen == "CONFIRM_KILL":
            return self._render_confirm_kill()
        return "Unknown screen state."

    def _render_hub(self) -> str:
        webhooks = self.manager.list_webhooks(include_terminated=False)
        lines = []
        lines.append(f"{CYAN}╔═════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        lines.append(f"{CYAN}║                    {BOLD}HOOKRELAY — Active Webhook Manager{RESET}{CYAN}                                   ║{RESET}")
        lines.append(f"{CYAN}╚═════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

        if self.status_message:
            lines.append(f" {self.status_color}▶ {self.status_message}{RESET}\n")

        # Table header
        lines.append(f"{DIM}  {'ID':<10} {'NAME':<12} {'PUBLIC HTTPS URL':<34} {'LOCAL TARGET':<20} {'EVENTS':<8} {'STATUS'}{RESET}")
        lines.append(f"{DIM}  {'─'*9} {'─'*11} {'─'*33} {'─'*19} {'─'*7} {'─'*10}{RESET}")

        if not webhooks:
            lines.append(f"\n  {YELLOW}No active webhooks.{RESET} Press {BOLD}[n]{RESET} to provision your first public HTTPS webhook tunnel.\n")
        else:
            for idx, wh in enumerate(webhooks):
                is_selected = (idx == self.selected_webhook_idx)
                prefix = f"{GREEN}▸{RESET} " if is_selected else "  "

                status_str = f"{GREEN}● ACTIVE{RESET}" if wh.is_active else f"{YELLOW}○ PAUSED{RESET}"
                count = self.manager.count_events(wh.id)

                row_style = BOLD if is_selected else ""
                url_display = wh.public_url if len(wh.public_url) <= 33 else wh.public_url[:30] + "..."
                target_display = wh.local_target if len(wh.local_target) <= 19 else wh.local_target[:16] + "..."

                lines.append(
                    f"{prefix}{row_style}{wh.id:<10} {wh.name:<12} {url_display:<34} {target_display:<20} {count:<8} {status_str}{RESET}"
                )

        lines.append("\n" + f"{DIM}─"*89 + f"{RESET}")
        lines.append(f" {BOLD}[↑/↓]{RESET} Navigate   {BOLD}[Enter]{RESET} Open Workspace   {BOLD}[n]{RESET} New Webhook   {BOLD}[p]{RESET} Pause/Resume")
        lines.append(f" {BOLD}[d/x]{RESET} Terminate Webhook   {BOLD}[c]{RESET} Copy URL   {BOLD}[q]{RESET} Quit")
        lines.append(f" {DIM}Zephyrus Labs • Lead Developer: Shubham Sharma (https://www.linkedin.com/in/shubham-sharma-28487819b/){RESET}")
        return "\n".join(lines)

    def _render_workspace(self) -> str:
        wh = self.manager.get_webhook(self.active_webhook_id) if self.active_webhook_id else None
        if not wh:
            self.screen = "HUB"
            return self._render_hub()

        events = self.manager.list_events(webhook_id=wh.id, limit=30)
        lines = []
        status_tag = f"{GREEN}[● LIVE LISTENING]{RESET}" if wh.is_active else f"{YELLOW}[○ PAUSED]{RESET}"

        lines.append(f"{CYAN}╔═════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        lines.append(f"{CYAN}║ {BOLD}HOOKRELAY » {wh.name} ({wh.id}){RESET} {status_tag} {CYAN}║{RESET}")
        lines.append(f"{CYAN}║ Public HTTPS URL: {GREEN}{wh.public_url}{RESET} {CYAN}                               ║{RESET}")
        lines.append(f"{CYAN}║ Forwarding to:    {WHITE}{wh.local_target}{RESET} {CYAN}                                              ║{RESET}")
        lines.append(f"{CYAN}╚═════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

        if self.status_message:
            lines.append(f" {self.status_color}▶ {self.status_message}{RESET}\n")

        lines.append(f"{DIM}  {'STATUS':<8} {'METHOD':<8} {'EVENT / PATH':<32} {'SIZE':<10} {'TIME':<10} {'FWD STATUS'}{RESET}")
        lines.append(f"{DIM}  {'─'*7} {'─'*7} {'─'*31} {'─'*9} {'─'*9} {'─'*15}{RESET}")

        if not events:
            lines.append(f"\n  {YELLOW}Awaiting incoming webhooks...{RESET} Send a POST request to {GREEN}{wh.public_url}{RESET}\n")
        else:
            for idx, evt in enumerate(events):
                is_selected = (idx == self.selected_event_idx)
                prefix = f"{GREEN}▸{RESET} " if is_selected else "  "
                row_style = BOLD if is_selected else ""

                fwd_color = GREEN if evt.is_success else RED
                fwd_str = f"{fwd_color}{evt.fwd_status or '-'}{RESET} ({evt.fwd_latency_ms or 0:.0f}ms)" if evt.fwd_status else f"{YELLOW}PAUSED{RESET}"
                size_str = f"{len(evt.payload.encode('utf-8'))} B"
                time_str = datetime.fromtimestamp(evt.timestamp).strftime("%H:%M:%S")

                summary = evt.event_summary
                if len(summary) > 30:
                    summary = summary[:27] + "..."

                lines.append(
                    f"{prefix}{row_style}{200:<8} {evt.method:<8} {summary:<32} {size_str:<10} {time_str:<10} {fwd_str}{RESET}"
                )

        lines.append("\n" + f"{DIM}─"*89 + f"{RESET}")
        lines.append(f" {BOLD}[↑/↓]{RESET} Select Event   {BOLD}[Enter]{RESET} Inspect Details   {BOLD}[r]{RESET} Instant Replay   {BOLD}[p]{RESET} Pause/Resume")
        lines.append(f" {BOLD}[c]{RESET} Copy URL       {BOLD}[b / Esc]{RESET} ← Back to Webhook Hub")
        return "\n".join(lines)

    def _render_inspector(self) -> str:
        evt = self.manager.get_event(self.active_event_id) if self.active_event_id else None
        if not evt:
            self.screen = "WORKSPACE"
            return self._render_workspace()

        lines = []
        lines.append(f"{CYAN}╔═════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        lines.append(f"{CYAN}║ {BOLD}EVENT INSPECTOR: {evt.id} ({evt.event_summary}){RESET} {CYAN}║{RESET}")
        lines.append(f"{CYAN}╚═════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

        if self.status_message:
            lines.append(f" {self.status_color}▶ {self.status_message}{RESET}\n")

        # Headers
        lines.append(f"{BOLD}─── HTTP Request Headers ─────────────────────────────────────────────────────────────────{RESET}")
        for k, v in evt.headers.items():
            lines.append(f"  {BLUE}{k}:{RESET} {v}")

        # Payload
        lines.append(f"\n{BOLD}─── Request Body / Payload ───────────────────────────────────────────────────────────────{RESET}")
        try:
            formatted_json = json.dumps(json.loads(evt.payload), indent=2)
            for line in formatted_json.splitlines()[:25]:
                lines.append(f"  {line}")
            if len(formatted_json.splitlines()) > 25:
                lines.append(f"  {DIM}... (truncated for display) ...{RESET}")
        except Exception:
            lines.append(f"  {evt.payload[:1000]}")

        # Response
        lines.append(f"\n{BOLD}─── Forwarding Response ──────────────────────────────────────────────────────────────────{RESET}")
        status_color = GREEN if evt.is_success else RED
        lines.append(f"  Status:  {status_color}{evt.fwd_status}{RESET} (Latency: {evt.fwd_latency_ms or 0:.2f}ms)")
        if evt.fwd_response:
            lines.append(f"  Body:    {evt.fwd_response[:300]}")

        lines.append("\n" + f"{DIM}─"*89 + f"{RESET}")
        lines.append(f" {BOLD}[r]{RESET} Replay Event   {BOLD}[c]{RESET} Copy Payload   {BOLD}[b / Esc]{RESET} ← Back to Event List")
        return "\n".join(lines)

    def _render_wizard(self) -> str:
        lines = []
        lines.append(f"{CYAN}╔═════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        lines.append(f"{CYAN}║                  {BOLD}Provision New Public HTTPS Webhook Tunnel{RESET}{CYAN}                             ║{RESET}")
        lines.append(f"{CYAN}╚═════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

        lines.append("  Configure your local destination endpoint:")
        lines.append(f"  1. Webhook Label / Name:      {GREEN}{self.wizard_data['name'] or '(typing...)'}{RESET}")
        lines.append(f"  2. Local Target (Port or URL): {WHITE}{self.wizard_data['target'] or '(e.g. 8080 or http://localhost:3000/hook)'}{RESET}")
        lines.append("\n" + f"{DIM}─"*89 + f"{RESET}")
        lines.append(f" {BOLD}[Enter]{RESET} Provision Webhook Tunnel   {BOLD}[Esc / b]{RESET} Cancel")
        return "\n".join(lines)

    def _render_confirm_kill(self) -> str:
        wh = self.manager.get_webhook(self.active_webhook_id) if self.active_webhook_id else None
        lines = []
        lines.append(f"{RED}╔═════════════════════════════════════════════════════════════════════════════════════════╗{RESET}")
        lines.append(f"{RED}║                             {BOLD}CONFIRM TERMINATION{RESET}{RED}                                       ║{RESET}")
        lines.append(f"{RED}╚═════════════════════════════════════════════════════════════════════════════════════════╝{RESET}\n")

        if wh:
            lines.append(f"  Are you sure you want to terminate webhook {BOLD}'{wh.name}' ({wh.id}){RESET}?")
            lines.append(f"  Public URL: {wh.public_url}")
            lines.append("  This will shut down the HTTPS tunnel and stop local listening.")
        lines.append("\n" + f"{DIM}─"*89 + f"{RESET}")
        lines.append(f" {BOLD}[y]{RESET} Yes, Terminate   {BOLD}[n / Esc]{RESET} Cancel")
        return "\n".join(lines)

    # -------------------------------------------------------------------------
    # State Machine & Event Dispatch
    # -------------------------------------------------------------------------

    def handle_key(self, key: str) -> bool:
        """
        Process a keystroke.
        Returns False if the user wants to quit, True to continue.
        """
        self.status_message = None

        if self.screen == "HUB":
            return self._handle_hub_key(key)
        elif self.screen == "WORKSPACE":
            return self._handle_workspace_key(key)
        elif self.screen == "INSPECTOR":
            return self._handle_inspector_key(key)
        elif self.screen == "CONFIRM_KILL":
            return self._handle_confirm_kill_key(key)
        elif self.screen == "WIZARD":
            return self._handle_wizard_key(key)

        return True

    def _handle_hub_key(self, key: str) -> bool:
        webhooks = self.manager.list_webhooks(include_terminated=False)

        if key in ("q", "Q", "\x03"):  # q or Ctrl+C
            return False

        if key in ("UP", "k") and self.selected_webhook_idx > 0:
            self.selected_webhook_idx -= 1
        elif key in ("DOWN", "j") and self.selected_webhook_idx < len(webhooks) - 1:
            self.selected_webhook_idx += 1
        elif key in ("\n", "\r", "ENTER"):
            if webhooks and 0 <= self.selected_webhook_idx < len(webhooks):
                self.active_webhook_id = webhooks[self.selected_webhook_idx].id
                self.selected_event_idx = 0
                self.screen = "WORKSPACE"
        elif key == "n":
            self.wizard_data = {"name": f"hook-{len(webhooks)+1}", "target": "http://localhost:8080"}
            self.screen = "WIZARD"
        elif key in ("d", "x"):
            if webhooks and 0 <= self.selected_webhook_idx < len(webhooks):
                self.active_webhook_id = webhooks[self.selected_webhook_idx].id
                self.screen = "CONFIRM_KILL"
        elif key == "p":
            if webhooks and 0 <= self.selected_webhook_idx < len(webhooks):
                wh = webhooks[self.selected_webhook_idx]
                if wh.is_active:
                    self.manager.pause_webhook(wh.id)
                    self.set_status(f"Webhook '{wh.name}' paused.", YELLOW)
                else:
                    self.manager.resume_webhook(wh.id)
                    self.set_status(f"Webhook '{wh.name}' resumed.", GREEN)
        elif key == "c":
            if webhooks and 0 <= self.selected_webhook_idx < len(webhooks):
                wh = webhooks[self.selected_webhook_idx]
                self.set_status(f"URL: {wh.public_url}", CYAN)

        return True

    def _handle_workspace_key(self, key: str) -> bool:
        events = self.manager.list_events(webhook_id=self.active_webhook_id, limit=30)

        if key in ("b", "B", "ESC", "\x1b"):
            self.screen = "HUB"
            return True

        if key in ("UP", "k") and self.selected_event_idx > 0:
            self.selected_event_idx -= 1
        elif key in ("DOWN", "j") and self.selected_event_idx < len(events) - 1:
            self.selected_event_idx += 1
        elif key in ("\n", "\r", "ENTER"):
            if events and 0 <= self.selected_event_idx < len(events):
                self.active_event_id = events[self.selected_event_idx].id
                self.screen = "INSPECTOR"
        elif key == "r":
            if events and 0 <= self.selected_event_idx < len(events):
                evt = events[self.selected_event_idx]
                res = self.manager.replay_event(evt.id)
                self.set_status(f"Replayed {evt.id}: HTTP {res.status_code} ({res.latency_ms:.0f}ms)", GREEN if res.status_code == 200 else RED)
        elif key == "p":
            if self.active_webhook_id:
                wh = self.manager.get_webhook(self.active_webhook_id)
                if wh and wh.is_active:
                    self.manager.pause_webhook(wh.id)
                    self.set_status("Paused webhook forwarding.", YELLOW)
                elif wh:
                    self.manager.resume_webhook(wh.id)
                    self.set_status("Resumed webhook forwarding.", GREEN)
        elif key == "c":
            if self.active_webhook_id:
                wh = self.manager.get_webhook(self.active_webhook_id)
                if wh:
                    self.set_status(f"URL: {wh.public_url}", CYAN)

        return True

    def _handle_inspector_key(self, key: str) -> bool:
        if key in ("b", "B", "ESC", "\x1b"):
            self.screen = "WORKSPACE"
            return True

        if key == "r" and self.active_event_id:
            res = self.manager.replay_event(self.active_event_id)
            self.set_status(f"Replayed: HTTP {res.status_code} ({res.latency_ms:.0f}ms)", GREEN if res.status_code == 200 else RED)
        elif key == "c" and self.active_event_id:
            evt = self.manager.get_event(self.active_event_id)
            if evt:
                self.set_status("Copied payload to clipboard.", CYAN)

        return True

    def _handle_confirm_kill_key(self, key: str) -> bool:
        if key in ("y", "Y"):
            if self.active_webhook_id:
                self.manager.terminate_webhook(self.active_webhook_id)
                self.set_status("Webhook successfully terminated.", YELLOW)
            self.selected_webhook_idx = 0
            self.screen = "HUB"
        elif key in ("n", "N", "ESC", "\x1b", "b"):
            self.screen = "HUB"

        return True

    def _handle_wizard_key(self, key: str) -> bool:
        if key in ("ESC", "\x1b", "b"):
            self.screen = "HUB"
            return True

        if key in ("\n", "\r", "ENTER"):
            name = self.wizard_data["name"] or "webhook"
            target = self.wizard_data["target"] or "http://localhost:8080"
            session = self.manager.create_webhook(name=name, local_target=target)
            self.set_status(f"Created webhook '{name}' ({session.public_url})", GREEN)
            self.screen = "HUB"

        return True


def get_key() -> str:
    """Read a single key or ANSI escape sequence from stdin."""
    import select
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    seq = sys.stdin.read(2)
                    if seq == "[A":
                        return "UP"
                    elif seq == "[B":
                        return "DOWN"
                    elif seq == "[C":
                        return "RIGHT"
                    elif seq == "[D":
                        return "LEFT"
                    return "ESC"
                return "ESC"
            elif ch in ("\r", "\n"):
                return "ENTER"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    except Exception:
        # Fallback for systems/environments where termios/tty is unavailable
        line = sys.stdin.readline()
        return line.strip()


def run_interactive(manager: WebhookManager) -> None:
    """Run full-screen interactive TUI."""
    if not sys.stdin.isatty():
        print("Non-interactive environment detected.")
        webhooks = manager.list_webhooks()
        if webhooks:
            print(f"Active webhooks: {len(webhooks)}")
            for w in webhooks:
                print(f"  {w.name} ({w.id}): {w.public_url} -> {w.local_target}")
        else:
            print("No active webhooks. Run 'hookrelay new --name stripe --to 8080' to create one.")
        return

    tui = HookRelayTUI(manager)
    sys.stdout.write("\033[?25l")  # Hide cursor
    sys.stdout.flush()

    try:
        while True:
            sys.stdout.write(CLEAR_SCREEN)
            sys.stdout.write(tui.render())
            sys.stdout.write("\n")
            sys.stdout.flush()

            key = get_key()
            if not tui.handle_key(key):
                break
    finally:
        sys.stdout.write("\033[?25h")  # Restore cursor
        sys.stdout.write("\nExiting HookRelay.\n")
        sys.stdout.flush()

