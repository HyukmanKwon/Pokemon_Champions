// ═════════════════════════════════════════════════════════════
// 도감 — 목록 + 상세
//
// 네 탭이 하는 일이 같다: 한 번 받아온 배열을 걸러서 표로 그리고, 한 줄을
// 누르면 상세를 받아 옆에 그린다. 그래서 탭마다 코드를 쓰지 않고
// "무엇을 어디서 받아 어느 칸으로 보여줄까"만 아래 표에 적는다.
//
// column: {key, label, cls, cell(row), sort(row)}
//   cell 은 HTML, sort 는 비교할 값. sort 가 없으면 cell 대신 쓰지 않고
//   그 칸은 정렬 불가로 둔다 — 이미지 칸까지 정렬 화살표가 붙으면 헷갈린다.
// filter: {key, label, options(rows), match(row, value)}
// ═════════════════════════════════════════════════════════════

const numCol = (key, label) => ({
  key, label, cls: "num",
  cell: r => dash(r[key]), sort: r => r[key] ?? -Infinity,
});

// 한국어 이름만 보인다. 영문 슬러그를 아래에 같이 깔면 한 줄 안에서
// 한글과 영문이 섞여 목록이 시끄러워진다. 영문으로 찾는 길은 남아 있다 —
// 각 표의 search 가 r.name 을 그대로 보고 있다.
//
// ko_name 이 없으면 영문이 나온다. 그건 섞인 것이 아니라 그 항목에
// 한국어 이름이 아직 없다는 뜻이고, 빈칸으로 두면 무엇인지 알 수 없다.
const nameCell = r => `<div>${esc(r.ko_name || r.name)}</div>`;

const DEX = {
  // ── 포켓몬 ───────────────────────────────────────────────
  pokemon: {
    url: "/api/dex/pokemons",
    detailUrl: name => `/api/dex/pokemons/${encodeURIComponent(name)}`,
    key: r => r.name,
    // 검색은 여기 적힌 것들을 이어붙여 부분일치로 본다.
    search: r => [r.ko_name, r.name, typeKo(r.type1), typeKo(r.type2)],
    columns: [
      {key: "icon", label: "", cell: r => iconImg(r.icon, r.ko_name || r.name)},
      // 보여주는 건 원종 도감 번호(pokemon_id)다. id 는 폼마다 다른
      // PokeAPI 번호라 메가가 10064 처럼 뜬다 — 그림을 찾는 데만 쓴다.
      //
      // 번호가 같은 원종·메가의 순서는 여기서 정하지 않는다. 배열 정렬이
      // 안정적이라, 서버가 준 순서(ORDER BY pokemon_id, id)가 그대로 남는다.
      {key: "pokemon_id", label: "번호", cls: "num",
       cell: r => r.pokemon_id, sort: r => r.pokemon_id},
      {key: "name", label: "이름", cell: nameCell, sort: r => nfc(r.ko_name || r.name)},
      {key: "types", label: "타입", cell: r => `<span class="type-badges">${typeBadges(r.types)}</span>`},
      ...STAT_KEYS.map((k, i) => ({
        key: k, label: STAT_SHORT[i], cls: "num",
        cell: r => r[k], sort: r => r[k],
      })),
      {key: "total", label: "합계", cls: "num",
       cell: r => bst(r), sort: r => bst(r)},
    ],
    filters: [
      {key: "type", label: "타입",
       options: () => Object.entries(TYPE_KO).map(([v, l]) => ({value: v, label: l})),
       match: (r, v) => r.type1 === v || r.type2 === v},
      {key: "form", label: "폼", options: () => [
         {value: "base", label: "원종만"}, {value: "mega", label: "메가만"},
         {value: "can", label: "메가 가능"}],
       match: (r, v) => v === "base" ? !r.is_mega
                      : v === "mega" ? r.is_mega : r.can_mega},
    ],
    detail: pokemonDetail,
  },

  // ── 기술 ─────────────────────────────────────────────────
  move: {
    url: "/api/dex/moves",
    detailUrl: name => `/api/dex/moves/${encodeURIComponent(name)}`,
    key: r => r.name,
    search: r => [r.ko_name, r.name, typeKo(r.type), CATEGORY_KO[r.category]],
    columns: [
      {key: "name", label: "이름", cell: nameCell, sort: r => nfc(r.ko_name || r.name)},
      {key: "type", label: "타입", cls: "mid",
       cell: r => j(iconImg(r.icon, typeKo(r.type), "tiny"),
                    r.icon ? "" : esc(typeKo(r.type))),
       sort: r => typeKo(r.type)},
      {key: "category", label: "분류", cls: "mid",
       cell: r => CATEGORY_KO[r.category] || dash(r.category),
       sort: r => r.category || ""},
      numCol("power", "위력"),
      numCol("accuracy", "명중"),
      numCol("pp", "PP"),
      numCol("priority", "우선도"),
    ],
    filters: [
      {key: "type", label: "타입",
       options: () => Object.entries(TYPE_KO).map(([v, l]) => ({value: v, label: l})),
       match: (r, v) => r.type === v},
      {key: "category", label: "분류",
       options: () => Object.entries(CATEGORY_KO).map(([v, l]) => ({value: v, label: l})),
       match: (r, v) => r.category === v},
    ],
    detail: moveDetail,
  },

  // ── 특성 ─────────────────────────────────────────────────
  ability: {
    url: "/api/dex/abilities",
    detailUrl: name => `/api/dex/abilities/${encodeURIComponent(name)}`,
    key: r => r.name,
    search: r => [r.ko_name, r.name, r.description],
    columns: [
      {key: "name", label: "이름", cell: nameCell, sort: r => nfc(r.ko_name || r.name)},
      {key: "description", label: "설명",
       cell: r => `<span class="sub">${esc(r.description || "")}</span>`},
    ],
    filters: [
      {key: "ko", label: "한국어 이름", options: () => [
         {value: "no", label: "없는 것만"}, {value: "yes", label: "있는 것만"}],
       match: (r, v) => v === "yes" ? !!r.ko_name : !r.ko_name},
    ],
    detail: abilityDetail,
  },

  // ── 도구 ─────────────────────────────────────────────────
  item: {
    url: "/api/dex/items",
    detailUrl: name => `/api/dex/items/${encodeURIComponent(name)}`,
    key: r => r.name,
    search: r => [r.ko_name, r.name, r.category, r.description],
    columns: [
      {key: "icon", label: "", cell: r => iconImg(r.icon, r.ko_name || r.name)},
      {key: "name", label: "이름", cell: nameCell, sort: r => nfc(r.ko_name || r.name)},
      {key: "category", label: "분류", cell: r => esc(dash(r.category)),
       sort: r => r.category || ""},
      numCol("fling_power", "던지기 위력"),
      {key: "description", label: "설명",
       cell: r => `<span class="sub">${esc((r.description || "").slice(0, 60))}</span>`},
    ],
    filters: [
      // 분류는 DB에 있는 값에서 그대로 뽑는다. 목록을 코드에 적어두면
      // ETL이 새 카테고리를 가져왔을 때 조용히 빠진다.
      {key: "category", label: "분류",
       options: rows => [...new Set(rows.map(r => r.category).filter(Boolean))]
         .sort().map(v => ({value: v, label: v})),
       match: (r, v) => r.category === v},
    ],
    detail: itemDetail,
  },
};

const bst = r => STAT_KEYS.reduce((s, k) => s + (r[k] || 0), 0);

// 탭별 화면 상태. 받아온 배열은 여기 한 번만 담고 다시 받지 않는다.
const DEX_STATE = {};

async function initDex(kind) {
  // 타입 표가 채워지기 전에 그리면 검색·정렬이 영문 슬러그로 굳는다.
  await TYPES_READY;
  if (DEX_STATE[kind]) return DEX_STATE[kind].ready;

  const spec = DEX[kind];
  const panel = document.getElementById(`panel-${kind}`);
  const st = DEX_STATE[kind] = {
    spec, panel, rows: [], q: "", filters: {},
    sort: null,          // null 이면 서버가 준 순서 그대로
    selected: null,
  };

  panel.innerHTML = `
    <div class="dex">
      <div class="dex-list">
        <div class="dex-controls">
          <input type="search" placeholder="검색 (한국어·영문)">
          ${spec.filters.map(f => `<select data-filter="${f.key}"></select>`).join("")}
          <button class="reset" type="button">초기화</button>
          <span class="count"></span>
        </div>
        <div class="table-wrap"><div class="empty">불러오는 중…</div></div>
      </div>
      <aside class="dex-detail"><div class="empty">목록에서 하나를 고르세요</div></aside>
    </div>`;

  // 검색은 입력할 때마다 다시 그린다. 서버에 묻지 않으니 부담이 없다.
  const search = panel.querySelector("input[type=search]");
  search.addEventListener("input", () => { st.q = search.value; renderTable(kind); });

  panel.querySelector(".dex-controls").addEventListener("change", e => {
    const sel = e.target.closest("select[data-filter]");
    if (!sel) return;
    st.filters[sel.dataset.filter] = sel.value;
    renderTable(kind);
  });

  panel.querySelector(".reset").addEventListener("click", () => {
    st.q = ""; st.filters = {}; st.sort = null;
    search.value = "";
    panel.querySelectorAll("select[data-filter]").forEach(s => s.value = "");
    renderTable(kind);
  });

  // 표는 통째로 다시 그려지므로 tr 마다 걸지 않고 wrap 에 한 번만 건다.
  const wrap = panel.querySelector(".table-wrap");
  wrap.addEventListener("click", e => {
    const th = e.target.closest("th[data-sort]");
    if (th) return sortBy(kind, th.dataset.sort);
    const tr = e.target.closest("tr[data-key]");
    if (tr) openDetail(kind, tr.dataset.key);
  });

  st.ready = (async () => {
    const res = await fetch(spec.url);
    st.rows = res.ok ? await res.json() : [];
    if (!res.ok) {
      wrap.innerHTML = `<div class="empty">불러오지 못했습니다 (${res.status})</div>`;
      return;
    }
    // 필터 후보는 받아온 데이터에서 만든다 (도구 분류처럼 DB에만 있는 것)
    spec.filters.forEach(f => {
      const sel = panel.querySelector(`select[data-filter="${f.key}"]`);
      sel.innerHTML = `<option value="">${esc(f.label)} 전체</option>` +
        f.options(st.rows).map(
          o => `<option value="${esc(o.value)}">${esc(o.label)}</option>`).join("");
    });
    renderTable(kind);
  })();

  return st.ready;
}

function visibleRows(kind) {
  const st = DEX_STATE[kind], spec = st.spec;
  const q = nfc(st.q).trim().toLowerCase();

  let rows = st.rows.filter(r => {
    for (const f of spec.filters) {
      const v = st.filters[f.key];
      if (v && !f.match(r, v)) return false;
    }
    if (!q) return true;
    return nfc(spec.search(r).filter(Boolean).join(" ")).toLowerCase().includes(q);
  });

  if (st.sort) {
    const col = spec.columns.find(c => c.key === st.sort.key);
    const dir = st.sort.dir;
    // slice 로 복사한 뒤 정렬한다. st.rows 를 직접 뒤집으면 "정렬 없음"
    // 으로 돌아갈 수 없다.
    rows = rows.slice().sort((x, y) => {
      const a = col.sort(x), b = col.sort(y);
      return (a < b ? -1 : a > b ? 1 : 0) * dir;
    });
  }
  return rows;
}

function renderTable(kind) {
  const st = DEX_STATE[kind], spec = st.spec;
  const rows = visibleRows(kind);
  const wrap = st.panel.querySelector(".table-wrap");

  st.panel.querySelector(".count").textContent =
    rows.length === st.rows.length
      ? `${st.rows.length}개`
      : `${rows.length} / ${st.rows.length}개`;

  if (!rows.length) {
    wrap.innerHTML = `<div class="empty">조건에 맞는 것이 없습니다</div>`;
    return;
  }

  const head = spec.columns.map(c => {
    const arrow = st.sort && st.sort.key === c.key
      ? `<span class="arrow">${st.sort.dir > 0 ? "▲" : "▼"}</span>` : "";
    const sortable = c.sort ? ` data-sort="${esc(c.key)}"` : ` style="cursor:default"`;
    return `<th class="${c.cls || ""}"${sortable}>${esc(c.label)}${arrow}</th>`;
  }).join("");

  const body = rows.map(r => {
    const key = spec.key(r);
    const on = st.selected === key ? " class=\"on\"" : "";
    const tds = spec.columns.map(
      c => `<td class="${c.cls || ""}">${c.cell(r)}</td>`).join("");
    return `<tr data-key="${esc(key)}"${on}>${tds}</tr>`;
  }).join("");

  wrap.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

// 같은 칸을 다시 누르면 방향이 뒤집히고, 세 번째에 정렬을 푼다.
// 원래 순서(도감 번호 · 가나다)로 돌아갈 방법이 없으면 답답하다.
function sortBy(kind, key) {
  const st = DEX_STATE[kind];
  if (!st.sort || st.sort.key !== key) st.sort = {key, dir: 1};
  else if (st.sort.dir === 1) st.sort.dir = -1;
  else st.sort = null;
  renderTable(kind);
}

async function openDetail(kind, key) {
  const st = DEX_STATE[kind];
  st.selected = key;
  st.panel.querySelectorAll("tr[data-key]").forEach(
    tr => tr.classList.toggle("on", tr.dataset.key === key));

  const box = st.panel.querySelector(".dex-detail");
  box.innerHTML = `<div class="empty">불러오는 중…</div>`;
  const res = await fetch(st.spec.detailUrl(key));
  if (!res.ok) {
    box.innerHTML = `<div class="empty">불러오지 못했습니다 (${res.status})</div>`;
    return;
  }
  box.innerHTML = st.spec.detail(await res.json());
  box.scrollTop = 0;
}

// 상세 안의 포켓몬·기술·도구 링크. 상세는 계속 다시 그려지므로 개별
// 요소가 아니라 body 에 한 번만 위임한다.
document.addEventListener("click", e => {
  const a = e.target.closest("[data-goto]");
  if (!a) return;
  e.preventDefault();
  goto(a.dataset.goto, a.dataset.gotoKey);
});

// ── 상세 화면 조각 ──────────────────────────────────────────

function detailHead(d, extra = "") {
  return `
    <div class="header-row">
      <h2>${esc(d.ko_name || d.name)}
        ${d.ko_name ? `<span class="en">${esc(d.name)}</span>` : ""}</h2>
      ${extra}
    </div>`;
}

function kv(pairs) {
  const shown = pairs.filter(([, v]) => v !== null && v !== undefined && v !== "");
  return shown.length
    ? `<dl class="kv">${shown.map(
        ([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>`
    : "";
}

function section(title, body) {
  return body ? `<section><h3>${esc(title)}</h3>${body}</section>` : "";
}

// 관계 목록. 어느 탭으로 건너뛸지를 data-goto 로 들고 다닌다.
function relList(kind, items, {icon, label, right, note} = {}) {
  if (!items.length) return "";
  return `<div class="rel">${items.map(o => `
    <a data-goto="${kind}" data-goto-key="${esc(o.name)}">
      ${icon ? iconImg(icon(o), "", "") : ""}
      <span>${esc(label ? label(o) : (o.ko_name || o.name))}
        ${note && note(o) ? `<span class="sub">${esc(note(o))}</span>` : ""}</span>
      ${right ? `<span class="t">${right(o)}</span>` : ""}
    </a>`).join("")}</div>`;
}

const pokemonRel = list => relList("pokemon", list, {
  icon: p => p.icon,
  right: p => typeBadges(p.types),
});

function statBars(d) {
  // 막대 길이의 기준을 255로 둔다. 종족값의 사실상 상한이라 여기에 맞추면
  // 다른 포켓몬을 열었을 때도 막대 길이를 그대로 비교할 수 있다.
  return `<div class="bars">${STAT_KEYS.map((k, i) => `
    <span class="bl">${STAT_LABELS[i]}</span>
    <span class="bv">${d[k]}</span>
    <span class="bar"><i style="width:${Math.min(100, d[k] / 255 * 100)}%"></i></span>
  `).join("")}
    <span class="bl">합계</span><span class="bv">${bst(d)}</span><span></span>
  </div>`;
}

function pokemonDetail(d) {
  const abilities = d.abilities.map(a => `
    <p><a data-goto="ability" data-goto-key="${esc(a.name)}"
          style="cursor:pointer;text-decoration:underline">${esc(a.ko_name || a.name)}</a>
      ${a.is_hidden ? `<span class="chip">숨은 특성</span>` : ""}
      <span class="eff sub"> ${esc(a.description || "")}</span></p>`).join("");

  const megaLine = o => `
    <p><a data-goto="pokemon" data-goto-key="${esc(o.mega_name || o.base_name)}"
          style="cursor:pointer;text-decoration:underline">${esc(
      o.mega_ko_name || o.base_ko_name || o.mega_name || o.base_name)}</a>
      ${o.variant ? `<span class="chip">${esc(o.variant.toUpperCase())}</span>` : ""}
      ${o.item_name ? `— ${iconImg(o.item_icon, "", "tiny")}
        <a data-goto="item" data-goto-key="${esc(o.item_name)}"
           style="cursor:pointer;text-decoration:underline">${esc(
          o.item_ko_name || o.item_name)}</a>` : ""}</p>`;

  const moves = d.moves.map(m => `
    <a data-goto="move" data-goto-key="${esc(m.name)}">
      ${iconImg(m.icon, typeKo(m.type), "tiny")}
      <span>${esc(m.ko_name || m.name)}</span>
      <span class="t sub">${esc(CATEGORY_KO[m.category] || "")} ${
        m.power ? `위력 ${m.power}` : ""}</span>
    </a>`).join("");

  return j(
    detailHead(d, `<span class="type-badges">${typeBadges(d.types)}</span>`),
    d.sprite ? `<div class="sprite-wrap">${iconImg(d.sprite, d.ko_name || d.name, "")}</div>` : "",
    kv([
      ["도감 번호", d.pokemon_id],
      ["신장", d.height != null ? `${d.height} m` : ""],
      ["체중", d.weight != null ? `${d.weight} kg` : ""],
      ["폼", j(d.is_mega ? `<span class="chip">메가진화</span>` : "",
               d.can_mega ? `<span class="chip ok">메가진화 가능</span>` : "") || "원종"],
    ]),
    section("종족값", statBars(d)),
    section("특성", abilities),
    section(d.is_mega ? "원종" : "메가진화",
      j(d.mega_of ? megaLine(d.mega_of) : "",
        d.mega_forms.map(megaLine).join(""))),
    section(`배울 수 있는 기술 (${d.moves.length})`,
      d.moves.length ? `<div class="rel">${moves}</div>` : ""),
  );
}

function moveDetail(d) {
  const flags = Object.entries(MOVE_FLAGS)
    .filter(([k]) => d[k]).map(([, l]) => `<span class="chip">${l}</span>`).join("");

  // 능력 변화가 누구에게 걸리는지는 meta_category 가 정한다 (schema.py 주석).
  const target = d.meta_category === "damage-lower" ? "상대" : "자신";
  const changes = d.stat_changes.map(c =>
    `<span class="chip ${c.change > 0 ? "ok" : "warn"}">${
      esc(STAT_KO[c.stat] || c.stat)} ${c.change > 0 ? "+" : ""}${c.change}</span>`).join("");

  return j(
    detailHead(d, `<span class="type-badges">${
      d.icon ? iconImg(d.icon, typeKo(d.type), "tiny") : esc(typeKo(d.type))}</span>`),
    d.description ? `<p>${esc(d.description)}</p>` : "",
    d.effect ? `<p class="eff">${esc(d.effect)}</p>` : "",
    kv([
      ["타입", esc(typeKo(d.type))],
      ["분류", esc(CATEGORY_KO[d.category] || dash(d.category))],
      ["위력", dash(d.power)],
      ["명중", d.accuracy == null ? "필중" : d.accuracy],
      ["PP", dash(d.pp)],
      ["우선도", dash(d.priority)],
      ["대상", esc(dash(d.target))],
      ["연속타수", d.min_hits ? `${d.min_hits}~${d.max_hits}` : ""],
    ]),
    section("부가 효과", kv([
      ["상태이상", d.ailment && d.ailment !== "none"
        ? `${esc(d.ailment)} ${d.ailment_chance ? `${d.ailment_chance}%` : "(확정)"}` : ""],
      ["풀죽음", d.flinch_chance ? `${d.flinch_chance}%` : ""],
      ["급소 보정", d.crit_rate ? `+${d.crit_rate}단계` : ""],
      ["흡수/반동", d.drain ? `${d.drain}%` : ""],
      ["회복", d.healing ? `${d.healing}%` : ""],
      ["능력 변화 확률", d.stat_chance ? `${d.stat_chance}%` : ""],
      ["능력 변화", changes ? `${changes} <span class="sub">(${target})</span>` : ""],
    ])),
    section("플래그", flags),
    section(`배우는 포켓몬 (${d.learners.length})`, pokemonRel(d.learners)),
  );
}

function abilityDetail(d) {
  const normal = d.pokemons.filter(p => !p.is_hidden);
  const hidden = d.pokemons.filter(p => p.is_hidden);
  return j(
    detailHead(d),
    d.description ? `<p>${esc(d.description)}</p>` : "",
    d.effect ? `<p class="eff">${esc(d.effect)}</p>` : "",
    section(`보통 특성 (${normal.length})`, pokemonRel(normal)),
    section(`숨은 특성 (${hidden.length})`, pokemonRel(hidden)),
    d.pokemons.length ? "" :
      `<p class="eff">이 특성을 가진 포켓몬이 DB에 없습니다.</p>`,
  );
}

function itemDetail(d) {
  const m = d.mega;
  return j(
    detailHead(d, d.icon ? iconImg(d.icon, d.ko_name || d.name, "") : ""),
    d.description ? `<p>${esc(d.description)}</p>` : "",
    d.effect ? `<p class="eff">${esc(d.effect)}</p>` : "",
    kv([
      ["분류", esc(dash(d.category))],
      ["던지기 위력", dash(d.fling_power)],
    ]),
    m ? section("메가진화", `
      <p>
        <a data-goto="pokemon" data-goto-key="${esc(m.base_name)}"
           style="cursor:pointer;text-decoration:underline">${esc(m.base_ko_name || m.base_name)}</a>
        →
        <a data-goto="pokemon" data-goto-key="${esc(m.mega_name)}"
           style="cursor:pointer;text-decoration:underline">${esc(m.mega_ko_name || m.mega_name)}</a>
        ${m.variant ? `<span class="chip">${esc(m.variant.toUpperCase())}</span>` : ""}
      </p>`) : "",
  );
}

