// ═════════════════════════════════════════════════════════════
// 채용률 — 메타 순위표와 한 마리의 채용 내역
//
// 도감(dex.js)과 모양은 닮았지만 접어 두지 않는다. 도감은 네 탭이 "목록 ->
// 상세" 로 똑같아서 DEX 표 하나로 묶였는데, 여기는 목록이 순위이고 상세가
// 여섯 갈래의 비율이라 겹치는 것이 화면 틀뿐이다. 억지로 묶으면 DEX 에
// "순위인가?" 같은 깃발이 생긴다.
//
// 목록은 한 번만 받아 들고 있는다. 235줄이라 검색은 브라우저에서 거른다 —
// 글자마다 서버에 물으면 느리고 서버도 할 일이 없다.
// ═════════════════════════════════════════════════════════════

const Usage = (() => {
  const state = {panel: null, rows: [], q: "", selected: null, ready: null,
                 date: null, comparedTo: null};

  async function init() {
    if (state.ready) return state.ready;
    await TYPES_READY;

    state.panel = document.getElementById("panel-usage");
    state.panel.innerHTML = `
      <div class="dex">
        <div class="dex-list">
          <div class="dex-controls">
            <input type="search" placeholder="검색 (한국어·영문)">
            <span class="count"></span>
          </div>
          <div class="table-wrap"><div class="empty">불러오는 중…</div></div>
        </div>
        <aside class="dex-detail">
          <div class="empty">순위에서 하나를 고르세요</div>
        </aside>
      </div>`;

    const search = state.panel.querySelector("input[type=search]");
    search.addEventListener("input", () => {
      state.q = search.value;
      renderTable();
    });

    state.panel.querySelector(".table-wrap").addEventListener("click", e => {
      const tr = e.target.closest("tr[data-key]");
      if (tr) openDetail(tr.dataset.key);
    });

    state.ready = load();
    return state.ready;
  }

  async function load() {
    const res = await fetch("/api/usage");
    const data = await res.json();
    state.rows = data.ranking || [];
    state.date = data.date;
    state.comparedTo = data.compared_to;
    renderTable();
  }

  // 검색은 한국어와 영문 둘 다 본다. 사용자가 "garchomp" 로도 "한카" 로도
  // 찾는다 — 한쪽만 걸면 나머지 절반이 "없다" 를 본다.
  function match(r) {
    const q = nfc(state.q).trim().toLowerCase();
    if (!q) return true;
    return nfc(r.ko_name).toLowerCase().includes(q)
        || String(r.name || "").toLowerCase().includes(q);
  }

  // 순위 변화. 오른 만큼 양수로 오므로 여기서 뒤집지 않는다.
  function deltaCell(d) {
    if (d === null || d === undefined) return `<td class="delta"></td>`;
    if (d === 0) return `<td class="delta same">—</td>`;
    const up = d > 0;
    return `<td class="delta ${up ? "up" : "down"}">`
         + `${up ? "▲" : "▼"}${Math.abs(d)}</td>`;
  }

  function renderTable() {
    const shown = state.rows.filter(match);
    const wrap = state.panel.querySelector(".table-wrap");
    state.panel.querySelector(".count").textContent =
      `${shown.length} / ${state.rows.length}`;

    if (!shown.length) {
      wrap.innerHTML = `<div class="empty">찾는 포켓몬이 없습니다</div>`;
      return;
    }

    wrap.innerHTML = `
      <table class="dex-table usage-table">
        <thead><tr>
          <th class="num">순위</th><th colspan="2">포켓몬</th><th>타입</th>
          <th class="num" title="${esc(state.comparedTo || "")} 대비">순위 변동</th>
        </tr></thead>
        <tbody>${shown.map(r => `
          <tr data-key="${esc(r.ko_name)}"
              class="${state.selected === r.ko_name ? "on" : ""}">
            <td class="num">${r.position}</td>
            <td class="pic">${iconImg(r.icon, r.ko_name)}</td>
            <td>${esc(r.ko_name)}</td>
            <td><span class="type-badges">${(r.types || []).map(t =>
                   iconImg(t.icon, typeKo(t.name), "")).join("")}</span></td>
            ${deltaCell(r.delta)}
          </tr>`).join("")}</tbody>
      </table>`;
  }

  // 갈래 하나를 "이름 비율" 줄로. percent 가 없는 갈래(팀원)도 있어서
  // 그때는 이름만 그린다 — 저쪽이 안 주는 값을 0 으로 만들지 않는다.
  function bars(rows) {
    if (!rows || !rows.length) return `<div class="empty">자료 없음</div>`;
    return `<ol class="usage-bars">${rows.map(r => `
      <li>
        ${r.icon ? iconImg(r.icon, r.name) : ""}
        <span class="nm">${esc(r.name)}</span>
        ${r.percent === null || r.percent === undefined ? ""
          : `<span class="bar"><i style="width:${Math.min(r.percent, 100)}%"></i></span>
             <span class="pct">${r.percent}%</span>`}
      </li>`).join("")}</ol>`;
  }

  // 성격만 칸이 넷이라(이름 · 보정 · 막대 · 비율) 좁은 칸에서 막대가
  // 눌린다. "특수공격" 을 "특공" 으로 줄여 자리를 낸다 — 내 팀 화면이
  // 쓰는 STAT_SHORT 와 같은 말이라 한 낱말이 두 모양으로 안 보인다.
  const SHORT = {"특수공격": "특공", "특수방어": "특방"};
  const shortStat = s => SHORT[s] || s;

  function natures(rows) {
    if (!rows.length) return `<div class="empty">자료 없음</div>`;
    return `<ol class="usage-bars">${rows.map(r => `
      <li>
        <span class="nm">${esc(r.name)}</span>
        <span class="sub">${r.up
          ? `${esc(shortStat(r.up))}↑ ${esc(shortStat(r.down))}↓` : "무보정"}</span>
        <span class="bar"><i style="width:${Math.min(r.percent, 100)}%"></i></span>
        <span class="pct">${r.percent}%</span>
      </li>`).join("")}</ol>`;
  }

  function spreads(rows) {
    if (!rows.length) return `<div class="empty">자료 없음</div>`;
    return `<ol class="usage-bars">${rows.map(r => `
      <li>
        <span class="nm mono">${r.spread.join(" / ")}</span>
        <span class="bar"><i style="width:${Math.min(r.percent, 100)}%"></i></span>
        <span class="pct">${r.percent}%</span>
      </li>`).join("")}</ol>`;
  }

  async function openDetail(koName) {
    state.selected = koName;
    renderTable();

    const box = state.panel.querySelector(".dex-detail");
    box.innerHTML = `<div class="empty">불러오는 중…</div>`;

    const res = await fetch(`/api/usage/${encodeURIComponent(koName)}`);
    if (!res.ok) {
      // 아직 안 받은 포켓몬이다. 빈 목록으로 그리면 "0%" 로 읽혀서,
      // 안 쓰인다는 뜻인지 우리가 안 받았다는 뜻인지 구별이 안 된다.
      const err = await res.json().catch(() => ({}));
      box.innerHTML = `<div class="empty">${esc(err.detail || "받지 못했습니다")}</div>`;
      return;
    }
    const d = await res.json();

    box.innerHTML = `
      <header class="usage-head">
        ${iconImg(d.sprite, d.ko_name, "sprite")}
        <div class="who">
          <div class="line">
            <h3>${esc(d.ko_name)}</h3>
            <span class="rank">${d.meta_rank}위</span>
          </div>
          <span class="type-badges">${(d.types || []).map(t =>
            iconImg(t.icon, typeKo(t.name), "")).join("")}</span>
        </div>
        <span class="sub">${esc(d.date)} · ${esc(d.format)}</span>
      </header>
      <div class="usage-cols">
        <section><h4>기술</h4>${bars(d.moves)}</section>
        <section><h4>도구</h4>${bars(d.items)}</section>
        <section><h4>특성</h4>${bars(d.abilities)}</section>
        <section><h4>성격</h4>${natures(d.natures)}</section>
        <section><h4>SP 배분<span class="sub">체/공/방/특공/특방/스피드</span></h4>
                 ${spreads(d.spreads)}</section>
        <section><h4>같이 쓰는 포켓몬</h4>${bars(d.teammates)}</section>
      </div>
      <p class="usage-source">${esc(d.source)}</p>`;
  }

  return {init, openDetail};
})();
