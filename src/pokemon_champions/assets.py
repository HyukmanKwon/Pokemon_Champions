"""타입 아이콘·포켓몬 사진·도구 아이콘을 PokeAPI sprites 저장소에서 받아 캐시한다.

한 번 받은 파일은 data/images/ 에 저장해두고, 다음부터는 다시 받지 않고
그 파일을 그대로 쓴다. 사진은 부가 정보라 다운로드가 실패해도 예외를
올리지 않고 None을 돌려준다 — 능력치 조회 자체가 이것 때문에 실패하면 안 된다.

── 왜 패키지 안이 아니라 data/ 에 받나 ──
  내려받은 이미지는 코드가 아니라 캐시다. 패키지 폴더에 쌓으면 git 에서
  코드와 섞이고, 나중에 wheel 로 설치했을 때 쓰기 권한이 없어 깨진다.

── ensure_* 는 URL 이 아니라 Path 를 돌려준다 ──
  예전에는 "/images/pokemon/6.png" 같은 URL 을 돌려줬다. 그러면 URL 을
  만들려면 반드시 파일을 먼저 받아야 해서, 목록 API 가 응답을 만드는 동안
  313장을 순서대로 내려받는 일이 벌어진다. 첫 페이지가 몇 분씩 걸린다.

  그래서 둘을 갈랐다. url_* 는 네트워크를 쓰지 않고 문자열만 만들고,
  실제 다운로드는 브라우저가 그 주소를 부를 때 라우트(app.py)에서 일어난다.
  느린 일이 요청 하나에 몰리지 않고 이미지마다 흩어지고, 화면에 보이는
  것만 받게 된다.
"""

from pathlib import Path

import requests

from .config import IMAGES_DIR

SPRITES_REPO = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"
TYPE_ICON_URL = f"{SPRITES_REPO}/types/generation-ix/scarlet-violet/{{type_id}}.png"
# 상세 화면용 큰 그림. 한 장에 수백 KB 라 목록에 313장을 깔면 안 된다.
POKEMON_SPRITE_URL = f"{SPRITES_REPO}/pokemon/other/official-artwork/{{pokemon_id}}.png"
# 목록용 96px 도트. 위의 1/50 크기라 표에 쭉 깔아도 견딘다.
POKEMON_ICON_URL = f"{SPRITES_REPO}/pokemon/{{pokemon_id}}.png"
# 도구는 id 가 아니라 영문 이름으로 찾는다 (leftovers.png, choice-band.png).
ITEM_SPRITE_URL = f"{SPRITES_REPO}/items/{{item_name}}.png"

TYPE_IDS = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10,
    "water": 11, "grass": 12, "electric": 13, "psychic": 14, "ice": 15,
    "dragon": 16, "dark": 17, "fairy": 18,
}

# 타입 배지는 두 폴더다. 내려받은 영문 원본이 재료이고, 화면이 보는 것은
# 그 심볼을 살려 한국어로 다시 그린 쪽이다. (scripts/make_type_icons.py)
# 한 폴더에 두면 다시 그릴 때 자기가 만든 것을 원본으로 삼는다.
TYPES_EN_DIR = IMAGES_DIR / "types_en"
TYPES_DIR = IMAGES_DIR / "types"
POKEMON_DIR = IMAGES_DIR / "pokemon"
POKEMON_ICON_DIR = IMAGES_DIR / "pokemon_icons"
ITEM_DIR = IMAGES_DIR / "items"

# 저장소에 아예 없는 그림(폼 변이는 흔하다)을 매번 다시 받으러 가지 않도록
# 실패한 주소를 기억해둔다. 프로세스가 살아 있는 동안만이라 서버를 다시
# 띄우면 한 번은 재시도한다 — 저장소에 나중에 올라올 수도 있기 때문이다.
_missing = set()


def _ensure_cached(path: Path, url: str):
    """파일이 없으면 받아서 저장하고, 그 경로를 돌려준다. 실패하면 None."""
    if path.exists():
        return path
    if url in _missing:
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        res = requests.get(url, timeout=5)
        res.raise_for_status()
    except requests.RequestException:
        _missing.add(url)
        return None
    path.write_bytes(res.content)
    return path


# ─────────────────────────────────────────────────────────────
# 받아오기 — 네트워크를 쓴다. 라우트와 일괄 다운로드 스크립트만 부른다.
# ─────────────────────────────────────────────────────────────

def ensure_type_source(type_name):
    """영문 원본 배지. 한국어 배지를 그리는 재료다.

    부르는 곳은 scripts/make_type_icons.py 하나뿐이다. 화면이 이걸 바로
    쓰면 영문 배지가 뜬다.
    """
    type_id = TYPE_IDS.get(type_name)
    if type_id is None:
        return None
    return _ensure_cached(TYPES_EN_DIR / f"{type_name}.png",
                          TYPE_ICON_URL.format(type_id=type_id))


def type_icon(type_name):
    """화면이 쓸 한국어 타입 배지. 아직 안 그렸으면 None.

    ── 여기서 그리지 않는다 ──
      다른 ensure_* 와 달리 없다고 만들어내지 않는다. 그리려면
      pokemon_type_names 를 읽어야 하는데, 그 순간 이 모듈이 DB 를 알게
      된다. 미리 한 번 그려두게 하고(scripts/make_type_icons.py), 없으면
      라우트가 404 를 준다 — 화면은 그때 한국어 글자로 대신 보여준다.
    """
    if type_name not in TYPE_IDS:
        return None
    path = TYPES_DIR / f"{type_name}.png"
    return path if path.exists() else None


def ensure_pokemon_sprite(pokemon_id):
    return _ensure_cached(POKEMON_DIR / f"{pokemon_id}.png",
                          POKEMON_SPRITE_URL.format(pokemon_id=pokemon_id))


def ensure_pokemon_icon(pokemon_id):
    return _ensure_cached(POKEMON_ICON_DIR / f"{pokemon_id}.png",
                          POKEMON_ICON_URL.format(pokemon_id=pokemon_id))


def ensure_item_sprite(item_name):
    """도구 아이콘. item_name 은 items.name (영문) 이다.

    한국어 이름으로는 못 찾는다 — 저장소 파일명이 영문 슬러그이기 때문이다.
    """
    if not item_name:
        return None
    return _ensure_cached(ITEM_DIR / f"{item_name}.png",
                          ITEM_SPRITE_URL.format(item_name=item_name))


# ─────────────────────────────────────────────────────────────
# 주소 만들기 — 네트워크를 쓰지 않는다. API 응답을 만들 때 쓴다.
#
# 여기서 만든 주소를 브라우저가 부르면 그때 위의 ensure_* 가 돈다.
# 그림이 없는 폼이면 라우트가 404 를 주고, 화면은 빈 칸으로 놔둔다.
# ─────────────────────────────────────────────────────────────

def url_type_icon(type_name):
    return f"/sprite/type/{type_name}" if type_name in TYPE_IDS else None


def url_pokemon_sprite(pokemon_id):
    return f"/sprite/pokemon/{pokemon_id}" if pokemon_id is not None else None


def url_pokemon_icon(pokemon_id):
    return f"/sprite/pokemon/{pokemon_id}/icon" if pokemon_id is not None else None


def url_item_sprite(item_name):
    return f"/sprite/item/{item_name}" if item_name else None
