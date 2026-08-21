"""ETL 이 읽고 쓰는 경로.

전부 pokemon_champions.config 에 정의된 값을 그대로 쓴다. 경로를 여기서
새로 계산하면 앱과 ETL 이 서로 다른 폴더를 보게 된다.

    data/sql/    생성한 SQL. 실행할 때마다 덮어쓴다 (git 커밋)
    data/cache/  내려받은 원본 CSV. 재생성 가능 (git 제외)
"""

from pokemon_champions.config import (  # noqa: F401
    CACHE_DIR,
    DATA_DIR,
    PROJECT_ROOT,
    SQL_DIR,
)
