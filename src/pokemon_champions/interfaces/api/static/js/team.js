// ═════════════════════════════════════════════════════════════
// 내 팀 — 기존 화면 그대로
// ═════════════════════════════════════════════════════════════
const grid = document.getElementById("grid");

// 슬롯별 메가 On/Off 상태. 서버에 보낼 값이 아니라 화면 상태라 여기 둔다.
// 메가 여부는 스펙(엔트리)이 아니라 배틀 중 상태이므로 저장하지 않는다.
const megaOn = new Map();

function statGrid(stats, compare) {
  const labels = STAT_KEYS.map(k => `<div class="label">${STAT_LABELS[STAT_KEYS.indexOf(k)]}</div>`).join("");
  const values = STAT_KEYS.map(k => {
    if (!compare) return `<div class="value">${stats[k]}</div>`;
    // 메가일 때는 원종 대비 증감을 같이 보여준다
    const diff = stats[k] - compare[k];
    const dir = diff > 0 ? "up" : "down";
    const mark = diff === 0 ? ""
      : `<span class="delta ${dir}">${diff > 0 ? "↑" : "↓"}${Math.abs(diff)}</span>`;
    // 숫자도 화살표와 같은 색으로. 오른 능력치가 파랗게 보이면 안 된다.
    return `<div class="value ${diff ? `changed ${dir}` : ""}">${stats[k]}${mark}</div>`;
  }).join("");
  return `<div class="stat-grid">${labels}${values}</div>`;
}

function megaBar(slot, on) {
  // 스톤을 지녔으면 버튼, 메가는 있는데 스톤이 없으면 안내, 둘 다 아니면 아무것도.
  if (slot.mega) {
    return `<div class="mega-bar">
      <button class="mega-toggle ${on ? "on" : ""}" data-mega>
        메가진화 ${on ? "ON" : "OFF"}
      </button>
      <span>${slot.mega.name}</span>
    </div>`;
  }
  if (slot.mega_stones && slot.mega_stones.length) {
    const names = slot.mega_stones
      .map(s => `${s.item_ko_name}(${s.mega_ko_name})`).join(" 또는 ");
    return `<div class="mega-hint">${names} 을(를) 지니면 메가진화할 수 있습니다</div>`;
  }
  return "";
}

function card(slot) {
  const el = document.createElement("div");
  el.className = "card";
  el.dataset.index = slot.index;
  el.innerHTML = `
    <div class="info"></div>
    <div class="edit">
      <div class="field">
        <label>이름</label>
        ${combo(`<input data-field="ko_name" data-combo="pokemon" type="text">`)}
      </div>
      <div class="field">
        <label>SP (H A B C D S)</label>
        <div class="sp-input-row">
          ${[0,1,2,3,4,5].map(i => `<input data-field="sp_values" data-sp="${i}" type="number" min="0">`).join("")}
        </div>
      </div>
      <div class="field">
        <label>성격</label>
        ${combo(`<input data-field="ko_nature" data-combo="nature" type="text">`)}
      </div>
      <div class="field">
        <label>특성</label>
        ${combo(`<input data-field="ability" data-combo="ability" type="text">`)}
      </div>
      <div class="field">
        <label>도구</label>
        ${combo(`<input data-field="item" data-combo="item" type="text">`)}
      </div>
      <div class="field">
        <label>기술 (최대 4개)</label>
        <div class="moves-input-row">
          ${[0,1,2,3].map(i => combo(
            `<input data-field="moves" data-move="${i}" data-combo="move" type="text">`
          )).join("")}
        </div>
      </div>
      <div class="error"></div>
    </div>
  `;
  fill(el, slot);

  el.querySelectorAll("[data-field]").forEach(input => {
    input.addEventListener("change", () => onEdit(el, input.dataset.field));
  });
  el.querySelectorAll("[data-combo]").forEach(
    input => setupCombo(input, () => CHOICES[input.dataset.combo](el._slot)));

  // 메가 버튼은 fill() 이 .info 를 통째로 갈아끼울 때마다 사라지므로,
  // 버튼이 아니라 카드에 한 번만 걸고 위임한다.
  el.addEventListener("click", e => {
    if (!e.target.closest("[data-mega]")) return;
    megaOn.set(el._slot.index, !megaOn.get(el._slot.index));
    fill(el, el._slot);   // 서버에 다시 묻지 않는다. 두 벌 다 이미 받아뒀다
  });

  return el;
}

// 성격 보정. 성실은 오르는 것도 내리는 것도 없다.
function natureArrows(nature) {
  if (!nature.up && !nature.down) return `<span class="label">보정 없음</span>`;
  return [
    nature.up ? `<span class="up">↑${esc(nature.up)}</span>` : "",
    nature.down ? `<span class="down">↓${esc(nature.down)}</span>` : "",
  ].join(" ");
}

// ─────────────────────────────────────────────────────────────
// 후보 목록 — 칸 아래에 직접 그리는 드롭다운
//
// <datalist> 를 쓰지 않는 이유가 둘이다. 위치를 브라우저가 정해서 칸 옆에
// 뜨기도 하고, 무엇보다 칸에 값이 있으면 그 값으로 목록을 걸러 버린다.
// 이미 채워둔 기술을 다른 것으로 바꾸려 할 때 후보가 하나도 안 뜬다.
// ─────────────────────────────────────────────────────────────

function combo(inputHtml) {
  return `<div class="combo">${inputHtml}<div class="combo-list"></div></div>`;
}

// 슬롯을 가리지 않는 것들. load() 에서 한 번만 받는다.
let POKEMONS = [];
let ITEMS = [];
let NATURES = [];

// data-combo 이름 -> 후보 [{value, hint}]
const CHOICES = {
  pokemon: () => POKEMONS.map(v => ({value: v})),
  nature: () => NATURES.map(n => ({
    value: n.name,
    hint: n.up || n.down ? `↑${n.up || "-"} ↓${n.down || "-"}` : "보정 없음",
  })),
  ability: slot => (slot.selectable_abilities || []).map(v => ({value: v})),
  move: slot => (slot.learnable_moves || []).map(v => ({value: v})),
  item: slot => {
    // 도구는 전역 목록 하나면 되지만, 메가스톤만은 포켓몬을 가린다.
    // 그 슬롯 것만 맨 위에 따로 올린다.
    const stones = (slot.mega_stones || [])
      .map(s => ({value: s.item_ko_name, hint: `${s.mega_ko_name} 메가스톤`}));
    const held = slot.spec.item ? [{value: nfc(slot.spec.item)}] : [];
    const seen = new Set();
    return [...stones, ...held, ...ITEMS.map(v => ({value: v}))]
      .filter(o => o.value && !seen.has(nfc(o.value)) && seen.add(nfc(o.value)));
  },
};

function renderChoices(list, choices) {
  list.innerHTML = choices.length
    ? choices.map(o => `<div data-value="${esc(o.value)}">${esc(o.value)}${
        o.hint ? `<span class="hint">${esc(o.hint)}</span>` : ""}</div>`).join("")
    : `<div class="none">후보가 없습니다</div>`;
}

// getChoices 는 () => [{value, hint}] 를 주는 함수다. 카드를 받지 않는
// 이유는 계산기도 같은 콤보를 쓰기 때문이다 — 슬롯 개념이 없는 화면에
// 슬롯을 넘기게 만들면 콤보가 두 벌이 된다.
function setupCombo(input, getChoices) {
  const box = input.closest(".combo");
  const list = box.querySelector(".combo-list");

  // filter 가 false 면 칸에 든 값을 무시하고 전부 보여준다. 저장된 기술을
  // 바꾸려고 칸을 눌렀을 때 후보가 사라지지 않게 하려는 것이다.
  function open(filter) {
    // 잠긴 칸(메가폼의 도구)은 목록을 열지 않는다. 열어두면 readOnly 라
    // 타이핑은 막혀 있는데 클릭으로는 바뀌는 반쪽짜리가 된다.
    if (input.readOnly) return;
    const all = getChoices();
    const q = filter ? nfc(input.value).trim().toLowerCase() : "";
    renderChoices(list, q
      ? all.filter(o => nfc(o.value).toLowerCase().includes(q))
      : all);
    box.classList.add("open");
    list.scrollTop = 0;
  }

  const close = () => box.classList.remove("open");
  const rows = () => [...list.querySelectorAll("div[data-value]")];

  function pick(value) {
    close();
    // ── 왜 다음 틱으로 미루나 ──
    //   한글은 조합 중에 Enter 를 누르면, 브라우저가 조합 중이던 글자를
    //   확정해 칸에 밀어 넣는다. 그 확정이 우리 대입보다 늦게 일어나서
    //   "메가갸" 로 고른 결과가 "메가갸라도스" + "갸" 가 된다.
    //   한 틱 미루면 확정이 끝난 뒤에 값을 통째로 덮어쓴다.
    setTimeout(() => {
      input.value = value;
      // bubbles 가 꼭 있어야 한다. new Event("change") 는 기본이 false 라
      // 칸에 직접 건 리스너에만 닿는다. 계산기는 위임으로 받으므로, 이게
      // 없으면 목록에서 고른 것이 전달되지 않는다.
      input.dispatchEvent(new Event("change", {bubbles: true}));
    }, 0);
  }

  // 칸에 들어올 때 들어 있던 값을 통째로 고른다. 바로 치면 갈아끼워진다.
  // 고쳐 쓰는 일보다 다른 것으로 바꾸는 일이 훨씬 잦은 칸들이다.
  //
  // mouseup 을 막는 이유: focus 는 mouseup 보다 먼저 오고, 그 mouseup 이
  // 방금 잡아둔 선택을 커서 하나로 되돌린다. 처음 들어올 때 한 번만
  // 막는다 — 계속 막으면 드래그로 일부만 고르는 일이 영영 안 된다.
  let entering = false;
  input.addEventListener("focus", () => {
    entering = true;
    input.select();
    open(false);
  });
  input.addEventListener("mouseup", e => {
    if (entering) { e.preventDefault(); entering = false; }
  });
  // 이미 포커스가 있는 칸을 다시 눌렀을 때도 열려야 한다. Esc 로 닫고 나면
  // focus 는 다시 일어나지 않아서, 이게 없으면 목록을 못 여는 칸이 생긴다.
  input.addEventListener("click", () => open(false));
  input.addEventListener("input", () => open(true));
  input.addEventListener("blur", () => setTimeout(close, 120));

  input.addEventListener("keydown", e => {
    const items = rows();
    const at = items.findIndex(r => r.classList.contains("on"));
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!box.classList.contains("open")) return open(false);
      const next = e.key === "ArrowDown"
        ? Math.min(at + 1, items.length - 1) : Math.max(at - 1, 0);
      items.forEach((r, i) => r.classList.toggle("on", i === next));
      items[next]?.scrollIntoView({block: "nearest"});
    } else if (e.key === "Enter") {
      // 화살표로 고른 게 있으면 그것, 없으면 걸러진 목록의 첫 줄.
      //
      // 예전에는 at >= 0 일 때만 골랐다. 그래서 "먹다남"까지 치고 Enter 를
      // 누르면 아무 일도 안 일어났고, 후보가 한 줄만 남아 있어도 굳이
      // 아래 화살표를 한 번 눌러야 했다.
      const row = at >= 0 ? items[at] : items[0];
      if (row && box.classList.contains("open")) {
        e.preventDefault();
        pick(row.dataset.value);
      }
    } else if (e.key === "Escape") {
      close();
    }
  });

  // click 은 blur 뒤에 와서 목록이 이미 닫힌다. mousedown 으로 먼저 잡는다.
  list.addEventListener("mousedown", e => {
    const row = e.target.closest("div[data-value]");
    if (!row) return;
    e.preventDefault();
    pick(row.dataset.value);
  });
}

function fill(el, slot) {
  el._slot = slot;   // 토글할 때 서버에 다시 묻지 않으려고 들고 있는다

  // 스톤을 뺐는데 메가 ON 이 남아 있으면 안 되므로, mega 가 없으면 강제로 끈다
  const on = !!slot.mega && megaOn.get(slot.index) === true;
  if (!slot.mega) megaOn.delete(slot.index);
  el.classList.toggle("mega-on", on);

  // 메가일 때 바뀌는 것: 종족값 · 타입 · 특성. SP 와 성격은 그대로다.
  const view = on ? slot.mega : slot;
  const base = on ? slot.mega.base : slot.base;
  const stats = on ? slot.mega.stats : slot.stats;
  const ability = on ? slot.mega.ability : slot.ability;

  el.querySelector(".info").innerHTML = `
    <div class="header-row">
      <h2 class="name">${view.name}</h2>
      <div class="type-badges">${view.types.map(typeBadge).join("")}</div>
    </div>
    ${megaBar(slot, on)}
    ${view.sprite ? `<div class="sprite-wrap"><img src="${view.sprite}" alt="${view.name}"></div>` : ""}

    <div class="stat-block">
      <div class="stat-title">종족값 <span class="total">합계 ${base.total}</span></div>
      ${statGrid(base, on ? slot.base : null)}
    </div>

    <div class="stat-block">
      <div class="stat-title">SP 투자량 <span class="total">합계 ${slot.sp.total}</span></div>
      ${statGrid(slot.sp)}
    </div>

    <div class="stat-block">
      <div class="stat-title">실제 능력치</div>
      ${statGrid(stats, on ? slot.stats : null)}
    </div>

    <div class="line nature-line">
      <span class="label">성격</span>${slot.nature.name} ${natureArrows(slot.nature)}
    </div>
    <div class="line ability-line">
      <span class="label">특성</span><span class="${on ? "changed" : ""}">${ability.name}</span>
      <span class="effect">${ability.effect || ""}</span>
    </div>
    <div class="line item-line"><span class="label">지닌 도구</span>${slot.item}</div>
    <div class="line condition-line"><span class="label">상태</span>${slot.condition}</div>

    <div class="stat-block">
      <div class="stat-title">기술</div>
      ${slot.moves.length ? slot.moves.map(m => `
        <div class="move-row">
          <span>${m.name}</span>
          ${m.icon ? `<img src="${m.icon}" alt="${m.type}">` : `<span>${m.type}</span>`}
        </div>
      `).join("") : `<div class="move-row">없음</div>`}
    </div>
  `;

  // 후보 목록은 열 때마다 el._slot 에서 새로 만든다. PATCH 응답이 슬롯
  // 전체를 주므로 이름을 바꾸면 다음에 열 때 새 포켓몬 목록이 나온다.

  // 메가는 특성이 고정이라 고를 수 있는 것이 없다.
  el.querySelector('[data-field="ability"]').disabled = on;

  el.querySelector('[data-field="ko_name"]').value = slot.spec.ko_name;
  el.querySelector('[data-field="ko_nature"]').value = slot.spec.ko_nature;
  el.querySelector('[data-field="ability"]').value = slot.spec.ability;
  el.querySelector('[data-field="item"]').value = slot.spec.item || "";
  el.querySelectorAll('[data-sp]').forEach(input => {
    input.value = slot.spec.sp_values[+input.dataset.sp];
  });
  el.querySelectorAll('[data-move]').forEach(input => {
    input.value = slot.spec.moves[+input.dataset.move] || "";
  });
  el.querySelector(".error").textContent = "";
}

function valueFor(el, field) {
  if (field === "sp_values") {
    return [...el.querySelectorAll('[data-sp]')].map(i => parseInt(i.value || "0", 10));
  }
  if (field === "moves") {
    return [...el.querySelectorAll('[data-move]')].map(i => i.value.trim()).filter(Boolean);
  }
  return el.querySelector(`[data-field="${field}"]`).value;
}

// 이름을 바꾸면 특성·기술이 새 포켓몬 것이 아니게 된다. 검증은 스펙 전체를
// 보므로 이름만 따로 보내면 반드시 거부된다. 그래서 새 포켓몬의 목록을 먼저
// 받아 특성을 첫 것으로 채우고 기술을 비운 뒤, 셋을 한 번에 보낸다.
async function renameBody(el, ko_name) {
  const res = await fetch(`/api/pokemon/${encodeURIComponent(ko_name)}/options`);
  if (!res.ok) {
    const data = await res.json();
    return {error: data.detail || "존재하지 않는 포켓몬"};
  }
  const opts = await res.json();
  el.querySelectorAll("[data-move]").forEach(i => i.value = "");
  return {ko_name, ability: opts.selectable_abilities[0] || "", moves: []};
}

async function onEdit(el, field) {
  const index = el.dataset.index;
  let body = {};
  body[field] = valueFor(el, field);

  // 서버는 NFC 로 정규화해 저장한다. 맥에서 온 분해형 한글을 그대로 비교하면
  // 같은 이름인데 바뀐 것으로 보여 기술이 지워진다.
  if (field === "ko_name" && nfc(body.ko_name) !== nfc(el._slot.spec.ko_name)) {
    body = await renameBody(el, body.ko_name);
    if (body.error) {
      el.querySelector(".error").textContent = body.error;
      return;
    }
  }

  const res = await fetch(`/api/team/${index}`, {
    method: "PATCH",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  const data = await res.json();

  if (!res.ok) {
    el.querySelector(".error").textContent = data.detail || "수정 실패";
    return;
  }
  fill(el, data);
}

async function load() {
  // 포켓몬·도구·성격 목록은 슬롯을 가리지 않는다. 여섯 번 받을 이유가
  // 없어서 여기서 한 번만 받아 카드들이 같이 쓴다.
  //
  // 도감 네 탭은 여기서 받지 않는다. 처음 열 때 initDex 가 한 번 받는다 —
  // 팀만 보려고 들어온 사람이 기술 498줄까지 기다릴 이유가 없다.
  const [slots, pokemons, items, natures] = await Promise.all([
    TYPES_READY,
    fetch("/api/team").then(r => r.json()),
    fetch("/api/pokemons").then(r => r.json()),
    fetch("/api/items").then(r => r.json()),
    fetch("/api/natures").then(r => r.json()),
  ]).then(([, ...rest]) => rest);
  POKEMONS = pokemons;
  ITEMS = items;
  NATURES = natures;

  grid.innerHTML = "";
  slots.forEach(slot => grid.appendChild(card(slot)));
}

// 계산기 폼이 ITEMS·NATURES 를 그대로 쓴다. 이것들이 채워지기 전에
// 탭을 누르면 빈 배열로 그려진 채 굳어버리므로, 끝나는 시점을 잡아둔다.
const LOADED = load();

