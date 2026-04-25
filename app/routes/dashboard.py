"""
app/api/dashboard.py  —  Token consumption dashboard with Cases + Users tabs
"""

from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from app.llm.token_tracker import (
    get_all_case_ids,
    get_case_stats,
    get_case_timeline,
    get_all_user_ids,
    get_user_stats,
    get_user_timeline,
    get_model_stats,
    get_global_stats,
)

router = APIRouter()


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%d %b %Y, %H:%M") if ts else "—"


def _fmt_num(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ── JSON API ──────────────────────────────────────────────────────────────────


@router.get("/api/tokens/global")
async def api_global():
    return JSONResponse(await get_global_stats())


@router.get("/api/tokens/models")
async def api_models():
    return JSONResponse(await get_model_stats())


@router.get("/api/tokens/cases")
async def api_cases():
    ids = await get_all_case_ids()
    stats = sorted(
        [await get_case_stats(i) for i in ids],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )
    return JSONResponse(stats)


@router.get("/api/tokens/users")
async def api_users():
    ids = await get_all_user_ids()
    stats = sorted(
        [await get_user_stats(i) for i in ids],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )
    return JSONResponse(stats)


@router.get("/api/tokens/case/{case_id}/timeline")
async def api_case_timeline(case_id: str):
    return JSONResponse(await get_case_timeline(case_id, 50))


@router.get("/api/tokens/user/{user_id}/timeline")
async def api_user_timeline(user_id: str):
    return JSONResponse(await get_user_timeline(user_id, 50))


@router.get("/api/tokens/user/{user_id}/cases")
async def api_user_cases(user_id: str):
    stats = await get_user_stats(user_id)
    cases = sorted(
        [await get_case_stats(c) for c in stats["case_ids"]],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )
    return JSONResponse(cases)


# ── HTML dashboard ────────────────────────────────────────────────────────────


@router.get("/tokens", response_class=HTMLResponse)
async def token_dashboard():
    gs = await get_global_stats()
    model_stats = await get_model_stats()

    case_ids = await get_all_case_ids()
    case_list = sorted(
        [await get_case_stats(i) for i in case_ids],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )

    user_ids = await get_all_user_ids()
    user_list = sorted(
        [await get_user_stats(i) for i in user_ids],
        key=lambda x: x["total_tokens"],
        reverse=True,
    )

    model_rows = (
        "".join(
            f"""
        <tr>
          <td class="name">{m["model"]}</td>
          <td>{_fmt_num(m["input_tokens"])}</td>
          <td>{_fmt_num(m["output_tokens"])}</td>
          <td class="total">{_fmt_num(m["total_tokens"])}</td>
          <td>{m["calls"]}</td>
        </tr>"""
            for m in model_stats
        )
        or '<tr><td colspan="5" class="empty">No data yet</td></tr>'
    )

    def case_row(c):
        pct = min(100, int(c["total_tokens"] / max(gs["total_tokens"], 1) * 100))
        return f"""
        <tr class="clickable" onclick="loadTimeline('case','{c["case_id"]}')">
          <td class="id-col">{c["case_id"]}</td>
          <td class="muted-col">{c["user_id"]}</td>
          <td>{_fmt_num(c["input_tokens"])}</td>
          <td>{_fmt_num(c["output_tokens"])}</td>
          <td class="total">{_fmt_num(c["total_tokens"])}</td>
          <td>{c["calls"]}</td>
          <td class="warn">{c["last_model"]}</td>
          <td class="ts">{_fmt_ts(c["last_ts"])}</td>
          <td><div class="bar-wrap"><div class="bar" style="width:{pct}%"></div></div></td>
        </tr>"""

    def user_row(u):
        pct = min(100, int(u["total_tokens"] / max(gs["total_tokens"], 1) * 100))
        return f"""
        <tr class="clickable" onclick="loadTimeline('user','{u["user_id"]}')">
          <td class="id-col">{u["user_id"]}</td>
          <td>{_fmt_num(u["input_tokens"])}</td>
          <td>{_fmt_num(u["output_tokens"])}</td>
          <td class="total">{_fmt_num(u["total_tokens"])}</td>
          <td>{u["calls"]}</td>
          <td>{u["case_count"]}</td>
          <td class="warn">{u["last_model"]}</td>
          <td class="ts">{_fmt_ts(u["last_ts"])}</td>
          <td><div class="bar-wrap"><div class="bar" style="width:{pct}%"></div></div></td>
        </tr>"""

    case_rows = (
        "".join(case_row(c) for c in case_list[:50])
        or '<tr><td colspan="9" class="empty">No cases tracked yet</td></tr>'
    )
    user_rows = (
        "".join(user_row(u) for u in user_list[:50])
        or '<tr><td colspan="9" class="empty">No users tracked yet</td></tr>'
    )
    generated_at = datetime.now().strftime("%d %b %Y %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>DraftAI — Token Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com"/>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet"/>
<style>
  :root {{
    --bg:#0a0c10; --surface:#111318; --border:#1e2330;
    --accent:#00e5a0; --accent2:#7c6dfa; --warn:#f4a035;
    --text:#e8eaf0; --muted:#5a6278; --hover:#161b26;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ background:var(--bg); color:var(--text); font-family:'JetBrains Mono',monospace; font-size:13px; }}

  header {{
    display:flex; align-items:center; justify-content:space-between;
    padding:18px 32px; border-bottom:1px solid var(--border); background:var(--surface);
  }}
  .logo {{ font-family:'Syne',sans-serif; font-size:20px; font-weight:800; }}
  .logo span {{ color:var(--accent); }}
  .badge {{ background:var(--accent); color:#000; font-size:10px; font-weight:700; padding:2px 8px; border-radius:20px; margin-left:10px; }}
  .gen-time {{ color:var(--muted); font-size:11px; }}
  .refresh-btn {{ background:transparent; border:1px solid var(--border); color:var(--accent); padding:6px 16px; border-radius:6px; cursor:pointer; font-family:'JetBrains Mono',monospace; font-size:12px; transition:all .2s; }}
  .refresh-btn:hover {{ background:var(--accent); color:#000; }}

  main {{ padding:24px 32px; max-width:1500px; margin:0 auto; }}

  /* stat cards */
  .stat-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-bottom:28px; }}
  .stat-card {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; position:relative; overflow:hidden; }}
  .stat-card::before {{ content:''; position:absolute; inset:0 0 auto 0; height:2px; background:var(--accent); }}
  .stat-card.warn::before {{ background:var(--warn); }}
  .stat-card.purple::before {{ background:var(--accent2); }}
  .stat-label {{ font-size:11px; color:var(--muted); letter-spacing:1px; text-transform:uppercase; margin-bottom:8px; }}
  .stat-value {{ font-family:'Syne',sans-serif; font-size:30px; font-weight:800; line-height:1; }}
  .stat-sub {{ font-size:11px; color:var(--muted); margin-top:5px; }}

  /* tabs */
  .tabs {{ display:flex; gap:4px; margin-bottom:16px; border-bottom:1px solid var(--border); }}
  .tab {{ padding:10px 22px; cursor:pointer; font-size:12px; font-weight:600; color:var(--muted); border-bottom:2px solid transparent; transition:all .2s; letter-spacing:.5px; text-transform:uppercase; }}
  .tab:hover {{ color:var(--text); }}
  .tab.active {{ color:var(--accent); border-bottom-color:var(--accent); }}
  .tab-content {{ display:none; }}
  .tab-content.active {{ display:block; }}

  /* layout */
  .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:24px; }}
  h2 {{ font-family:'Syne',sans-serif; font-size:12px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:var(--muted); margin-bottom:12px; }}

  /* tables */
  .table-wrap {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }}
  table {{ width:100%; border-collapse:collapse; }}
  thead th {{ background:#0d1018; padding:9px 13px; text-align:left; font-size:11px; color:var(--muted); letter-spacing:1px; text-transform:uppercase; border-bottom:1px solid var(--border); }}
  tbody tr {{ border-bottom:1px solid var(--border); transition:background .15s; }}
  tbody tr:last-child {{ border-bottom:none; }}
  tbody tr.clickable {{ cursor:pointer; }}
  tbody tr.clickable:hover {{ background:var(--hover); }}
  tbody td {{ padding:9px 13px; white-space:nowrap; }}
  td.total {{ color:var(--accent); font-weight:600; }}
  td.id-col {{ color:var(--accent); font-weight:600; font-size:12px; }}
  td.name {{ color:var(--accent2); font-weight:600; }}
  td.warn {{ color:var(--warn); }}
  td.ts {{ color:var(--muted); font-size:11px; }}
  td.muted-col {{ color:var(--muted); font-size:11px; }}
  td.empty {{ color:var(--muted); padding:20px; }}
  .bar-wrap {{ width:100px; height:4px; background:var(--border); border-radius:2px; overflow:hidden; }}
  .bar {{ height:100%; background:linear-gradient(90deg,var(--accent),var(--accent2)); border-radius:2px; }}

  /* timeline panel */
  #tl-panel {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }}
  #tl-title {{ font-family:'Syne',sans-serif; font-size:13px; font-weight:700; color:var(--accent); margin-bottom:12px; }}
  .tl-row {{ display:flex; gap:14px; align-items:center; padding:7px 0; border-bottom:1px solid var(--border); font-size:12px; }}
  .tl-row:last-child {{ border-bottom:none; }}
  .tl-ts {{ color:var(--muted); width:145px; flex-shrink:0; }}
  .tl-model {{ color:var(--warn); width:75px; flex-shrink:0; }}
  .tl-case {{ color:var(--muted); font-size:11px; width:110px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; }}
  .tl-in {{ color:var(--text); }}
  .tl-out {{ color:var(--accent); }}
  .tl-badge {{ font-size:10px; padding:2px 5px; border-radius:4px; background:var(--border); color:var(--muted); }}
  #tl-placeholder {{ color:var(--muted); font-size:12px; padding:12px 0; }}

  @media(max-width:900px) {{ .stat-grid {{ grid-template-columns:1fr 1fr; }} .two-col {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>

<header>
  <div><span class="logo">Draft<span>AI</span></span><span class="badge">TOKEN DASHBOARD</span></div>
  <div class="gen-time">Generated: {generated_at}</div>
  <button class="refresh-btn" onclick="location.reload()">↻ Refresh</button>
</header>

<main>

  <!-- Global stats -->
  <div class="stat-grid">
    <div class="stat-card"><div class="stat-label">Total Tokens</div><div class="stat-value">{_fmt_num(gs["total_tokens"])}</div><div class="stat-sub">all-time combined</div></div>
    <div class="stat-card warn"><div class="stat-label">Input Tokens</div><div class="stat-value">{_fmt_num(gs["input_tokens"])}</div><div class="stat-sub">prompts sent</div></div>
    <div class="stat-card purple"><div class="stat-label">Output Tokens</div><div class="stat-value">{_fmt_num(gs["output_tokens"])}</div><div class="stat-sub">tokens generated</div></div>
    <div class="stat-card"><div class="stat-label">LLM Calls</div><div class="stat-value">{gs["calls"]}</div><div class="stat-sub">total API calls</div></div>
  </div>

  <!-- Tabs -->
  <div class="tabs">
    <div class="tab active" onclick="switchTab('cases')">📁 By Case</div>
    <div class="tab" onclick="switchTab('users')">👤 By User</div>
  </div>

  <!-- Cases tab -->
  <div id="tab-cases" class="tab-content active">
    <div class="two-col">
      <section>
        <h2>By Model</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Total</th><th>Calls</th></tr></thead>
            <tbody>{model_rows}</tbody>
          </table>
        </div>
      </section>
      <section>
        <h2>Call Timeline</h2>
        <div id="tl-panel" style="display:none">
          <div id="tl-title"></div>
          <div id="tl-content"></div>
        </div>
        <div id="tl-placeholder">← Click any row to inspect its call timeline</div>
      </section>
    </div>

    <section>
      <h2>Cases (top 50) — click to inspect</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Case ID</th><th>User ID</th><th>Input</th><th>Output</th><th>Total</th><th>Calls</th><th>Last Model</th><th>Last Activity</th><th>Share</th></tr></thead>
          <tbody id="case-tbody">{case_rows}</tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- Users tab -->
  <div id="tab-users" class="tab-content">
    <div class="two-col">
      <section>
        <h2>By Model</h2>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Model</th><th>Input</th><th>Output</th><th>Total</th><th>Calls</th></tr></thead>
            <tbody>{model_rows}</tbody>
          </table>
        </div>
      </section>
      <section>
        <h2>User Timeline</h2>
        <div id="tl-panel-u" style="display:none">
          <div id="tl-title-u"></div>
          <div id="tl-content-u"></div>
        </div>
        <div id="tl-placeholder-u">← Click any user row to inspect their timeline</div>
      </section>
    </div>

    <section>
      <h2>Users (top 50) — click to inspect</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>User ID</th><th>Input</th><th>Output</th><th>Total</th><th>Calls</th><th>Cases</th><th>Last Model</th><th>Last Activity</th><th>Share</th></tr></thead>
          <tbody id="user-tbody">{user_rows}</tbody>
        </table>
      </div>
    </section>
  </div>

</main>

<script>
function switchTab(name) {{
  document.querySelectorAll('.tab').forEach((t,i) => t.classList.toggle('active', ['cases','users'][i] === name));
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
}}

function fmtTs(ts) {{
  const d = new Date(ts * 1000);
  return d.toLocaleDateString('en-GB', {{day:'2-digit',month:'short',year:'numeric'}})
       + ', ' + d.toLocaleTimeString('en-GB', {{hour:'2-digit',minute:'2-digit',second:'2-digit'}});
}}

async function loadTimeline(type, id) {{
  const isUser = type === 'user';
  const panelId = isUser ? 'tl-panel-u' : 'tl-panel';
  const titleId = isUser ? 'tl-title-u' : 'tl-title';
  const contentId = isUser ? 'tl-content-u' : 'tl-content';
  const phId = isUser ? 'tl-placeholder-u' : 'tl-placeholder';

  document.getElementById(phId).style.display = 'none';
  document.getElementById(panelId).style.display = 'block';
  document.getElementById(titleId).textContent = (isUser ? 'User: ' : 'Case: ') + id;
  document.getElementById(contentId).innerHTML = '<div style="color:var(--muted)">Loading…</div>';

  try {{
    const url = isUser
      ? `/dashboard/api/tokens/user/${{encodeURIComponent(id)}}/timeline`
      : `/dashboard/api/tokens/case/${{encodeURIComponent(id)}}/timeline`;
    const rows = await (await fetch(url)).json();

    if (!rows.length) {{
      document.getElementById(contentId).innerHTML = '<div style="color:var(--muted)">No entries yet.</div>';
      return;
    }}

    document.getElementById(contentId).innerHTML = rows.map(r => `
      <div class="tl-row">
        <span class="tl-ts">${{fmtTs(r.ts)}}</span>
        <span class="tl-model">${{r.model}}</span>
        ${{isUser && r.case_id ? `<span class="tl-case">${{r.case_id}}</span>` : ''}}
        <span class="tl-badge">in</span><span class="tl-in">${{r.in.toLocaleString()}}</span>
        <span class="tl-badge">out</span><span class="tl-out">${{r.out.toLocaleString()}}</span>
      </div>`).join('');
  }} catch(e) {{
    document.getElementById(contentId).innerHTML = `<div style="color:#e55">Error: ${{e.message}}</div>`;
  }}
}}
</script>
</body>
</html>"""
    return HTMLResponse(content=html)
