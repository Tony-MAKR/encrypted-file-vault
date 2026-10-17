#!/usr/bin/env python
"""Create a local .env file with a random Django secret key.

The generated file is ignored by Git. The secret is never printed, so it does
not end up in terminal history or logs.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXAMPLE_PATH = ROOT / ".env.example"
PLACEHOLDER = "replace-with-a-long-random-value"


def main() -> None:
    if ENV_PATH.exists():
        print(".env already exists; leaving it unchanged.")
        return

    if not EXAMPLE_PATH.exists():
        raise SystemExit("Cannot find .env.example; refusing to generate .env.")

    template = EXAMPLE_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit("Placeholder missing from .env.example; refusing to generate .env.")

    content = template.replace(PLACEHOLDER, secrets.token_urlsafe(64))
    ENV_PATH.write_text(content, encoding="utf-8")

    # Best effort on Windows; on POSIX this restricts the file to the owner.
    try:
        os.chmod(ENV_PATH, 0o600)
    except OSError:
        pass

    print("Created .env with a random secret (not displayed, not committed).")


if __name__ == "__main__":
    main()
