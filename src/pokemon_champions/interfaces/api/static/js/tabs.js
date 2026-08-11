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
  // 도감 탭인지는 DEX 에 있는지로 판정한다. "team 이 아니면 도감" 으로
  // 적어두면 탭을 하나 더할 때마다 여기가 조용히 틀린다 — 실제로 도우미
  // 탭을 더했을 때 initDex("agent") 를 부를 뻔했다.
  if (kind === "calc") Calc.init();
  else if (DEX[kind]) initDex(kind);
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

