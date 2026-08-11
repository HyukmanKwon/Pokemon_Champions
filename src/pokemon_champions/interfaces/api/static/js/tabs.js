// ═════════════════════════════════════════════════════════════
// 탭
// ═════════════════════════════════════════════════════════════
const tabs = document.getElementById("tabs");

tabs.addEventListener("click", e => {
  const btn = e.target.closest("button[data-tab]");
  if (btn) showTab(btn.dataset.tab);
});

function showTab(kind) {
  [...tabs.querySelectorAll("button")].forEach(
    b => b.classList.toggle("on", b.dataset.tab === kind));
  document.querySelectorAll(".panel").forEach(
    p => p.hidden = p.id !== `panel-${kind}`);
  // 계산기는 목록/상세 구조가 아니라 DEX 를 안 탄다.
  if (kind === "calc") Calc.init();
  else if (kind !== "team") initDex(kind);
}

// 다른 탭의 상세로 건너뛴다. 기술 상세에서 "배우는 포켓몬"을 눌렀을 때처럼
// 표를 찾아 스크롤까지 맞춰준다 — 탭만 바꾸면 어디를 눌렀는지 잃어버린다.
async function goto(kind, key) {
  showTab(kind);
  await initDex(kind);
  const st = DEX_STATE[kind];
  st.q = "";                       // 검색으로 걸러져 있으면 그 줄이 안 보인다
  st.panel.querySelector("input[type=search]").value = "";
  renderTable(kind);
  openDetail(kind, key);
  st.panel.querySelector(`tr[data-key="${CSS.escape(key)}"]`)
    ?.scrollIntoView({block: "center"});
}

