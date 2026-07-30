"""문자열 정규화 — 계층 어디서나 쓰는 최소 유틸."""

import unicodedata


def normalize(text):
    """한글 입력을 NFC로 맞춘다.

    macOS에서 복사해 온 문자열은 자모가 분리된 NFD일 수 있다. 눈으로는
    같아 보이는데 '성실' != '성실' 이 되어 DB 조회가 조용히 실패한다.
    """
    return unicodedata.normalize("NFC", text.strip())
