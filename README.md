# hookrelay-cli

[![PyPI version](https://img.shields.io/pypi/v/hookrelay-cli.svg)](https://pypi.org/project/hookrelay-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/hookrelay-cli.svg)](https://pypi.org/project/hookrelay-cli/)
[![GitHub stars](https://img.shields.io/github/stars/uchiha-fire/hookrelay-cli?style=social)](https://github.com/uchiha-fire/hookrelay-cli)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-Shubham%20Sharma-0A66C2.svg?style=flat&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/shubham-sharma-28487819b/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Zephyrus Labs](https://img.shields.io/badge/Developed%20by-Zephyrus%20Labs-6366f1.svg)](https://zephyrus-labs.tech/)

An interactive multi-webhook gateway, instant public HTTPS tunnel, and replay debugger by **[Zephyrus Labs](https://zephyrus-labs.tech/)** for Linux, macOS, and Windows.

---

## The Problem

Testing webhooks from providers like **Stripe**, **GitHub**, **HubSpot**, **Twilio**, **Shopify**, and **Google Calendar** during local development is painful:

1. **Strict HTTPS Requirement**: Providers reject `http://localhost:8080`. They require an active, public `https://...` callback URL.
2. **Multi-Service Friction**: Developers rarely test just one webhook. You often juggle Stripe (`:8080/stripe`), HubSpot (`:8081/crm`), and Google Calendar (`:3000/calendar`) simultaneously.
3. **Black Box Payloads**: When your backend fails or returns 500, finding the exact headers, HMAC signatures, and JSON body requires digging through messy server logs.
4. **Tedious Retesting**: Re-triggering webhooks requires manually recreating events (checking out products, submitting forms) over and over.

`hookrelay-cli` solves this with a **zero-dependency, single-command interactive terminal workspace**.

---

## Key Features

- ⚡ **Zero External Dependencies**: Pure Python standard library implementation (`http.server`, `sqlite3`, `subprocess`, `urllib`). No accounts, no tokens, no proprietary daemon binaries.
- 🔒 **Instant Public HTTPS Tunnels**: Provisions secure public HTTPS callback URLs via lightweight SSH reverse tunneling with zero configuration.
- 🎛️ **Multi-Webhook Hub**: Manage multiple active webhooks concurrently in one clean terminal dashboard.
- 📡 **Real-Time Event Stream**: Live incoming webhook feed displaying HTTP methods, event types, payload sizes, and forwarding latency.
- 🔁 **One-Key Instant Replay**: Replay any captured webhook directly to your localhost server with `[r]` without retriggering actions on third-party provider dashboards.
- 🔍 **Deep Payload & Header Inspector**: Inspect full request headers (including `Stripe-Signature`), formatted JSON bodies, and your local server's response.
- ⏸️ **Pause & Resume**: Temporarily capture incoming webhooks without forwarding to your local service when debugging or refactoring.
- 💾 **Persistent SQLite Event Log**: Events persist in local SQLite (`~/.hookrelay/data.db`) across sessions and server restarts.
- 🔄 **Fluid Back-and-Forth Navigation**: Zero modal traps; `[b]` or `[Esc]` returns to the previous view instantly.
- 🤖 **Scriptable CLI Engine**: Full subcommand suite (`hookrelay new`, `list`, `kill`, `events`, `replay`, `inspect`) for automation and CI/CD pipelines.

---

## Interactive TUI Workspace

Launch `hookrelay` without flags to enter the interactive terminal workspace:

```text
╔═════════════════════════════════════════════════════════════════════════════════════════╗
║                    HOOKRELAY — Active Webhook Manager                                   ║
╚═════════════════════════════════════════════════════════════════════════════════════════╝

  ID         NAME         PUBLIC HTTPS URL                  LOCAL TARGET        EVENTS   STATUS
  ─────────  ───────────  ────────────────────────────────  ──────────────────  ───────  ──────────
▸ wh_101     stripe       https://a9f3-8080.pinggy.link     http://:8080/hook   14       ● ACTIVE
  wh_102     hubspot      https://c4e2-8081.pinggy.link     http://:8081/crm    3        ● ACTIVE
  wh_103     calendar     https://d7a1-3000.pinggy.link     http://:3000/gcal   0        ○ PAUSED

─────────────────────────────────────────────────────────────────────────────────────────
 [↑/↓] Navigate   [Enter] Open Workspace   [n] New Webhook   [p] Pause/Resume
 [d/x] Terminate Webhook   [c] Copy URL   [q] Quit
```

### Drill Down into Any Webhook (`[Enter]`):

```text
╔═════════════════════════════════════════════════════════════════════════════════════════╗
║ HOOKRELAY » stripe (wh_101)                                         [● LIVE LISTENING]  ║
║ Public HTTPS URL: https://a9f3-8080.pinggy.link                                         ║
║ Forwarding to:    http://localhost:8080/hook                                            ║
╚═════════════════════════════════════════════════════════════════════════════════════════╝

  STATUS  METHOD  EVENT / PATH                     SIZE      TIME      FWD STATUS
  ──────  ──────  ───────────────────────────────  ────────  ────────  ───────────────
▸ 200     POST    payment_intent.succeeded         1.8 KB    23:14:02  200 (38ms)
  200     POST    charge.updated                   2.1 KB    23:13:58  200 (42ms)
  200     POST    customer.subscription.created    1.2 KB    23:12:11  500 (110ms) ⚠️

─────────────────────────────────────────────────────────────────────────────────────────
 [↑/↓] Select Event   [Enter] Inspect Details   [r] Instant Replay   [p] Pause/Resume
 [c] Copy URL         [b / Esc] ← Back to Webhook Hub
```

---

## Installation

```bash
pip install hookrelay-cli
```

Or install the development build directly:

```bash
pip install git+https://github.com/uchiha-fire/hookrelay-cli.git
```

---

## CLI Quickstart & Subcommands

### 1. Provision a New Webhook Tunnel
```bash
# Forward to local port 8080
hookrelay new --name stripe --to 8080

# Forward to specific local URL endpoint
hookrelay new --name hubspot --to http://localhost:3000/api/webhooks/hubspot
```

### 2. List Active Webhooks
```bash
hookrelay list

# Or machine-readable JSON:
hookrelay list --json
```

### 3. List Captured Events
```bash
hookrelay events stripe
```

### 4. Inspect an Event
```bash
hookrelay inspect evt_3N8e12
```

### 5. Replay an Event to Localhost
```bash
# Replay to original local target
hookrelay replay evt_3N8e12

# Replay to an alternative local target URL
hookrelay replay evt_3N8e12 --to http://localhost:9000/test-hook
```

### 6. Pause / Resume Forwarding
```bash
hookrelay pause stripe
hookrelay resume stripe
```

### 7. Terminate a Webhook Tunnel
```bash
hookrelay kill stripe
```

---

## Programmatic Python API

You can embed `hookrelay` directly in pytest test suites or developer scripts:

```python
from hookrelay import WebhookManager, EventReplayer

# Initialize manager
manager = WebhookManager()

# Create active webhook
session = manager.create_webhook(name="stripe", local_target="http://localhost:8080/webhook")
print(f"Public HTTPS URL: {session.public_url}")

# Fetch events
events = manager.list_events(webhook_id=session.id)

# Replay an event
replayer = EventReplayer()
res = replayer.replay(events[0], target_url="http://localhost:8080/webhook")
print(f"Replay response status: {res.status_code}")

# Terminate session
manager.terminate_webhook(session.id)
```

---

## Developed & Maintained by Zephyrus Labs

Built and maintained with ❤️ by **[Zephyrus Labs](https://zephyrus-labs.tech/)** and Lead Developer **[Shubham Sharma](https://www.linkedin.com/in/shubham-sharma-28487819b/)**.

- 💼 **LinkedIn**: [linkedin.com/in/shubham-sharma-28487819b](https://www.linkedin.com/in/shubham-sharma-28487819b/)
- 💻 **GitHub**: [@uchiha-fire](https://github.com/uchiha-fire)
- 🌐 **Website**: [zephyrus-labs.tech](https://zephyrus-labs.tech/)
- ✉️ **Organization Email**: [zephyrus.labs@gmail.com](mailto:zephyrus.labs@gmail.com)
- 📬 **Developer Email**: [sharmashubham25962@gmail.com](mailto:sharmashubham25962@gmail.com)

If you find this tool helpful, please give it a ⭐️ on [GitHub](https://github.com/uchiha-fire/hookrelay-cli)!

---

## Acknowledgements & Attributions

This tool is built entirely on the Python standard library with zero runtime dependencies. It credits the open tunneling ecosystem:

- **OpenSSH**: Standard secure shell client for port forwarding and reverse tunneling.
- **Python Standard Library**: `http.server`, `urllib.request`, `sqlite3`, and `select`.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

<p align="right">
  <sub>Lead Developer: <a href="https://www.linkedin.com/in/shubham-sharma-28487819b/">Shubham Sharma</a> (<a href="https://github.com/uchiha-fire">@uchiha-fire</a>) &bull; <a href="mailto:sharmashubham25962@gmail.com">sharmashubham25962@gmail.com</a></sub>
</p>
