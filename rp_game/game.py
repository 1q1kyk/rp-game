from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import random
from typing import List, Optional


class ActionId(str, Enum):
    ATTACK = "attack"
    CHECK_HP = "check_hp"
    FLEE = "flee"


PlayerId = int  # 1 or 2


@dataclass(frozen=True)
class FighterArchetype:
    id: str
    name: str
    max_hp: int
    base_damage: int
    color: str
    crit_chance: float = 0.15
    flee_chance: float = 0.5


@dataclass
class Fighter:
    archetype: FighterArchetype
    hp: int
    fled: bool = False

    @property
    def name(self) -> str:
        return self.archetype.name

    @property
    def max_hp(self) -> int:
        return self.archetype.max_hp

    @property
    def color(self) -> str:
        return self.archetype.color

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def defeated(self) -> bool:
        return self.hp <= 0

    @property
    def hp_ratio(self) -> float:
        if self.max_hp <= 0:
            return 0.0
        return self.hp / self.max_hp


@dataclass(frozen=True)
class GameRules:
    damage_spread: int = 5
    crit_multiplier: float = 1.75
    min_damage: int = 1


@dataclass
class BattleState:
    fighters: dict[PlayerId, Fighter]
    active_player: PlayerId = 1
    is_over: bool = False
    winner: Optional[PlayerId] = None
    end_reason: str = ""


@dataclass(frozen=True)
class AttackIntent:
    attacker: PlayerId
    defender: PlayerId
    damage: int
    is_crit: bool


class GameEvent:
    pass


@dataclass(frozen=True)
class MessageEvent(GameEvent):
    text: str
    color: str = "#ffffff"
    seconds: float = 1.2


@dataclass(frozen=True)
class AttackResolvedEvent(GameEvent):
    intent: AttackIntent
    did_kill: bool


@dataclass(frozen=True)
class FleeEvent(GameEvent):
    player: PlayerId
    success: bool


@dataclass(frozen=True)
class TurnChangedEvent(GameEvent):
    active_player: PlayerId


@dataclass(frozen=True)
class GameOverEvent(GameEvent):
    winner: Optional[PlayerId]
    reason: str


class BattleEngine:
    def __init__(
        self,
        state: BattleState,
        *,
        rules: Optional[GameRules] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.state = state
        self.rules = rules or GameRules()
        self.rng = rng or random.Random()

    def other_player(self, player: PlayerId) -> PlayerId:
        return 2 if player == 1 else 1

    def can_act(self, player: PlayerId) -> bool:
        return (not self.state.is_over) and (self.state.active_player == player)

    def begin_attack(self, player: PlayerId) -> Optional[AttackIntent]:
        if not self.can_act(player):
            return None
        attacker = self.state.fighters[player]
        defender_id = self.other_player(player)
        defender = self.state.fighters[defender_id]
        if not attacker.alive or not defender.alive:
            return None

        spread = abs(self.rules.damage_spread)
        raw = self.rng.randint(attacker.archetype.base_damage - spread, attacker.archetype.base_damage + spread)
        raw = max(self.rules.min_damage, raw)
        is_crit = self.rng.random() < max(0.0, min(1.0, attacker.archetype.crit_chance))
        dmg = int(round(raw * (self.rules.crit_multiplier if is_crit else 1.0)))
        dmg = max(self.rules.min_damage, dmg)
        return AttackIntent(attacker=player, defender=defender_id, damage=dmg, is_crit=is_crit)

    def resolve_attack(self, intent: AttackIntent) -> List[GameEvent]:
        if self.state.is_over:
            return []
        if intent.attacker != self.state.active_player:
            return []

        defender = self.state.fighters[intent.defender]
        if not defender.alive:
            return []

        defender.hp = max(0, defender.hp - intent.damage)
        did_kill = defender.hp == 0

        events: List[GameEvent] = [AttackResolvedEvent(intent=intent, did_kill=did_kill)]

        attacker = self.state.fighters[intent.attacker]
        if did_kill:
            self.state.is_over = True
            self.state.winner = intent.attacker
            self.state.end_reason = "defeat"
            events.append(MessageEvent(f"{defender.name} has been defeated!", color="#f0c040", seconds=2.2))
            events.append(GameOverEvent(winner=intent.attacker, reason="defeat"))
            return events

        self.state.active_player = self.other_player(intent.attacker)
        next_name = self.state.fighters[self.state.active_player].name
        events.append(TurnChangedEvent(active_player=self.state.active_player))
        events.append(MessageEvent(f"{next_name}'s turn", color="#cccccc", seconds=1.0))
        return events

    def check_hp(self, player: PlayerId) -> List[GameEvent]:
        if not self.can_act(player):
            return []
        fighter = self.state.fighters[player]
        pct = int(round(fighter.hp_ratio * 100))
        return [
            MessageEvent(
                f"{fighter.name}: {fighter.hp}/{fighter.max_hp} HP ({pct}%)",
                color=fighter.color,
                seconds=1.6,
            )
        ]

    def try_flee(self, player: PlayerId) -> List[GameEvent]:
        if not self.can_act(player):
            return []
        fighter = self.state.fighters[player]
        chance = max(0.0, min(1.0, fighter.archetype.flee_chance))
        success = self.rng.random() < chance
        events: List[GameEvent] = [FleeEvent(player=player, success=success)]

        if success:
            fighter.fled = True
            self.state.is_over = True
            self.state.winner = self.other_player(player)
            self.state.end_reason = "flee"
            events.append(MessageEvent(f"{fighter.name} escaped!", color="#a5d6a7", seconds=2.0))
            events.append(GameOverEvent(winner=self.state.winner, reason="flee"))
            return events

        # Fail: lose your turn.
        self.state.active_player = self.other_player(player)
        next_name = self.state.fighters[self.state.active_player].name
        events.append(MessageEvent(f"{fighter.name} failed to flee!", color="#ef9a9a", seconds=1.4))
        events.append(TurnChangedEvent(active_player=self.state.active_player))
        events.append(MessageEvent(f"{next_name}'s turn", color="#cccccc", seconds=1.0))
        return events


FIGHTERS: dict[str, FighterArchetype] = {
    "warrior": FighterArchetype(
        id="warrior",
        name="Warrior",
        max_hp=250,
        base_damage=20,
        color="#4fc3f7",
        crit_chance=0.18,
        flee_chance=0.5,
    ),
    "heavy": FighterArchetype(
        id="heavy",
        name="Heavy",
        max_hp=200,
        base_damage=28,
        color="#ef5350",
        crit_chance=0.12,
        flee_chance=0.45,
    ),
}


def create_default_battle(*, rng: Optional[random.Random] = None) -> BattleEngine:
    engine_rng = rng or random.Random()
    state = BattleState(
        fighters={
            1: Fighter(archetype=FIGHTERS["warrior"], hp=FIGHTERS["warrior"].max_hp),
            2: Fighter(archetype=FIGHTERS["heavy"], hp=FIGHTERS["heavy"].max_hp),
        },
        active_player=1,
    )
    return BattleEngine(state, rng=engine_rng)


def create_battle(
    *,
    player1: str,
    player2: str,
    rng: Optional[random.Random] = None,
) -> BattleEngine:
    """Create a battle from registered archetype ids in `FIGHTERS`."""
    if player1 not in FIGHTERS or player2 not in FIGHTERS:
        raise KeyError("Unknown fighter id. Add it to FIGHTERS first.")
    engine_rng = rng or random.Random()
    a1 = FIGHTERS[player1]
    a2 = FIGHTERS[player2]
    state = BattleState(
        fighters={
            1: Fighter(archetype=a1, hp=a1.max_hp),
            2: Fighter(archetype=a2, hp=a2.max_hp),
        },
        active_player=1,
    )
    return BattleEngine(state, rng=engine_rng)
