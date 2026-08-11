"""조립 층 — DB 조회와 기본값 채우기와 계산 호출을 한 번만 적는다.

── 왜 이 층이 필요한가 ──
  services/damage.py 는 DB 를 안 본다. 그건 옳다 — 계산이 순수해야
  scripts/check_damage.py 로 실제 게임과 대조할 수 있고 tests/ 에 박아둘
  수 있다. 대신 "DB 에서 읽어 계산에 넘길 모양으로 만드는 일" 을 누군가는
  해야 하는데, 그 자리가 없어서 어댑터가 각자 떠맡고 있었다.

  결과는 같은 결정이 세 벌:

    무보정 성격 "성실"     app.py · tools.py · check_damage.py
    SP 기본 [0] * 6       셋 다
    allow_mega=True       셋 다
    스펙 -> Pokemon        _side_pokemon · _build · build
    BattleContext 조립     셋 다

  하나를 고치면 나머지 둘은 조용히 갈린다.

── 돌려주는 것은 뷰가 아니다 ──
  Pokemon 객체와 DamageRange 를 그대로 들고 있는 값을 돌려준다. JSON 이
  아니다. 그래야 어댑터마다 다른 모양으로 펼 수 있다 — API 는 아이콘
  URL 과 랭크를, 도구는 ko_name 짝을, CLI 는 터미널 한 줄을 만든다.
  계산은 한 번, 모양은 셋이다.

── 이 층이 모르는 것 ──
  HTTP 상태코드 · Pydantic · 도구 JSON 스키마 · {"error": ...} 규약 ·
  아이콘 URL. 어느 하나라도 들어오면 이건 다시 어댑터다.

── 커넥션은 인자로 ──
  모든 함수가 conn 을 첫 인자로 받는다. 모듈에 들고 있으면 웹에서
  동시 요청이 같은 psycopg2 커넥션을 나눠 쓰게 된다. 참조 데이터 캐시는
  모듈에 둬도 되지만(같은 값이 들어가므로) 커넥션은 아니다.
"""
