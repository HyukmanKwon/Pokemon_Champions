"""로컬 웹 진입점. `python web.py` 로 띄우고 http://127.0.0.1:8000 접속.

app 을 import 하지 않고 문자열 경로로 넘긴다. reload 를 쓰려면 uvicorn 이
자식 프로세스에서 직접 import 해야 하기 때문이다.

── reload 를 켜두는 이유 ──
  index.html 은 요청마다 디스크에서 다시 읽지만(app.index), 라우트는
  프로세스가 뜰 때 한 번 등록된다. 그래서 app.py 를 고치고 서버를 안 껐다
  켜면 "새 화면 + 없는 API" 라는 이상한 상태가 된다 — 탭은 보이는데
  누르면 404 가 난다. 원인을 찾기 어려운 종류의 혼란이라 아예 막아둔다.

  watchfiles 가 깔려 있으면 그걸 쓰고, 없으면 uvicorn 내장 감시로 돈다.
  둘 다 별도 설치 없이 동작한다.
"""

from pathlib import Path

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "pokemon_champions.interfaces.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        # 감시 범위를 소스로 좁힌다. 프로젝트 전체를 보면 data/images 에
        # 스프라이트가 캐시될 때마다 서버가 다시 뜬다.
        reload_dirs=[str(Path(__file__).resolve().parent / "src")],
    )
