"""PokeAPI -> SQL -> DB 구축 파이프라인.

── 왜 src/ 밖에 있나 ──
  ETL 은 몇 달에 한 번 손으로 돌리는 코드고, src/pokemon_champions 는 요청마다
  도는 코드다. 생명주기가 다르다. 섞어 두면 앱 배포판에 PokeAPI 파싱 코드가
  딸려 들어가고, PokeAPI 응답 형식이 바뀔 때 앱까지 같이 깨질 여지가 생긴다.

── import 방향 ──
  scripts/etl -> pokemon_champions  (O)  접속 설정·도메인 모델 재사용
  pokemon_champions -> scripts/etl  (X)  절대 금지

── 실행 ──
  프로젝트 루트에서 -m 으로 돌린다. 예전처럼 cd 해서 실행하지 않는다.

      python -m scripts.etl.build          전체 구축
      python -m scripts.etl.get_items      06_items.sql 만 생성
      python -m scripts.etl.annotator.moves
"""
