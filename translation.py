import psycopg2
import db
import requests
from get_pokemon import fetch_pokemon

DB_CONFIG = db.DB_CONFIG       #db.py에 정의된 DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

def ko_to_en(korean_name):
    cur.execute(
        """
        SELECT EN_NAME 
        FROM POKEMON_NAME 
        WHERE KO_NAME = %s
        """, 
        (korean_name,), 
    )
    row = cur.fetchone()         
    if row is None:
        return None
    return row[0]      

def en_to_ko(english_name):
    cur.execute(
        """
        SELECT KO_NAME 
        FROM POKEMON_NAME 
        WHERE EN_NAME = %s
        """, 
        (english_name,), 
    )
    row = cur.fetchone()         
    if row is None:
        return None
    return row[0]  

def fetch_korean_name(data):
    species = requests.get(data["species"]["url"]).json()
    for n in species["names"]:
        if n["language"]["name"] == "ko":
            return n["name"]        # "냐오닉스"
    return None

def build_korean_name(data, base_ko):
    en = data["name"]              # "meowstic-mega"
    if en=="floette-eternal":
        return f"영원의 꽃 플라엣테" 
    if en=="palafin-zero":
        return f"{base_ko} 나이브폼"
    if en=="palafin-hero":
        return f"{base_ko} 마이티폼"
    if "-mega-x" in en:
        return f"메가{base_ko}X"
    if "-mega-y" in en:
        return f"메가{base_ko}Y"
    if "-mega" in en:
        return f"메가{base_ko}"
    if "-alola" in en:
        return f"알로라 {base_ko}"
    if "-galar" in en:
        return f"가라르 {base_ko}"
    if "-hisui" in en:
        return f"히스이 {base_ko}"
    if "tauros-paldea-combat" in en:
        return f"팔데아 {base_ko}(격투)"
    if "tauros-paldea-blaze" in en:
        return f"팔데아 {base_ko}(불꽃)"
    if "tauros-paldea-aqua" in en:
        return f"팔데아 {base_ko}(물)"
    if "rotom-heat" in en:
        return f"히트{base_ko}"
    if "rotom-wash" in en:
        return f"워시{base_ko}"
    if "rotom-frost" in en:
        return f"프로스트{base_ko}"
    if "rotom-fan" in en:
        return f"스핀{base_ko}"
    if "rotom-mow" in en:
        return f"커트{base_ko}"
    if "lycanroc-midday" in en:
        return f"{base_ko}(한낮)"
    if "lycanroc-dusk" in en:
        return f"{base_ko}(황혼)"
    if "lycanroc-midnight" in en:
        return f"{base_ko}(한밤)"
    if "basculegion-female" in en:
        return f"{base_ko}(암컷)"
    if "basculegion-male" in en:
        return f"{base_ko}(수컷)"
    return base_ko    

def get_korean_name():
    cur.execute("SELECT NAME FROM POKEMON")
    names = [row[0] for row in cur.fetchall()]  #english names

    for en in names:
        data = fetch_pokemon(en)                #data -> 포켓몬 영어이름들
        if data is None:          # PokeAPI에 없는 포켓몬은 건너뜀
            print(f"건너뜀 : {en}#######")
            continue
        base_ko = fetch_korean_name(data)       #base_ko -> 기본 포켓몬 이름
        ko = build_korean_name(data, base_ko)   #ko -> 수정 완료한 포켓몬 이름
        cur.execute(
            """
            INSERT INTO POKEMON_NAME(EN_NAME, KO_NAME)
            VALUES (%s, %s)
            ON CONFLICT (EN_NAME) DO UPDATE SET
            KO_NAME   = EXCLUDED.KO_NAME
            """,
            (en, ko),
        )
        conn.commit()
        print(f"{en} -> {ko}")    
    