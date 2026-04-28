from __future__ import annotations

from enum import Enum


class Pokemon(str, Enum):
    ALAKAZAM = "alakazam"
    BLASTOISE = "blastoise"
    BULBASAUR = "bulbasaur"
    PIKACHU = "pikachu"
    CHARMANDER = "charmander"
    CHARIZARD = "charizard"
    DRAGONITE = "dragonite"
    EEVEE = "eevee"
    GARCHOMP = "garchomp"
    GENGAR = "gengar"
    GRENINJA = "greninja"
    GYARADOS = "gyarados"
    JIGGLYPUFF = "jigglypuff"
    LUCARIO = "lucario"
    LUGIA = "lugia"
    MACHAMP = "machamp"
    MAGIKARP = "magikarp"
    MEW = "mew"
    MEWTWO = "mewtwo"
    PSYDUCK = "psyduck"
    RAYQUAZA = "rayquaza"
    SNORLAX = "snorlax"
    SQUIRTLE = "squirtle"
    SYLVEON = "sylveon"
    UMBREON = "umbreon"
    VENUSAUR = "venusaur"

    @property
    def aliases(self) -> tuple[str, ...]:
        return POKEMON_ALIASES[self]

    @property
    def display_name(self) -> str:
        return self.value.title()


POKEMON_ALIASES: dict[Pokemon, tuple[str, ...]] = {
    Pokemon.ALAKAZAM: ("alakazam",),
    Pokemon.BLASTOISE: ("blastoise",),
    Pokemon.BULBASAUR: ("bulbasaur",),
    Pokemon.PIKACHU: ("pikachu",),
    Pokemon.CHARMANDER: ("charmander",),
    Pokemon.CHARIZARD: ("charizard", "mega charizard"),
    Pokemon.DRAGONITE: ("dragonite",),
    Pokemon.EEVEE: ("eevee",),
    Pokemon.GARCHOMP: ("garchomp",),
    Pokemon.GENGAR: ("gengar",),
    Pokemon.GRENINJA: ("greninja",),
    Pokemon.GYARADOS: ("gyarados",),
    Pokemon.JIGGLYPUFF: ("jigglypuff",),
    Pokemon.LUCARIO: ("lucario",),
    Pokemon.LUGIA: ("lugia",),
    Pokemon.MACHAMP: ("machamp",),
    Pokemon.MAGIKARP: ("magikarp",),
    Pokemon.MEW: ("mew",),
    Pokemon.MEWTWO: ("mewtwo",),
    Pokemon.PSYDUCK: ("psyduck",),
    Pokemon.RAYQUAZA: ("rayquaza",),
    Pokemon.SNORLAX: ("snorlax",),
    Pokemon.SQUIRTLE: ("squirtle",),
    Pokemon.SYLVEON: ("sylveon",),
    Pokemon.UMBREON: ("umbreon",),
    Pokemon.VENUSAUR: ("venusaur",),
}
