"""날씨 · 필드 · 상태이상 상수.

── 왜 DB 가 아니라 코드인가 ──
  이 셋은 표 열다섯 줄인데 조인 상대가 없다. 어느 표도 이것을 참조하지
  않고, 읽는 방법도 "통째로 한 번 읽어 dict 로 접기" 하나뿐이었다.
  진입점에서 한 번 읽어 계산 내내 돌려썼으므로 DB 에 두어 아끼는 것도
  없었다 — 프로세스 수명 동안 쿼리 세 번이 전부였다.

  반대로 코드에 두면 얻는 것이 있다. calc/ 는 db/ 를 import 할 수 없어서
  이 값들을 인자로 받아야 했는데, 상수가 되면 그 우회가 사라진다.

  값의 출처는 9세대 본가다. 포챔스 룰이 다르면 이 파일만 고친다.

── 순서가 곧 화면 순서다 ──
  dict 는 넣은 순서를 지킨다. 쾌청이 먼저인 것은 알파벳이 아니라 본가
  순서다. /api/calc/rules 가 이 dict 를 그대로 펴서 드롭다운을 채우므로,
  재배열하려면 여기 줄을 옮기면 된다. (전에는 sort_order 칸이 하던 일)

── 여기 없는 규칙 ──
  note 로만 적어 둔 것들은 아직 계산에 반영돼 있지 않다. 타입에 따른
  상태이상 면역(불꽃은 화상에 안 걸린다)이 그렇고, 필드의 접지 판정처럼
  코드로만 할 수 있는 것도 있다. 값을 늘리기 전에 쓰는 쪽을 먼저 본다.
"""

# 날씨. 보정이 두 종류다.
#   1. 기술 위력    비에서 물 1.5배, 불꽃 0.5배
#   2. 방어 능력치  모래바람은 바위의 '특수방어', 눈은 얼음의 '방어'
# 둘이 붙는 능력치가 달라서 def_boost_stat 으로 구분한다.
#
# name 은 날씨를 까는 기술 이름과 맞춰 뒀다.
#   sunny-day -> sun    rain-dance -> rain    snowscape -> snow
#
# 8세대까지 싸라기눈(hail)은 얼음을 뺀 전원이 매 턴 1/16을 잃었지만,
# 9세대 눈(snow)은 지속 데미지가 없고 얼음의 방어가 1.5배가 된다.
WEATHERS = {
    "sun": {
        "name": "sun", "ko_name": "쾌청",
        "boost_type": "fire", "boost_mult": 1.5,
        "weaken_type": "water", "weaken_mult": 0.5,
        "def_boost_type": None, "def_boost_stat": None, "def_boost_mult": None,
        "chip_damage": None, "chip_immune": None,
        # 솔라빔이 즉시 발동. 대타출동·아침햇살 회복량 2/3
    },
    "rain": {
        "name": "rain", "ko_name": "비",
        "boost_type": "water", "boost_mult": 1.5,
        "weaken_type": "fire", "weaken_mult": 0.5,
        "def_boost_type": None, "def_boost_stat": None, "def_boost_mult": None,
        "chip_damage": None, "chip_immune": None,
        # 번개·폭풍이 필중. 아침햇살 회복량 1/4
    },
    "sandstorm": {
        "name": "sandstorm", "ko_name": "모래바람",
        "boost_type": None, "boost_mult": None,
        "weaken_type": None, "weaken_mult": None,
        "def_boost_type": "rock", "def_boost_stat": "d", "def_boost_mult": 1.5,
        "chip_damage": 1 / 16, "chip_immune": ["rock", "ground", "steel"],
        # 바위 타입의 특수방어 1.5배
    },
    "snow": {
        "name": "snow", "ko_name": "눈",
        "boost_type": None, "boost_mult": None,
        "weaken_type": None, "weaken_mult": None,
        "def_boost_type": "ice", "def_boost_stat": "b", "def_boost_mult": 1.5,
        "chip_damage": None, "chip_immune": None,
        # 얼음 타입의 방어 1.5배. 9세대부터 지속 데미지 없음
    },
}

# 필드. 접지된 포켓몬에게만 걸린다 — 비행 타입, 부유, 풍선, 텔레키네시스는
# 제외다. 그 판정은 여기 값이 아니라 계산 코드가 한다 (calc/modifiers.py).
# 위력 1.3배도 '기술을 쓰는 쪽이 접지되어 있을 때'만 붙는다.
#
# name 은 기술 이름의 접두사와 같다. electric-terrain -> electric
TERRAINS = {
    "electric": {
        "name": "electric", "ko_name": "일렉트릭필드",
        "boost_type": "electric", "boost_mult": 1.3,
        "weaken_type": None, "weaken_mult": None, "heal_fraction": None,
        # 접지된 포켓몬은 잠듦 상태가 되지 않는다
    },
    "grassy": {
        "name": "grassy", "ko_name": "그래스필드",
        "boost_type": "grass", "boost_mult": 1.3,
        "weaken_type": None, "weaken_mult": None, "heal_fraction": 1 / 16,
        # 지진·땅고르기·매그니튜드 위력 0.5배. 접지된 쪽이 매 턴 회복
    },
    "misty": {
        "name": "misty", "ko_name": "미스트필드",
        "boost_type": None, "boost_mult": None,
        "weaken_type": "dragon", "weaken_mult": 0.5, "heal_fraction": None,
        # 접지된 포켓몬은 상태이상·혼란에 걸리지 않는다
    },
    "psychic": {
        "name": "psychic", "ko_name": "사이코필드",
        "boost_type": "psychic", "boost_mult": 1.3,
        "weaken_type": None, "weaken_mult": None, "heal_fraction": None,
        # 접지된 포켓몬에게 우선도 1 이상의 기술이 통하지 않는다
    },
}

# 상태이상. name 은 PokeAPI 의 move-ailment 를 그대로 쓴다 — moves.ailment
# 가 이 열쇠다.
#
# 세대마다 바뀐 적이 있는 항목:
#   화상 지속 데미지  1/8 (2~6세대) -> 1/16 (7세대~)
#   마비 스피드      1/4 (2~6세대) -> 1/2 (7세대~)
#
# 맹독은 턴마다 1/16씩 누적되는 특수 계산이라 turn_damage 가 None 이다.
# 그 계산은 calc/residual.py 가 한다.
STATUS_CONDITIONS = {
    "burn": {
        "name": "burn", "ko_name": "화상", "attack_mult": 0.5,
        "speed_mult": None, "turn_damage": 1 / 16,
        "immobile": False, "fail_chance": None,
        # 물리공격 0.5배. 불꽃 타입은 걸리지 않는다 (미구현)
    },
    "paralysis": {
        "name": "paralysis", "ko_name": "마비", "attack_mult": None,
        "speed_mult": 0.5, "turn_damage": None,
        "immobile": False, "fail_chance": 0.25,
        # 행동 실패 25%. 전기 타입은 걸리지 않는다 (미구현)
    },
    "poison": {
        "name": "poison", "ko_name": "독", "attack_mult": None,
        "speed_mult": None, "turn_damage": 1 / 8,
        "immobile": False, "fail_chance": None,
        # 독·강철 타입은 걸리지 않는다 (미구현)
    },
    "toxic": {
        "name": "toxic", "ko_name": "맹독", "attack_mult": None,
        "speed_mult": None, "turn_damage": None,
        "immobile": False, "fail_chance": None,
        # 턴마다 1/16씩 누적. n턴째 n/16
    },
    "sleep": {
        "name": "sleep", "ko_name": "잠듦", "attack_mult": None,
        "speed_mult": None, "turn_damage": None,
        "immobile": True, "fail_chance": None,
        # 1~3턴. 잠꼬대·코골기만 사용 가능
    },
    "freeze": {
        "name": "freeze", "ko_name": "얼음", "attack_mult": None,
        "speed_mult": None, "turn_damage": None,
        "immobile": True, "fail_chance": None,
        # 매 턴 20% 확률로 해동. 얼음 타입은 걸리지 않는다 (미구현)
    },
    "confusion": {
        "name": "confusion", "ko_name": "혼란", "attack_mult": None,
        "speed_mult": None, "turn_damage": None,
        "immobile": False, "fail_chance": 0.33,
        # 부가 상태. 33% 확률로 자신을 공격
    },
}
