"""DB 접근 계층. SQL은 이 폴더 밖으로 나가지 않는다."""

from .connection import connect, connection

# connection 도 같이 내보낸다. 안 내보내면 `from ..db import connection` 이
# 함수가 아니라 같은 이름의 모듈을 집어온다 — import 는 통과하고 부를 때야
# "module object is not callable" 로 터진다. 찾기 어려운 종류의 실수다.
__all__ = ["connect", "connection"]
