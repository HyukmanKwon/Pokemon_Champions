"""프로젝트 전역 설정 — 접속 정보, 경로, 룰 상수.

여기 있는 값은 대부분 "포켓몬 챔피언스 레귤레이션 M-B 의 규칙"이지
물리 법칙이 아니다. 레귤레이션이 바뀌면 이 파일만 고친다.
"""

import os
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# 경로
# ─────────────────────────────────────────────────────────────
# src/pokemon_champions/config.py -> src/pokemon_champions -> src -> 프로젝트 루트
PROJECT_ROOT = Path(
    os.getenv("POKEMON_CHAMPIONS_ROOT", Path(__file__).resolve().parents[2])
)

DATA_DIR = PROJECT_ROOT / "data"
SQL_DIR = DATA_DIR / "sql"            # ETL 이 생성한 SQL (재생성 가능)
OVERRIDE_DIR = DATA_DIR / "overrides"  # 사람이 확정한 값 (git 커밋 대상)
CACHE_DIR = DATA_DIR / "cache"        # 내려받은 원본 (재생성 가능)
IMAGES_DIR = DATA_DIR / "images"      # 스프라이트·타입 아이콘 캐시
TEAM_PATH = DATA_DIR / "my_team.json"  # 내 포켓몬 6마리 스펙

# ─────────────────────────────────────────────────────────────
# DB 접속
# ─────────────────────────────────────────────────────────────
DB_CONFIG = {
    "host": os.getenv("PGHOST", "localhost"),
    "port": os.getenv("PGPORT", "5432"),
    "dbname": os.getenv("PGDATABASE", "pokemon"),
    "user": os.getenv("PGUSER", "hyukman"),
    "password": os.getenv("PGPASSWORD", ""),
}

# ─────────────────────────────────────────────────────────────
# 레귤레이션 M-B 룰
# ─────────────────────────────────────────────────────────────
LEVEL = 50              # 레벨 고정
IV = 31                 # 개체값 고정
MAX_SP = 66             # SP 총 투자 가능치
MAX_SP_PER_STAT = 32    # 능력치 하나당 SP 투자 가능치
TEAM_SIZE = 6

# 실능 공식의 상수. LEVEL·IV 가 고정이라 미리 접어 둔 값이다.
#   HP     = 종족값 + HP_OFFSET + SP
#   나머지 = int((종족값 + STAT_OFFSET + SP) * 성격보정)
HP_OFFSET = 75
STAT_OFFSET = 20
