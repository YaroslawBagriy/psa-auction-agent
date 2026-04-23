from __future__ import annotations

from enum import Enum


class Pokemon(str, Enum):
    PIKACHU = "pikachu"
    CHARIZARD = "charizard"
    GENGAR = "gengar"
    MEWTWO = "mewtwo"
    UMBREON = "umbreon"

    @property
    def aliases(self) -> tuple[str, ...]:
        return POKEMON_ALIASES[self]

    @property
    def display_name(self) -> str:
        return self.value.title()


POKEMON_ALIASES: dict[Pokemon, tuple[str, ...]] = {
    Pokemon.PIKACHU: ("pikachu",),
    Pokemon.CHARIZARD: ("charizard", "mega charizard"),
    Pokemon.GENGAR: ("gengar",),
    Pokemon.MEWTWO: ("mewtwo",),
    Pokemon.UMBREON: ("umbreon",),
}

