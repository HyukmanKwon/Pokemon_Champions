"""데미지 계산 — 아직 뼈대만 있다. 채우는 건 여기부터.

── 왜 conn 이 없나 ──
  옮기기 전 이 파일은 모듈 최상단에서 psycopg2.connect() 를 했다. import
  하는 것만으로 DB 접속이 일어났고, 그래서 DB 없이는 테스트도 import 도
  불가능했다. 이제 이 모듈은 이미 조회된 값만 인자로 받는다.

  조회는 부르는 쪽(agent 툴이나 API 라우터)에서 repositories 로 하고,
  여기에는 숫자만 넘어온다. 그 덕에 세 가지가 가능해진다.

    1. 실제 게임에서 확인한 데미지 케이스를 테스트로 박아둘 수 있다.
       @smogon/calc 를 쓰지 않고 직접 구현하기로 했으니, 이 테스트 묶음이
       계산기의 신뢰도 그 자체다.
    2. LLM 툴로 감쌀 때 시그니처가 그대로 툴 스키마가 된다.
    3. "왜 이 숫자가 나왔나" 를 인자만 다시 넣어 재현할 수 있다.

── 왜 BattleContext 로 묶나 ──
  날씨·필드·랭크·스크린·상태이상은 순차 계산 도중에 값이 변한다. 인자로
  하나씩 늘리면 새 요소를 지원할 때마다 모든 호출부를 고쳐야 한다. 한
  덩어리로 묶으면 필드 추가가 호출부를 건드리지 않고, 확정 N방 분석도
  "context 를 한 턴씩 바꾸며 같은 함수를 반복 호출" 로 깔끔하게 써진다.
  스태미나처럼 맞을 때마다 방어가 오르는 특성이 정확히 이 모양이다.
"""

from dataclasses import dataclass, field


@dataclass
class BattleContext:
    """한 번의 데미지 계산에 걸리는 판 상태.

    전부 기본값이 있다. 아무것도 안 넘기면 평지·맑음·랭크 0 이다.
    """

    weather: str = None          # weathers.name — "sun" "rain" "sandstorm" "snow"
    terrain: str = None          # terrains.name — "electric" "grassy" ...
    attacker_rank: dict = field(default_factory=dict)   # {"a": 2, "s": -1}
    defender_rank: dict = field(default_factory=dict)
    attacker_condition: str = None   # status_conditions.name — "burn" "paralysis"
    defender_condition: str = None
    is_critical: bool = False
    reflect: bool = False        # 리플렉터 (물리 반감)
    light_screen: bool = False   # 빛의장막 (특수 반감)
    attacker_grounded: bool = True   # 필드 효과는 접지된 쪽에만 걸린다
    defender_grounded: bool = True


@dataclass
class DamageRange:
    """난수 16단계(85~100%)의 최소·최대와 전체 목록."""

    rolls: list

    @property
    def min(self):
        return min(self.rolls)

    @property
    def max(self):
        return max(self.rolls)


def type_multiplier(move_type, defender_types, chart):
    """타입 상성 배수. chart 는 {(공격, 방어): 배수} — pokemon_types 테이블.

    조회 결과를 인자로 받는다. 이 함수 안에서 SELECT 하지 않는다.
    """
    raise NotImplementedError


def calc_damage(attacker, defender, move, ctx=None, chart=None):
    """데미지 난수 16개를 DamageRange 로 돌려준다.

    attacker / defender  Pokemon (실능치가 이미 계산되어 있다)
    move                 moves 테이블 한 행 (dict). power, type, category ...
    ctx                  BattleContext. None 이면 기본 상태
    chart                타입 상성표 {(공격, 방어): 배수}

    곱해야 할 것 — 하나씩 순서대로 붙이면서 테스트를 늘려 나가면 된다.
        실능치 · 기술 위력 · 자속 · 타입 상성 · 급소
        · 랭크 · 날씨 · 필드 · 특성 · 도구 · 상태이상 · 스크린 · 난수
    """
    raise NotImplementedError


def analyze_ko(attacker, defender, move, ctx=None, chart=None, max_turns=4):
    """몇 방에 쓰러지는지 — 확정 1타 / 난수 2타 처럼 판정한다.

    calc_damage 를 턴마다 다시 부르고, 그 사이에 ctx 를 갱신한다.
    스태미나·이판사판태클처럼 맞는 도중에 값이 바뀌는 특성 때문에
    "데미지 × N" 으로 계산하면 틀린다.
    """
    raise NotImplementedError
