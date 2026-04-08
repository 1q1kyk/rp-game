from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Tuple


def clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease_out_cubic(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def ease_in_out_sine(t: float) -> float:
    t = clamp(t, 0.0, 1.0)
    return -(math.cos(math.pi * t) - 1.0) / 2.0


@dataclass(frozen=True)
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.hypot(self.x, self.y)

    def normalized(self) -> "Vec2":
        length = self.length() or 1.0
        return Vec2(self.x / length, self.y / length)

    @staticmethod
    def lerp(a: "Vec2", b: "Vec2", t: float) -> "Vec2":
        return Vec2(lerp(a.x, b.x, t), lerp(a.y, b.y, t))


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Expected #rrggbb, got: {hex_color!r}")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_to_hex(rgb: Tuple[float, float, float]) -> str:
    r, g, b = rgb
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"


def lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two #rrggbb colors (t=0->c1, t=1->c2)."""
    r1, g1, b1 = hex_to_rgb(c1)
    r2, g2, b2 = hex_to_rgb(c2)
    t = clamp(t, 0.0, 1.0)
    return rgb_to_hex(
        (
            r1 + (r2 - r1) * t,
            g1 + (g2 - g1) * t,
            b1 + (b2 - b1) * t,
        )
    )


def hp_color(ratio: float) -> str:
    """Smooth health color: green -> yellow -> red."""
    ratio = clamp(ratio, 0.0, 1.0)
    green = "#4caf50"
    yellow = "#ffc107"
    red = "#f44336"
    if ratio >= 0.5:
        t = (1.0 - ratio) / 0.5
        return lerp_color(green, yellow, t)
    t = (0.5 - ratio) / 0.5
    return lerp_color(yellow, red, t)

