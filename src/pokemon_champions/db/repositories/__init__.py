"""테이블별 조회 모듈.

프로젝트에서 SQL 문자열이 등장해도 되는 유일한 곳이다. 이 규칙 덕분에
스키마를 바꿀 때 고칠 곳이 이 폴더 하나로 좁혀지고, 위 계층(services)은
DB 없이 테스트할 수 있다.

조회 함수는 값을 못 찾으면 ValueError 를 올린다. psycopg2 예외를 그대로
위로 흘리지 않는 이유는, 그 순간 services 가 psycopg2 를 알아야 하기
때문이다.
"""

from . import (ability_repo, item_repo, mega_repo, move_repo, nature_repo,
               pokemon_repo, rules_repo)

__all__ = ["pokemon_repo", "nature_repo", "ability_repo", "move_repo",
           "mega_repo", "item_repo", "rules_repo"]
