from __future__ import annotations

from dataclasses import dataclass
import math
import random
from typing import Callable, List, Optional

from .util import Vec2, clamp, ease_out_cubic, lerp_color


@dataclass
class Particle:
    pos: Vec2
    vel: Vec2
    life: float
    max_life: float
    color: str
    text: str = ""
    size: float = 14.0
    gravity: float = 0.0
    drag: float = 0.88  # per 60fps-ish frame; applied as exponential decay

    def update(self, dt: float) -> None:
        self.life = max(0.0, self.life - dt)
        if self.life <= 0.0:
            return

        # Convert a "per-frame" drag into a dt-scaled factor.
        drag_factor = self.drag ** (dt * 60.0)
        self.vel = Vec2(self.vel.x * drag_factor, (self.vel.y + self.gravity * dt) * drag_factor)
        self.pos = Vec2(self.pos.x + self.vel.x * dt, self.pos.y + self.vel.y * dt)

    @property
    def alive(self) -> bool:
        return self.life > 0.0

    @property
    def alpha(self) -> float:
        if self.max_life <= 0:
            return 0.0
        return clamp(self.life / self.max_life, 0.0, 1.0)


@dataclass
class Projectile:
    start: Vec2
    end: Vec2
    color: str
    on_hit: Callable[[], None]
    duration: float = 0.34
    arc_height: float = 26.0
    t: float = 0.0
    done: bool = False

    def update(self, dt: float) -> None:
        if self.done:
            return
        self.t += dt / max(0.001, self.duration)
        if self.t >= 1.0:
            self.t = 1.0
            self.on_hit()
            self.done = True

    def position(self) -> Vec2:
        # Smooth travel + arc.
        u = ease_out_cubic(self.t)
        p = Vec2.lerp(self.start, self.end, u)
        arc = math.sin(math.pi * clamp(u, 0.0, 1.0)) * self.arc_height
        return Vec2(p.x, p.y - arc)


def make_damage_burst(
    *,
    rng: random.Random,
    center: Vec2,
    color: str,
    damage: int,
    is_crit: bool,
) -> List[Particle]:
    parts: List[Particle] = []

    # Sparks
    spark_count = 18 if is_crit else 12
    for _ in range(spark_count):
        ang = rng.random() * math.tau
        speed = rng.uniform(160.0, 320.0) * (1.25 if is_crit else 1.0)
        vel = Vec2(math.cos(ang) * speed, math.sin(ang) * speed - rng.uniform(60.0, 140.0))
        life = rng.uniform(0.28, 0.46)
        parts.append(
            Particle(
                pos=Vec2(center.x + rng.uniform(-10, 10), center.y + rng.uniform(-8, 8)),
                vel=vel,
                life=life,
                max_life=life,
                color=color,
                text="",
                size=rng.uniform(2.0, 4.0),
                gravity=520.0,
                drag=0.84,
            )
        )

    # Main damage number
    text_color = "#ffd54f" if is_crit else color
    text = f"-{damage}"
    parts.append(
        Particle(
            pos=Vec2(center.x, center.y - 8),
            vel=Vec2(rng.uniform(-10, 10), -220.0 if is_crit else -170.0),
            life=0.95 if is_crit else 0.8,
            max_life=0.95 if is_crit else 0.8,
            color=text_color,
            text=text,
            size=22.0 if is_crit else 18.0,
            gravity=260.0,
            drag=0.9,
        )
    )

    # Crit tag
    if is_crit:
        parts.append(
            Particle(
                pos=Vec2(center.x, center.y - 34),
                vel=Vec2(rng.uniform(-10, 10), -240.0),
                life=0.7,
                max_life=0.7,
                color="#ffd54f",
                text="CRIT!",
                size=16.0,
                gravity=240.0,
                drag=0.9,
            )
        )
    return parts


def projectile_trail_particle(
    *,
    rng: random.Random,
    pos: Vec2,
    color: str,
) -> Particle:
    # A small, quickly fading glow to make projectiles feel smoother.
    vel = Vec2(rng.uniform(-30, 30), rng.uniform(-20, 20))
    return Particle(
        pos=Vec2(pos.x + rng.uniform(-2.5, 2.5), pos.y + rng.uniform(-2.5, 2.5)),
        vel=vel,
        life=0.16,
        max_life=0.16,
        color=lerp_color(color, "#000000", 0.15),
        text="",
        size=rng.uniform(1.5, 2.5),
        gravity=0.0,
        drag=0.8,
    )
