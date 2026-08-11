// ═════════════════════════════════════════════════════════════
// 공통
// ═════════════════════════════════════════════════════════════
const STAT_LABELS = ["체력", "공격", "방어", "특수공격", "특수방어", "스피드"];
// 표 머리글용 줄임말. 앞 두 글자로 자르면 특수공격과 특수방어가 둘 다
// "특수"가 되어 어느 칸인지 구별할 수 없다.
const STAT_SHORT = ["체력", "공격", "방어", "특공", "특방", "스피드"];
const STAT_KEYS = ["h", "a", "b", "c", "d", "s"];

// 능력 변화(move_stat_changes.stat)는 명중·회피도 쓴다. 여섯 칸과 별개다.
const STAT_KO = {
  h: "체력", a: "공격", b: "방어", c: "특수공격", d: "특수방어", s: "스피드",
  acc: "명중률", eva: "회피율",
};

// DB는 타입을 영문 enum으로 들고 있다. 화면에만 한국어를 씌운다 —
// 타입의 한국어 표기. 여기 적어두면 검색창에 "불꽃"을 쳐도 걸리는데,
// 그러면 DB 의 pokemon_type_names 와 두 벌이 되어 표기를 다듬을 때
// 한쪽만 고치게 된다. 그래서 비워두고 부팅 때 받아 채운다.
//
// const 인 채로 내용만 채우는 이유는, 이 객체를 참조하는 코드가 이미
// 여기저기 있기 때문이다. 통째로 갈아끼우면 먼저 잡아둔 참조가 빈 객체를
// 계속 본다.
const TYPE_KO = {};

const TYPES_READY = fetch("/api/types")
  .then(r => r.json())
  .then(rows => rows.forEach(t => { TYPE_KO[t.name] = t.ko_name; }));
const CATEGORY_KO = { physical: "물리", special: "특수", status: "변화" };

// 기술 플래그. true인 것만 배지로 띄운다.
const MOVE_FLAGS = {
  is_contact: "접촉", is_punch: "펀치", is_bite: "물기", is_sound: "소리",
  is_powder: "가루", is_bullet: "구슬", is_wind: "바람", is_slicing: "베기",
  is_dance: "춤", is_pulse: "파동", is_gravity: "중력영향", is_press: "누르기",
};

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g,
    c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}
const nfc = s => String(s ?? "").normalize("NFC");
const dash = v => (v === null || v === undefined || v === "") ? "—" : v;
const typeKo = t => TYPE_KO[t] || t || "";
const j = (...xs) => xs.filter(Boolean).join("");

// 타입 배지. icon 이 없는 폼도 있으므로 그때는 이름을 글자로 보여준다.
function typeBadge(type) {
  return type.icon
    ? `<img src="${type.icon}" alt="${esc(typeKo(type.name))}" title="${esc(typeKo(type.name))}" loading="lazy">`
    : esc(typeKo(type.name));
}
const typeBadges = ts => (ts || []).map(typeBadge).join("");

// 목록 아이콘. src 를 못 받아오면(저장소에 없는 폼) 그 자리를 비운다.
function iconImg(url, alt, cls = "icon") {
  return url
    ? `<img class="${cls}" src="${url}" alt="${esc(alt)}" loading="lazy"
            onerror="this.style.visibility='hidden'">`
    : "";
}

