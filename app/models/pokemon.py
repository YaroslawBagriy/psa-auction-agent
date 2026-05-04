from __future__ import annotations

from enum import Enum


class Pokemon(str, Enum):
    ABSOL = "absol"
    AERODACTYL = "aerodactyl"
    ALAKAZAM = "alakazam"
    ARCEUS = "arceus"
    ARTICUNO = "articuno"
    BIDOOF = "bidoof"
    BLASTOISE = "blastoise"
    BLAZIKEN = "blaziken"
    BULBASAUR = "bulbasaur"
    CERULEDGE = "ceruledge"
    CHANSEY = "chansey"
    PIKACHU = "pikachu"
    CHARMANDER = "charmander"
    CHARIZARD = "charizard"
    CLEFAIRY = "clefairy"
    DARKRAI = "darkrai"
    DITTO = "ditto"
    DRAGONITE = "dragonite"
    DUGTRIO = "dugtrio"
    EEVEE = "eevee"
    ESPEON = "espeon"
    FLAREON = "flareon"
    GARCHOMP = "garchomp"
    GARDEVOIR = "gardevoir"
    GENGAR = "gengar"
    GRENINJA = "greninja"
    GYARADOS = "gyarados"
    HAUNTER = "haunter"
    HO_OH = "ho-oh"
    JIGGLYPUFF = "jigglypuff"
    JOLTEON = "jolteon"
    KIRLIA = "kirlia"
    LAPRAS = "lapras"
    LEAFEON = "leafeon"
    LIEPARD = "liepard"
    LUCARIO = "lucario"
    LUGIA = "lugia"
    LYCANROC = "lycanroc"
    MACHAMP = "machamp"
    MAGIKARP = "magikarp"
    METAGROSS = "metagross"
    MEW = "mew"
    MEWTWO = "mewtwo"
    MOLTRES = "moltres"
    ONIX = "onix"
    PALKIA = "palkia"
    PSYDUCK = "psyduck"
    RAICHU = "raichu"
    RAIKOU = "raikou"
    RAYQUAZA = "rayquaza"
    RAPIDASH = "rapidash"
    SCIZOR = "scizor"
    SKARMORY = "skarmory"
    SNORLAX = "snorlax"
    SQUIRTLE = "squirtle"
    SUICUNE = "suicune"
    SYLVEON = "sylveon"
    TYRANITAR = "tyranitar"
    UMBREON = "umbreon"
    VAPOREON = "vaporeon"
    VENUSAUR = "venusaur"
    ZAPDOS = "zapdos"
    ZEKROM = "zekrom"

    @property
    def aliases(self) -> tuple[str, ...]:
        return POKEMON_ALIASES[self]

    @property
    def display_name(self) -> str:
        return self.value.title()


POKEMON_ALIASES: dict[Pokemon, tuple[str, ...]] = {
    pokemon: (pokemon.value,) for pokemon in Pokemon
}
POKEMON_ALIASES.update(
    {
        Pokemon.CHARIZARD: ("charizard", "mega charizard", "mega charizard x", "mega charizard y"),
        Pokemon.GENGAR: ("gengar", "mega gengar"),
        Pokemon.RAYQUAZA: ("rayquaza", "m rayquaza", "mega rayquaza"),
        Pokemon.HO_OH: ("ho-oh", "ho oh"),
        Pokemon.PIKACHU: ("pikachu", "detective pikachu", "red's pikachu"),
        Pokemon.MEWTWO: ("mewtwo", "mewtwo gx"),
    }
)
