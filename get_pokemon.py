"""PokeAPI를 통해 포켓몬 정보를 가져오는 파일"""

import db
import requests 
import psycopg2 #postgreSQL 연동
import translation

import time

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
    # ===== 3세대 (기본 21, 폼 17) =====
    "sceptile", "blaziken", "swampert", "pelipper", "gardevoir", "sableye",
    "mawile", "aggron", "medicham", "manectric", "sharpedo", "camerupt",
    "torkoal", "altaria", "milotic", "castform", "banette", "chimecho",
    "absol", "glalie", "metagross",
    # -- 3세대 폼 --
    "absol-mega", "aggron-mega", "altaria-mega", "banette-mega", "blaziken-mega", "camerupt-mega",
    "chimecho-mega", "gardevoir-mega", "glalie-mega", "manectric-mega", "mawile-mega", "medicham-mega",
    "metagross-mega", "sableye-mega", "sceptile-mega", "sharpedo-mega", "swampert-mega",
    # ===== 4세대 (기본 24, 폼 11) =====
    "torterra", "infernape", "empoleon", "staraptor", "luxray", "roserade",
    "rampardos", "bastiodon", "lopunny", "spiritomb", "garchomp", "lucario",
    "hippowdon", "toxicroak", "abomasnow", "weavile", "rhyperior", "leafeon",
    "glaceon", "gliscor", "mamoswine", "gallade", "froslass", "rotom",
    # -- 4세대 폼 --
    "abomasnow-mega", "gallade-mega", "garchomp-mega", "lopunny-mega", "lucario-mega", "rotom-fan",
    "rotom-frost", "rotom-heat", "rotom-mow", "rotom-wash", "staraptor-mega",
    # ===== 5세대 (기본 30, 폼 11) =====
    "serperior", "emboar", "samurott", "watchog", "liepard", "simisage",
    "simisear", "simipour", "musharna", "excadrill", "audino", "conkeldurr",
    "scolipede", "whimsicott", "basculin-red-striped", "krookodile", "scrafty", "cofagrigus",
    "garbodor", "zoroark", "reuniclus", "vanilluxe", "emolga", "eelektross",
    "chandelure", "beartic", "stunfisk", "golurk", "hydreigon", "volcarona",
    # -- 5세대 폼 --
    "audino-mega", "chandelure-mega", "eelektross-mega", "emboar-mega", "excadrill-mega", "golurk-mega",
    "samurott-hisui", "scolipede-mega", "scrafty-mega", "stunfisk-galar", "zoroark-hisui",
    # ===== 6세대 (기본 32, 폼 13) =====
    "chesnaught", "delphox", "greninja", "diggersby", "talonflame", "vivillon",
    "pyroar-male", "flabebe", "floette", "florges", "pangoro", "furfrou",
    "meowstic-male", "aegislash-shield", "aromatisse", "slurpuff", "malamar", "barbaracle",
    "dragalge", "clawitzer", "heliolisk", "tyrantrum", "aurorus", "sylveon",
    "hawlucha", "dedenne", "goodra", "klefki", "trevenant", "gourgeist-average",
    "avalugg", "noivern",
    # -- 6세대 폼 --
    "avalugg-hisui", "barbaracle-mega", "chesnaught-mega", "delphox-mega", "dragalge-mega", "floette-eternal",
    "goodra-hisui", "greninja-mega", "hawlucha-mega", "malamar-mega",
    "pyroar-mega",
    # ===== 7세대 (기본 17, 폼 5) =====
    "decidueye", "incineroar", "primarina", "toucannon", "vikavolt", "crabominable",
    "toxapex", "mudsdale", "araquanid", "salazzle", "tsareena",
    "oranguru", "passimian", "mimikyu-disguised", "drampa", "kommo-o",
    # -- 7세대 폼 --
    "crabominable-mega", "decidueye-hisui", "drampa-mega", "lycanroc-midday", "lycanroc-dusk", "lycanroc-midnight",
    # ===== 8세대 (기본 18, 폼 2) =====
    "corviknight", "flapple", "appletun", "sandaconda", "centiskorch", "polteageist",
    "hatterene", "grimmsnarl", "mr-rime", "alcremie", "falinks", "indeedee-male",
    "dragapult", "wyrdeer", "kleavor", "basculegion-male", "sneasler", "overqwil",
    # -- 8세대 폼 --
    "basculegion-female", "falinks-mega",
    # ===== 9세대 (기본 23, 폼 2) =====
    "meowscarada", "skeledirge", "quaquaval", "maushold-family-of-four", "garganacl", "armarouge",
    "ceruledge", "bellibolt", "toedscruel", "scovillain", "espathra", "tinkaton",
    "palafin-zero", "orthworm", "glimmora", "houndstone", "annihilape", "farigiraf",
    "kingambit", "gholdengo", "sinistcha", "archaludon", "hydrapple",
    # -- 9세대 폼 --
    "glimmora-mega", "scovillain-mega",
]

POKEAPI_BASE = "https://pokeapi.co/api/v2/pokemon"
DB_CONFIG = db.DB_CONFIG       #db.py에 정의된 DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

def fetch_pokemon(name):  #pokemon_id를 받아 url을 생성후, API를 받아옴
    url = f"{POKEAPI_BASE}/{name}"
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200: #이름 못 찾음
        return None
    return requests.get(url).json()

def parse_pokemon(data):        #필요한 정보를 parsing해서 반환
    stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}          # key : values
    types = {t["slot"]: t["type"]["name"] for t in data["types"]}
    abilities = {a["slot"]: a["ability"]["name"] for a in data["abilities"]}
    return {
        "POKEMON_ID": data["id"],
        "NAME": data["name"],
        "TYPE1": types.get(1),
        "TYPE2": types.get(2),
        "ABILITY1": abilities.get(1),   #key가 1인 값을 가져온다.
        "ABILITY2": abilities.get(2),
        "ABILITY3": abilities.get(3),
        "HEIGHT": data["height"] / 10,   # 17 → 1.7 (m)
        "WEIGHT": data["weight"] / 10,   # 905 → 90.5 (kg)
        "H": stats["hp"],
        "A": stats["attack"],
        "B": stats["defense"],
        "C": stats["special-attack"],
        "D": stats["special-defense"],
        "S": stats["speed"],
        "TOTAL": stats["hp"] + stats["attack"] + stats["defense"]
               + stats["special-attack"] + stats["special-defense"] + stats["speed"],
    }

def insert_pokemon_infor():
    failed = []
    for n in pokemon_M_B:    #pokemon_M_B에 있는 이름을 받아 차례대로 저장
        data = fetch_pokemon(n) #data에서 받아오기
        if data is None:                 # 실패하면 기록하고 다음으로
            failed.append(n)
            print(f"{n} - failed")
            continue
        p = parse_pokemon(data) #p에 포켓몬 정보 받기
        cur.execute(            #정보 담아 SQL로 변환
            """
            INSERT INTO pokemon (POKEMON_ID, NAME, TYPE1, TYPE2, ABILITY1, ABILITY2, ABILITY3,
            HEIGHT, WEIGHT, H, A, B, C, D, S, TOTAL)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (name) DO UPDATE SET
            type1   = EXCLUDED.type1,
            type2   = EXCLUDED.type2,
            h = EXCLUDED.h, a = EXCLUDED.a, b = EXCLUDED.b,
            c = EXCLUDED.c, d = EXCLUDED.d, s = EXCLUDED.s,
            ability1 = EXCLUDED.ability1,
            ability2 = EXCLUDED.ability2,
            ability3 = EXCLUDED.ability3,
            height = EXCLUDED.height,
            weight = EXCLUDED.weight,
            total  = EXCLUDED.total
            """,
            (p["POKEMON_ID"], p["NAME"], p["TYPE1"], p["TYPE2"], 
             p["ABILITY1"], p["ABILITY2"], p["ABILITY3"],
             p["HEIGHT"], p["WEIGHT"], 
             p["H"], p["A"], p["B"], p["C"], p["D"], p["S"], p["TOTAL"]),
        )
        conn.commit()           #하나씩 저장
        print(f"{p['NAME']} - save complete")  
    print(f"\n 실패: {len(failed)}개 - {failed}")  
 

def main():
    insert_pokemon_infor()
    translation.get_korean_name()
    conn.close()

if __name__ == "__main__":
    main()