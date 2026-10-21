"""Build the portable executable for the system this runs on (Windows, Linux or macOS).

    python scripts/build.py              lint, type-check, test, then build
    python scripts/build.py --fast       build only

Needs the dev tools:  pip install -e ".[dev]"
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fast", action="store_true", help="skip lint, type check and tests")
    a = ap.parse_args()
    py = sys.executable
    if not a.fast:
        run(py, "-m", "ruff", "check", "src", "tests", "tools")
        run(py, "-m", "mypy")
        run(py, "-m", "pytest", "-q")
    run(py, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "--workpath", "build",
        "packaging/aio_receiver.spec")
    print("\nBuilt:", *sorted(p.name for p in (ROOT / "dist").iterdir()), sep="\n  ")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(e.returncode)
