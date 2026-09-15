#!/usr/bin/python3
"""CGI entry point. Hosts that map / to a Python script execute this file."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_VENV_ROOT = ROOT / ".venv"
_VENV_PY = _VENV_ROOT / "bin" / "python3"
if _VENV_PY.is_file() and Path(sys.prefix).resolve() != _VENV_ROOT.resolve():
    os.execv(str(_VENV_PY), [str(_VENV_PY), str(ROOT / "index.py"), *sys.argv[1:]])

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

""" 
These two imports have to come after sys.path.insert(...) 
so the 'dvra' package can be found when the CGI host runs this file. 
The 'noqa: E402' comments suppress the "import not at top of file" warning.
"""
from dvra.app import handle_request  # noqa: E402
from dvra.http import write_cgi  # noqa: E402


def main() -> None:
    write_cgi(handle_request())


if __name__ == "__main__":
    main()
