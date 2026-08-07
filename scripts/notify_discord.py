"""Send a file's contents to a Discord webhook.

Usage:
    python scripts/notify_discord.py <report_path> [--priority]

Environment:
    DISCORD_WEBHOOK — Discord webhook URL (required)

Options:
    --priority    Prepend @here mention to the message body

Exit codes:
    0 — webhook returned 2xx
    1 — missing env var, file not found, or non-2xx response
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

_MAX_DISCORD_LENGTH = 1900  # leave room for @here prefix and code block markers


def _read_report(report_path: Path) -> str:
    """Read report file; return as plain text."""
    if not report_path.exists():
        raise FileNotFoundError(f"Report file not found: {report_path}")
    content = report_path.read_text(encoding="utf-8", errors="replace")
    # If JSON, pretty-print up to max length
    if report_path.suffix == ".json":
        try:
            data = json.loads(content)
            content = json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            pass
    return content


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def send_notification(report_path: Path, priority: bool = False) -> int:
    """Send report to Discord webhook. Returns exit code (0=success, 1=failure)."""
    webhook_url = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK environment variable is not set", file=sys.stderr)
        return 1

    try:
        body = _read_report(report_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    prefix = "@here " if priority else ""
    message = _truncate(prefix + body, _MAX_DISCORD_LENGTH)

    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        print(f"ERROR: Discord webhook returned HTTP {exc.code}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: Failed to reach Discord webhook: {exc}", file=sys.stderr)
        return 1

    if 200 <= status < 300:
        return 0

    print(f"ERROR: Discord webhook returned HTTP {status}", file=sys.stderr)
    return 1


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("Usage: notify_discord.py <report_path> [--priority]", file=sys.stderr)
        return 1

    report_path = Path(args[0])
    priority = "--priority" in args

    return send_notification(report_path, priority=priority)


if __name__ == "__main__":
    sys.exit(main())
