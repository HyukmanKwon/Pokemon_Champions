"""배틀에 실제로 나가는 포켓몬 한 마리.

── 화면 출력은 여기 없다 ──
  예전 __str__ 은 터미널 폭을 맞춰 표를 그렸다. 그건 CLI 사정이지 포켓몬의
  성질이 아니라서 interfaces/cli.py 의 format_pokemon() 으로 옮겼다.
  웹은 같은 객체를 JSON으로 내보낸다 — 표현을 밖에 두면 이게 가능하다.

── 스펙(spec)과 Pokemon 은 다르다 ──
  스펙은 이름/SP/성격/특성/도구/기술이고, Pokemon 은 거기서 실능치를 계산해
  만든 결과다. 배틀 중 rank/condition 은 Pokemon 에서만 바뀌고 스펙에는
  반영되지 않으므로, 배틀이 끝나면 스펙으로 다시 만들기만 하면 초기화된다.
"""

from dataclasses import dataclass

from .stats import Stats


@dataclass
class Pokemon:
    name: str               # 한국어 이름
    stats: Stats            # 실능치
    ability: str
    item: str = None
    rank: dict = None       # {"a": int, ..., "s": int} -6 ~ +6, 기본 0
    moves: list = None      # 기술 4개까지
    condition: str = None   # None 이면 정상, "poison" 등
    nature: str = None
