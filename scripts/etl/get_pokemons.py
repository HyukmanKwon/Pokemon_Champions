"""포챔스 사용 가능 포켓몬(pokemon_M_B)을 PokeAPI에서 받아,
pokemons 테이블용 03_pokemons.sql 을 생성한다.

can_mega / is_mega 는 API가 주는 값이 아니라 pokemon_M_B 안에서 계산한다.
`gengar-mega` 가 목록에 있으면 `gengar` 의 can_mega 가 TRUE 가 되는 식이다.
그래서 포챔스에서 못 쓰는 메가는 목록에서 빼는 것만으로 반영된다.
"""
import re

import requests

from pokemon_champions.db import connect

from . import paths
from . import schema
from . import translation
from .parse_utils import render, mogrify_rows

pokemon_M_B = [
    # ===== 1세대 (기본 29, 폼 26) =====
    "venusaur", "charizard", "blastoise", "beedrill", "pidgeot", "arbok",
    "pikachu", "raichu", "clefable", "ninetales", "vileplume", "arcanine",
    "alakazam", "machamp", "victreebel", "slowbro", "gengar", "kangaskhan",
    "starmie", "pinsir", "tauros", "gyarados", "ditto", "vaporeon",
    "jolteon", "flareon", "aerodactyl", "snorlax", "dragonite",
    # -- 1세대 폼 --
    "aerodactyl-mega", "alakazam-mega", "arcanine-hisui", "beedrill-mega", "blastoise-mega", "charizard-mega-x",
    "charizard-mega-y", "clefable-mega", "dragonite-mega", "gengar-mega", "gyarados-mega", "kangaskhan-mega",
    "ninetales-alola", "pidgeot-mega", "pinsir-mega", "raichu-alola", "raichu-mega-x", "raichu-mega-y",
    "slowbro-galar", "slowbro-mega", "starmie-mega", "tauros-paldea-aqua-breed", "tauros-paldea-blaze-breed", "tauros-paldea-combat-breed",
    "venusaur-mega", "victreebel-mega",
    # ===== 2세대 (기본 18, 폼 11) =====
    "meganium", "typhlosion", "feraligatr", "ariados", "ampharos", "azumarill",
    "politoed", "espeon", "umbreon", "slowking", "forretress", "steelix",
    "qwilfish", "scizor", "heracross", "skarmory", "houndoom", "tyranitar",
    # -- 2세대 폼 --
    "ampharos-mega", "feraligatr-mega", "heracross-mega", "houndoom-mega", "meganium-mega", "scizor-mega",
    "skarmory-mega", "slowking-galar", "steelix-mega", "typhlosion-hisui", "tyranitar-mega",
    # ===== 3세대 (기본 21, 폼 20) =====
    "sceptile", "blaziken", "swampert", "pelipper", "gardevoir", "sableye",
    "mawile", "aggron", "medicham", "manectric", "sharpedo", "camerupt",
    "torkoal", "altaria", "milotic", "castform", "banette", "chimecho",
    "absol", "glalie", "metagross",
    # -- 3세대 폼 --
    "absol-mega", "aggron-mega", "altaria-mega", "banette-mega", "blaziken-mega", "camerupt-mega",
    # 캐스퐁은 날씨에 따라 타입과 종족값이 통째로 바뀐다. 한 줄로 두면
    # 데미지 계산이 어느 모습인지 모른다.
    "castform-rainy", "castform-snowy", "castform-sunny",
    "chimecho-mega", "gardevoir-mega", "glalie-mega", "manectric-mega", "mawile-mega", "medicham-mega",
    "metagross-mega", "sableye-mega", "sceptile-mega", "sharpedo-mega", "swampert-mega",
    # ===== 4세대 (기본 24, 폼 12) =====
    "torterra", "infernape", "empoleon", "staraptor", "luxray", "roserade",
    "rampardos", "bastiodon", "lopunny", "spiritomb", "garchomp", "lucario",
    "hippowdon", "toxicroak", "abomasnow", "weavile", "rhyperior", "leafeon",
    "glaceon", "gliscor", "mamoswine", "gallade", "froslass", "rotom",
    # -- 4세대 폼 --
    "abomasnow-mega", "froslass-mega", "gallade-mega", "garchomp-mega", "lopunny-mega", "lucario-mega",
    "rotom-fan", "rotom-frost", "rotom-heat", "rotom-mow", "rotom-wash", "staraptor-mega",
    # ===== 5세대 (기본 29, 폼 11) =====
    # 배쓰나이(basculin-red-striped) 제외
    "serperior", "emboar", "samurott", "watchog", "liepard", "simisage",
    "simisear", "simipour", "musharna", "excadrill", "audino", "conkeldurr",
    "scolipede", "whimsicott", "krookodile", "scrafty", "cofagrigus",
    "garbodor", "zoroark", "reuniclus", "vanilluxe", "emolga", "eelektross",
    "chandelure", "beartic", "stunfisk", "golurk", "hydreigon", "volcarona",
    # -- 5세대 폼 --
    "audino-mega", "chandelure-mega", "eelektross-mega", "emboar-mega", "excadrill-mega", "golurk-mega",
    "samurott-hisui", "scolipede-mega", "scrafty-mega", "stunfisk-galar", "zoroark-hisui",
    # ===== 6세대 (기본 34, 폼 15) =====
    "chesnaught", "delphox", "greninja", "diggersby", "talonflame", "vivillon",
    # 플라베베·플라엣(일반) 제외. 남는 건 영원의 꽃 플라엣테와 그 메가뿐이다.
    "pyroar-male", "florges", "pangoro", "furfrou",
    "meowstic-male","meowstic-female", "aegislash-shield", "aromatisse", "slurpuff", "malamar", "barbaracle",
    "dragalge", "clawitzer", "heliolisk", "tyrantrum", "aurorus", "sylveon",
    "hawlucha", "dedenne", "goodra", "klefki", "trevenant", "gourgeist-average",
    "avalugg", "noivern", "floette-eternal", "meowstic-male-mega","meowstic-female-mega",
    # -- 6세대 폼 --
    # 킬가르도는 배틀 중 실드폼↔블레이드폼이 오간다. 종족값이 정반대라
    # 한쪽만 두면 계산이 반쯤 틀린다.
    "aegislash-blade",
    "avalugg-hisui", "barbaracle-mega", "chesnaught-mega", "delphox-mega", "dragalge-mega", "floette-mega",
    "goodra-hisui", "gourgeist-large", "gourgeist-small", "gourgeist-super",
    "greninja-mega", "hawlucha-mega", "malamar-mega",
    "pyroar-mega",
    # ===== 7세대 (기본 16, 폼 6) =====
    "decidueye", "incineroar", "primarina", "toucannon", "vikavolt", "crabominable",
    "toxapex", "mudsdale", "araquanid", "salazzle", "tsareena",
    "oranguru", "passimian", "mimikyu-disguised", "drampa", "kommo-o",
    # -- 7세대 폼 --
    "crabominable-mega", "decidueye-hisui", "drampa-mega", "lycanroc-midday", "lycanroc-dusk", "lycanroc-midnight",
    # ===== 8세대 (기본 17, 폼 3) =====
    # 다태우지네(centiskorch) · 에써르(indeedee-male) 제외
    "corviknight", "flapple", "appletun", "sandaconda", "polteageist",
    "hatterene", "grimmsnarl", "mr-rime", "alcremie", "falinks", "morpeko-full-belly",
    "dragapult", "wyrdeer", "kleavor", "basculegion-male", "sneasler", "overqwil",
    # -- 8세대 폼 --
    # 모르페코는 턴마다 배부른↔배고픈이 바뀌고, 그때 오파의 타입이 달라진다.
    "basculegion-female", "falinks-mega", "morpeko-hangry",
    # ===== 9세대 (기본 23, 폼 2) =====
    # 육파리(toedscruel) 제외
    "meowscarada", "skeledirge", "quaquaval", "maushold-family-of-four", "garganacl", "armarouge",
    "ceruledge", "bellibolt", "scovillain", "espathra", "tinkaton",
    "palafin-zero", "palafin-hero", "orthworm", "glimmora", "houndstone", "annihilape", "farigiraf",
    "kingambit", "gholdengo", "sinistcha", "archaludon", "hydrapple",
    # -- 9세대 폼 --
    "glimmora-mega", "scovillain-mega",
]

POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"

FILENAME = "03_pokemons.sql"
TABLE = "pokemons"
COLUMNS = ["id", "pokemon_id", "name", "ko_name", "type1", "type2",
           "ability1", "ability2", "ability3", "height", "weight",
           "h", "a", "b", "c", "d", "s", "can_mega", "is_mega"]
DDL = schema.POKEMONS
USES_API = True   # 생성 시 PokeAPI를 호출하는가

# charizard-mega-x -> ("charizard", "x") / gengar-mega -> ("gengar", None)
MEGA_RE = re.compile(r"^(.*)-mega(?:-([xy]))?$")

# 이름을 잘라서는 베이스를 못 찾는 예외. 여기 적힌 것이 우선한다.
#   pyroar-mega  -> 목록에 pyroar 가 아니라 pyroar-male 로 들어 있다
#   floette-mega -> 메가가 되는 건 일반 플라엣테가 아니라 영원의 꽃 쪽이다.
#                   일반 플라엣테를 목록에서 뺐으므로 여기서 이어줘야 한다.
# get_mega_evolutions.py 도 이 표를 그대로 쓴다 — 베이스 판정이 두 곳에서
# 갈리면 can_mega 는 켜졌는데 관계표에는 없는 상태가 된다.
MANUAL_BASE = {
    "pyroar-mega": "pyroar-male",
    "floette-mega": "floette-eternal",
}


def split_mega(name):
    """메가폼 이름을 (베이스, 변형) 으로 쪼갠다. 메가폼이 아니면 (None, None)."""
    m = MEGA_RE.match(name)
    if m is None:
        return None, None
    return m.group(1), m.group(2)


def base_of(name):
    """메가폼의 베이스 이름. 메가폼이 아니면 None."""
    if name in MANUAL_BASE:
        return MANUAL_BASE[name]
    return split_mega(name)[0]


def mega_bases(names):
    """목록 안에서 메가폼을 가진 베이스 이름의 집합."""
    return {b for b in map(base_of, names) if b is not None}

def fetch_pokemon(name):  #포켓몬 이름을 받아 url을 생성후, API를 받아옴
    url = f"{POKEAPI_BASE}/{name}"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200: #이름 못 찾음
        return None
    return resp.json()

def species_id(data):
    """폼 응답에서 원종(species) 번호를 뽑는다.

    .../pokemon-species/6/ 의 6 이다. 폼이 무엇이든 원종이 같으면 같은 값이
    나오므로, 10000번대로 흩어지는 id 대신 화면에 보여줄 도감 번호가 된다.
    """
    return int(data["species"]["url"].rstrip("/").rsplit("/", 1)[1])


def parse_pokemon(data, bases=()):        #필요한 정보를 parsing해서 반환
    stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}          # key : values
    types = {t["slot"]: t["type"]["name"] for t in data["types"]}
    abilities = {a["slot"]: a["ability"]["name"] for a in data["abilities"]}

    base_ko = translation.fetch_korean_name(data)          # 한국어 기본 이름
    ko_name = translation.build_korean_name(data, base_ko)

    return {
        "id": data["id"],
        # 원종 도감 번호. species URL 끝 숫자가 그것이라 API 를 더 부르지
        # 않는다 — .../pokemon-species/6/ 이면 메가리자몽X 도 6 이 된다.
        "pokemon_id": species_id(data),
        "name": data["name"],
        "ko_name": ko_name,
        "type1": types.get(1),
        "type2": types.get(2),
        "ability1": abilities.get(1),   #key가 1인 값을 가져온다.
        "ability2": abilities.get(2),
        "ability3": abilities.get(3),
        "height": data["height"] / 10,   # 17 → 1.7 (m)
        "weight": data["weight"] / 10,   # 905 → 90.5 (kg)
        "h": stats["hp"],
        "a": stats["attack"],
        "b": stats["defense"],
        "c": stats["special-attack"],
        "d": stats["special-defense"],
        "s": stats["speed"],
        "can_mega": data["name"] in bases,
        "is_mega": split_mega(data["name"])[0] is not None,
    }

def build(conn):
    """03_pokemons.sql 전문을 만들어 돌려준다. (pokemon_M_B 개수만큼 API 호출)"""
    cur = conn.cursor()
    bases = mega_bases(pokemon_M_B)        # 메가폼을 가진 베이스 이름들
    failed = []
    values = []                            # 완성된 행들을 여기 모음
    for n in pokemon_M_B:
        data = fetch_pokemon(n)
        if data is None:
            failed.append(n)
            print(f"{n} - failed")
            continue
        p = parse_pokemon(data, bases)
        values.append(tuple(p[c] for c in COLUMNS))
        print(f"{p['name']} - collected")
    print(f"\n성공: {len(values)}개")
    print(f"\n실패: {len(failed)}개 - {failed}")

    # 베이스가 목록에 없는 메가폼은 mega_evolutions(10단계)에서 빠진다
    orphans = sorted(bases - set(pokemon_M_B))
    if orphans:
        print(f"베이스가 목록에 없는 메가: {len(orphans)}개 - {orphans}")
    return render(schema.POKEMONS, TABLE, COLUMNS,
                  mogrify_rows(cur, values, len(COLUMNS)))

def main():
    conn = connect()
    paths.SQL_DIR.mkdir(exist_ok=True)
    (paths.SQL_DIR / FILENAME).write_text(build(conn), encoding="utf-8")
    print(f"{FILENAME} 생성 완료")
    conn.close()

if __name__ == "__main__":
    main()