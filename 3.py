"""
Two-Player Visual RPG — tkinter edition

Controls (defaults):
  Player 1 (left):   A = Attack  |  S = Check HP  |  D = Flee
  Player 2 (right):  ← = Attack  |  ↓ = Check HP  |  → = Flee

Optional:
  Create `controls.json` (see `controls.example.json`) to customize keybindings.
"""

from __future__ import annotations

from pathlib import Path

from rp_game.config import load_controls
from rp_game.tk_app import run_tk


def main() -> None:
    controls = load_controls(Path("controls.json"))
    run_tk(controls=controls)


if __name__ == "__main__":
    main()

