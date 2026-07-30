"""포켓몬 이름 한↔영 변환.

get_pokemons.py 가 폼 이름을 한국어로 조립할 때 쓴다.

- 모듈 로드 시점에 DB 커넥션을 열지 않는다. import 만 해도 접속이 일어나면
  아직 테이블이 없는 구축 초기 단계에서 main.py 가 죽기 때문이다.
- get_pokemons 를 import 하지 않는다. get_pokemons 가 이 모듈을 import 하고
  있어서 서로 물고 도는 순환 import 가 된다.
"""

import requests

import db


def ko_to_en(korean_name, conn=None):
    """한국어 이름으로 영문 이름을 찾는다. 없으면 None."""
    own = conn is None
    conn = conn or db.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM pokemons WHERE ko_name = %s", (korean_name,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        if own:
            conn.close()


def en_to_ko(english_name, conn=None):
    """영문 이름으로 한국어 이름을 찾는다. 없으면 None."""
    own = conn is None
    conn = conn or db.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ko_name FROM pokemons WHERE name = %s", (english_name,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        if own:
            conn.close()


def fetch_korean_name(data):
    """PokeAPI 포켓몬 응답에서 species를 타고 들어가 기본 한국어 이름을 얻는다."""
    species = requests.get(data["species"]["url"], timeout=10).json()
    for n in species["names"]:
        if n["language"]["name"] == "ko":
            return n["name"]        # "냐오닉스"
    return None


def build_korean_name(data, base_ko):
    """폼 접미사(-mega, -alola ...)를 한국어 표기로 붙인다."""
    en = data["name"]              # "meowstic-mega"
    if en == "floette-eternal":
        return "영원의 꽃 플라엣테"
    if en == "palafin-zero":
        return f"{base_ko} 나이브폼"
    if en == "palafin-hero":
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
