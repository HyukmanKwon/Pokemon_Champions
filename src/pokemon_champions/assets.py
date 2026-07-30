"""타입 아이콘·포켓몬 사진을 PokeAPI sprites 저장소에서 받아 로컬에 캐시한다.

한 번 받은 파일은 data/images/ 에 저장해두고, 다음부터는 다시 받지 않고
그 파일을 그대로 쓴다. 사진은 부가 정보라 다운로드가 실패해도 예외를
올리지 않고 None을 돌려준다 — 능력치 조회 자체가 이것 때문에 실패하면 안 된다.

── 왜 패키지 안이 아니라 data/ 에 받나 ──
  내려받은 이미지는 코드가 아니라 캐시다. 패키지 폴더에 쌓으면 git 에서
  코드와 섞이고, 나중에 wheel 로 설치했을 때 쓰기 권한이 없어 깨진다.
"""

from pathlib import Path

import requests

from .config import IMAGES_DIR

SPRITES_REPO = "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites"
TYPE_ICON_URL = f"{SPRITES_REPO}/types/generation-ix/scarlet-violet/{{type_id}}.png"
POKEMON_SPRITE_URL = f"{SPRITES_REPO}/pokemon/other/official-artwork/{{pokemon_id}}.png"

TYPE_IDS = {
    "normal": 1, "fighting": 2, "flying": 3, "poison": 4, "ground": 5,
    "rock": 6, "bug": 7, "ghost": 8, "steel": 9, "fire": 10,
    "water": 11, "grass": 12, "electric": 13, "psychic": 14, "ice": 15,
    "dragon": 16, "dark": 17, "fairy": 18,
}

TYPES_DIR = IMAGES_DIR / "types"
POKEMON_DIR = IMAGES_DIR / "pokemon"


def _ensure_cached(path: Path, url: str):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            res = requests.get(url, timeout=5)
            res.raise_for_status()
        except requests.RequestException:
            return None
        path.write_bytes(res.content)
    return f"/images/{path.relative_to(IMAGES_DIR).as_posix()}"


def ensure_type_icon(type_name):
    type_id = TYPE_IDS.get(type_name)
    if type_id is None:
        return None
    path = TYPES_DIR / f"{type_name}.png"
    return _ensure_cached(path, TYPE_ICON_URL.format(type_id=type_id))


def ensure_pokemon_sprite(pokemon_id):
    path = POKEMON_DIR / f"{pokemon_id}.png"
    return _ensure_cached(path, POKEMON_SPRITE_URL.format(pokemon_id=pokemon_id))
