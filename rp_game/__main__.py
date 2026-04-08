from __future__ import annotations

from pathlib import Path

from .config import load_controls
from .tk_app import run_tk


def main() -> None:
    controls = load_controls(Path("controls.json"))
    run_tk(controls=controls)


if __name__ == "__main__":
    main()

