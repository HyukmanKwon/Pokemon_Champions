"""로컬 웹 진입점. `python web.py` 로 띄우고 http://127.0.0.1:8000 접속.

--reload 를 쓰려면 문자열 경로로 넘겨야 해서 import 하지 않는다.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "pokemon_champions.interfaces.api.app:app",
        host="127.0.0.1",
        port=8000,
    )
