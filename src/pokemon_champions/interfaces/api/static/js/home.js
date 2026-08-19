// ═════════════════════════════════════════════════════════════
// 홈 — 열자마자 보이는 화면
//
// ── 네 층이다 ──
//     바로가기   여섯 칸. 탭 줄보다 크고, 계산기처럼 안쪽 갈래까지 곧장 간다
//     안내       처음 온 사람 / 바로 물어볼 사람
//     내 엔트리  지금 뭘 들고 있나
//     메타 상위  상대로 뭐가 나오나
//
// ── 왜 탭 줄과 겹치는 것을 또 놓나 ──
//   위의 알약 탭은 "지금 어디 있나" 를 알려주는 표시지 들어가는 문이 아니다.
//   글자만 8px 이라 처음 여는 사람 눈에 안 들어오고, 계산기 안의 세 갈래는
//   탭을 눌러 들어가야 비로소 보인다. 홈의 타일은 그 안쪽까지 곧장 간다.
//
// ── 여기서 계산하는 것은 없다 ──
//   이미 있는 세 라우트(/api/team, /api/decks, /api/usage)가 주는 것을
//   늘어놓기만 한다. 홈이 자기만의 자료를 갖기 시작하면 다른 탭과 두 벌이
//   되고, 그때부터 어느 쪽이 맞는지 물어야 한다.
//
// ── 왜 매번 다시 받나 ──
//   덱은 내 팀 탭에서 바뀐다. 홈을 한 번만 그려두면 덱을 고치고 돌아와도
//   옛 엔트리가 그대로 있어서, 화면 둘이 서로 다른 팀을 보여준다.
// ═════════════════════════════════════════════════════════════

const Home = (() => {
  const TOP = 10;

  // 아이콘은 그림 파일이 아니라 글자다. 여섯 개를 위해 SVG 예순 줄을
  // 들이거나 아이콘 세트를 받아올 만한 자리가 아니다 — 스프라이트와 달리
  // 이건 장식이라, 못 그려도 이름이 남는다.
  //
  // go 는 눌렀을 때 부를 것. 계산기는 갈래까지 정해서 보낸다.
  const TILES = [
    {icon: "📕", label: "도감",       sub: "포켓몬 · 기술 · 특성 · 도구",
     go: () => { showTab("dex"); showDex("pokemon"); }},
    {icon: "🧩", label: "내 팀",      sub: "엔트리 여섯 칸",
     go: () => showTab("team")},
    {icon: "📊", label: "채용률",     sub: "메타 순위와 채용 내역",
     go: () => showTab("usage")},
    {icon: "🧮", label: "데미지 계산", sub: "확정 몇 타인가",
     go: () => gotoCalc("damage")},
    {icon: "🛡️", label: "결정력 · 내구력", sub: "어느 쪽이 더 단단한가",
     go: () => gotoCalc("power")},
    {icon: "💬", label: "도우미",     sub: "말로 물어보기",
     go: () => showTab("agent")},
  ];

  // 처음 여는 사람이 무엇을 물어도 되는지 모른다. 빈 입력칸만 있으면
  // 대개 아무것도 안 묻는다. 세 갈래를 서로 다른 종류로 골라 둔다 —
  // 팀 전체 · 한 판의 계산 · 메타.
  const SAMPLES = [
    "내 팀이 제일 약한 타입이 뭐야?",
    "한카리아스 지진을 우리 팀이 버티나?",
    "요즘 제일 많이 쓰는 포켓몬 다섯 마리 알려줘",
  ];

  const state = {panel: null, wired: false};

  function skeleton() {
    state.panel.innerHTML = `
      <div class="home">
        <nav class="home-tiles">${TILES.map((t, i) => `
          <button type="button" data-tile="${i}">
            <span class="ico">${t.icon}</span>
            <span class="lb">${esc(t.label)}</span>
            <span class="sb">${esc(t.sub)}</span>
          </button>`).join("")}
        </nav>

        <div class="home-guides">
          <section class="guide ok">
            <h2>처음이신가요?</h2>
            <p><a data-tile-go="dex">도감</a>에서 포켓몬과 기술을 찾아보고,
               <a data-tile-go="team">내 팀</a>의 여섯 칸을 채운 뒤,
               <a data-tile-go="damage">계산기</a>로 한 판을 미리 재 보세요.</p>
            <p class="fine">레귤레이션 M-B — 레벨 50 · 개체값 31 고정,
               노력치 대신 SP 총 66(능력치당 최대 32), 성격 21종.</p>
          </section>

          <section class="guide info">
            <h2>바로 물어보고 싶다면</h2>
            <p>숫자는 전부 도구가 냅니다. 도우미는 어느 도구를 부를지만
               고르고, 무엇을 물었는지 화면에 그대로 펼쳐 둡니다.</p>
            <form class="home-ask-form">
              <input autocomplete="off" placeholder="궁금한 것을 적어 보세요">
              <button type="submit">묻기</button>
            </form>
            <div class="home-chips">${SAMPLES.map(
              q => `<button type="button" class="chip">${esc(q)}</button>`).join("")}</div>
          </section>
        </div>

        <div class="home-main">
          <section class="home-card">
            <header>
              <h2>내 엔트리</h2>
              <span class="sub" data-slot="deck"></span>
              <button type="button" data-tile-go="team">고치기</button>
            </header>
            <div data-slot="party"><div class="empty">불러오는 중…</div></div>
          </section>

          <section class="home-card">
            <header>
              <h2>메타 상위 ${TOP}</h2>
              <span class="sub" data-slot="asof"></span>
            </header>
            <div data-slot="rank"><div class="empty">불러오는 중…</div></div>
          </section>
        </div>
      </div>`;
  }

  // 안내 문장 안의 링크. 타일과 같은 곳으로 보내되 여기서 다시 적지 않고
  // 열쇠로 부른다 — 두 벌이 되면 타일은 바뀌고 문장은 안 바뀐다.
  const GO = {
    dex: () => { showTab("dex"); showDex("pokemon"); },
    team: () => showTab("team"),
    damage: () => gotoCalc("damage"),
  };

  // 다시 그려도 살아 있게 패널에 한 번만 건다. 조각마다 걸면 show 를
  // 부를 때마다 같은 처리기가 겹쳐 쌓여서, 한 번 누른 것이 두 번 간다.
  function wire() {
    if (state.wired) return;
    state.wired = true;

    state.panel.addEventListener("click", e => {
      const tile = e.target.closest("[data-tile]");
      if (tile) return TILES[+tile.dataset.tile].go();

      const link = e.target.closest("[data-tile-go]");
      if (link) return GO[link.dataset.tileGo]();

      const chip = e.target.closest(".chip");
      if (chip) return ask(chip.textContent);

      const row = e.target.closest("[data-usage]");
      if (row) return gotoUsage(row.dataset.usage);
    });

    state.panel.addEventListener("submit", e => {
      e.preventDefault();
      const input = e.target.querySelector("input");
      const q = input.value.trim();
      if (!q) return;
      input.value = "";
      ask(q);
    });
  }

  // 도우미 탭으로 넘기고 거기서 묻는다. 홈에 대화를 또 그리지 않는 이유는
  // 도구 호출 내역이 접혀 쌓이는 화면이기 때문이다 — 홈에 두면 홈이
  // 대화창이 되고, 그럼 도우미 탭이 두 개가 된다.
  function ask(question) {
    showTab("agent");
    askAgent(question);
  }

  function party(slots) {
    if (!slots.length) return `<div class="empty">엔트리가 비어 있습니다</div>`;
    return `<ol class="home-party">${slots.map(s => `
      <li data-tile-go="team">
        ${iconImg(s.sprite, s.name, "pic")}
        <span class="nm">${esc(s.name)}</span>
        <span class="type-badges">${typeBadges(s.types)}</span>
      </li>`).join("")}</ol>`;
  }

  function rank(rows) {
    if (!rows.length) return `<div class="empty">받은 순위가 없습니다</div>`;
    return `<ol class="home-rank">${rows.slice(0, TOP).map(r => `
      <li data-usage="${esc(r.ko_name)}">
        <span class="pos">${r.position}</span>
        ${iconImg(r.icon, r.ko_name)}
        <span class="nm">${esc(r.ko_name)}</span>
        <span class="type-badges">${(r.types || []).map(
          t => iconImg(t.icon, typeKo(t.name), "")).join("")}</span>
      </li>`).join("")}</ol>`;
  }

  const put = (key, html) => {
    const box = state.panel.querySelector(`[data-slot="${key}"]`);
    if (box) box.innerHTML = html;
  };

  // 둘 중 하나가 안 와도 나머지는 그린다. 한 덩어리로 묶어 await 하면
  // 채용률을 아직 안 받은 DB 에서 홈 전체가 "불러오는 중…" 으로 멈춘다.
  async function loadTeam() {
    try {
      const [slots, book] = await Promise.all([
        fetch(`/api/team${deckQuery()}`).then(r => r.json()),
        fetch("/api/decks").then(r => r.json()),
      ]);
      const now = (book.decks || []).find(d => d.id === book.active);
      put("deck", now ? `${now.name} · ${now.size}/6` : "");
      put("party", party(slots || []));
    } catch (e) {
      put("party", `<div class="empty">엔트리를 못 불러왔습니다</div>`);
    }
  }

  async function loadRank() {
    try {
      const data = await fetch("/api/usage").then(r => r.json());
      const rows = data.ranking || [];
      const asof = state.panel.querySelector('[data-slot="asof"]');
      if (asof && rows.length) asof.textContent = `${data.date} · Singles`;
      put("rank", rank(rows));
    } catch (e) {
      put("rank", `<div class="empty">순위를 못 불러왔습니다</div>`);
    }
  }

  async function show() {
    if (!state.panel) {
      state.panel = document.getElementById("panel-home");
      await TYPES_READY;          // 타입 배지가 영문 슬러그로 굳지 않게
    }
    skeleton();
    wire();
    return Promise.all([loadTeam(), loadRank()]);
  }

  return {show};
})();

// 처음 열리는 탭이라 아무도 안 부른다. 여기서 한 번 그린다.
Home.show();
