"""Create the GitPulse GitHub App with every setting already filled in.

    python scripts/create_github_app.py
    python scripts/create_github_app.py --name "GitPulse Dev" --private \
        --webhook-url https://smee.io/abc
    python scripts/create_github_app.py --org my-org

Uses GitHub's app manifest flow: your browser opens GitHub with the name,
permissions, events and webhook URL pre-filled, you confirm, and GitHub hands
the credentials back to this script. It then writes:

- the private key to private-key.pem,
- GITHUB_APP_ID and GITHUB_WEBHOOK_SECRET to .env (created from .env.example if needed).

https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest
"""

from __future__ import annotations

import argparse
import html
import json
import re
import secrets
import shutil
import sys
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent

PERMISSIONS = {
    "contents": "read",
    "issues": "write",
    "metadata": "read",
    "pull_requests": "read",
}
EVENTS = ["issues", "pull_request", "push", "release"]


def build_manifest(args: argparse.Namespace, redirect_url: str) -> dict[str, Any]:
    return {
        "name": args.name,
        "url": args.homepage,
        "description": (
            "Posts releases, pushes, issues and pull requests to Discord, and lets you "
            "look up repositories and open issues from Discord."
        ),
        "hook_attributes": {"url": args.webhook_url, "active": True},
        "redirect_url": redirect_url,
        "public": not args.private,
        "default_permissions": PERMISSIONS,
        "default_events": EVENTS,
    }


def convert(code: str) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.github.com/app-manifests/{code}/conversions",
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "GitPulse-setup",
        },
    )
    with urllib.request.urlopen(request, timeout=20) as resp:
        return json.load(resp)


def update_env(path: Path, values: dict[str, str]) -> None:
    if not path.exists():
        example = ROOT / ".env.example"
        if example.exists():
            shutil.copy(example, path)
        else:
            path.touch()

    lines = path.read_text(encoding="utf-8").splitlines()
    remaining = dict(values)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_credentials(app: dict[str, Any]) -> Path:
    key_path = ROOT / "private-key.pem"
    if key_path.exists():
        # never overwrite an existing key
        key_path = ROOT / f"{app['slug']}.private-key.pem"
    key_path.write_text(app["pem"], encoding="utf-8")

    update_env(
        ROOT / ".env",
        {
            "GITHUB_APP_ID": str(app["id"]),
            "GITHUB_WEBHOOK_SECRET": app["webhook_secret"],
            "GITHUB_APP_PRIVATE_KEY_PATH": f"./{key_path.name}",
        },
    )
    return key_path


def page(title: str, body: str) -> bytes:
    return (
        "<!doctype html><meta charset=utf-8><title>GitPulse setup</title>"
        "<body style='font:16px system-ui;max-width:560px;margin:60px auto;padding:0 16px'>"
        f"<h2>{html.escape(title)}</h2>{body}</body>"
    ).encode()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create the GitPulse GitHub App from a manifest.")
    parser.add_argument("--name", default="GitPulse", help="app name, unique across GitHub")
    parser.add_argument("--homepage", default="https://gitpulse.saiyiidev.com")
    parser.add_argument("--webhook-url", default="https://gitpulse.saiyiidev.com/webhook")
    parser.add_argument("--org", help="create the app under this organization")
    parser.add_argument("--private", action="store_true", help="only installable on your account")
    parser.add_argument("--port", type=int, default=3456, help="local port for the redirect")
    args = parser.parse_args()

    state = secrets.token_urlsafe(16)
    redirect_url = f"http://127.0.0.1:{args.port}/callback"
    manifest = build_manifest(args, redirect_url)
    if args.org:
        target = f"https://github.com/organizations/{args.org}/settings/apps/new"
    else:
        target = "https://github.com/settings/apps/new"

    result: dict[str, Any] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/":
                form = (
                    f"<form id=f method=post action='{target}?state={state}'>"
                    "<input type=hidden name=manifest "
                    f"value='{html.escape(json.dumps(manifest), quote=True)}'>"
                    "<p>Redirecting to GitHub...</p><button>Continue</button></form>"
                    "<script>document.getElementById('f').submit()</script>"
                )
                self._send(200, page("Creating the GitHub App", form))
            elif url.path == "/callback":
                self._callback(parse_qs(url.query))
            else:
                self._send(404, page("Not found", ""))

        def _callback(self, query: dict[str, list[str]]) -> None:
            code = query.get("code", [""])[0]
            if query.get("state", [""])[0] != state or not re.fullmatch(r"[\w-]+", code):
                self._send(400, page("Invalid request", "<p>State or code mismatch.</p>"))
                return
            try:
                app = convert(code)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode(errors="replace")
                self._send(
                    502, page("GitHub refused the conversion", f"<pre>{html.escape(detail)}</pre>")
                )
                result["error"] = detail
                return

            key_path = save_credentials(app)
            result.update(app=app, key_path=key_path)
            install = f"{app['html_url']}/installations/new"
            self._send(
                200,
                page(
                    f"{app['name']} is ready",
                    "<p>Credentials saved, you can close this tab.</p>"
                    f"<p>Next: <a href='{html.escape(install)}'>install the app</a> "
                    "on your repositories.</p>",
                ),
            )

        def _send(self, status: int, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    start = f"http://127.0.0.1:{args.port}/"
    print(f"Opening {start} (open it yourself if no browser shows up)")
    print("Confirm on GitHub, then come back here. Ctrl+C to cancel.")
    webbrowser.open(start)

    try:
        while not result:
            server.handle_request()
    except KeyboardInterrupt:
        print("\ncancelled")
        return 1
    finally:
        server.server_close()

    if "error" in result:
        print(f"GitHub refused the manifest conversion: {result['error']}", file=sys.stderr)
        return 1

    app = result["app"]
    print()
    print(f"Created {app['name']} (id {app['id']}): {app['html_url']}")
    print(f"Private key saved to {result['key_path'].name}")
    print("GITHUB_APP_ID and GITHUB_WEBHOOK_SECRET written to .env")
    print(f"Install it on your repositories: {app['html_url']}/installations/new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
