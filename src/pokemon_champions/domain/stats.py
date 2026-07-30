"""능력치 6칸을 담는 값 객체.

종족값·SP 투자값·실능치가 전부 같은 모양이라 한 타입으로 쓴다.
"""

from dataclasses import dataclass

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

    def as_dict(self):
        return {k: self[k] for k in STAT_ORDER}
