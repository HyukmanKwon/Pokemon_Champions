"""annotator 공통 뼈대. 표 하나를 브라우저에서 체크하며 고치는 도구.

각 annotator(moves.py 등)는 Spec 하나를 만들어 serve() 에 넘긴다.
서버·HTML·저장 흐름은 전부 여기 있고, 개별 파일은 "무엇을 보여주고
무엇을 체크할지"만 정한다.

── 경로 처리 ──
  이 폴더는 database/ 의 하위라서, 부모를 sys.path 에 넣어야
  `import db`, `import schema` 같은 평평한 import 가 그대로 통한다.
  annotator 파일들은 맨 위에서 이 모듈부터 import 할 것.

── 의존 패키지 없음 ──
  표준 라이브러리 http.server 만 쓴다.
"""

import json
import sys
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Callable

# database/ 를 import 경로에 추가한다. 다른 import 보다 먼저 와야 한다.
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


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
    # 한 행을 저장하는 함수. (키, {체크필드: bool}, reviewed) -> 바뀐 것 dict
    save: Callable
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
  <h1>__TITLE__ &mdash; 추측값을 훑어보고 틀린 것만 고치세요</h1>
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
  return v;
}

// 체크박스를 건드리면 그 줄만 즉시 저장한다 (저장 버튼 없음)
$('#rows').addEventListener('change', async e => {
  const box = e.target;
  if (box.type !== 'checkbox') return;
  const r = rows.find(x => String(x[CFG.key]) === e.target.closest('tr').dataset.key);
  r[box.dataset.f] = box.checked;
  if (box.dataset.f !== 'reviewed') r.reviewed = true;   // 손대면 확인 처리
  if (await post({key: r[CFG.key], values: valuesOf(r), reviewed: r.reviewed})) {
    flash(); render();
  }
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
        "checks": spec.check_columns,
        "detail": spec.detail_field,
        "search": list(spec.search_fields),
        "groups": spec.groups,
    }
    return (PAGE
            .replace("__TITLE__", spec.title)
            .replace("__CONFIG__", json.dumps(cfg, ensure_ascii=False)))


def make_handler(spec):
    check_fields = [c[0] for c in spec.check_columns]

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
                diff = spec.save(key, values, bool(body.get("reviewed")))
            except Exception as e:          # 브라우저에 그대로 띄운다
                return self._send(400, f"{type(e).__name__}: {e}",
                                  "text/plain; charset=utf-8")
            mark = " ".join(
                f"{spec.labels.get(f, f)}={'O' if v else 'X'}"
                for f, v in (diff or {}).items()) or "추측 그대로"
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
