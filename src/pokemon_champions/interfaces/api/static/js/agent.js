// ═════════════════════════════════════════════════════════════
// 도우미 — 로컬 LLM 에게 묻고, 무엇을 부르는지 보면서 기다린다
//
// ── 왜 도구 호출을 보여주나 ──
//   답만 나오면 그 숫자가 어디서 왔는지 알 수 없다. 모델이 지어낸 것과
//   도구가 낸 것이 화면에서 똑같아 보이면, 도구를 붙인 의미가 없다.
//   무엇을 어떤 인자로 불렀는지 그대로 펼쳐 둔다.
//
// ── history ──
//   서버가 돌려준 것을 그대로 되돌려준다. 우리가 손대면 system 프롬프트나
//   tool 메시지의 짝이 어긋나고, 그건 모델 쪽에서 조용히 이상해진다.
//
// ── 모델을 바꾸면 대화를 새로 시작한다 ──
//   history 는 그 대화를 시작한 백엔드의 메시지 모양이다. OpenAI 는
//   tool_call_id 로 도구 결과를 짝짓고 Ollama 는 이름으로 짝짓는다.
//   섞으면 오류가 아니라 "엉뚱한 도구 결과를 보고 쓴 답" 이 나온다.
//   그래서 바꾸는 순간 비운다. (backends/__init__.py 첫머리)
// ═════════════════════════════════════════════════════════════

const chatLog = document.getElementById("chat-log");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const chatModel = document.getElementById("chat-model");

let chatHistory = null;
let asking = false;

// 목록은 서버에서 받는다. 여기 적어두면 모델을 하나 더할 때 두 군데를
// 고치게 되고, 한쪽만 고치면 "고를 수는 있는데 없는 모델" 이 된다.
fetch("/api/models")
  .then(r => r.json())
  .then(d => {
    chatModel.innerHTML = d.models.map(m => {
      const tail = m.ready ? m.label : `${m.label} · 키 없음`;
      return `<option value="${esc(m.name)}"${m.name === d.default ? " selected" : ""}
                      ${m.ready ? "" : " disabled"}>${esc(m.name)} (${esc(tail)})</option>`;
    }).join("");
  })
  .catch(() => { chatModel.innerHTML = `<option value="">(목록을 못 받았습니다)</option>`; });

chatModel?.addEventListener("change", () => {
  if (chatHistory === null) return;      // 아직 아무것도 안 물어봤다
  chatHistory = null;
  bubble("note", `모델을 <strong>${esc(chatModel.value)}</strong> 로 바꿔 대화를 새로 시작합니다. `
                 + `앞의 대화는 그 모델의 메시지 모양이라 이어 붙일 수 없습니다.`);
});

function bubble(cls, html) {
  const el = document.createElement("div");
  el.className = `bubble ${cls}`;
  el.innerHTML = html;
  chatLog.appendChild(el);
  chatLog.scrollTop = chatLog.scrollHeight;
  return el;
}

// 도구 결과는 길다. 접어두고 누르면 펼친다 — 평소에는 "무엇을 불렀나" 만
// 보면 되고, 숫자가 이상할 때만 안을 들여다본다.
function toolBubble({name, args, result}) {
  const brief = JSON.stringify(args, null, 0);
  return bubble("tool", `
    <details>
      <summary><code>${esc(name)}</code> <span class="sub">${esc(brief)}</span></summary>
      <pre>${esc(JSON.stringify(result, null, 2))}</pre>
    </details>`);
}

// 마크다운을 통째로 들이지 않는다. 모델이 쓰는 것은 **굵게** 와 줄바꿈이
// 대부분이라, 그 둘만 처리하고 나머지는 글자 그대로 둔다.
function answerHtml(text) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n/g, "<br>");
}

async function askAgent(question) {
  if (asking) return;
  asking = true;

  bubble("me", esc(question));
  const waiting = bubble("waiting", "생각하는 중…");
  const started = Date.now();
  const tick = setInterval(() => {
    waiting.textContent = `생각하는 중… ${Math.round((Date.now() - started) / 1000)}초`;
  }, 500);

  const done = () => { clearInterval(tick); waiting.remove(); asking = false; };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        question,
        // 화면이 보고 있는 덱을 묶어 보낸다. 모델은 이 값을 못 고른다.
        deck: ACTIVE_DECK,
        // 빈 값이면 서버의 기본 모델로 간다.
        model: chatModel?.value || null,
        history: chatHistory,
      }),
    });

    // SSE 를 EventSource 로 못 받는다 — 그건 GET 전용이고 우리는 질문을
    // 본문에 실어 POST 한다. 그래서 스트림을 직접 읽어 이벤트로 자른다.
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";

    for (;;) {
      const {done: fin, value} = await reader.read();
      if (fin) break;
      buf += dec.decode(value, {stream: true});

      let cut;
      while ((cut = buf.indexOf("\n\n")) !== -1) {
        const chunk = buf.slice(0, cut);
        buf = buf.slice(cut + 2);

        const ev = /^event: (.+)$/m.exec(chunk)?.[1];
        const data = JSON.parse(/^data: (.+)$/m.exec(chunk)?.[1] || "{}");

        if (ev === "tool") {
          waiting.before(toolBubble(data));
        } else if (ev === "answer") {
          done();
          chatHistory = data.history;
          bubble("bot", answerHtml(data.text));
          // 이번 질문이 쓴 토큰. 돈으로 안 바꾼다 — 가격표를 화면에 박으면
          // 저쪽이 바꿨을 때 조용히 틀린 금액을 보게 된다.
          if (data.usage) bubble("usage", esc(data.usage));
        } else if (ev === "error") {
          done();
          bubble("err", esc(data.message));
        }
      }
    }
  } catch (e) {
    bubble("err", esc(`요청이 끊겼습니다: ${e.message}`));
  } finally {
    done();
  }
}

chatForm?.addEventListener("submit", e => {
  e.preventDefault();
  const q = chatInput.value.trim();
  if (!q) return;
  chatInput.value = "";
  askAgent(q);
});
