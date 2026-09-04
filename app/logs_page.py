"""HTML for the /logs live viewer page.

Kept as a plain string (no template engine dependency) so the page can be
served straight from app/main.py with zero extra requirements. It renders
the recent-log backlog immediately, then subscribes to /logs/stream (SSE)
for live updates.
"""

from __future__ import annotations

LOGS_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Live Logs · Universal Media Downloader</title>
<style>
  :root{
    --bg:#0a0d10;
    --panel:#10151a;
    --border:#1f2933;
    --text:#d7e0e6;
    --muted:#6d7d8a;
    --accent:#3ddc84;
    --accent-dim:#1f5c3d;
    --debug:#6d7d8a;
    --info:#4fb0e8;
    --warning:#e8b74f;
    --error:#f0554f;
    --critical:#ff5f8f;
    font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--text);}
  body{display:flex;flex-direction:column;font-size:13px;}

  header{
    display:flex;align-items:center;gap:12px;
    padding:12px 16px;border-bottom:1px solid var(--border);
    background:var(--panel);flex-wrap:wrap;
  }
  .brand{display:flex;align-items:center;gap:8px;margin-right:auto;}
  .brand .dot{width:9px;height:9px;border-radius:50%;background:var(--muted);flex-shrink:0;transition:background .2s,box-shadow .2s;}
  .brand .dot.live{background:var(--accent);box-shadow:0 0 8px var(--accent);}
  .brand .dot.down{background:var(--error);box-shadow:0 0 8px var(--error);}
  .brand h1{font-size:13px;font-weight:600;margin:0;letter-spacing:.02em;color:var(--text);}
  .brand .sub{color:var(--muted);font-size:11px;}

  .filters{display:flex;gap:6px;flex-wrap:wrap;}
  button.pill,label.pill{
    appearance:none;border:1px solid var(--border);background:transparent;color:var(--muted);
    padding:5px 10px;border-radius:999px;font-size:11px;font-family:inherit;cursor:pointer;
    display:flex;align-items:center;gap:6px;user-select:none;transition:border-color .15s,color .15s;
  }
  button.pill:hover{border-color:var(--muted);}
  button.pill[data-active="true"]{color:var(--bg);background:var(--text);border-color:var(--text);}
  input#search{
    background:var(--bg);border:1px solid var(--border);color:var(--text);
    border-radius:999px;padding:5px 12px;font-size:11px;font-family:inherit;width:180px;
  }
  input#search:focus{outline:none;border-color:var(--accent);}
  button.action{
    appearance:none;border:1px solid var(--border);background:transparent;color:var(--muted);
    padding:5px 10px;border-radius:6px;font-size:11px;font-family:inherit;cursor:pointer;
  }
  button.action:hover{color:var(--text);border-color:var(--muted);}
  button.action[data-active="true"]{color:var(--accent);border-color:var(--accent-dim);}

  main{flex:1;overflow:auto;padding:0;position:relative;}
  #log{padding:8px 0 24px;}
  .row{
    display:flex;gap:10px;padding:2px 16px;white-space:pre-wrap;word-break:break-word;
    line-height:1.55;border-left:2px solid transparent;
  }
  .row:hover{background:rgba(255,255,255,.02);}
  .row .t{color:var(--muted);flex-shrink:0;}
  .row .lvl{flex-shrink:0;font-weight:700;width:58px;}
  .row .logger{color:var(--muted);flex-shrink:0;}
  .row .msg{flex:1;color:var(--text);}
  .row.level-DEBUG .lvl{color:var(--debug);}
  .row.level-INFO .lvl{color:var(--info);}
  .row.level-WARNING{border-left-color:var(--warning);}
  .row.level-WARNING .lvl{color:var(--warning);}
  .row.level-ERROR{border-left-color:var(--error);background:rgba(240,85,79,.06);}
  .row.level-ERROR .lvl{color:var(--error);}
  .row.level-CRITICAL{border-left-color:var(--critical);background:rgba(255,95,143,.08);}
  .row.level-CRITICAL .lvl{color:var(--critical);}
  .row.hidden{display:none;}

  #empty{color:var(--muted);padding:24px 16px;}

  footer{
    display:flex;align-items:center;gap:16px;padding:6px 16px;
    border-top:1px solid var(--border);background:var(--panel);color:var(--muted);font-size:11px;
  }
  footer .spacer{flex:1;}

  #jump{
    position:fixed;right:20px;bottom:52px;background:var(--accent);color:#06130a;
    border:none;border-radius:999px;padding:8px 14px;font-size:11px;font-weight:600;
    cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.4);display:none;font-family:inherit;
  }
</style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="dot" id="statusDot"></span>
      <div>
        <h1>Live Logs</h1>
        <div class="sub">Universal Media Downloader</div>
      </div>
    </div>

    <div class="filters" id="levelFilters">
      <button class="pill" data-level="DEBUG" data-active="true">Debug</button>
      <button class="pill" data-level="INFO" data-active="true">Info</button>
      <button class="pill" data-level="WARNING" data-active="true">Warning</button>
      <button class="pill" data-level="ERROR" data-active="true">Error</button>
      <button class="pill" data-level="CRITICAL" data-active="true">Critical</button>
    </div>

    <input id="search" type="text" placeholder="Filter text (e.g. job id, url)…" />

    <button class="action" id="pauseBtn">Pause</button>
    <button class="action" id="autoscrollBtn" data-active="true">Autoscroll</button>
    <button class="action" id="clearBtn">Clear</button>
  </header>

  <main id="main">
    <div id="log"></div>
    <div id="empty" style="display:none;">No log lines yet. Waiting for activity…</div>
  </main>

  <button id="jump">↓ Jump to latest</button>

  <footer>
    <span id="countLabel">0 lines</span>
    <span class="spacer"></span>
    <span id="connLabel">connecting…</span>
  </footer>

<script>
(function () {
  var logEl = document.getElementById("log");
  var emptyEl = document.getElementById("empty");
  var mainEl = document.getElementById("main");
  var dot = document.getElementById("statusDot");
  var connLabel = document.getElementById("connLabel");
  var countLabel = document.getElementById("countLabel");
  var searchInput = document.getElementById("search");
  var jumpBtn = document.getElementById("jump");
  var pauseBtn = document.getElementById("pauseBtn");
  var autoscrollBtn = document.getElementById("autoscrollBtn");
  var clearBtn = document.getElementById("clearBtn");
  var levelFiltersEl = document.getElementById("levelFilters");

  var MAX_ROWS = 2000;
  var paused = false;
  var autoscroll = true;
  var searchTerm = "";
  var activeLevels = { DEBUG: true, INFO: true, WARNING: true, ERROR: true, CRITICAL: true };
  var pending = [];
  var count = 0;

  function keyParam() {
    var params = new URLSearchParams(window.location.search);
    var key = params.get("key");
    return key ? "?key=" + encodeURIComponent(key) : "";
  }

  function fmtTime(ts) {
    var d = new Date(ts * 1000);
    return d.toLocaleTimeString([], { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
  }

  function matches(entry) {
    if (!activeLevels[entry.level]) return false;
    if (searchTerm && entry.message.toLowerCase().indexOf(searchTerm) === -1
        && (entry.logger || "").toLowerCase().indexOf(searchTerm) === -1) return false;
    return true;
  }

  function render(entry) {
    var row = document.createElement("div");
    row.className = "row level-" + entry.level;
    if (!matches(entry)) row.classList.add("hidden");
    var t = document.createElement("span"); t.className = "t"; t.textContent = fmtTime(entry.time);
    var lvl = document.createElement("span"); lvl.className = "lvl"; lvl.textContent = entry.level;
    var logger = document.createElement("span"); logger.className = "logger"; logger.textContent = entry.logger;
    var msg = document.createElement("span"); msg.className = "msg"; msg.textContent = entry.message;
    row.appendChild(t); row.appendChild(lvl); row.appendChild(logger); row.appendChild(msg);
    logEl.appendChild(row);
    count++;
    while (logEl.children.length > MAX_ROWS) logEl.removeChild(logEl.firstChild);
    emptyEl.style.display = "none";
    countLabel.textContent = count + " line" + (count === 1 ? "" : "s");
  }

  function isNearBottom() {
    return mainEl.scrollHeight - mainEl.scrollTop - mainEl.clientHeight < 80;
  }

  function scrollToBottom() {
    mainEl.scrollTop = mainEl.scrollHeight;
    jumpBtn.style.display = "none";
  }

  function flush() {
    if (!pending.length) return;
    var wasNearBottom = isNearBottom();
    pending.forEach(render);
    pending = [];
    if (autoscroll && wasNearBottom) scrollToBottom();
    else if (autoscroll) jumpBtn.style.display = "block";
  }
  setInterval(flush, 150);

  mainEl.addEventListener("scroll", function () {
    if (isNearBottom()) jumpBtn.style.display = "none";
  });
  jumpBtn.addEventListener("click", function () { autoscroll = true; scrollToBottom(); });

  pauseBtn.addEventListener("click", function () {
    paused = !paused;
    pauseBtn.textContent = paused ? "Resume" : "Pause";
    pauseBtn.setAttribute("data-active", paused ? "true" : "false");
  });

  autoscrollBtn.addEventListener("click", function () {
    autoscroll = !autoscroll;
    autoscrollBtn.setAttribute("data-active", autoscroll ? "true" : "false");
    if (autoscroll) scrollToBottom();
  });

  clearBtn.addEventListener("click", function () {
    logEl.innerHTML = "";
    count = 0;
    countLabel.textContent = "0 lines";
    emptyEl.style.display = "block";
  });

  searchInput.addEventListener("input", function () {
    searchTerm = searchInput.value.trim().toLowerCase();
    Array.prototype.forEach.call(logEl.children, function (row) {
      var msg = row.querySelector(".msg").textContent.toLowerCase();
      var logger = row.querySelector(".logger").textContent.toLowerCase();
      var levelOk = activeLevels[row.className.replace("row level-", "")];
      var hit = !searchTerm || msg.indexOf(searchTerm) !== -1 || logger.indexOf(searchTerm) !== -1;
      row.classList.toggle("hidden", !(levelOk && hit));
    });
  });

  Array.prototype.forEach.call(levelFiltersEl.children, function (btn) {
    btn.addEventListener("click", function () {
      var lvl = btn.getAttribute("data-level");
      activeLevels[lvl] = !activeLevels[lvl];
      btn.setAttribute("data-active", activeLevels[lvl] ? "true" : "false");
      Array.prototype.forEach.call(logEl.querySelectorAll(".row.level-" + lvl), function (row) {
        var msg = row.querySelector(".msg").textContent.toLowerCase();
        var logger = row.querySelector(".logger").textContent.toLowerCase();
        var hit = !searchTerm || msg.indexOf(searchTerm) !== -1 || logger.indexOf(searchTerm) !== -1;
        row.classList.toggle("hidden", !(activeLevels[lvl] && hit));
      });
    });
  });

  function connect() {
    var es = new EventSource("logs/stream" + keyParam());
    es.onopen = function () {
      dot.className = "dot live";
      connLabel.textContent = "live";
    };
    es.onerror = function () {
      dot.className = "dot down";
      connLabel.textContent = "reconnecting…";
    };
    es.onmessage = function (ev) {
      if (paused) return;
      try {
        var entry = JSON.parse(ev.data);
        pending.push(entry);
      } catch (e) { /* ignore malformed frame */ }
    };
  }

  connect();
})();
</script>
</body>
</html>
"""
