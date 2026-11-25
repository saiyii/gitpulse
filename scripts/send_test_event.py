"""Send a signed test webhook to a running GitPulse instance.

    python scripts/send_test_event.py release tests/fixtures/release_published.json
    python scripts/send_test_event.py push tests/fixtures/push.json --url https://gitpulse.example.com/webhook

The secret is read from GITHUB_WEBHOOK_SECRET (the .env file is loaded if present).
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("event", help="X-GitHub-Event value, e.g. release, push, issues")
    parser.add_argument("payload", type=Path, help="JSON payload file")
    port = os.getenv("WEBHOOK_PORT") or "8080"
    parser.add_argument("--url", default=f"http://127.0.0.1:{port}/webhook")
    parser.add_argument("--secret", help="defaults to $GITHUB_WEBHOOK_SECRET")
    args = parser.parse_args()

    if load_dotenv:
        load_dotenv()
    secret = args.secret or os.getenv("GITHUB_WEBHOOK_SECRET")
    if not secret:
        print("no secret: pass --secret or set GITHUB_WEBHOOK_SECRET", file=sys.stderr)
        return 1

    body = args.payload.read_bytes()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    request = urllib.request.Request(
        args.url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "GitHub-Hookshot/test",
            "X-GitHub-Event": args.event,
            "X-GitHub-Delivery": str(uuid.uuid4()),
            "X-Hub-Signature-256": f"sha256={signature}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as resp:
            print(resp.status, resp.read().decode())
    except urllib.error.HTTPError as exc:
        print(exc.code, exc.read().decode())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
