"""
pokemon class를 정의
"""
import unicodedata
from dataclasses import dataclass


def _visual_width(text):
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def _pad(text, width):
    return text + " " * (width - _visual_width(text))


STAT_LABELS = {
    "h": "체력", "a": "공격", "b": "방어",
    "c": "특수공격", "d": "특수방어", "s": "스피드",
}
STAT_ORDER = ("h", "a", "b", "c", "d", "s")


@dataclass
class Stats:
    h: int
    a: int
    b: int
    c: int
    d: int
    s: int

    def __getitem__(self, key):
        return getattr(self, key)

    def total(self):
        return self.h + self.a + self.b + self.c + self.d + self.s

@dataclass
class Pokemon:
    name: str               #string
    stats: Stats            #dict {"h":int, ..., "s":int}
    ability: str            #string
    item: str = None        #string
    rank: dict = None             #{"a":int, ..., "s": int} - -6 ~ +6, 기본 =0
    moves: list = None            #기술 4개까지
    condition: str = None   #기본은 None, "poison"등의 상태 주어질 수 o
    nature: str = None      #성격

    def __str__(self):
        labels = [STAT_LABELS[k] for k in STAT_ORDER]
        values = [str(self.stats[k]) for k in STAT_ORDER]
        widths = [_visual_width(label) + 2 for label in labels]
        header = "".join(_pad(label, w) for label, w in zip(labels, widths))
        row = "".join(_pad(value, w) for value, w in zip(values, widths))

        moves = " / ".join(self.moves) if self.moves else "없음"

        return "\n".join([
            self.name,
            header,
            row,
            self.nature or "-",
            self.item or "없음",
            self.condition or "정상",
            moves,
        ])

