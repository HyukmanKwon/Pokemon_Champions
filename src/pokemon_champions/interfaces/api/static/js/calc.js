// ═════════════════════════════════════════════════════════════
// 계산기 — 데미지 · 결정력 · 내구력
//
// 전부 Calc 하나에 담는다. 이 파일은 1,500줄이 전역 스코프를 같이 쓰는
// 구조라, statGrid 처럼 이름이 겹치면 나중 선언이 앞의 것을 조용히
// 덮어쓴다. 실제로 그렇게 내 팀 카드가 통째로 죽은 적이 있다.
//
// 서버가 숫자를 만든다. 여기서 공식을 다시 쓰지 않는다 — 두 벌이 되는
// 순간 CLI(check_damage.py)와 값이 갈라지고 어느 쪽이 맞는지 알 수 없다.
// 이 코드가 하는 일은 입력을 모아 POST 하고 돌아온 것을 그리는 것뿐이다.
//
// 예외가 하나 있다. HP 옆의 % 는 여기서 센다. 실능 HP 는 종족값 + 75 + SP
// 로 성격 보정이 없어 정확히 나오고, 슬라이더를 끌 때마다 서버에 물으면
// 화면이 끊긴다.
// ═════════════════════════════════════════════════════════════
const Calc = {
  HP_OFFSET: 75,                 // config.py 와 같은 값
  RANKS: Array.from({length: 13}, (_, i) => i - 6),
  MODES: [
    {key: "damage", label: "데미지"},
    {key: "power", label: "결정력"},
    {key: "bulk", label: "내구력"},
  ],

  ready: null, rules: null, names: null, base: null,
  mode: "damage",
  // 포켓몬마다 다른 후보. 콤보가 열릴 때 이걸 본다.
  side: {attacker: {abilities: [], moves: []}, defender: {abilities: [], moves: []}},

  // ── 준비 ───────────────────────────────────────────────────

  async init() {
    if (this.ready) return this.ready;
    const panel = document.getElementById("panel-calc");
    this.ready = this.build(panel).catch(err => {
      // 실패한 약속을 남겨두면 탭을 다시 눌러도 영영 그 실패가 돌아온다.
      this.ready = null;
      panel.innerHTML = `<div class="empty err">계산기를 불러오지 못했습니다 —
        ${esc(err.message)}<br>탭을 다시 누르면 재시도합니다.</div>`;
    });
    return this.ready;
  },

  async build(panel) {
    panel.innerHTML = `<div class="empty">불러오는 중…</div>`;
    const [, rules, dex] = await Promise.all([
      LOADED,   // ITEMS · NATURES 가 채워질 때까지
      fetch("/api/calc/rules").then(r => r.json()),
      // 도감 전체다. 메가폼도 상대로 세울 수 있어야 하므로
      // /api/pokemons(엔트리용, 메가 제외)를 쓰지 않는다.
      fetch("/api/dex/pokemons").then(r => r.json()),
    ]);
    this.rules = rules;
    const rows = dex.filter(p => p.ko_name);
    this.names = rows.map(p => p.ko_name)
      .sort((a, b) => nfc(a).localeCompare(nfc(b), "ko"));
    // HP % 를 그리려면 종족값이 필요하다.
    this.base = Object.fromEntries(rows.map(p => [p.ko_name, p]));

    panel.innerHTML = `
      <nav class="tabs sub" id="calc-modes">
        ${this.MODES.map(m => `<button data-mode="${m.key}"
          class="${m.key === this.mode ? "on" : ""}">${m.label} 계산기</button>`).join("")}
      </nav>
      <div id="calc-body"></div>`;

    panel.querySelector("#calc-modes").addEventListener("click", e => {
      const btn = e.target.closest("button[data-mode]");
      if (btn) this.setMode(btn.dataset.mode);
    });

    // 위임이라 여기서 한 번만 건다. setMode 안에서 걸면 모드를 바꿀
    // 때마다 같은 핸들러가 #calc-body 에 겹겹이 쌓인다.
    const body = panel.querySelector("#calc-body");
    body.addEventListener("change", e => this.onChange(e));
    body.addEventListener("input", e => this.onInput(e));

    await this.setMode(this.mode);
  },

  async setMode(mode) {
    this.mode = mode;
    [...document.querySelectorAll("#calc-modes button")].forEach(
      b => b.classList.toggle("on", b.dataset.mode === mode));

    const body = document.getElementById("calc-body");
    body.innerHTML = this[`${mode}Form`]();

    // 버튼과 콤보는 innerHTML 로 매번 새로 생기므로 여기서 건다.
    body.querySelector(".run").addEventListener("click", () => this[`run${
      mode[0].toUpperCase() + mode.slice(1)}`]());
    body.querySelector(".swap")?.addEventListener("click", () => this.swap());
    body.querySelectorAll("[data-combo]").forEach(
      input => setupCombo(input, () => this.choices(input)));

    const [first, second] = [this.names[0], this.names[1] || this.names[0]];
    await Promise.all([...body.querySelectorAll("[data-f='ko_name']")].map(
      (input, i) => {
        input.value = i ? second : first;
        return this.loadSide(input.closest("fieldset").dataset.side, input.value);
      }));
    body.querySelectorAll("fieldset[data-side]").forEach(el => this.syncHp(el));
  },

  // ── 콤보 후보 ──────────────────────────────────────────────

  choices(input) {
    // 기술 칸 하나는 "기술 · 배틀 상황" 안에 있어 data-side 가 없다.
    // 그건 언제나 공격자의 기술이다.
    const who = input.closest("fieldset[data-side]")?.dataset.side || "attacker";
    const s = this.side[who] || {abilities: [], moves: []};
    const plain = xs => xs.map(v => ({value: v}));
    const ko = xs => xs.map(o => ({value: o.ko_name}));

    // 분기 이름은 data-combo 값이고, data-combo 는 곧 필드 이름이다.
    // 둘을 따로 두면(pokemon vs ko_name) 어긋났을 때 조용히 빈 목록이
    // 나온다 — 실제로 "후보가 없습니다" 만 뜨는 칸이 생겼었다.
    switch (input.dataset.combo) {
      case "ko_name":   return plain(this.names);
      case "ability":   return plain(s.abilities);
      case "move":      return plain(s.moves);
      case "item":      return plain(ITEMS);
      case "ko_nature": return NATURES.map(n => ({
        value: n.name,
        hint: n.up || n.down ? `↑${n.up || "-"} ↓${n.down || "-"}` : "보정 없음",
      }));
      case "condition": return ko(this.rules.conditions);
      case "weather":   return ko(this.rules.weathers);
      case "terrain":   return ko(this.rules.terrains);
      default: return [];
    }
  },

  // 콤보는 한국어를 보여주고, 서버는 영문 키를 받는다. 그 사이를 잇는다.
  // 빈 칸은 "없음/정상" 이라 null 이다.
  keyOf(kind, koName) {
    const v = nfc(koName || "").trim();
    if (!v) return null;
    return (this.rules[kind].find(o => nfc(o.ko_name) === v) || {}).name || null;
  },

  // ── 입력 폼 ────────────────────────────────────────────────

  // 여섯 칸짜리 입력줄. 칸마다 무슨 능력치인지 위에 적는다 —
  // 순서를 외우고 있어야 쓸 수 있는 화면은 매번 세어보게 된다.
  statGrid(cell) {
    return `<div class="statgrid">${STAT_KEYS.map((k, i) => `<div>
      <span class="cap">${STAT_SHORT[i]}</span>${cell(k, i)}
    </div>`).join("")}</div>`;
  },

  field(label, inner) {
    return `<div><label>${label}</label>${inner}</div>`;
  },

  comboInput(name, extra = "") {
    return combo(`<input type="text" data-f="${name}" data-combo="${name}"
      autocomplete="off" ${extra}>`);
  },

  // 아군은 HP 를 숫자로 쓴다 — 내 포켓몬은 실제 수치가 보인다.
  // 상대는 게임에서도 % 로만 보이므로 막대로 맞춘다.
  hpControl(who) {
    return who === "defender"
      ? `<div class="hpwrap">
           <label class="inline">남은 HP</label>
           <input type="range" data-f="hp_pct" min="0" max="100" step="1" value="100">
           <span class="hpinfo" data-hp-info></span>
         </div>`
      : `<div class="hpwrap">
           <label class="inline">남은 HP
             <input type="number" data-f="hp" min="1" onfocus="this.select()"></label>
           <span class="hpinfo" data-hp-info></span>
         </div>`;
  },

  sideFields(who, label, {moves = false} = {}) {
    return `
    <fieldset data-side="${who}">
      <legend>${label}</legend>
      <div class="row">${this.field("포켓몬", this.comboInput("ko_name"))}</div>
      <div class="row two">
        ${this.field("특성", this.comboInput("ability"))}
        ${this.field("성격", this.comboInput("ko_nature"))}
      </div>
      <div class="row two">
        ${this.field("도구", this.comboInput("item", 'placeholder="없음"'))}
        ${this.field("상태이상", this.comboInput("condition", 'placeholder="정상"'))}
      </div>
      <div class="row">
        <label>SP · 총 66 · 칸당 32</label>
        ${this.statGrid(k => `<input type="number" data-sp="${k}" min="0" max="32"
           value="0" onfocus="this.select()">`)}
      </div>
      <div class="row">
        <label>랭크</label>
        ${this.statGrid(k => `<select data-rank="${k}">${
          opt(this.RANKS.map(r => [r, r > 0 ? `+${r}` : String(r)]), 0)}</select>`)}
      </div>
      ${moves ? `<div class="row">
        <label>기술 (최대 4개)</label>
        <div class="row two" style="margin:0">
          ${[0, 1, 2, 3].map(i => combo(`<input type="text" data-move="${i}"
            data-combo="move" autocomplete="off" placeholder="없음">`)).join("")}
        </div></div>` : ""}
      <div class="hprow">
        <label class="inline"><input type="checkbox" data-f="grounded" checked> 접지</label>
        ${this.hpControl(who)}
      </div>
    </fieldset>`;
  },

  // ── HP ─────────────────────────────────────────────────────

  // 실능 HP = 종족값 + 75 + SP. 성격은 HP 에 안 걸린다.
  maxHp(el) {
    const row = this.base[nfc(el.querySelector("[data-f='ko_name']").value)];
    if (!row) return null;
    return row.h + this.HP_OFFSET + (+el.querySelector("[data-sp='h']").value || 0);
  },

  syncHp(el) {
    const max = this.maxHp(el);
    const info = el.querySelector("[data-hp-info]");
    if (!info) return;
    if (max == null) { info.textContent = ""; return; }

    const bar = el.querySelector("[data-f='hp_pct']");
    if (bar) {
      const pct = +bar.value;
      info.textContent = `${pct}%  ≈ ${Math.max(1, Math.round(max * pct / 100))} / ${max}`;
      return;
    }
    // 비워두면 만피로 본다. 그때도 실제 숫자를 보여준다 — "만피" 라고만
    // 쓰여 있으면 그게 몇인지 알 수 없다.
    const input = el.querySelector("[data-f='hp']");
    input.max = max;
    input.placeholder = max;
    const cur = input.value ? +input.value : max;
    info.textContent = `/ ${max}  (${(cur / max * 100).toFixed(1)}%)`;
  },

  // ── 읽고 쓰기 ──────────────────────────────────────────────

  el(who) { return document.querySelector(`fieldset[data-side="${who}"]`); },

  async loadSide(who, koName) {
    const el = this.el(who);
    if (!el) return;
    const res = await fetch(`/api/pokemon/${encodeURIComponent(koName)}/options`);
    if (!res.ok) return;
    const {selectable_abilities, learnable_moves,
           is_mega, forced_item} = await res.json();
    this.side[who] = {abilities: selectable_abilities, moves: learnable_moves};

    // 메가폼은 지닐 도구가 하나로 정해져 있다. 메가스톤 없이는 그 폼 자체가
    // 성립하지 않으므로, 칸을 채우고 잠근다. 고를 여지가 없는 것을 고르게
    // 두면 다른 도구를 넣어놓고 왜 안 되는지 찾게 된다.
    const item = el.querySelector("[data-f='item']");
    item.readOnly = !!is_mega;
    item.classList.toggle("locked", !!is_mega);
    if (is_mega) {
      item.value = forced_item || "";
      item.title = forced_item ? "메가폼은 이 스톤으로 고정됩니다"
                               : "이 메가폼의 스톤이 DB에 없습니다";
    } else {
      item.title = "";
    }

    // 이전 포켓몬의 특성이 남아 있으면 서버가 400 을 낸다. 첫 후보로 채운다.
    const ab = el.querySelector("[data-f='ability']");
    if (!selectable_abilities.includes(nfc(ab.value))) ab.value = selectable_abilities[0] || "";
    if (!el.querySelector("[data-f='ko_nature']").value) {
      el.querySelector("[data-f='ko_nature']").value = "성실";
    }
    // 기술도 마찬가지. 배울 수 없는 게 남으면 계산이 안 된다.
    //
    // 기술 칸은 공격자만 건드린다. 방어자를 바꿨다고 공격자의 기술이
    // 지워지면, 상대만 갈아끼우며 비교하는 흔한 흐름이 매번 끊긴다.
    if (who !== "attacker") return;
    const learn = new Set(learnable_moves);
    const one = document.querySelector('.calc .wide [data-f="move"]');
    el.querySelectorAll("[data-move]").forEach(
      i => { if (!learn.has(nfc(i.value))) i.value = ""; });
    if (one) {
      if (!learn.has(nfc(one.value))) one.value = "";
      if (!one.value) one.value = learnable_moves[0] || "";
    }
  },

  read(who) {
    const el = this.el(who);
    const v = f => el.querySelector(`[data-f="${f}"]`);
    const rank = {};
    el.querySelectorAll("[data-rank]").forEach(s => {
      const n = +s.value;
      if (n) rank[s.dataset.rank] = n;      // 0 은 안 보낸다. 기본값이다
    });

    const bar = v("hp_pct");
    const max = this.maxHp(el);
    let hp = null;
    if (bar) {
      // 100% 는 만피와 같으므로 안 보낸다. 서버의 기본값이 그것이다.
      if (+bar.value < 100 && max) hp = Math.max(1, Math.round(max * +bar.value / 100));
    } else if (v("hp").value) {
      hp = +v("hp").value;
    }

    return {
      ko_name: nfc(v("ko_name").value),
      ability: nfc(v("ability").value),
      item: nfc(v("item").value) || null,
      ko_nature: nfc(v("ko_nature").value) || "성실",
      sp_values: [...el.querySelectorAll("[data-sp]")].map(i => +i.value || 0),
      rank,
      condition: this.keyOf("conditions", v("condition").value),
      hp,
      grounded: v("grounded").checked,
    };
  },

  // 공격자와 방어자를 통째로 맞바꾼다. "이번엔 내가 맞는 쪽" 을 보려고
  // 열 몇 칸을 다시 고르는 일이 제일 잦다.
  async swap() {
    const [a, b] = [this.read("attacker"), this.read("defender")];
    await this.write("attacker", b);
    await this.write("defender", a);
    // HP 는 스펙을 다 옮긴 뒤에 넣는다. 종족값과 SP 가 자리를 잡아야
    // 절대값 ↔ % 환산의 분모(만피)가 정해진다.
    this.setHp("attacker", b.hp);
    this.setHp("defender", a.hp);
  },

  // 한쪽은 숫자 칸이고 한쪽은 % 막대다. 어느 쪽이든 절대값으로 받아 넣는다.
  setHp(who, hp) {
    const el = this.el(who), max = this.maxHp(el);
    const bar = el.querySelector("[data-f='hp_pct']");
    if (bar) bar.value = (hp && max) ? Math.round(hp / max * 100) : 100;
    else el.querySelector("[data-f='hp']").value = hp ?? "";
    this.syncHp(el);
  },

  async write(who, spec) {
    const el = this.el(who);
    el.querySelector("[data-f='ko_name']").value = spec.ko_name;
    await this.loadSide(who, spec.ko_name);   // 후보 목록을 먼저 갈아끼운다
    const v = f => el.querySelector(`[data-f="${f}"]`);
    v("ability").value = spec.ability;
    // 메가폼이면 loadSide 가 스톤으로 채우고 잠갔다. 덮어쓰지 않는다.
    if (!v("item").readOnly) v("item").value = spec.item || "";
    v("ko_nature").value = spec.ko_nature;
    v("condition").value = this.koOf("conditions", spec.condition);
    v("grounded").checked = spec.grounded;
    el.querySelectorAll("[data-sp]").forEach((i, n) => i.value = spec.sp_values[n]);
    el.querySelectorAll("[data-rank]").forEach(
      s => s.value = spec.rank[s.dataset.rank] || 0);
    this.syncHp(el);
  },

  koOf(kind, name) {
    if (!name) return "";
    return (this.rules[kind].find(o => o.name === name) || {}).ko_name || "";
  },

  // ── 이벤트 ─────────────────────────────────────────────────

  onChange(e) {
    const input = e.target.closest("[data-f='ko_name']");
    if (input) {
      const el = input.closest("fieldset");
      this.loadSide(el.dataset.side, nfc(input.value));
      this.syncHp(el);
    }
  },

  onInput(e) {
    const el = e.target.closest("fieldset[data-side]");
    if (el && e.target.matches("[data-sp], [data-f='hp'], [data-f='hp_pct']")) {
      this.syncHp(el);
    }
  },

  // ── 데미지 ─────────────────────────────────────────────────

  damageForm() {
    return `
    <div class="calc">
      ${this.sideFields("attacker", "공격자")}
      ${this.sideFields("defender", "방어자")}

      <fieldset class="wide">
        <legend>기술 · 배틀 상황</legend>
        <div class="row two">
          ${this.field("기술", combo(`<input type="text" data-f="move"
            data-combo="move" autocomplete="off">`))}
          <div class="row two" style="margin:0">
            ${this.field("날씨", combo(`<input type="text" data-f="weather"
              data-combo="weather" autocomplete="off" placeholder="없음">`))}
            ${this.field("필드", combo(`<input type="text" data-f="terrain"
              data-combo="terrain" autocomplete="off" placeholder="없음">`))}
          </div>
        </div>
        <div class="checks">
          <label><input type="checkbox" data-f="is_critical"> 급소</label>
          <label><input type="checkbox" data-f="reflect"> 리플렉터</label>
          <label><input type="checkbox" data-f="light_screen"> 빛의장막</label>
          <label><input type="checkbox" data-f="is_doubles"> 더블</label>
          <button class="swap" type="button">공수 교대</button>
          <button class="run" type="button" style="margin-left:auto">계산</button>
        </div>
      </fieldset>

      <fieldset class="wide result" id="calc-result" hidden></fieldset>
    </div>`;
  },

  async runDamage() {
    const g = f => document.querySelector(`.calc .wide [data-f="${f}"]`);
    await this.post("/api/calc/damage", {
      attacker: this.read("attacker"),
      defender: this.read("defender"),
      move: nfc(g("move").value),
      weather: this.keyOf("weathers", g("weather").value),
      terrain: this.keyOf("terrains", g("terrain").value),
      is_critical: g("is_critical").checked,
      reflect: g("reflect").checked,
      light_screen: g("light_screen").checked,
      is_doubles: g("is_doubles").checked,
    }, d => this.damageResult(d));
  },

  // ── 결정력 ─────────────────────────────────────────────────

  powerForm() {
    return `
    <div class="calc">
      ${this.sideFields("attacker", "포켓몬", {moves: true})}
      <fieldset>
        <legend>결정력이란</legend>
        <p class="note">공격 실능 × 기술 위력 × 자속(1.5)입니다.
        상성 · 랭크 · 날씨는 상대와 판이 있어야 정해지므로 빠집니다.
        절대값 자체에는 의미가 없고, <b>기술끼리 · 포켓몬끼리 견주는 데만</b>
        씁니다.</p>
        <div class="checks"><button class="run" type="button">계산</button></div>
      </fieldset>
      <fieldset class="wide result" id="calc-result" hidden></fieldset>
    </div>`;
  },

  async runPower() {
    const moves = [...this.el("attacker").querySelectorAll("[data-move]")]
      .map(i => nfc(i.value)).filter(Boolean);
    await this.post("/api/calc/power",
      {side: this.read("attacker"), moves}, d => this.powerResult(d));
  },

  // ── 내구력 ─────────────────────────────────────────────────

  bulkForm() {
    return `
    <div class="calc">
      ${this.sideFields("attacker", "포켓몬")}
      <fieldset>
        <legend>내구력이란</legend>
        <p class="note">HP × 방어, HP × 특수방어입니다.
        HP만 봐도 방어만 봐도 몇 방 버티는지가 안 나옵니다. 받는 데미지가
        방어에 반비례하고 남은 턴이 HP에 비례하므로 두 값의 곱이 기준이
        됩니다. 이것도 <b>비교용</b>입니다.</p>
        <div class="checks"><button class="run" type="button">계산</button></div>
      </fieldset>
      <fieldset class="wide result" id="calc-result" hidden></fieldset>
    </div>`;
  },

  async runBulk() {
    await this.post("/api/calc/bulk",
      {side: this.read("attacker")}, d => this.bulkResult(d));
  },

  // ── 결과 ───────────────────────────────────────────────────

  async post(url, body, render) {
    const box = document.getElementById("calc-result");
    box.hidden = false;
    box.innerHTML = `<div class="empty">계산 중…</div>`;
    const res = await fetch(url, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    });
    const data = await res.json();
    box.innerHTML = res.ok ? render(data)
      : `<legend>결과</legend><div class="err">${esc(
          typeof data.detail === "string" ? data.detail : "계산 실패")}</div>`;
  },

  EFF_KO: {0: "무효", 0.25: "반의 반감", 0.5: "반감", 2: "효과가 굉장함", 4: "4배"},

  // 랭크를 그대로 적는다. used 에 없는 능력치는 이 계산에 안 쓰이므로
  // "무시됨" 이라고 밝힌다 — 체력 랭크를 올려놓고 왜 안 변하나 하게 된다.
  rankText(rank, used) {
    const all = Object.entries(rank || {});
    if (!all.length) return "랭크 보정 없음";
    const fmt = ([k, v]) => `${STAT_KO[k]} ${v > 0 ? "+" : ""}${v}`;
    const on = all.filter(([k]) => used.includes(k));
    const off = all.filter(([k]) => !used.includes(k));
    return j(
      on.length ? `적용됨 — ${on.map(fmt).map(esc).join(" · ")}` : "적용된 랭크 없음",
      off.length ? `　(이 계산에 안 쓰임 — ${off.map(fmt).map(esc).join(" · ")})` : "");
  },

  // 서버가 실제로 무엇을 받아 계산했는지 적는다. 랭크를 올렸는데 숫자가
  // 그대로일 때, 안 보낸 건지 안 걸리는 건지를 여기서 가른다.
  appliedText(d) {
    const c = d.context || {};
    const rankKo = r => Object.entries(r || {})
      .map(([k, v]) => `${STAT_KO[k]} ${v > 0 ? "+" : ""}${v}`).join(" ");
    const parts = [
      rankKo(c.attacker_rank) && `공격자 랭크 ${rankKo(c.attacker_rank)}`,
      rankKo(c.defender_rank) && `방어자 랭크 ${rankKo(c.defender_rank)}`,
      c.weather && this.koOf("weathers", c.weather),
      c.terrain && this.koOf("terrains", c.terrain),
      d.attacker.condition && this.koOf("conditions", d.attacker.condition) + "(공격자)",
      d.defender.condition && this.koOf("conditions", d.defender.condition) + "(방어자)",
      c.is_critical && "급소",
      c.reflect && "리플렉터",
      c.light_screen && "빛의장막",
      c.is_doubles && "더블",
      c.defender_hp && `방어자 잔여 HP ${c.defender_hp}`,
    ].filter(Boolean);
    return parts.length
      ? `적용됨 — ${parts.map(esc).join(" · ")}`
      : "적용된 보정 없음 (싱글 · 랭크 0 · 날씨 없음 · 만피)";
  },

  damageResult(d) {
    const {damage: dm, ko} = d;
    const p = v => v / dm.defender_hp * 100;
    const pct1 = v => v.toFixed(1);
    const avg = Math.round(dm.rolls.reduce((s, x) => s + x, 0) / dm.rolls.length);
    const eff = d.type_effect;

    return `
      <legend>결과</legend>

      <div class="verdict">
        <div class="ko">${esc(ko.text)}</div>
        <div class="line">
          ${esc(d.attacker.name)} 의 <b>${esc(d.move.name)}</b>
          ${iconImg(d.move.icon, typeKo(d.move.type), "tiny")}
          (${CATEGORY_KO[d.move.category]} · 위력 ${dash(d.move.power)})
          → ${esc(d.defender.name)}
          ${eff !== 1 ? `<span class="chip ${eff > 1 ? "warn" : ""}">${
            esc(this.EFF_KO[eff] || `×${eff}`)}</span>` : ""}
        </div>
      </div>

      <div class="applied">${this.appliedText(d)}</div>

      <div class="hpbar">
        <i class="hi" style="width:${Math.min(100, p(dm.max))}%"></i>
        <i class="lo" style="width:${Math.min(100, p(dm.min))}%"></i>
      </div>
      <div class="hpscale"><span>0</span><span>방어자 HP ${dm.defender_hp}</span></div>

      <table class="rolltable">
        <thead><tr><th></th><th class="num">데미지</th><th class="num">HP 대비</th>
          <th class="num">남는 HP</th></tr></thead>
        <tbody>
          <tr><td>최소 (운 나쁠 때)</td><td class="num">${dm.min}</td>
            <td class="num">${pct1(dm.percent_min)}%</td>
            <td class="num">${Math.max(0, dm.defender_hp - dm.min)}</td></tr>
          <tr><td>평균</td><td class="num">${avg}</td>
            <td class="num">${pct1(p(avg))}%</td>
            <td class="num">${Math.max(0, dm.defender_hp - avg)}</td></tr>
          <tr><td>최대 (운 좋을 때)</td><td class="num">${dm.max}</td>
            <td class="num">${pct1(dm.percent_max)}%</td>
            <td class="num">${Math.max(0, dm.defender_hp - dm.max)}</td></tr>
        </tbody>
      </table>

      ${ko.turns.length > 1 ? `
      <table class="rolltable">
        <thead><tr><th>턴</th><th class="num">맞기 전 HP</th>
          <th class="num">데미지</th><th class="num">맞은 뒤</th></tr></thead>
        <tbody>${ko.turns.map((t, i) => `<tr>
          <td>${i + 1}턴</td>
          <td class="num">${t.hp_before}</td>
          <td class="num">${t.damage_min}~${t.damage_max}</td>
          <td class="num">${Math.max(0, t.hp_before - t.damage_max)}~${
            Math.max(0, t.hp_before - t.damage_min)}</td>
        </tr>`).join("")}</tbody>
      </table>` : ""}

      <details class="rolls">
        <summary>난수 16단계 펼치기</summary>
        <div>본가는 데미지에 85~100% 를 16단계로 굴린다. 아래가 그 16개다.</div>
        <div class="rollgrid">${dm.rolls.map(
          r => `<span>${r}<em>${pct1(p(r))}%</em></span>`).join("")}</div>
      </details>`;
  },

  powerResult(d) {
    if (!d.moves.length) {
      return `<legend>결과</legend><div class="empty">기술을 하나 이상 고르세요.</div>`;
    }
    const top = d.moves[0].index || 1;
    return `
      <legend>결과 — ${esc(d.side.name)}</legend>
      <div class="sub2">공격 ${d.side.stats.a} · 특수공격 ${d.side.stats.c}</div>
      <div class="applied">${this.rankText(d.side.rank, ["a", "c"])}</div>
      <table class="rolltable">
        <thead><tr><th>기술</th><th class="mid">분류</th><th class="num">위력</th>
          <th class="mid">자속</th><th class="num">결정력</th><th></th></tr></thead>
        <tbody>${d.moves.map(m => `<tr>
          <td>${iconImg(m.icon, typeKo(m.type), "tiny")} ${esc(m.name)}</td>
          <td class="mid">${CATEGORY_KO[m.category]}</td>
          <td class="num">${dash(m.power)}</td>
          <td class="mid">${m.stab ? "○" : ""}</td>
          <td class="num"><b>${m.index.toLocaleString()}</b></td>
          <td style="width:40%"><span class="minibar"><i style="width:${
            m.index / top * 100}%"></i></span></td>
        </tr>`).join("")}</tbody>
      </table>`;
  },

  bulkResult(d) {
    const s = d.side.stats;
    const max = Math.max(d.bulk.physical, d.bulk.special) || 1;
    const row = (label, value, stat) => `<tr>
      <td>${label}</td>
      <td class="num">${s.h} × ${stat}</td>
      <td class="num"><b>${value.toLocaleString()}</b></td>
      <td style="width:45%"><span class="minibar"><i style="width:${
        value / max * 100}%"></i></span></td></tr>`;
    return `
      <legend>결과 — ${esc(d.side.name)}</legend>
      <div class="sub2">체력 ${s.h} · 방어 ${s.b} · 특수방어 ${s.d}</div>
      <div class="applied">${this.rankText(d.side.rank, ["b", "d"])}</div>
      <table class="rolltable">
        <thead><tr><th>구분</th><th class="num">계산</th>
          <th class="num">내구력</th><th></th></tr></thead>
        <tbody>
          ${row("물리 내구", d.bulk.physical, s.b)}
          ${row("특수 내구", d.bulk.special, s.d)}
        </tbody>
      </table>`;
  },
};

// 랭크만 남은 <select>. 나머지는 전부 검색 가능한 콤보다.
function opt(list, sel) {
  return list.map(([v, l]) =>
    `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(l)}</option>`).join("");
}
