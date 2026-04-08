from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time
import tkinter as tk
from typing import Dict, List, Optional

from .config import Controls, DEFAULT_CONTROLS, controls_hint_text
from .effects import Particle, Projectile, make_damage_burst, projectile_trail_particle
from .game import (
    ActionId,
    AttackResolvedEvent,
    BattleEngine,
    FleeEvent,
    GameOverEvent,
    MessageEvent,
    TurnChangedEvent,
    create_default_battle,
)
from .util import Vec2, clamp, ease_in_out_sine, hp_color, lerp_color


W, H = 960, 580
TARGET_FPS = 60
FRAME_DELAY_MS = max(1, int(1000 / TARGET_FPS))


@dataclass
class QueuedMessage:
    text: str
    color: str
    seconds: float
    time_left: float

    @staticmethod
    def create(text: str, color: str, seconds: float) -> "QueuedMessage":
        s = max(0.2, float(seconds))
        return QueuedMessage(text=text, color=color, seconds=s, time_left=s)


@dataclass
class HealthBarAnim:
    display_hp: float
    chip_hp: float
    last_target_hp: float
    chip_delay: float = 0.0

    def on_damage(self) -> None:
        self.chip_delay = max(self.chip_delay, 0.14)

    def update(self, dt: float, target_hp: int) -> None:
        target = float(max(0, target_hp))
        if target < self.last_target_hp:
            self.on_damage()
        self.last_target_hp = target

        # Fast smoothing for the main fill.
        self.display_hp = _exp_smooth(self.display_hp, target, smoothing=18.0, dt=dt)
        self.display_hp = max(0.0, self.display_hp)

        if self.chip_delay > 0.0:
            self.chip_delay = max(0.0, self.chip_delay - dt)
        else:
            # Slow smoothing for the "chip" (damage lag) effect.
            if self.chip_hp > self.display_hp:
                self.chip_hp = _exp_smooth(self.chip_hp, self.display_hp, smoothing=5.0, dt=dt)
            else:
                self.chip_hp = self.display_hp
        self.chip_hp = max(0.0, self.chip_hp)


@dataclass
class FighterAnim:
    idle_phase: float
    hit_flash_left: float = 0.0
    hit_flash_total: float = 0.14
    recoil_left: float = 0.0
    recoil_total: float = 0.18
    attack_bump_left: float = 0.0
    attack_bump_total: float = 0.18
    turn_pulse_left: float = 0.0
    turn_pulse_total: float = 0.45
    fail_pulse_left: float = 0.0
    fail_pulse_total: float = 0.35

    def start_hit_flash(self, seconds: float) -> None:
        s = max(0.01, float(seconds))
        self.hit_flash_left = s
        self.hit_flash_total = s

    def start_recoil(self, seconds: float) -> None:
        s = max(0.01, float(seconds))
        self.recoil_left = s
        self.recoil_total = s

    def start_attack_bump(self, seconds: float) -> None:
        s = max(0.01, float(seconds))
        self.attack_bump_left = s
        self.attack_bump_total = s

    def start_turn_pulse(self, seconds: float) -> None:
        s = max(0.01, float(seconds))
        self.turn_pulse_left = s
        self.turn_pulse_total = s

    def start_fail_pulse(self, seconds: float) -> None:
        s = max(0.01, float(seconds))
        self.fail_pulse_left = s
        self.fail_pulse_total = s

    def update(self, dt: float) -> None:
        self.hit_flash_left = max(0.0, self.hit_flash_left - dt)
        self.recoil_left = max(0.0, self.recoil_left - dt)
        self.attack_bump_left = max(0.0, self.attack_bump_left - dt)
        self.turn_pulse_left = max(0.0, self.turn_pulse_left - dt)
        self.fail_pulse_left = max(0.0, self.fail_pulse_left - dt)


def _exp_smooth(current: float, target: float, *, smoothing: float, dt: float) -> float:
    if smoothing <= 0.0:
        return target
    # Stable exponential smoothing factor.
    k = 1.0 - math.exp(-smoothing * dt)
    return current + (target - current) * k


class TkRpgApp:
    P1_X, P2_X = 200, 760
    SPRITE_Y = 320

    def __init__(
        self,
        root: tk.Tk,
        *,
        engine: Optional[BattleEngine] = None,
        controls: Controls = DEFAULT_CONTROLS,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.root = root
        self.rng = rng or random.Random()
        self.engine = engine or create_default_battle(rng=self.rng)
        self.controls = controls

        root.title("⚔  Two-Player RPG")
        root.resizable(False, False)
        root.configure(bg="#0a0a0f")

        self.canvas = tk.Canvas(root, width=W, height=H, bg="#0a0a0f", highlightthickness=0)
        self.canvas.pack()

        self._build_overlay_labels()
        self._draw_static_background()

        self.particles: List[Particle] = []
        self.projectiles: List[Projectile] = []
        self._trail_cooldown = 0.0

        self._message_queue: List[QueuedMessage] = []
        self._active_message: Optional[QueuedMessage] = None

        self._time = 0.0
        self._last_time = time.perf_counter()

        self._post_action_cooldown = 0.0
        self._shake_time = 0.0
        self._shake_strength = 0.0

        self._end_overlay_time = -1.0
        self._end_overlay_text = ""

        # Per-fighter animation state
        self._bars: Dict[int, HealthBarAnim] = {}
        self._anims: Dict[int, FighterAnim] = {}
        for pid, fighter in self.engine.state.fighters.items():
            self._bars[pid] = HealthBarAnim(
                display_hp=float(fighter.hp),
                chip_hp=float(fighter.hp),
                last_target_hp=float(fighter.hp),
            )
            self._anims[pid] = FighterAnim(idle_phase=self.rng.random() * math.tau)

        self.root.bind("<KeyPress>", self._on_key)

        self.queue_message("BATTLE START", color="#f0c040", seconds=1.8)
        self._anims[self.engine.state.active_player].start_turn_pulse(0.5)
        self._loop()

    # --- UI / Input ---------------------------------------------------------

    def _build_overlay_labels(self) -> None:
        hint_style = dict(bg="#0a0a0f", fg="#555577", font=("Courier", 10))
        p1_text, p2_text = controls_hint_text(self.controls)
        self._lbl_p1 = tk.Label(self.root, text=p1_text, **hint_style)
        self._lbl_p1.place(x=10, y=H - 22)
        self._lbl_p2 = tk.Label(self.root, text=p2_text, **hint_style)
        self._lbl_p2.place(x=W - 260, y=H - 22)

    def _input_blocked(self) -> bool:
        return self.engine.state.is_over or bool(self.projectiles) or (self._post_action_cooldown > 0.0)

    def _on_key(self, event: tk.Event) -> None:
        if self._input_blocked():
            return
        k = str(getattr(event, "keysym", "")).lower()
        active = self.engine.state.active_player
        bindings = self.controls.player1 if active == 1 else self.controls.player2
        action = bindings.action_for_key(k)
        if action is None:
            return
        if action == ActionId.ATTACK:
            self._start_attack(active)
        elif action == ActionId.CHECK_HP:
            self._handle_events(self.engine.check_hp(active))
        elif action == ActionId.FLEE:
            self._handle_events(self.engine.try_flee(active))
            self._post_action_cooldown = 0.12

    # --- Actions ------------------------------------------------------------

    def _fighter_pos(self, pid: int) -> Vec2:
        return Vec2(self.P1_X, self.SPRITE_Y) if pid == 1 else Vec2(self.P2_X, self.SPRITE_Y)

    def _start_attack(self, attacker: int) -> None:
        intent = self.engine.begin_attack(attacker)
        if intent is None:
            return

        self._anims[attacker].start_attack_bump(0.18)

        start = Vec2(self._fighter_pos(intent.attacker).x, self.SPRITE_Y - 20)
        end = Vec2(self._fighter_pos(intent.defender).x, self.SPRITE_Y - 20)
        color = self.engine.state.fighters[intent.attacker].color

        def on_hit() -> None:
            events = self.engine.resolve_attack(intent)
            self._handle_events(events)
            self._post_action_cooldown = 0.10

        self.projectiles.append(Projectile(start=start, end=end, color=color, on_hit=on_hit))

    # --- Events / Feedback --------------------------------------------------

    def queue_message(self, text: str, *, color: str = "#ffffff", seconds: float = 1.2) -> None:
        self._message_queue.append(QueuedMessage.create(text, color, seconds))
        if self._active_message is None:
            self._active_message = self._message_queue.pop(0)

    def _handle_events(self, events) -> None:
        for e in events:
            if isinstance(e, MessageEvent):
                self.queue_message(e.text, color=e.color, seconds=e.seconds)
            elif isinstance(e, TurnChangedEvent):
                self._anims[e.active_player].start_turn_pulse(0.45)
            elif isinstance(e, AttackResolvedEvent):
                self._on_attack_resolved(e)
            elif isinstance(e, FleeEvent):
                self._on_flee(e)
            elif isinstance(e, GameOverEvent):
                # Delay the overlay slightly so the final hit feels impactful.
                self._end_overlay_time = 2.2 if e.reason == "defeat" else 1.8
                winner = self.engine.state.fighters.get(e.winner).name if e.winner else "Nobody"
                if e.reason == "flee":
                    fled_name = next((f.name for f in self.engine.state.fighters.values() if f.fled), "Someone")
                    self._end_overlay_text = f"{fled_name} FLED!"
                    self.queue_message(f"{winner} wins!", color="#f0c040", seconds=2.0)
                else:
                    self._end_overlay_text = f"{winner} WINS!"

    def _on_attack_resolved(self, e: AttackResolvedEvent) -> None:
        intent = e.intent
        defender_pos = Vec2(self._fighter_pos(intent.defender).x, self.SPRITE_Y - 60)
        attacker_color = self.engine.state.fighters[intent.attacker].color

        # Impact feedback
        self._anims[intent.defender].start_hit_flash(0.18 if intent.is_crit else 0.14)
        self._anims[intent.defender].start_recoil(0.22 if intent.is_crit else 0.18)

        self._shake_time = 0.18 if intent.is_crit else 0.12
        self._shake_strength = max(self._shake_strength, 10.0 if intent.is_crit else 6.0)

        # Health bar chip effect
        self._bars[intent.defender].on_damage()

        # Particles
        self.particles.extend(
            make_damage_burst(
                rng=self.rng,
                center=defender_pos,
                color=attacker_color,
                damage=intent.damage,
                is_crit=intent.is_crit,
            )
        )

        if intent.is_crit:
            self.queue_message("CRITICAL HIT!", color="#ffd54f", seconds=0.8)

    def _on_flee(self, e: FleeEvent) -> None:
        pid = e.player
        pos = Vec2(self._fighter_pos(pid).x, self.SPRITE_Y - 40)
        if e.success:
            self._shake_time = max(self._shake_time, 0.12)
            self._shake_strength = max(self._shake_strength, 5.0)
            for _ in range(14):
                ang = self.rng.random() * math.tau
                speed = self.rng.uniform(140.0, 260.0)
                vel = Vec2(math.cos(ang) * speed, math.sin(ang) * speed - 120.0)
                self.particles.append(
                    Particle(pos=pos, vel=vel, life=0.5, max_life=0.5, color="#a5d6a7", size=3.0, gravity=520.0)
                )
        else:
            self._anims[pid].start_fail_pulse(0.35)
            self._shake_time = max(self._shake_time, 0.14)
            self._shake_strength = max(self._shake_strength, 7.0)
            for _ in range(18):
                ang = self.rng.random() * math.tau
                speed = self.rng.uniform(160.0, 300.0)
                vel = Vec2(math.cos(ang) * speed, math.sin(ang) * speed - 80.0)
                self.particles.append(
                    Particle(pos=pos, vel=vel, life=0.55, max_life=0.55, color="#ef9a9a", size=3.0, gravity=520.0)
                )
            # Message comes from the engine; this is purely visual feedback.

    # --- Loop ---------------------------------------------------------------

    def _loop(self) -> None:
        now = time.perf_counter()
        dt = now - self._last_time
        self._last_time = now
        dt = clamp(dt, 0.0, 1.0 / 20.0)  # clamp big stalls

        self._time += dt
        self._update(dt)
        self._draw()
        self.root.after(FRAME_DELAY_MS, self._loop)

    def _update(self, dt: float) -> None:
        # Cooldowns
        self._post_action_cooldown = max(0.0, self._post_action_cooldown - dt)

        # Camera shake
        if self._shake_time > 0.0:
            self._shake_time = max(0.0, self._shake_time - dt)
            self._shake_strength = _exp_smooth(self._shake_strength, 0.0, smoothing=10.0, dt=dt)
        else:
            self._shake_strength = 0.0

        # Messages
        if self._active_message is not None:
            self._active_message.time_left = max(0.0, self._active_message.time_left - dt)
            if self._active_message.time_left <= 0.0:
                self._active_message = self._message_queue.pop(0) if self._message_queue else None

        # End overlay countdown
        if self._end_overlay_time >= 0.0:
            self._end_overlay_time -= dt

        # Bars + per-fighter anim
        for pid, fighter in self.engine.state.fighters.items():
            self._bars[pid].update(dt, fighter.hp)
            self._anims[pid].update(dt)

        # Projectiles
        for proj in self.projectiles:
            proj.update(dt)
            # Trail particles
            if not proj.done:
                self._trail_cooldown -= dt
                if self._trail_cooldown <= 0.0:
                    self._trail_cooldown = 0.02
                    self.particles.append(
                        projectile_trail_particle(rng=self.rng, pos=proj.position(), color=proj.color)
                    )
        self.projectiles = [p for p in self.projectiles if not p.done]

        # Particles
        for p in self.particles:
            p.update(dt)
        # Cap to keep frame time stable even during spam
        self.particles = [p for p in self.particles if p.alive][-320:]

    # --- Rendering ----------------------------------------------------------

    def _camera_offset(self) -> Vec2:
        if self._shake_strength <= 0.01:
            return Vec2(0.0, 0.0)
        return Vec2(
            self.rng.uniform(-1.0, 1.0) * self._shake_strength,
            self.rng.uniform(-1.0, 1.0) * self._shake_strength,
        )

    def _draw_static_background(self) -> None:
        c = self.canvas
        c.delete("static")

        # Gradient-ish dark background via stacked rectangles.
        band_h = 58
        for i, y in enumerate(range(0, H, band_h)):
            shade = max(0, 12 - i)
            col = f"#{shade:02x}{shade:02x}{(shade + 6):02x}"
            c.create_rectangle(0, y, W, y + band_h, fill=col, outline="", tags="static")

        # Stars.
        star_rng = random.Random(42)
        for _ in range(90):
            sx = star_rng.randint(0, W)
            sy = star_rng.randint(0, 130)
            r = star_rng.choice([1, 1, 1, 2])
            br = star_rng.randint(70, 170)
            col = f"#{br:02x}{br:02x}{br:02x}"
            c.create_oval(sx - r, sy - r, sx + r, sy + r, fill=col, outline="", tags="static")

        # Arena / ground.
        c.create_line(0, 420, W, 420, fill="#1e1e2e", width=2, tags="static")
        c.create_rectangle(50, 420, W - 50, 430, fill="#16213e", outline="#2a2a5a", tags="static")
        c.create_rectangle(50, 430, W - 50, H - 40, fill="#0d1117", outline="", tags="static")

    def _draw(self) -> None:
        c = self.canvas
        c.delete("dynamic")

        cam = self._camera_offset()

        self._draw_turn_glow(c, cam)
        self._draw_fighters(c, cam)
        self._draw_health_bars(c, cam)
        self._draw_projectiles(c, cam)
        self._draw_particles(c, cam)
        self._draw_message(c)
        self._draw_end_overlay(c)

    def _draw_turn_glow(self, c: tk.Canvas, cam: Vec2) -> None:
        if self.engine.state.is_over:
            return
        active = self.engine.state.active_player
        base = self._fighter_pos(active)
        pulse = 0.5 + 0.5 * math.sin(self._time * 5.0)
        col = lerp_color("#f0c040", "#885500", pulse)
        r = 46 + 6 * pulse
        c.create_oval(
            base.x - r + cam.x,
            base.y + 62 - r / 3 + cam.y,
            base.x + r + cam.x,
            base.y + 62 + r / 3 + cam.y,
            outline=col,
            width=2,
            tags="dynamic",
        )

    def _fighter_offsets(self, pid: int) -> Vec2:
        anim = self._anims[pid]
        facing = 1.0 if pid == 1 else -1.0

        idle = math.sin(self._time * 2.1 + anim.idle_phase) * 2.0

        ax = 0.0
        ay = 0.0
        if anim.attack_bump_left > 0.0:
            t = 1.0 - anim.attack_bump_left / max(0.001, anim.attack_bump_total)
            bump = math.sin(math.pi * clamp(t, 0.0, 1.0))
            ax += facing * 10.0 * bump
            ay -= 4.0 * bump

        rx = 0.0
        if anim.recoil_left > 0.0:
            away = -1.0 if pid == 1 else 1.0
            t = 1.0 - anim.recoil_left / max(0.001, anim.recoil_total)
            rx += away * 12.0 * ease_in_out_sine(clamp(t, 0.0, 1.0))

        return Vec2(ax + rx, idle + ay)

    def _fighter_color(self, pid: int) -> str:
        fighter = self.engine.state.fighters[pid]
        anim = self._anims[pid]

        if not fighter.alive:
            return "#555555"
        if anim.hit_flash_left > 0.0:
            # Blink to a warm white on impact.
            pulse = 0.5 + 0.5 * math.sin(anim.hit_flash_left * 55.0)
            return lerp_color(fighter.color, "#ffffff", 0.55 + 0.35 * pulse)
        return fighter.color

    def _draw_fighters(self, c: tk.Canvas, cam: Vec2) -> None:
        self._draw_fighter(c, pid=1, facing="right", cam=cam)
        self._draw_fighter(c, pid=2, facing="left", cam=cam)

    def _draw_fighter(self, c: tk.Canvas, *, pid: int, facing: str, cam: Vec2) -> None:
        fighter = self.engine.state.fighters[pid]
        base = self._fighter_pos(pid)
        off = self._fighter_offsets(pid)
        cx = base.x + off.x + cam.x
        cy = base.y + off.y + cam.y

        col = self._fighter_color(pid)

        # Shadow
        c.create_oval(cx - 38, cy + 65, cx + 38, cy + 80, fill="#050510", outline="", tags="dynamic")

        if not fighter.alive:
            c.create_oval(cx - 50, cy + 40, cx + 50, cy + 70, fill=col, outline="", tags="dynamic")
            c.create_text(cx, cy + 22, text="X", font=("Courier", 28, "bold"), fill="#888899", tags="dynamic")
            return

        # Failed flee pulse (a red ring)
        anim = self._anims[pid]
        if anim.fail_pulse_left > 0.0:
            t = 1.0 - anim.fail_pulse_left / max(0.001, anim.fail_pulse_total)
            r = 62 + 18 * t
            a = 1.0 - t
            ring_col = lerp_color("#ef9a9a", "#000000", 1.0 - a)
            c.create_oval(cx - r, cy - r / 3, cx + r, cy + r / 3, outline=ring_col, width=2, tags="dynamic")

        # Legs
        lx = -12 if facing == "right" else 12
        c.create_line(cx + lx, cy + 40, cx - 20, cy + 70, fill=col, width=7, capstyle=tk.ROUND, tags="dynamic")
        c.create_line(cx - lx, cy + 40, cx + 20, cy + 70, fill=col, width=7, capstyle=tk.ROUND, tags="dynamic")

        # Body
        c.create_rectangle(cx - 22, cy - 20, cx + 22, cy + 42, fill=col, outline="", tags="dynamic")

        # Weapon arm
        wx = 30 if facing == "right" else -30
        c.create_line(cx, cy, cx + wx, cy - 20, fill=col, width=8, capstyle=tk.ROUND, tags="dynamic")
        c.create_oval(cx + wx - 6, cy - 26, cx + wx + 6, cy - 14, fill="#f0c040", outline="", tags="dynamic")

        # Shield arm
        sx = -26 if facing == "right" else 26
        c.create_line(cx, cy, cx + sx, cy + 8, fill=col, width=8, capstyle=tk.ROUND, tags="dynamic")
        c.create_rectangle(
            cx + sx - 8,
            cy,
            cx + sx + 8,
            cy + 28,
            fill="#37474f",
            outline="#607d8b",
            width=2,
            tags="dynamic",
        )

        # Head + visor
        c.create_oval(cx - 20, cy - 62, cx + 20, cy - 22, fill=col, outline="", tags="dynamic")
        vy = cy - 48
        c.create_rectangle(cx - 16, vy - 4, cx + 16, vy + 4, fill="#263238", outline="", tags="dynamic")

        # Name tag
        c.create_text(cx, cy - 76, text=fighter.name, font=("Courier", 11, "bold"), fill=col, tags="dynamic")

        # Turn pulse sparkle near the head
        if anim.turn_pulse_left > 0.0 and not self.engine.state.is_over:
            t = 1.0 - anim.turn_pulse_left / max(0.001, anim.turn_pulse_total)
            r = 8 + 22 * t
            a = 1.0 - t
            glow = lerp_color("#f0c040", "#000000", 1.0 - a)
            c.create_oval(cx - r, cy - 88 - r, cx + r, cy - 88 + r, outline=glow, width=2, tags="dynamic")

    def _draw_health_bars(self, c: tk.Canvas, cam: Vec2) -> None:
        self._draw_health_bar(c, pid=1, x=self.P1_X - 80, y=40)
        self._draw_health_bar(c, pid=2, x=self.P2_X - 80, y=40)

    def _draw_health_bar(self, c: tk.Canvas, *, pid: int, x: int, y: int) -> None:
        fighter = self.engine.state.fighters[pid]
        anim = self._bars[pid]

        bw, bh = 160, 20
        max_hp = max(1, fighter.max_hp)
        ratio = clamp(anim.display_hp / max_hp, 0.0, 1.0)
        chip_ratio = clamp(anim.chip_hp / max_hp, 0.0, 1.0)

        # Background frame
        c.create_rectangle(x, y, x + bw, y + bh, fill="#1a1a2e", outline="#2a2a4a", width=1, tags="dynamic")

        # Chip (damage lag) behind the main bar
        if chip_ratio > ratio + 0.005:
            cx1 = x + 1 + int((bw - 2) * ratio)
            cx2 = x + 1 + int((bw - 2) * chip_ratio)
            c.create_rectangle(cx1, y + 1, cx2, y + bh - 1, fill="#e57373", outline="", tags="dynamic")

        # Main fill
        if ratio > 0.0:
            bar_col = hp_color(ratio)
            c.create_rectangle(
                x + 1,
                y + 1,
                x + 1 + int((bw - 2) * ratio),
                y + bh - 1,
                fill=bar_col,
                outline="",
                tags="dynamic",
            )

        # Turn highlight on active player's bar
        if (not self.engine.state.is_over) and (self.engine.state.active_player == pid):
            pulse = 0.5 + 0.5 * math.sin(self._time * 6.0)
            col = lerp_color("#f0c040", "#885500", pulse)
            c.create_rectangle(x - 2, y - 2, x + bw + 2, y + bh + 2, outline=col, width=2, tags="dynamic")

        # Text
        c.create_text(
            x + bw // 2,
            y + bh // 2,
            text=f"{fighter.name}  {fighter.hp}/{fighter.max_hp}",
            font=("Courier", 9, "bold"),
            fill="#e0e0e0",
            tags="dynamic",
        )

    def _draw_projectiles(self, c: tk.Canvas, cam: Vec2) -> None:
        for proj in self.projectiles:
            p = proj.position()
            x = p.x + cam.x
            y = p.y + cam.y
            r = 10
            c.create_oval(x - r, y - r, x + r, y + r, fill=proj.color, outline="#ffffff", width=1, tags="dynamic")
            for gr in (16, 22, 28):
                ring_col = lerp_color(proj.color, "#ffffff", 0.25)
                c.create_oval(
                    x - gr,
                    y - gr,
                    x + gr,
                    y + gr,
                    outline=ring_col,
                    width=1,
                    tags="dynamic",
                )

    def _draw_particles(self, c: tk.Canvas, cam: Vec2) -> None:
        for p in self.particles:
            a = p.alpha
            if p.text:
                col = lerp_color(p.color, "#000000", 1.0 - a)
                size = max(9, int(p.size * (0.7 + 0.3 * a)))
                c.create_text(p.pos.x + cam.x, p.pos.y + cam.y, text=p.text, font=("Courier", size, "bold"), fill=col, tags="dynamic")
            else:
                r = max(1, int(p.size * (0.6 + 0.4 * a)))
                col = lerp_color(p.color, "#000000", 1.0 - a)
                c.create_oval(
                    p.pos.x - r + cam.x,
                    p.pos.y - r + cam.y,
                    p.pos.x + r + cam.x,
                    p.pos.y + r + cam.y,
                    fill=col,
                    outline="",
                    tags="dynamic",
                )

    def _draw_message(self, c: tk.Canvas) -> None:
        if self._active_message is None:
            return
        m = self._active_message
        # Fade in/out a bit.
        fade = min(1.0, m.time_left / 0.25, (m.seconds - m.time_left) / 0.15 if m.seconds > 0.15 else 1.0)
        fade = clamp(fade, 0.0, 1.0)
        col = lerp_color(m.color, "#000000", 1.0 - fade)
        c.create_text(W // 2, 490, text=m.text, font=("Georgia", 18, "bold"), fill=col, tags="dynamic")

    def _draw_end_overlay(self, c: tk.Canvas) -> None:
        if not self.engine.state.is_over:
            return
        if self._end_overlay_time > 0.0:
            return
        c.create_rectangle(0, 0, W, H, fill="#000000", stipple="gray50", tags="dynamic")
        c.create_text(W // 2, H // 2 - 30, text=self._end_overlay_text or "GAME OVER", font=("Georgia", 42, "bold"), fill="#f0c040", tags="dynamic")
        c.create_text(
            W // 2,
            H // 2 + 36,
            text="Close the window to exit",
            font=("Courier", 16),
            fill="#888899",
            tags="dynamic",
        )


def run_tk(*, controls: Controls = DEFAULT_CONTROLS) -> None:
    root = tk.Tk()
    TkRpgApp(root, controls=controls)
    root.mainloop()
