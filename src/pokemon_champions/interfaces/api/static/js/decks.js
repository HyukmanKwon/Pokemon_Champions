// ═════════════════════════════════════════════════════════════
// 덱 — 여러 벌 중 하나를 골라 본다
//
// ── 서버가 활성 덱을 들고 있는데 왜 화면도 드나 ──
//   ACTIVE_DECK 은 "이 탭이 보고 있는 덱" 이다. 서버의 active 는 "다음에
//   열면 보일 덱" 이라 저장되는 값이고, 이건 지금 화면의 값이다. 둘을
//   하나로 합치면 탭 두 개를 띄웠을 때 한쪽에서 덱을 바꾸는 순간 다른
//   쪽 화면이 조용히 다른 덱을 고치게 된다.
//
//   도우미도 이 값을 그대로 실어 보낸다. 화면에 뜬 덱과 도우미가 답하는
//   덱이 갈리면 안 된다.
// ═════════════════════════════════════════════════════════════

const deckbar = document.getElementById("deckbar");

let DECKS = [];

async function loadDecks() {
  const book = await fetch("/api/decks").then(r => r.json());
  DECKS = book.decks;
  // 처음 열 때만 서버의 활성 덱을 따라간다. 그 뒤로는 이 탭의 선택이 이긴다.
  if (!ACTIVE_DECK) ACTIVE_DECK = book.active;
  renderDeckBar();
}

function renderDeckBar() {
  deckbar.innerHTML = DECKS.map(d => `
    <button class="deck${d.id === ACTIVE_DECK ? " on" : ""}"
            data-deck="${esc(d.id)}" title="${esc(d.members.join(" · "))}">
      ${esc(d.name)}
    </button>`).join("") + `
    <span class="deck-actions">
      <button data-act="new">새 덱</button>
      <button data-act="copy">복제</button>
      <button data-act="rename">이름</button>
      <button data-act="delete">삭제</button>
    </span>`;
}

async function switchDeck(id) {
  if (id === ACTIVE_DECK) return;
  ACTIVE_DECK = id;
  // 서버에도 남긴다. 다음에 열 때, 그리고 CLI·check_damage 가 같은 덱을 본다.
  await fetch(`/api/decks/${encodeURIComponent(id)}/activate`, {method: "POST"});
  renderDeckBar();
  await load();
}

// 실패하면 서버 문구를 그대로 보여준다. "마지막 덱은 지울 수 없습니다"
// 같은 말은 이미 서버가 사람이 읽을 문장으로 만들어 두었다.
async function deckOp(path, opts) {
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    alert(data.detail || "덱을 고치지 못했습니다.");
    return null;
  }
  return data;
}

deckbar.addEventListener("click", async e => {
  const pick = e.target.closest("button[data-deck]");
  if (pick) return switchDeck(pick.dataset.deck);

  const act = e.target.closest("button[data-act]")?.dataset.act;
  if (!act) return;

  const here = DECKS.find(d => d.id === ACTIVE_DECK);

  if (act === "new") {
    const name = prompt("새 덱 이름", "새 덱");
    if (!name) return;
    const made = await deckOp("/api/decks", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    });
    if (made) { await loadDecks(); await switchDeck(made.id); }

  } else if (act === "copy") {
    const made = await deckOp(
      `/api/decks/${encodeURIComponent(ACTIVE_DECK)}/copy`, {method: "POST"});
    if (made) { await loadDecks(); await switchDeck(made.id); }

  } else if (act === "rename") {
    const name = prompt("덱 이름", here?.name || "");
    if (!name) return;
    const done = await deckOp(`/api/decks/${encodeURIComponent(ACTIVE_DECK)}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name}),
    });
    if (done) await loadDecks();

  } else if (act === "delete") {
    if (!confirm(`'${here?.name}' 덱을 지울까요? 되돌릴 수 없습니다.`)) return;
    const done = await deckOp(
      `/api/decks/${encodeURIComponent(ACTIVE_DECK)}`, {method: "DELETE"});
    if (done) {
      // 지운 덱을 계속 가리키고 있으면 다음 요청이 404 다. 서버가 알려준
      // 남은 활성 덱으로 옮겨 탄다.
      ACTIVE_DECK = done.active;
      await loadDecks();
      await load();
    }
  }
});

// team.js 의 load() 가 이미 ACTIVE_DECK 없이 한 번 그렸다. 그때 서버가
// 활성 덱을 썼으므로 내용은 맞다 — 여기서는 그 덱이 어느 것인지 알아내
// 바를 그리기만 하면 되고, 다시 그릴 필요가 없다.
loadDecks();
