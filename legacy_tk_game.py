# Legacy reference copy of the original tkinter version.
"""
Two-Player Visual RPG — tkinter edition
Controls:
  Player 1 (left):   A = Attack  |  S = Check HP  |  D = Flee
  Player 2 (right):  ← = Attack  |  ↓ = Check HP  |  → = Flee
"""

import tkinter as tk
import random
import math

# ──────────────────────────────────────────────
# DATA LAYER — pure game logic, no UI
# ──────────────────────────────────────────────

class Fighter:
    """A single combatant.  All game logic lives here."""

    def __init__(self, name: str, hp: int, damage: int, color: str):
        self.name   = name
        self.max_hp = hp
        self.hp     = hp
        self.damage = damage
        self.color  = color          # hex color used by the renderer
        self.alive  = True
        self.fled   = False

    # ── actions ──────────────────────────────
    def attack(self, enemy: "Fighter") -> int:
        """Deal damage to enemy; return actual damage dealt."""
        dmg = random.randint(self.damage - 5, self.damage + 5)
        dmg = max(1, dmg)
        enemy.take_damage(dmg)
        return dmg

    def take_damage(self, amount: int) -> None:
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.alive = False

    def flee(self) -> bool:
        """50 % chance to escape successfully."""
        success = random.random() < 0.5
        if success:
            self.fled = True
        return success

    # ── convenience ──────────────────────────
    @property
    def hp_ratio(self) -> float:
        return self.hp / self.max_hp


# ──────────────────────────────────────────────
# VISUAL LAYER — tkinter rendering
# ──────────────────────────────────────────────

W, H = 960, 580          # canvas dimensions
FPS  = 60


class Particle:
    """A single damage-number or spark particle."""
    def __init__(self, x, y, text, color, vx=0, vy=-3, life=40):
        self.x, self.y = x, y
        self.text  = text
        self.color = color
        self.vx, self.vy = vx, vy
        self.life  = life
        self.max_life = life

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vy *= 0.92          # decelerate
        self.life -= 1

    @property
    def alive(self):
        return self.life > 0

    @property
    def alpha_ratio(self):
        return self.life / self.max_life


class Projectile:
    """A moving orb fired from attacker toward defender."""
    def __init__(self, x, y, tx, ty, color, on_hit):
        self.x, self.y   = float(x), float(y)
        self.color       = color
        self.on_hit      = on_hit      # callback when it arrives
        dx, dy = tx - x, ty - y
        dist = math.hypot(dx, dy) or 1
        speed = 14
        self.vx = dx / dist * speed
        self.vy = dy / dist * speed
        self.tx, self.ty = tx, ty
        self.done = False

    def update(self):
        self.x += self.vx
        self.y += self.vy
        # arrived?
        if math.hypot(self.tx - self.x, self.ty - self.y) < 16:
            self.on_hit()
            self.done = True


class RPGCanvas:
    """Main game window — owns the canvas and the game loop."""

    # ── layout constants ──────────────────────
    P1_X, P2_X = 200, 760       # sprite centre-x
    SPRITE_Y    = 320            # sprite centre-y

    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("⚔  Two-Player RPG")
        root.resizable(False, False)
        root.configure(bg="#0a0a0f")

        self.canvas = tk.Canvas(root, width=W, height=H,
                                bg="#0a0a0f", highlightthickness=0)
        self.canvas.pack()

        self._build_fighters()
        self._build_ui_overlay()

        self.particles:   list[Particle]   = []
        self.projectiles: list[Projectile] = []
        self.flash_timer  = 0          # frames left for screen flash
        self.flash_target = None       # which fighter was hit
        self.message      = ""         # centre status line
        self.msg_timer    = 0
        self.game_over    = False
        self.whose_turn   = 1          # 1 or 2 — whose action is pending

        self._bind_keys()
        self._show_message("⚔  BATTLE START  ⚔", color="#f0c040", duration=120)
        self._loop()

    # ── initialisation helpers ────────────────

    def _build_fighters(self):
        self.p1 = Fighter("Warrior", hp=250, damage=20, color="#4fc3f7")
        self.p2 = Fighter("Heavy",   hp=200, damage=28, color="#ef5350")

    def _build_ui_overlay(self):
        """Tkinter labels that sit over the canvas for keybind hints."""
        hint_style = dict(bg="#0a0a0f", fg="#555577",
                          font=("Courier", 10))
        tk.Label(self.root, text="P1 → A:Attack  S:HP  D:Flee",
                 **hint_style).place(x=10, y=H - 22)
        tk.Label(self.root, text="P2 → ←:Attack  ↓:HP  →:Flee",
                 **hint_style).place(x=W - 240, y=H - 22)

    def _bind_keys(self):
        self.root.bind("<KeyPress>", self._on_key)

    # ── game-logic callbacks ──────────────────

    def _on_key(self, event):
        if self.game_over:
            return
        # Block input while a projectile is flying
        if self.projectiles:
            return

        k = event.keysym.lower()

        if self.whose_turn == 1:
            if   k == "a": self._do_attack(self.p1, self.p2)
            elif k == "s": self._do_check(self.p1)
            elif k == "d": self._do_flee(self.p1)
        elif self.whose_turn == 2:
            if   k == "left":  self._do_attack(self.p2, self.p1)
            elif k == "down":  self._do_check(self.p2)
            elif k == "right": self._do_flee(self.p2)

    def _do_attack(self, attacker: Fighter, defender: Fighter):
        sx = self.P1_X if attacker is self.p1 else self.P2_X
        tx = self.P2_X if attacker is self.p1 else self.P1_X

        # Store dmg so the closure captures it properly
        def on_hit():
            dmg = attacker.attack(defender)
            self._spawn_damage_numbers(tx, self.SPRITE_Y - 60, dmg, attacker.color)
            self.flash_target = defender
            self.flash_timer  = 18
            self._end_turn(attacker, defender)

        proj = Projectile(sx, self.SPRITE_Y - 20,
                          tx, self.SPRITE_Y - 20,
                          attacker.color, on_hit)
        self.projectiles.append(proj)

    def _do_check(self, player: Fighter):
        pct = int(player.hp_ratio * 100)
        self._show_message(
            f"{player.name}: {player.hp}/{player.max_hp} HP  ({pct}%)",
            color=player.color, duration=110)
        # Check HP doesn't end the turn

    def _do_flee(self, player: Fighter):
        success = player.flee()
        if success:
            self._show_message(f"{player.name} escaped! 🏃", color="#a5d6a7", duration=160)
            self.game_over = True
            self._schedule_end(f"{player.name} fled the battle!")
        else:
            self._show_message(f"{player.name} failed to flee!", color="#ef9a9a", duration=110)
            self._end_turn_after_flee(player)

    def _end_turn(self, attacker: Fighter, defender: Fighter):
        if not defender.alive:
            self._show_message(f"{defender.name} has been defeated! 💀",
                               color="#f0c040", duration=200)
            self.game_over = True
            self._schedule_end(f"{attacker.name} WINS!")
            return
        # Switch turns
        self.whose_turn = 2 if attacker is self.p1 else 1
        name = self.p2.name if self.whose_turn == 2 else self.p1.name
        self._show_message(f"{name}'s turn", color="#cccccc", duration=90)

    def _end_turn_after_flee(self, player: Fighter):
        self.whose_turn = 2 if player is self.p1 else 1
        name = self.p2.name if self.whose_turn == 2 else self.p1.name
        self._show_message(f"{name}'s turn", color="#cccccc", duration=90)

    def _schedule_end(self, msg: str):
        self.root.after(2200, lambda: self._show_end_screen(msg))

    def _show_end_screen(self, msg: str):
        # Dim overlay
        self.canvas.create_rectangle(0, 0, W, H, fill="#000000", stipple="gray50",
                                     tags="end_overlay")
        self.canvas.create_text(W // 2, H // 2 - 30, text=msg,
                                font=("Georgia", 42, "bold"),
                                fill="#f0c040", tags="end_overlay")
        self.canvas.create_text(W // 2, H // 2 + 36,
                                text="Close the window to exit",
                                font=("Courier", 16), fill="#888899",
                                tags="end_overlay")

    # ── particle helpers ──────────────────────

    def _spawn_damage_numbers(self, x, y, dmg, color):
        for _ in range(6):
            vx = random.uniform(-2, 2)
            vy = random.uniform(-5, -2)
            p = Particle(x + random.randint(-20, 20),
                         y + random.randint(-10, 10),
                         "", color, vx=vx, vy=vy, life=30)
            self.particles.append(p)
        # Main number
        self.particles.append(
            Particle(x, y - 10, f"-{dmg}", color, vy=-3.5, life=55))

    # ── message helper ────────────────────────

    def _show_message(self, text: str, color="#ffffff", duration=90):
        self.message       = text
        self.msg_color     = color
        self.msg_timer     = duration

    # ── rendering ────────────────────────────

    def _loop(self):
        self._update()
        self._draw()
        self.root.after(1000 // FPS, self._loop)

    def _update(self):
        # Projectiles
        for proj in self.projectiles:
            proj.update()
        self.projectiles = [p for p in self.projectiles if not p.done]

        # Particles
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.alive]

        # Flash timer
        if self.flash_timer > 0:
            self.flash_timer -= 1

        # Message timer
        if self.msg_timer > 0:
            self.msg_timer -= 1

    def _draw(self):
        c = self.canvas
        c.delete("dynamic")          # clear all redrawn elements each frame

        self._draw_background(c)
        self._draw_arena(c)

        self._draw_fighter(c, self.p1, self.P1_X, self.SPRITE_Y,
                           facing="right", flash=(self.flash_target is self.p1))
        self._draw_fighter(c, self.p2, self.P2_X, self.SPRITE_Y,
                           facing="left",  flash=(self.flash_target is self.p2))

        self._draw_health_bar(c, self.p1, self.P1_X - 80, 40)
        self._draw_health_bar(c, self.p2, self.P2_X - 80, 40)

        self._draw_turn_indicator(c)
        self._draw_projectiles(c)
        self._draw_particles(c)
        self._draw_message(c)

    # ── draw sub-routines ─────────────────────

    def _draw_background(self, c):
        # Gradient-ish dark background via stacked rectangles
        for i, band in enumerate(range(0, H, 60)):
            shade = max(0, 10 - i)
            col = f"#{shade:02x}{shade:02x}{shade + 5:02x}"
            c.create_rectangle(0, band, W, band + 60,
                                fill=col, outline="", tags="dynamic")
        # Ground line
        c.create_line(0, 420, W, 420, fill="#1e1e2e", width=2, tags="dynamic")
        # Stars
        random.seed(42)
        for _ in range(80):
            sx = random.randint(0, W)
            sy = random.randint(0, 120)
            r  = random.choice([1, 1, 1, 2])
            br = random.randint(60, 160)
            col = f"#{br:02x}{br:02x}{br:02x}"
            c.create_oval(sx-r, sy-r, sx+r, sy+r,
                          fill=col, outline="", tags="dynamic")
        random.seed()   # restore randomness

    def _draw_arena(self, c):
        # Ground platform
        c.create_rectangle(50, 420, W - 50, 430,
                            fill="#16213e", outline="#2a2a5a", tags="dynamic")
        c.create_rectangle(50, 430, W - 50, H - 40,
                            fill="#0d1117", outline="", tags="dynamic")

    def _draw_fighter(self, c, fighter: Fighter, cx, cy,
                      facing="right", flash=False):
        col = fighter.color if fighter.alive else "#555555"
        if flash and self.flash_timer > 0:
            # Alternate between white and normal color for hit flash
            col = "#ffffff" if (self.flash_timer // 3) % 2 == 0 else col

        # Shadow
        c.create_oval(cx - 38, cy + 65, cx + 38, cy + 80,
                      fill="#050510", outline="", tags="dynamic")

        if not fighter.alive:
            # Draw fallen (rotated illusion via a wide flat oval)
            c.create_oval(cx - 50, cy + 40, cx + 50, cy + 70,
                          fill=col, outline="", tags="dynamic")
            c.create_text(cx, cy + 20, text="💀",
                          font=("Arial", 28), fill="#888", tags="dynamic")
            return

        # Legs
        lx = -12 if facing == "right" else 12
        c.create_line(cx + lx,   cy + 40, cx - 20, cy + 70,
                      fill=col, width=7, capstyle=tk.ROUND, tags="dynamic")
        c.create_line(cx - lx,   cy + 40, cx + 20, cy + 70,
                      fill=col, width=7, capstyle=tk.ROUND, tags="dynamic")

        # Body
        c.create_rectangle(cx - 22, cy - 20, cx + 22, cy + 42,
                            fill=col, outline="", tags="dynamic")

        # Weapon arm
        wx = 30 if facing == "right" else -30
        c.create_line(cx, cy,  cx + wx, cy - 20,
                      fill=col, width=8, capstyle=tk.ROUND, tags="dynamic")
        # Sword tip
        c.create_oval(cx + wx - 6, cy - 26, cx + wx + 6, cy - 14,
                      fill="#f0c040", outline="", tags="dynamic")

        # Shield arm
        sx = -26 if facing == "right" else 26
        c.create_line(cx, cy,  cx + sx, cy + 8,
                      fill=col, width=8, capstyle=tk.ROUND, tags="dynamic")
        c.create_rectangle(cx + sx - 8, cy, cx + sx + 8, cy + 28,
                            fill="#37474f", outline="#607d8b", width=2,
                            tags="dynamic")

        # Head
        c.create_oval(cx - 20, cy - 62, cx + 20, cy - 22,
                      fill=col, outline="", tags="dynamic")

        # Helmet visor
        vy = cy - 48
        c.create_rectangle(cx - 16, vy - 4, cx + 16, vy + 4,
                            fill="#263238", outline="", tags="dynamic")

        # Name tag
        c.create_text(cx, cy - 76, text=fighter.name,
                      font=("Courier", 11, "bold"),
                      fill=col, tags="dynamic")

    def _draw_health_bar(self, c, fighter: Fighter, x, y):
        bw, bh = 160, 20
        ratio = fighter.hp_ratio

        # Background
        c.create_rectangle(x, y, x + bw, y + bh,
                            fill="#1a1a2e", outline="#2a2a4a", width=1,
                            tags="dynamic")
        # Fill
        if ratio > 0:
            # Color: green → yellow → red
            if ratio > 0.6:
                bar_col = "#4caf50"
            elif ratio > 0.3:
                bar_col = "#ffc107"
            else:
                bar_col = "#f44336"
            c.create_rectangle(x + 1, y + 1,
                                x + 1 + int((bw - 2) * ratio), y + bh - 1,
                                fill=bar_col, outline="", tags="dynamic")

        # Text
        c.create_text(x + bw // 2, y + bh // 2,
                      text=f"{fighter.name}  {fighter.hp}/{fighter.max_hp}",
                      font=("Courier", 9, "bold"),
                      fill="#e0e0e0", tags="dynamic")

    def _draw_turn_indicator(self, c):
        if self.game_over:
            return
        active = self.p1 if self.whose_turn == 1 else self.p2
        cx = self.P1_X if self.whose_turn == 1 else self.P2_X
        # Pulsing arrow below feet
        pulse = 0.5 + 0.5 * math.sin(self.root.tk.call("clock", "milliseconds") / 200)
        alpha_col = _lerp_color("#f0c040", "#885500", pulse)
        c.create_text(cx, self.SPRITE_Y + 100,
                      text="▲ YOUR TURN",
                      font=("Courier", 11, "bold"),
                      fill=alpha_col, tags="dynamic")

    def _draw_projectiles(self, c):
        for proj in self.projectiles:
            r = 10
            c.create_oval(proj.x - r, proj.y - r,
                          proj.x + r, proj.y + r,
                          fill=proj.color, outline="#ffffff",
                          width=1, tags="dynamic")
            # Glow rings
            for gr in [16, 22]:
                c.create_oval(proj.x - gr, proj.y - gr,
                              proj.x + gr, proj.y + gr,
                              outline=proj.color, width=1, tags="dynamic")

    def _draw_particles(self, c):
        for p in self.particles:
            a = p.alpha_ratio
            if p.text:
                # Damage number — fake alpha via color interpolation
                col = _lerp_color(p.color, "#000000", 1 - a)
                size = max(9, int(18 * a))
                c.create_text(p.x, p.y, text=p.text,
                              font=("Courier", size, "bold"),
                              fill=col, tags="dynamic")
            else:
                # Spark
                r = max(1, int(4 * a))
                col = _lerp_color(p.color, "#000000", 1 - a)
                c.create_oval(p.x - r, p.y - r, p.x + r, p.y + r,
                              fill=col, outline="", tags="dynamic")

    def _draw_message(self, c):
        if self.msg_timer > 0:
            a = min(1.0, self.msg_timer / 30)  # fade in/out
            col = _lerp_color(
                getattr(self, "msg_color", "#ffffff"),
                "#000000", 1 - a)
            c.create_text(W // 2, 490,
                          text=self.message,
                          font=("Georgia", 18, "bold"),
                          fill=col, tags="dynamic")


# ──────────────────────────────────────────────
# UTILITY
# ──────────────────────────────────────────────

def _hex_to_rgb(hex_col: str):
    h = hex_col.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def _rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colors (t=0→c1, t=1→c2)."""
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    t = max(0.0, min(1.0, t))
    return _rgb_to_hex(r1 + (r2 - r1) * t,
                       g1 + (g2 - g1) * t,
                       b1 + (b2 - b1) * t)


# ──────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    RPGCanvas(root)
    root.mainloop()
