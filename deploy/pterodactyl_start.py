"""Pterodactyl start script: update GitPulse from GitHub, then run it.

Copy this file to the server root as `start.py` and set the egg's Python file to
`start.py`. On every start it downloads the latest code of the branch, replaces
`main.py`, `requirements.txt` and the `gitpulse/` package, installs the
requirements and runs the bot. `.env`, the private key and the database are
never touched.

Set GITPULSE_AUTO_UPDATE=0 in .env to skip the download and run what is there.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO = "saiyii/gitpulse"
ROOT = Path(__file__).resolve().parent
KEEP = ("main.py", "requirements.txt", "gitpulse/")


def read_env(name: str, default: str) -> str:
    # .env isn't loaded yet (python-dotenv may not even be installed), read it by hand
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == name:
                return value.strip() or default
    return os.getenv(name, default)


def resolve(ref: str) -> str:
    """Branch name -> commit sha. Branch tarballs can be cached for a few minutes."""
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/commits/{ref}",
        headers={"Accept": "application/vnd.github.sha", "User-Agent": "GitPulse-start"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.read().decode().strip()
    except OSError as exc:
        print(f"[start] could not resolve {ref} ({exc}), using the branch", file=sys.stderr)
        return f"refs/heads/{ref}"


def update(ref: str) -> None:
    target = resolve(ref)
    url = f"https://codeload.github.com/{REPO}/tar.gz/{target}"
    print(f"[start] downloading {REPO}@{ref} ({target[:7]})", file=sys.stderr, flush=True)
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = resp.read()

    with (
        tempfile.TemporaryDirectory(dir=ROOT) as tmp,
        tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar,
    ):
        members = []
        for member in tar.getmembers():
            # strip the "gitpulse-main/" prefix
            _, _, rel = member.name.partition("/")
            if rel and (rel in KEEP or rel.startswith(KEEP[2])):
                member.name = rel
                members.append(member)
        if not any(m.name == "main.py" for m in members):
            raise RuntimeError("archive doesn't look like GitPulse")

        if hasattr(tarfile, "data_filter"):
            tar.extractall(tmp, members=members, filter="data")
        else:
            tar.extractall(tmp, members=members)

        # replace the package as a whole so removed modules don't linger
        shutil.rmtree(ROOT / "gitpulse", ignore_errors=True)
        shutil.move(os.path.join(tmp, "gitpulse"), ROOT / "gitpulse")
        for name in ("main.py", "requirements.txt"):
            shutil.copyfile(os.path.join(tmp, name), ROOT / name)


def main() -> None:
    os.chdir(ROOT)
    if read_env("GITPULSE_AUTO_UPDATE", "1") != "0":
        try:
            update(read_env("GITPULSE_BRANCH", "main"))
        except Exception as exc:
            if not (ROOT / "main.py").exists():
                raise
            print(
                f"[start] update failed ({exc}), starting the current version",
                file=sys.stderr,
                flush=True,
            )

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-cache-dir", "-q", "-r", "requirements.txt"],
        check=True,
    )
    print("[start] starting GitPulse", file=sys.stderr, flush=True)
    os.execv(sys.executable, [sys.executable, "main.py"])


if __name__ == "__main__":
    main()
