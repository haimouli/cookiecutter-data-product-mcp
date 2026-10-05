"""Lock dependencies after generation so image builds can use uv sync --frozen."""

from __future__ import annotations

import shutil
import subprocess
import sys


def main() -> None:
    """Run uv lock when uv is installed, without failing project generation."""
    if shutil.which("uv") is None:
        print("uv is not installed; skipping uv lock. Install uv, then run `uv lock`.", file=sys.stderr)
        return
    completed = subprocess.run(["uv", "lock"], check=False)
    if completed.returncode != 0:
        print("uv lock failed. Run it manually before `make docker-build`.", file=sys.stderr)


if __name__ == "__main__":
    main()
