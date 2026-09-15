#!/usr/bin/env python3
"""CGI entry point. Hosts that map / to a Python script execute this file."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dvra.app import handle_request  # noqa: E402
from dvra.http import write_cgi  # noqa: E402


def main() -> None:
    write_cgi(handle_request())


if __name__ == "__main__":
    main()
