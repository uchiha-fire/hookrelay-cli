"""
CLI tests for hookrelay command line subcommands and options.
"""
import io
import json
import pytest
from hookrelay.cli import main
from hookrelay.manager import WebhookManager
from hookrelay.models import WebhookEvent


def test_cli_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "hookrelay-cli 0.1.0" in captured.out


def test_cli_lifecycle_commands(capsys, tmp_path):
    db_file = str(tmp_path / "test_cli.db")

    # 1. New webhook
    res = main(["--db", db_file, "new", "--name", "stripe", "--to", "http://localhost:8080"])
    assert res == 0
    captured = capsys.readouterr()
    assert "✓ Provisioned Webhook: stripe" in captured.out
    assert "Public HTTPS URL:" in captured.out

    # 2. List webhooks
    res = main(["--db", db_file, "list"])
    assert res == 0
    captured = capsys.readouterr()
    assert "stripe" in captured.out
    assert "ACTIVE" in captured.out

    # 3. List webhooks as JSON
    res = main(["--db", db_file, "list", "--json"])
    assert res == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert len(parsed) == 1
    assert parsed[0]["name"] == "stripe"
    wh_id = parsed[0]["id"]

    # 4. Pause webhook
    res = main(["--db", db_file, "pause", wh_id])
    assert res == 0
    captured = capsys.readouterr()
    assert f"✓ Webhook '{wh_id}' paused." in captured.out

    # 5. Resume webhook
    res = main(["--db", db_file, "resume", wh_id])
    assert res == 0
    captured = capsys.readouterr()
    assert f"✓ Webhook '{wh_id}' resumed." in captured.out

    # 6. Add dummy event directly to verify events and inspect CLI
    mgr = WebhookManager(db_path=db_file)
    evt = WebhookEvent(
        id="evt_cli_test",
        webhook_id=wh_id,
        timestamp=123456.0,
        method="POST",
        path="/v1/webhook",
        headers={"Content-Type": "application/json"},
        payload='{"type": "customer.created", "name": "Jane"}',
        fwd_status=200,
        fwd_latency_ms=12.4,
        fwd_response='{"ok": true}',
    )
    mgr.store.save_event(evt)

    # 7. List events
    res = main(["--db", db_file, "events", wh_id])
    assert res == 0
    captured = capsys.readouterr()
    assert "evt_cli_test" in captured.out
    assert "customer.created" in captured.out

    # 8. Inspect event
    res = main(["--db", db_file, "inspect", "evt_cli_test"])
    assert res == 0
    captured = capsys.readouterr()
    assert "Event: evt_cli_test" in captured.out
    assert "customer.created" in captured.out
    assert "Content-Type" in captured.out

    # 9. Kill webhook
    res = main(["--db", db_file, "kill", wh_id])
    assert res == 0
    captured = capsys.readouterr()
    assert f"✓ Webhook '{wh_id}' terminated successfully." in captured.out

    # Verify no active webhooks in default list
    res = main(["--db", db_file, "list"])
    assert res == 0
    captured = capsys.readouterr()
    assert "No active webhooks found" in captured.out
