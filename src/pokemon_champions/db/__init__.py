"""DB 접근 계층. SQL은 이 폴더 밖으로 나가지 않는다."""

from .connection import connect

__all__ = ["connect"]
