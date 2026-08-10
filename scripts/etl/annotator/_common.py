"""annotator 공통 뼈대. 표 하나를 브라우저에서 체크하며 고치는 도구.

각 annotator(moves.py 등)는 Spec 하나를 만들어 serve() 에 넘긴다.
서버·HTML·저장 흐름은 전부 여기 있고, 개별 파일은 "무엇을 보여주고
무엇을 체크할지"만 정한다.

── 실행 ──
  프로젝트 루트에서 `python -m scripts.etl.annotator.<이름>` 으로 돌린다.
  예전에는 이 파일이 sys.path 를 손대서 평평한 import 를 통하게 했지만,
  이제 정식 패키지라 그 조작이 필요 없다.

── 의존 패키지 없음 ──
  표준 라이브러리 http.server 만 쓴다.
"""

import json
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Callable


@dataclass
class Spec:
    """annotator 하나의 정의."""

    title: str
    # 화면에 그냥 보여주기만 하는 열: [(필드, 헤더)] 또는 [(필드, 헤더, "num")]
    # "num" 을 붙이면 오른쪽 정렬 + 숫자 폭 고정
    info_columns: list
    # 체크박스로 고치는 열: [(필드, 헤더)]
    check_columns: list
    # 행을 읽어오는 함수. dict 리스트를 돌려준다
    fetch: Callable
    # 한 행을 저장하는 함수. (키, {필드: 값}, reviewed) -> 바뀐 것 dict
    save: Callable
    # 글자를 직접 쳐 넣는 열
    #   (필드, 헤더)                     기본 폭 한 줄 입력
    #   (필드, 헤더, 폭px)               폭 지정
    #   (필드, 헤더, 폭px, "area")       여러 줄 입력(textarea). 설명문용
    #   빈 칸이면 None 으로 저장된다. 체크박스와 섞어 써도 된다.
    #   기본값이 있는 필드는 없는 필드 뒤에 와야 해서 여기 놓았다.
    text_columns: list = field(default_factory=list)
    # 제목 옆에 붙는 한 줄 안내
    subtitle: str = "추측값을 훑어보고 틀린 것만 고치세요"
    key_field: str = "name"
    # 검색 대상 필드
    search_fields: tuple = ("name",)
    # 마지막 열에 길게 붙이는 설명 필드 (없으면 None)
    detail_field: str = None
    port: int = 8765
    # 종료할 때 출력할 요약을 만드는 함수
    summary: Callable = None
    labels: dict = field(default_factory=dict)
    # 계열 필터. [{"field": "is_wind", "label": "바람", "hints": ["wind", ...]}]
    #   hints 는 키(보통 영문 이름)에 들어 있으면 '후보'로 보는 조각들이다.
    #   플래그가 켜진 것과 후보를 같이 띄워서, 빠뜨린 것을 찾게 한다.
    groups: list = field(default_factory=list)


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root { color-scheme: light dark; }
  body { font: 14px/1.5 -apple-system, "Apple SD Gothic Neo", sans-serif;
         margin: 0; padding: 0 16px 80px; }
  header { position: sticky; top: 0; background: Canvas; padding: 12px 0;
           border-bottom: 1px solid #8884; z-index: 2; }
  h1 { font-size: 16px; margin: 0 0 8px; }
  .bar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
  input[type=search] { padding: 6px 10px; width: 220px; font-size: 14px; }
  .count { opacity: .7; font-variant-numeric: tabular-nums; }
  .saved { color: #2a2; opacity: 0; transition: opacity .2s; }
  .saved.on { opacity: 1; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: 4px 8px; border-bottom: 1px solid #8883;
           text-align: left; white-space: nowrap; }
  th { position: sticky; top: 76px; background: Canvas; font-weight: 600;
       font-size: 12px; }
  td.flag, th.flag { text-align: center; width: 48px; }
  td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
  tr.done { opacity: .45; }
  tr:hover { background: #8881; }
  .detail { max-width: 260px; overflow: hidden; text-overflow: ellipsis;
            font-size: 12px; opacity: .75; }
  i { opacity: .35; font-style: normal; }
  input[type=checkbox] { width: 16px; height: 16px; cursor: pointer; }
  .txt { padding: 3px 6px; font-size: 14px; width: 130px;
         font-family: inherit; }
  .txt:placeholder-shown { outline: 2px solid #e9a33a80; outline-offset: -2px; }
  textarea.txt { min-height: 3.4em; resize: vertical; line-height: 1.4;
                 vertical-align: top; }
  td.wrap { white-space: normal; }
  button { padding: 5px 10px; font-size: 13px; cursor: pointer; }
  .chips { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 8px; }
  .chip { padding: 3px 9px; font-size: 13px; border: 1px solid #8886;
          border-radius: 12px; background: transparent; color: inherit; }
  .chip.on { background: CanvasText; color: Canvas; border-color: CanvasText; }
  .mode { display: none; gap: 4px; align-items: center; margin-top: 8px;
          font-size: 13px; }
  .mode.show { display: flex; }
  .mode button.on { background: CanvasText; color: Canvas; }
  td.cand { outline: 2px solid #e9a33a80; outline-offset: -2px; }
</style></head><body>

<header>
  <h1>__TITLE__ &mdash; __SUBTITLE__</h1>
  <div class="bar">
    <input type="search" id="q" placeholder="검색">
    <label><input type="checkbox" id="onlyTodo"> 미확인만</label>
    <span class="count" id="count"></span>
    <span class="saved" id="saved">저장됨</span>
    <button id="markPage">보이는 것 전부 확인 처리</button>
  </div>
  <div class="chips" id="chips"></div>
  <div class="mode" id="mode">
    <span>표시:</span>
    <button data-m="both" class="on">켜진 것 + 후보</button>
    <button data-m="on">켜진 것만</button>
    <button data-m="cand">후보만</button>
    <span class="count" id="groupCount"></span>
  </div>
</header>

<table><thead><tr id="head"></tr></thead><tbody id="rows"></tbody></table>

<script>
const CFG = __CONFIG__;
let rows = [];
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

$('#head').innerHTML =
  CFG.info.map(c => `<th class="${c[2] ?? ''}">${esc(c[1])}</th>`).join('') +
  CFG.texts.map(c => `<th title="${esc(c[0])}">${esc(c[1])}</th>`).join('') +
  CFG.checks.map(c => `<th class="flag" title="${esc(c[0])}">${esc(c[1])}</th>`).join('') +
  '<th class="flag">확인</th>' +
  (CFG.detail ? '<th>설명</th>' : '');

// 계열 필터 ─ 플래그가 켜진 것과 '이름에 힌트가 있는 후보'를 같이 본다
let group = null, mode = 'both';
const groupOf = f => CFG.groups.find(g => g.field === f);
const isCand = (r, g) => g.hints.some(
  h => String(r[CFG.key] ?? '').toLowerCase().includes(h));

function inGroup(r) {
  if (!group) return true;
  const g = groupOf(group);
  const on = !!r[g.field];
  if (mode === 'on') return on;
  if (mode === 'cand') return !on && isCand(r, g);
  return on || isCand(r, g);
}

function visible() {
  const q = $('#q').value.trim().toLowerCase();
  const todo = $('#onlyTodo').checked;
  return rows.filter(r => {
    if (todo && r.reviewed) return false;
    if (!inGroup(r)) return false;
    if (!q) return true;
    return CFG.search.map(f => r[f] ?? '').join(' ').toLowerCase().includes(q);
  });
}

$('#chips').innerHTML =
  `<button class="chip on" data-g="">전체</button>` +
  CFG.groups.map(g =>
    `<button class="chip" data-g="${g.field}">${esc(g.label)}</button>`).join('');

$('#chips').addEventListener('click', e => {
  const b = e.target.closest('.chip');
  if (!b) return;
  group = b.dataset.g || null;
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('on', c === b));
  $('#mode').classList.toggle('show', !!group);
  render();
});

$('#mode').addEventListener('click', e => {
  const b = e.target.closest('button');
  if (!b) return;
  mode = b.dataset.m;
  $('#mode').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  render();
});

function render() {
  const list = visible();
  const done = rows.filter(r => r.reviewed).length;
  $('#count').textContent =
    `${list.length}개 표시 / 확인 ${done} / 전체 ${rows.length}`;

  if (group) {
    const g = groupOf(group);
    const on = rows.filter(r => r[g.field]).length;
    const cand = rows.filter(r => !r[g.field] && isCand(r, g)).length;
    $('#groupCount').textContent = `${g.label} 켜짐 ${on} / 후보 ${cand}`;
  }

  $('#rows').innerHTML = list.map(r => {
    // 선택한 계열의 칸은, 후보인데 아직 안 켜져 있으면 테두리로 표시한다
    const g = group ? groupOf(group) : null;
    const mark = f => (g && f === g.field && !r[f] && isCand(r, g)) ? ' cand' : '';
    return `
    <tr class="${r.reviewed ? 'done' : ''}" data-key="${esc(r[CFG.key])}">
      ${CFG.info.map(c => `<td class="${c[2] ?? ''}">${
          r[c[0]] === null || r[c[0]] === undefined
          ? '<i>·</i>' : esc(r[c[0]])}</td>`).join('')}
      ${CFG.texts.map(c => {
          const style = c[2] ? ` style="width:${c[2]}px"` : '';
          return c[3] === 'area'
            ? `<td class="wrap"><textarea class="txt" data-f="${c[0]}"
                 placeholder="비어 있음"${style}>${esc(r[c[0]] ?? '')}</textarea></td>`
            : `<td><input type="text" class="txt" data-f="${c[0]}"
                 placeholder="비어 있음"${style} value="${esc(r[c[0]] ?? '')}"></td>`;
        }).join('')}
      ${CFG.checks.map(c => `<td class="flag${mark(c[0])}"><input type="checkbox"
          data-f="${c[0]}" ${r[c[0]] ? 'checked' : ''}></td>`).join('')}
      <td class="flag"><input type="checkbox" data-f="reviewed"
          ${r.reviewed ? 'checked' : ''}></td>
      ${CFG.detail ? `<td class="detail" title="${esc(r[CFG.detail])}">${
          esc(r[CFG.detail])}</td>` : ''}
    </tr>`;
  }).join('');
}

async function post(body) {
  const res = await fetch('/api/save', {method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  if (!res.ok) { alert('저장 실패: ' + await res.text()); return null; }
  return res.json();
}

let timer;
function flash() {
  $('#saved').classList.add('on');
  clearTimeout(timer);
  timer = setTimeout(() => $('#saved').classList.remove('on'), 900);
}

function valuesOf(r) {
  const v = {};
  CFG.checks.forEach(c => v[c[0]] = !!r[c[0]]);
  CFG.texts.forEach(c => v[c[0]] = r[c[0]] ?? null);
  return v;
}

// 건드리면 그 줄만 즉시 저장한다 (저장 버튼 없음).
// 글자 칸은 change 라서 포커스를 벗어나거나 Enter 를 쳐야 저장된다.
// 한 글자마다 저장하면 조합 중인 한글이 그대로 들어간다.
$('#rows').addEventListener('change', async e => {
  const el = e.target;
  const isText = el.classList.contains('txt');
  if (el.type !== 'checkbox' && !isText) return;

  const r = rows.find(x => String(x[CFG.key]) === el.closest('tr').dataset.key);
  r[el.dataset.f] = isText ? (el.value.trim() || null) : el.checked;
  if (el.dataset.f !== 'reviewed') r.reviewed = true;   // 손대면 확인 처리
  if (await post({key: r[CFG.key], values: valuesOf(r), reviewed: r.reviewed})) {
    flash(); render();
  }
});

// 한 줄 칸에서 Enter 는 다음 줄 같은 칸으로 넘어간다. 쭉 채워 넣기 편하다.
// textarea 에서는 Enter 가 줄바꿈이어야 하므로 건드리지 않는다.
$('#rows').addEventListener('keydown', e => {
  if (e.key !== 'Enter' || !e.target.classList.contains('txt')) return;
  if (e.target.tagName === 'TEXTAREA') return;
  e.preventDefault();
  const cells = [...document.querySelectorAll(
    `input.txt[data-f="${e.target.dataset.f}"]`)];
  const next = cells[cells.indexOf(e.target) + 1];
  e.target.blur();
  if (next) setTimeout(() => { next.focus(); next.select(); }, 60);
});

$('#markPage').addEventListener('click', async () => {
  const list = visible().filter(r => !r.reviewed);
  if (!list.length) return;
  if (!confirm(`${list.length}개를 확인 처리합니다. 추측값을 그대로 확정합니다.`)) return;
  for (const r of list) {
    await post({key: r[CFG.key], values: valuesOf(r), reviewed: true});
    r.reviewed = true;
  }
  flash(); render();
});

$('#q').addEventListener('input', render);
$('#onlyTodo').addEventListener('change', render);
fetch('/api/rows').then(r => r.json()).then(d => { rows = d; render(); });
</script></body></html>
"""


def build_page(spec):
    cfg = {
        "key": spec.key_field,
        "info": spec.info_columns,
        "texts": spec.text_columns,
        "checks": spec.check_columns,
        "detail": spec.detail_field,
        "search": list(spec.search_fields),
        "groups": spec.groups,
    }
    return (PAGE
            .replace("__TITLE__", spec.title)
            .replace("__SUBTITLE__", spec.subtitle)
            .replace("__CONFIG__", json.dumps(cfg, ensure_ascii=False)))


def make_handler(spec):
    check_fields = [c[0] for c in spec.check_columns]
    text_fields = [c[0] for c in spec.text_columns]

    class Handler(BaseHTTPRequestHandler):

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            raw = body if isinstance(body, bytes) else body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/":
                return self._send(200, build_page(spec),
                                  "text/html; charset=utf-8")
            if self.path == "/api/rows":
                return self._send(
                    200, json.dumps(spec.fetch(), ensure_ascii=False))
            self._send(404, "{}")

        def do_POST(self):
            if self.path != "/api/save":
                return self._send(404, "{}")
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            try:
                key = body["key"]
                values = {f: bool(body["values"].get(f)) for f in check_fields}
                for f in text_fields:
                    raw = body["values"].get(f)
                    values[f] = raw.strip() or None if isinstance(raw, str) else None
                diff = spec.save(key, values, bool(body.get("reviewed")))
            except Exception as e:          # 브라우저에 그대로 띄운다
                return self._send(400, f"{type(e).__name__}: {e}",
                                  "text/plain; charset=utf-8")
            def show(v):
                if isinstance(v, bool):
                    return "O" if v else "X"
                if not v:
                    return "-"
                one_line = " ".join(str(v).split())
                return one_line if len(one_line) <= 30 else one_line[:29] + "…"

            mark = " ".join(
                f"{spec.labels.get(f, f)}={show(v)}"
                for f, v in (diff or {}).items()) or "기존 값 그대로"
            print(f"  {key:<24} {mark}")
            self._send(200, json.dumps({"ok": True}))

        def log_message(self, *a):
            pass                            # 요청 로그는 끈다

    return Handler


def serve(spec):
    url = f"http://localhost:{spec.port}"
    print(f"{spec.title} - {url}")
    print("체크하면 즉시 저장됩니다. 끝내려면 Ctrl+C\n")
    webbrowser.open(url)
    try:
        HTTPServer(("127.0.0.1", spec.port), make_handler(spec)).serve_forever()
    except KeyboardInterrupt:
        if spec.summary:
            print()
            spec.summary()
