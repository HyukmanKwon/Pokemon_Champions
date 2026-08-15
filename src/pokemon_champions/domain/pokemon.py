"""배틀에 실제로 나가는 포켓몬 한 마리.

── 스펙(spec)과 Pokemon 은 다르다 ──
  스펙은 이름/SP/성격/특성/도구/기술이고, Pokemon 은 거기서 실능치를 계산해
  만든 결과다. 배틀이 끝나면 스펙으로 다시 만들기만 하면 초기화된다.

── 한 마리에게 걸린 것은 전부 여기 있다 ──
  실능치와 특성처럼 판 내내 안 변하는 것도, 랭크·상태이상·남은 HP 처럼
  턴마다 변하는 것도 같이 들고 있다. 나누지 않는 이유가 있다.

  예전에는 랭크·상태이상·남은 HP·접지가 BattleContext 에도 같이 있었다.
  같은 사실이 두 군데 적히니 어긋날 수 있었고, 실제로 읽는 쪽이 갈려
  있었다 — 화상의 공격 반감은 ctx 를 보고, 근성과 이상한비늘은 Pokemon 을
  봤다. 그래서 "화상 걸린 근성" 을 재려면 burn 을 두 번 적어야 했고, 한
  번만 적으면 예외 없이 조용히 다른 값이 나왔다.

  지금은 갈리는 기준이 하나다.

      Pokemon         이 한 마리에게 걸린 것
      BattleContext   판 전체에 걸린 것 (날씨·필드·급소·스크린·더블)

── 화면 출력은 여기 없다 ──
  예전 __str__ 은 터미널 폭을 맞춰 표를 그렸다. 그건 CLI 사정이지 포켓몬의
  성질이 아니라서 interfaces/cli.py 의 format_pokemon() 으로 옮겼다.
  웹은 같은 객체를 JSON으로 내보낸다 — 표현을 밖에 두면 이게 가능하다.
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
    # 영문 타입 1~2개. ("fire", "flying") 또는 ("water",)
    #
    # 이름이 아니라 타입을 들고 있는 이유: 데미지 계산이 자속과 상성을
    # 판정하려면 타입이 필요한데, calc/damage.py 는 DB를 안 본다.
    # 이름만 들고 있으면 계산 함수가 "이 이름의 타입이 뭐지"를 물으러
    # DB로 돌아가야 하고, 그 순간 순수 함수가 아니게 된다.
    #
    # 메가진화하면 여기가 바뀐다 — 메가폼의 타입으로 다시 만들면 된다.
    types: tuple = ()

    # 남은 HP. None 은 "안 물어봤다" 이고 만피로 본다. 0 과 구분해야
    # 하므로 기본값을 stats.h 로 채우지 않는다 — 그러면 만들 때 실능치가
    # 이미 있어야 한다.
    #
    # 멀티스케일(만피일 때만)과 궁지 특성(1/3 이하일 때만)이 이걸 본다.
    hp: int = None

    # 접지 여부. 필드 효과는 접지된 쪽에만 걸린다. 부유·비행 타입이
    # 아니면 참이라 기본값이 True 다.
    grounded: bool = True

    def rank_of(self, stat):
        """랭크 변화 단계. 안 걸려 있으면 0."""
        return (self.rank or {}).get(stat, 0)

    def hp_now(self):
        """남은 HP. 안 물어봤으면 만피.

        부르는 쪽이 매번 `hp if hp is not None else stats.h` 를 적지 않게
        한다. 그 세 갈래를 여섯 군데 적으면 한 곳은 반드시 틀린다.
        """
        return self.stats.h if self.hp is None else self.hp
