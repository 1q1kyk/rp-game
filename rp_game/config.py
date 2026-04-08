from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

from .game import ActionId


def _normalize_key(keysym: str) -> str:
    return keysym.strip().lower()


def _to_key_tuple(value: Any) -> Tuple[str, ...]:
    if isinstance(value, str):
        return (_normalize_key(value),)
    if isinstance(value, Iterable):
        out = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(_normalize_key(item))
        return tuple(out)
    return tuple()


@dataclass(frozen=True)
class PlayerBindings:
    attack: Tuple[str, ...]
    check_hp: Tuple[str, ...]
    flee: Tuple[str, ...]

    def action_for_key(self, keysym: str) -> Optional[ActionId]:
        k = _normalize_key(keysym)
        if k in self.attack:
            return ActionId.ATTACK
        if k in self.check_hp:
            return ActionId.CHECK_HP
        if k in self.flee:
            return ActionId.FLEE
        return None


@dataclass(frozen=True)
class Controls:
    player1: PlayerBindings
    player2: PlayerBindings


DEFAULT_CONTROLS = Controls(
    player1=PlayerBindings(attack=("a",), check_hp=("s",), flee=("d",)),
    player2=PlayerBindings(attack=("left",), check_hp=("down",), flee=("right",)),
)


def load_controls(path: Path) -> Controls:
    """Load optional JSON controls config; fall back to defaults on any error."""
    try:
        if not path.exists():
            return DEFAULT_CONTROLS
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return DEFAULT_CONTROLS
    except Exception:
        return DEFAULT_CONTROLS

    def read_player(d: Dict[str, Any]) -> PlayerBindings:
        return PlayerBindings(
            attack=_to_key_tuple(d.get("attack")),
            check_hp=_to_key_tuple(d.get("check_hp")),
            flee=_to_key_tuple(d.get("flee")),
        )

    try:
        p1 = read_player(data.get("player1", {}))
        p2 = read_player(data.get("player2", {}))
        # If any binding is missing, keep the default so the game stays playable.
        if not (p1.attack and p1.check_hp and p1.flee):
            p1 = DEFAULT_CONTROLS.player1
        if not (p2.attack and p2.check_hp and p2.flee):
            p2 = DEFAULT_CONTROLS.player2
        return Controls(player1=p1, player2=p2)
    except Exception:
        return DEFAULT_CONTROLS


_PRETTY_KEYS = {
    "left": "←",
    "right": "→",
    "down": "↓",
    "up": "↑",
    "space": "Space",
    "return": "Enter",
    "escape": "Esc",
}


def pretty_key(keysym: str) -> str:
    k = _normalize_key(keysym)
    if k in _PRETTY_KEYS:
        return _PRETTY_KEYS[k]
    if len(k) == 1:
        return k.upper()
    return k


def controls_hint_text(controls: Controls) -> Tuple[str, str]:
    p1 = controls.player1
    p2 = controls.player2
    p1_text = f"P1 → {pretty_key(p1.attack[0])}:Attack  {pretty_key(p1.check_hp[0])}:HP  {pretty_key(p1.flee[0])}:Flee"
    p2_text = f"P2 → {pretty_key(p2.attack[0])}:Attack  {pretty_key(p2.check_hp[0])}:HP  {pretty_key(p2.flee[0])}:Flee"
    return p1_text, p2_text

