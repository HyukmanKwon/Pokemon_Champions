"""사람이 손으로 확정한 값을 담아두는 곳.

PokeAPI가 주지 않는 정보(기술 플래그 등)는 이름 규칙으로 추측할 수밖에
없는데, 추측은 반드시 틀린다. 그 수정을 DB에만 해두면 다음 재구축에서
사라진다. 그래서 JSON 파일에 쌓고, 생성기가 매번 이걸 덮어씌운다.

    추측값  ->  overrides 적용  ->  SQL 파일  ->  DB

파일 형식 (overrides/move_flags.json)

    {
      "reviewed": ["fire-punch", "sucker-punch"],
      "values": {
        "sucker-punch": {"is_punch": false}
      }
    }

  reviewed  사람이 눈으로 확인한 항목. 추측과 결론이 같아도 여기 들어간다.
            annotator 의 "미확인만 보기" 필터가 이걸 본다.
  values    추측과 결론이 다른 항목만. 바꾼 필드만 적는다.

git 에 커밋되므로 누가 언제 무엇을 고쳤는지 남는다.
"""

import json

from pokemon_champions.db import connect

from . import paths

OVERRIDE_DIR = paths.OVERRIDE_DIR

EMPTY = {"reviewed": [], "values": {}}


def path(name):
    """move_flags -> data/overrides/move_flags.json"""
    return OVERRIDE_DIR / f"{name}.json"


_cache = {}


def load(name, refresh=False):
    """없으면 빈 구조를 돌려준다. 한 번 읽으면 캐시한다."""
    if not refresh and name in _cache:
        return _cache[name]
    p = path(name)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
    else:
        data = {}
    data.setdefault("reviewed", [])
    data.setdefault("values", {})
    _cache[name] = data
    return data


def save(name, data):
    OVERRIDE_DIR.mkdir(exist_ok=True)
    data["reviewed"] = sorted(set(data["reviewed"]))
    path(name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _cache[name] = data


def apply(name, key, guessed):
    """추측값 dict 에 저장된 확정값을 덮어씌운다.

    guessed 를 그 자리에서 고치고, (사람이 확인했는가) 를 돌려준다.
    """
    data = load(name)
    guessed.update(data["values"].get(key, {}))
    return key in data["reviewed"]
