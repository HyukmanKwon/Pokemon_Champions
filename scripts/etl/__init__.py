"""데이터베이스 — 짓고, 넣고, 받아 적고, 채용률을 이어 받는다.

── 왜 src/ 밖에 있나 ──
  ETL 은 몇 달에 한 번 손으로 돌리는 코드고, src/pokemon_champions 는 요청마다
  도는 코드다. 생명주기가 다르다. 섞어 두면 앱 배포판에 PokeAPI 파싱 코드가
  딸려 들어가고, PokeAPI 응답 형식이 바뀔 때 앱까지 같이 깨질 여지가 생긴다.

── import 방향 ──
  scripts/etl -> pokemon_champions  (O)  접속 설정·도메인 모델 재사용
  pokemon_champions -> scripts/etl  (X)  절대 금지

── 파일 이름이 값의 출처를 말한다 ──
      schema.py       표를 만드는 SQL 과 넣는 SQL. DDL 의 단일 출처
      pokeapi.py      남의 서버(PokeAPI)에서 오는 값
      build.py        코드에 적힌 고정값 + 구축 순서. 유일한 진입점
      sync_usage.py   날마다 쌓이는 것 (championsbattledata.com)
      load_sql.py     data/sql/ -> DB
      dump_sql.py     DB -> data/sql/

── 실행 ──
  프로젝트 루트에서 -m 으로 돌린다.

      python -m scripts.etl.load_sql                 설치. API 0회, 몇 초
      python -m scripts.etl.build                    전체 구축. 약 1,900회
      python -m scripts.etl.build --only items       한 단계만
      python -m scripts.etl.sync_usage --live        채용률 오늘 값

  pokeapi.py 는 직접 돌리지 않는다. 노출하는 것은 build_* 함수와 표 이름
  뿐이고, DB 에 올리는 일은 build.py 가 한다.
"""
