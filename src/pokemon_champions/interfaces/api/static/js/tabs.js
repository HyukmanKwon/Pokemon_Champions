// ═════════════════════════════════════════════════════════════
// 탭 — 위 줄 여섯 개와, 도감 안의 네 갈래
//
// ── 두 층인 이유 ──
//   도감 네 갈래는 화면 틀이 같다(목록 + 상세). 같은 모양이 위 줄에
//   나란히 있으면 탭 줄이 "무엇을 보고 있나" 를 알려주는 대신 목록이
//   된다. 안으로 넣고 위 줄은 하는 일이 다른 것만 남긴다.
//
// ── 안쪽 칸의 id 를 안 바꾼 이유 ──
//   dex.js 가 panel-pokemon · panel-move … 를 이름으로 찾는다. 감싸는
//   칸을 하나 씌우는 일에 dex.js 를 건드릴 까닭이 없다. 대신 클래스를
//   subpanel 로 두어 showTab 의 일괄 숨김에 걸리지 않게 한다.
// ═════════════════════════════════════════════════════════════
const tabs = document.getElementById("tabs");
const dexNav = document.getElementById("dex-kinds");

const DEX_KINDS = ["pokemon", "move", "ability", "item"];

// 도감 탭을 떠났다 돌아오면 보던 갈래로 돌아온다. 늘 포켓몬으로
// 되돌리면 기술을 훑다가 계산기에 한 번 다녀올 때마다 자리를 잃는다.
let dexKind = "pokemon";

tabs.addEventListener("click", e => {
  const btn = e.target.closest("button[data-tab]");
  if (btn) showTab(btn.dataset.tab);
});

dexNav.addEventListener("click", e => {
  const btn = e.target.closest("button[data-dex]");
  if (btn) showDex(btn.dataset.dex);
});

function showTab(kind) {
  [...tabs.querySelectorAll("button")].forEach(
    b => b.classList.toggle("on", b.dataset.tab === kind));
  document.querySelectorAll(".panel").forEach(
    p => p.hidden = p.id !== `panel-${kind}`);

  // 탭마다 초기화가 다르다. "team 이 아니면 도감" 처럼 적어두면 탭을
  // 하나 더할 때마다 여기가 조용히 틀린다 — 실제로 도우미 탭을 더했을 때
  // initDex("agent") 를 부를 뻔했다.
  if (kind === "home") Home.show();
  else if (kind === "calc") Calc.init();
  else if (kind === "usage") Usage.init();
  else if (kind === "dex") showDex(dexKind);
}

// 도감 안에서 갈래를 바꾼다. 돌려주는 값은 그 갈래가 다 그려졌을 때
// 풀리는 약속이다 — goto 가 표의 줄을 찾으려면 표가 있어야 한다.
function showDex(kind) {
  dexKind = kind;
  [...dexNav.querySelectorAll("button")].forEach(
    b => b.classList.toggle("on", b.dataset.dex === kind));
  DEX_KINDS.forEach(k => {
    document.getElementById(`panel-${k}`).hidden = k !== kind;
  });
  return initDex(kind);
}

// 다른 갈래의 상세로 건너뛴다. 기술 상세에서 "배우는 포켓몬"을 눌렀을 때처럼
// 표를 찾아 스크롤까지 맞춰준다 — 갈래만 바꾸면 어디를 눌렀는지 잃어버린다.
async function goto(kind, key) {
  showTab("dex");
  await showDex(kind);
  const st = DEX_STATE[kind];
  st.q = "";                       // 검색으로 걸러져 있으면 그 줄이 안 보인다
  st.panel.querySelector("input[type=search]").value = "";
  renderTable(kind);
  openDetail(kind, key);
  st.panel.querySelector(`tr[data-key="${CSS.escape(key)}"]`)
    ?.scrollIntoView({block: "center"});
}

// 홈에서 채용률 한 마리로 건너뛴다. 도감의 goto 와 나누는 이유는 채용률이
// DEX 표에 없어서다 — 순위는 목록이 아니라 그 자체가 자료다.
async function gotoUsage(koName) {
  showTab("usage");
  await Usage.init();
  Usage.openDetail(koName);
}

// 계산기의 세 갈래 중 하나로 곧장 간다. 탭만 열면 늘 데미지가 나오는데,
// 결정력을 보러 온 사람은 거기서 갈래가 셋이라는 것을 또 찾아야 한다.
async function gotoCalc(mode) {
  showTab("calc");
  await Calc.init();
  return Calc.setMode(mode);
}
