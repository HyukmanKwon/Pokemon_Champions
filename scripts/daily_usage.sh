#!/bin/bash
# 채용률을 하루 한 번 받아 DB 에 쌓는다. launchd 가 부른다.
#
#   scripts/com.hyukman.pokemon-usage.plist 참고
#
# ── 왜 --backfill 인가 ──
#   "오늘 것만" 이 아니라 "안 받은 것 전부" 를 받는다. 노트북을 며칠 안
#   켰거나 실행이 실패했으면 그 구멍을 다음 실행이 메운다. 저쪽은 16일치만
#   남기므로 놓친 날은 그 안에 받아야 영영 잃지 않는다.
#   이미 받은 날짜는 건너뛰므로 매일 돌아도 낭비가 없다.
#
# ── 왜 shim 이 아니라 실제 인터프리터인가 ──
#   launchd 는 로그인 셸을 안 거쳐서 PATH 에 asdf 가 없다.
#   ~/.asdf/shims/python 은 asdf 를 다시 부르므로 "asdf: not found" 로 죽는다.
#   버전을 올리면 이 줄을 같이 고쳐야 한다.
#
# ── 실패해도 0 으로 끝내지 않는다 ──
#   launchd 는 종료 코드를 본다. 조용히 성공한 척하면 며칠 뒤 자료가
#   비어 있는 것을 사람이 발견하게 된다.
#
# ── 두 번 겹쳐 돌지 않는다 ──
#   백필이 15일치면 30분 넘게 걸린다. 그 사이에 예약 실행이 겹치면 같은
#   날짜를 두 프로세스가 동시에 받아 남의 서버를 두 배로 두드린다.
#   (실제로 겪었다.) flock 대신 mkdir 을 쓰는 이유는 macOS 기본 셸에
#   flock 이 없어서다 — mkdir 은 원자적이라 같은 일을 한다.

set -euo pipefail

PROJECT="/Users/hyukman/Pokemon_Champions"
PYTHON="/Users/hyukman/.asdf/installs/python/3.12.1/bin/python"
LOG_DIR="$HOME/Library/Logs/pokemon-champions"
LOCK="/tmp/pokemon-usage.lock"

mkdir -p "$LOG_DIR"
cd "$PROJECT"

if ! mkdir "$LOCK" 2>/dev/null; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') 이미 돌고 있습니다 ($LOCK). 건너뜁니다."
    exit 0
fi
# 어떻게 끝나든 자물쇠를 푼다. 안 풀면 다음 실행이 영영 건너뛴다.
trap 'rmdir "$LOCK" 2>/dev/null || true' EXIT

echo "───── $(date '+%Y-%m-%d %H:%M:%S') ─────"
# --backfill 이 순위(usage_rankings)도 같이 받는다. 요청 한 번이라 공짜에
# 가깝고, 이게 없으면 "가장 많이 쓰이는 포켓몬" 에 답할 자료가 없다.
"$PYTHON" -m scripts.etl.sync_usage --backfill --format Singles
echo "끝: $(date '+%H:%M:%S')"
