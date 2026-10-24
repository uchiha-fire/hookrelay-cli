"""
Command Line Interface (CLI) for hookrelay.
Supports both interactive TUI mode and scriptable subcommands.
"""
import argparse
import json
import sys
from typing import List, Optional

from hookrelay.manager import WebhookManager
from hookrelay.tui import run_interactive

VERSION = "0.1.0"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hookrelay",
        description="Interactive Multi-Webhook Gateway, HTTPS Tunnel & Replay Debugger by Zephyrus Labs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--version", action="version", version=f"hookrelay-cli {VERSION}")
    parser.add_argument("--db", help="Path to custom SQLite database file")

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # new
    new_p = subparsers.add_parser("new", help="Provision a new public HTTPS webhook endpoint")
    new_p.add_argument("--name", "-n", required=True, help="Webhook identifier/name (e.g. stripe, hubspot)")
    new_p.add_argument("--to", "-t", required=True, help="Local destination port or URL (e.g. 8080 or http://localhost:8080/hook)")
    new_p.add_argument("--port", "-p", type=int, default=0, help="Local sink port to bind (default: dynamic random port)")

    # list
    list_p = subparsers.add_parser("list", help="List active webhooks")
    list_p.add_argument("--all", "-a", action="store_true", help="Include terminated webhooks")
    list_p.add_argument("--json", action="store_true", dest="json_output", help="Output in JSON format")

    # kill / terminate
    kill_p = subparsers.add_parser("kill", aliases=["terminate"], help="Terminate an active webhook tunnel")
    kill_p.add_argument("id_or_name", help="Webhook ID or Name to terminate")

    # pause
    pause_p = subparsers.add_parser("pause", help="Pause forwarding for a webhook (captures without forwarding)")
    pause_p.add_argument("id_or_name", help="Webhook ID or Name to pause")

    # resume
    resume_p = subparsers.add_parser("resume", help="Resume forwarding for a paused webhook")
    resume_p.add_argument("id_or_name", help="Webhook ID or Name to resume")

    # events
    events_p = subparsers.add_parser("events", help="List captured events")
    events_p.add_argument("id_or_name", nargs="?", default=None, help="Optional webhook ID or Name to filter")
    events_p.add_argument("--limit", "-l", type=int, default=30, help="Max events to return (default: 30)")
    events_p.add_argument("--json", action="store_true", dest="json_output", help="Output in JSON format")

    # inspect
    inspect_p = subparsers.add_parser("inspect", help="Inspect detailed payload and headers of an event")
    inspect_p.add_argument("event_id", help="Event ID (e.g. evt_xxxx)")

    # replay
    replay_p = subparsers.add_parser("replay", help="Replay a captured webhook event to local backend")
    replay_p.add_argument("event_id", help="Event ID to replay")
    replay_p.add_argument("--to", help="Override destination target URL")

    return parser


def handle_new(manager: WebhookManager, args: argparse.Namespace) -> int:
    session = manager.create_webhook(name=args.name, local_target=args.to, local_port=args.port)
    print(f"✓ Provisioned Webhook: {session.name} ({session.id})")
    print(f"  Public HTTPS URL: {session.public_url}")
    print(f"  Forwarding to:    {session.local_target}")
    print(f"  Status:           {session.status}")
    return 0


def handle_list(manager: WebhookManager, args: argparse.Namespace) -> int:
    webhooks = manager.list_webhooks(include_terminated=args.all)
    if args.json_output:
        print(json.dumps([w.to_dict() for w in webhooks], indent=2))
        return 0

    if not webhooks:
        print("No active webhooks found. Create one with: hookrelay new --name <name> --to <target>")
        return 0

    print(f"{'ID':<10} {'NAME':<12} {'PUBLIC HTTPS URL':<35} {'LOCAL TARGET':<22} {'EVENTS':<8} {'STATUS'}")
    print(f"{'─'*9} {'─'*11} {'─'*34} {'─'*21} {'─'*7} {'─'*10}")
    for w in webhooks:
        count = manager.count_events(w.id)
        print(f"{w.id:<10} {w.name:<12} {w.public_url:<35} {w.local_target:<22} {count:<8} {w.status}")
    return 0


def handle_kill(manager: WebhookManager, args: argparse.Namespace) -> int:
    success = manager.terminate_webhook(args.id_or_name)
    if success:
        print(f"✓ Webhook '{args.id_or_name}' terminated successfully.")
        return 0
    else:
        print(f"✗ Webhook '{args.id_or_name}' not found.", file=sys.stderr)
        return 1


def handle_pause(manager: WebhookManager, args: argparse.Namespace) -> int:
    success = manager.pause_webhook(args.id_or_name)
    if success:
        print(f"✓ Webhook '{args.id_or_name}' paused.")
        return 0
    print(f"✗ Webhook '{args.id_or_name}' not found.", file=sys.stderr)
    return 1


def handle_resume(manager: WebhookManager, args: argparse.Namespace) -> int:
    success = manager.resume_webhook(args.id_or_name)
    if success:
        print(f"✓ Webhook '{args.id_or_name}' resumed.")
        return 0
    print(f"✗ Webhook '{args.id_or_name}' not found.", file=sys.stderr)
    return 1


def handle_events(manager: WebhookManager, args: argparse.Namespace) -> int:
    webhook_id = None
    if args.id_or_name:
        wh = manager.get_webhook(args.id_or_name)
        webhook_id = wh.id if wh else args.id_or_name

    events = manager.list_events(webhook_id=webhook_id, limit=args.limit)
    if args.json_output:
        print(json.dumps([e.to_dict() for e in events], indent=2))
        return 0

    if not events:
        print("No captured events found.")
        return 0

    print(f"{'EVENT ID':<16} {'METHOD':<8} {'SUMMARY / TYPE':<32} {'FWD STATUS':<12} {'LATENCY'}")
    print(f"{'─'*15} {'─'*7} {'─'*31} {'─'*11} {'─'*10}")
    for e in events:
        fwd = str(e.fwd_status) if e.fwd_status else "PAUSED"
        lat = f"{e.fwd_latency_ms:.1f}ms" if e.fwd_latency_ms is not None else "-"
        print(f"{e.id:<16} {e.method:<8} {e.event_summary:<32} {fwd:<12} {lat}")
    return 0


def handle_inspect(manager: WebhookManager, args: argparse.Namespace) -> int:
    event = manager.get_event(args.event_id)
    if not event:
        print(f"✗ Event '{args.event_id}' not found.", file=sys.stderr)
        return 1

    print(f"Event: {event.id} ({event.method} {event.path})")
    print(f"Webhook ID: {event.webhook_id}")
    print("\n--- Headers ---")
    for k, v in event.headers.items():
        print(f"{k}: {v}")
    print("\n--- Payload ---")
    try:
        print(json.dumps(json.loads(event.payload), indent=2))
    except Exception:
        print(event.payload)
    print("\n--- Forwarding Result ---")
    print(f"Status: {event.fwd_status} (Latency: {event.fwd_latency_ms or 0:.2f}ms)")
    if event.fwd_response:
        print(f"Response: {event.fwd_response}")
    return 0


def handle_replay(manager: WebhookManager, args: argparse.Namespace) -> int:
    try:
        res = manager.replay_event(event_id=args.event_id, target_override=args.to)
        print(f"✓ Event {args.event_id} replayed.")
        print(f"  HTTP Status: {res.status_code}")
        print(f"  Latency:     {res.latency_ms:.2f}ms")
        if res.response_body:
            print(f"  Response:    {res.response_body[:200]}")
        return 0 if res.status_code < 400 else 1
    except Exception as e:
        print(f"✗ Replay failed: {e}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manager = WebhookManager(db_path=args.db)

    if not args.subcommand:
        # Default: Launch Interactive TUI
        run_interactive(manager)
        return 0

    if args.subcommand == "new":
        return handle_new(manager, args)
    elif args.subcommand == "list":
        return handle_list(manager, args)
    elif args.subcommand in ("kill", "terminate"):
        return handle_kill(manager, args)
    elif args.subcommand == "pause":
        return handle_pause(manager, args)
    elif args.subcommand == "resume":
        return handle_resume(manager, args)
    elif args.subcommand == "events":
        return handle_events(manager, args)
    elif args.subcommand == "inspect":
        return handle_inspect(manager, args)
    elif args.subcommand == "replay":
        return handle_replay(manager, args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
