"""HTML for the root ("/") landing page.

Kept as a plain string (no template engine dependency, no new requirements)
so it can be served straight from app/main.py, matching the approach used
for the /logs viewer in logs_page.py. Documents the same endpoints that
used to be dumped as plain text at "/", and also ships a small interactive
"Playground" tab so media can be previewed and downloaded straight from
the browser without touching curl or Postman.
"""

from __future__ import annotations

LANDING_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Universal Media Downloader API</title>
<style>
  :root{
    --bg:#0a0d10;
    --panel:#10151a;
    --panel-2:#0d1216;
    --border:#1f2933;
    --text:#d7e0e6;
    --muted:#6d7d8a;
    --accent:#3ddc84;
    --accent-dim:#1f5c3d;
    --get:#4fb0e8;
    --post:#e8b74f;
    --error:#f0554f;
    font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
  }
  *{box-sizing:border-box;}
  html,body{margin:0;min-height:100%;background:var(--bg);color:var(--text);}
  body{font-size:14px;line-height:1.6;}

  a{color:var(--accent);text-decoration:none;}
  a:hover{text-decoration:underline;}

  header{
    display:flex;align-items:center;gap:12px;
    padding:20px 24px;border-bottom:1px solid var(--border);
    background:var(--panel);flex-wrap:wrap;
  }
  header .dot{width:9px;height:9px;border-radius:50%;background:var(--accent);box-shadow:0 0 8px var(--accent);flex-shrink:0;}
  header h1{font-size:15px;font-weight:600;margin:0;letter-spacing:.02em;color:var(--text);}
  header .sub{color:var(--muted);font-size:12px;margin-top:2px;}
  header .titles{margin-right:auto;}
  header nav{display:flex;gap:8px;flex-wrap:wrap;}
  header nav a{
    border:1px solid var(--border);border-radius:999px;padding:6px 14px;
    font-size:12px;color:var(--text);white-space:nowrap;
  }
  header nav a:hover{border-color:var(--accent);color:var(--accent);text-decoration:none;}
  header nav a.primary{border-color:var(--accent-dim);color:var(--accent);}

  main{max-width:860px;margin:0 auto;padding:24px 24px 64px;}

  .tabs{display:flex;gap:8px;margin-bottom:28px;border-bottom:1px solid var(--border);}
  .tab{
    appearance:none;border:none;background:transparent;color:var(--muted);
    font-family:inherit;font-size:13px;font-weight:600;letter-spacing:.02em;
    padding:10px 4px;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;
  }
  .tab:hover{color:var(--text);}
  .tab[data-active="true"]{color:var(--accent);border-bottom-color:var(--accent);}
  .tab + .tab{margin-left:14px;}
  .panel{display:none;}
  .panel[data-active="true"]{display:block;}

  section{margin-bottom:36px;}
  section h2{
    font-size:12px;text-transform:uppercase;letter-spacing:.08em;
    color:var(--muted);font-weight:600;margin:0 0 14px;
  }

  .card{
    background:var(--panel);border:1px solid var(--border);border-radius:10px;
    padding:16px 18px;margin-bottom:10px;
  }
  .route{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;margin-bottom:6px;}
  .method{
    font-size:11px;font-weight:700;letter-spacing:.03em;padding:2px 8px;border-radius:5px;
    background:var(--panel-2);border:1px solid var(--border);flex-shrink:0;
  }
  .method.get{color:var(--get);border-color:var(--get);}
  .method.post{color:var(--post);border-color:var(--post);}
  .path{color:var(--text);font-size:13.5px;word-break:break-all;}
  .desc{color:var(--muted);font-size:12.5px;margin:0;}
  .desc code{color:var(--text);background:var(--panel-2);border-radius:4px;padding:1px 5px;font-size:12px;}

  .fields{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px;}
  .field{
    font-size:11.5px;color:var(--muted);background:var(--panel-2);
    border:1px solid var(--border);border-radius:5px;padding:3px 8px;
  }
  .field b{color:var(--text);font-weight:600;}

  .callout{
    border:1px solid var(--accent-dim);background:rgba(61,220,132,.06);
    border-radius:10px;padding:14px 18px;color:var(--text);font-size:13px;
  }
  .callout a{font-weight:600;}

  footer{
    text-align:center;color:var(--muted);font-size:11.5px;
    padding:20px 24px 32px;
  }

  /* --- Playground --- */
  .pg-card{
    background:var(--panel);border:1px solid var(--border);border-radius:12px;
    padding:20px;margin-bottom:18px;
  }
  .pg-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px;}
  .pg-row:last-child{margin-bottom:0;}
  .pg-field{display:flex;flex-direction:column;gap:6px;flex:1;min-width:130px;}
  .pg-field.wide{flex-basis:100%;}
  .pg-field label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;}
  .pg-field input[type="text"],
  .pg-field input[type="url"],
  .pg-field select{
    background:var(--panel-2);border:1px solid var(--border);color:var(--text);
    border-radius:8px;padding:10px 12px;font-size:13px;font-family:inherit;width:100%;
  }
  .pg-field input:focus,.pg-field select:focus{outline:none;border-color:var(--accent);}
  .pg-check{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);flex:0 0 auto;align-self:flex-end;padding-bottom:10px;}
  .pg-check input{accent-color:var(--accent);width:14px;height:14px;}

  .pg-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px;}
  button.pg-btn{
    appearance:none;border:1px solid var(--border);background:var(--panel-2);color:var(--text);
    font-family:inherit;font-size:13px;font-weight:600;border-radius:8px;
    padding:10px 18px;cursor:pointer;transition:border-color .15s,color .15s,background .15s;
  }
  button.pg-btn:hover{border-color:var(--muted);}
  button.pg-btn.primary{background:var(--accent);color:#06130a;border-color:var(--accent);}
  button.pg-btn.primary:hover{background:#35c878;}
  button.pg-btn:disabled{opacity:.55;cursor:not-allowed;}

  #pgStatus{margin-top:14px;font-size:12.5px;color:var(--muted);min-height:18px;}
  #pgStatus.error{color:var(--error);}
  #pgStatus.success{color:var(--accent);}

  #pgPreview{display:none;margin-top:16px;gap:14px;padding-top:16px;border-top:1px solid var(--border);}
  #pgPreview.show{display:flex;flex-wrap:wrap;}
  #pgPreview img{
    width:160px;max-width:100%;border-radius:8px;border:1px solid var(--border);
    object-fit:cover;aspect-ratio:16/9;background:var(--panel-2);
  }
  #pgPreview .pg-meta{flex:1;min-width:180px;}
  #pgPreview .pg-meta .title{font-size:14px;color:var(--text);font-weight:600;margin-bottom:6px;word-break:break-word;}
  #pgPreview .pg-meta .sub{font-size:12px;color:var(--muted);}
  #pgPreview .pg-meta .sub + .sub{margin-top:2px;}

  .pg-hint{color:var(--muted);font-size:12px;margin-top:10px;}

  @media (max-width:520px){
    header{padding:16px;}
    main{padding:20px 16px 48px;}
    .pg-check{align-self:flex-start;padding-bottom:0;}
  }
</style>
</head>
<body>
  <header>
    <span class="dot"></span>
    <div class="titles">
      <h1>Universal Media Downloader</h1>
      <div class="sub">yt-dlp powered media downloader &amp; Telegram delivery API</div>
    </div>
    <nav>
      <a href="docs">API docs</a>
      <a href="logs" class="primary">Live logs</a>
    </nav>
  </header>

  <main>
    <div class="tabs" id="tabs">
      <button class="tab" data-tab="playground" data-active="true">Playground</button>
      <button class="tab" data-tab="api">API reference</button>
    </div>

    <section class="panel" id="panel-playground" data-active="true">
      <h2>Try it in the browser</h2>
      <div class="pg-card">
        <div class="pg-row">
          <div class="pg-field wide">
            <label for="pgUrl">Media URL</label>
            <input id="pgUrl" type="url" placeholder="https://x.com/.../status/..." autocomplete="off" />
          </div>
        </div>
        <div class="pg-row">
          <div class="pg-field">
            <label for="pgType">Media type</label>
            <select id="pgType">
              <option value="video">Video</option>
              <option value="audio">Audio</option>
              <option value="auto">Any (image / gif / video)</option>
            </select>
          </div>
          <div class="pg-field">
            <label for="pgQuality">Quality</label>
            <select id="pgQuality">
              <option value="best">Best</option>
              <option value="1080p">1080p</option>
              <option value="720p">720p</option>
              <option value="480p">480p</option>
              <option value="360p">360p</option>
            </select>
          </div>
          <div class="pg-field">
            <label for="pgCookies">Cookies</label>
            <select id="pgCookies">
              <option value="">None</option>
            </select>
          </div>
          <div class="pg-check">
            <input id="pgPlaylist" type="checkbox" />
            <label for="pgPlaylist">Playlist</label>
          </div>
        </div>

        <div class="pg-actions">
          <button class="pg-btn" id="pgPreviewBtn" type="button">Preview info</button>
          <button class="pg-btn primary" id="pgDownloadBtn" type="button">Download</button>
        </div>

        <div id="pgStatus"></div>

        <div id="pgPreview">
          <img id="pgThumb" alt="" />
          <div class="pg-meta">
            <div class="title" id="pgTitle"></div>
            <div class="sub" id="pgUploader"></div>
            <div class="sub" id="pgDuration"></div>
            <div class="sub" id="pgFormats"></div>
          </div>
        </div>

        <p class="pg-hint">
          Preview fetches metadata only (via <code>/info</code>). Download streams the
          file directly from <code>/download</code> — your browser will save it like any
          normal file download. Cookies come from the <code>cookies/</code> folder on the server.
        </p>
      </div>
    </section>

    <section class="panel" id="panel-api">
      <section>
        <h2>Sync — returns the file bytes</h2>
        <div class="card">
          <div class="route"><span class="method get">GET</span><span class="path">/download</span></div>
          <p class="desc">Downloads the media and streams the raw file straight back (e.g. for a bot to re-upload to Telegram).</p>
          <div class="fields">
            <span class="field"><b>url</b> — source link</span>
            <span class="field"><b>media_type</b> — video | audio</span>
            <span class="field"><b>quality</b> — best / 720p / etc</span>
            <span class="field"><b>cookies</b> — file.txt in ./cookies/</span>
            <span class="field"><b>playlist</b> — true | false</span>
          </div>
        </div>
        <div class="card">
          <div class="route"><span class="method get">GET</span><span class="path">/info</span></div>
          <p class="desc">Looks up metadata for a URL without downloading anything.</p>
          <div class="fields">
            <span class="field"><b>url</b> — source link</span>
            <span class="field"><b>cookies</b> — file.txt in ./cookies/</span>
          </div>
        </div>
        <p class="desc">POST variants of both routes accept the same fields as a JSON body.</p>
      </section>

      <section>
        <h2>Webhook — push, Cobalt-style (sends straight to Telegram)</h2>
        <div class="card">
          <div class="route"><span class="method post">POST</span><span class="path">/jobs</span></div>
          <p class="desc">Queues a download and delivers the result directly into a Telegram chat using the supplied bot token. Returns immediately with a job id.</p>
          <div class="fields">
            <span class="field"><b>url</b></span>
            <span class="field"><b>chat_id</b></span>
            <span class="field"><b>bot_token</b></span>
            <span class="field"><b>media_type</b></span>
            <span class="field"><b>quality</b></span>
            <span class="field"><b>cookies</b></span>
            <span class="field"><b>playlist</b></span>
            <span class="field"><b>caption</b></span>
          </div>
        </div>
        <div class="card">
          <div class="route"><span class="method get">GET</span><span class="path">/jobs/&lt;job_id&gt;</span></div>
          <p class="desc">Checks the status of a previously queued job.</p>
        </div>
      </section>

      <section>
        <h2>Observability</h2>
        <div class="callout">
          Watch requests and downloads as they happen in a live-tailing,
          filterable log viewer — <a href="logs">open /logs</a>.
          Add <code>?key=...</code> to the URL if <code>YDL_LOGS_SECRET</code> is set.
        </div>
      </section>
    </section>
  </main>

  <footer>Interactive Swagger docs are available at <a href="docs">/docs</a>.</footer>

<script>
(function () {
  // --- Tabs ---
  var tabs = document.querySelectorAll("#tabs .tab");
  Array.prototype.forEach.call(tabs, function (btn) {
    btn.addEventListener("click", function () {
      Array.prototype.forEach.call(tabs, function (b) { b.setAttribute("data-active", "false"); });
      Array.prototype.forEach.call(document.querySelectorAll("main > .panel"), function (p) { p.setAttribute("data-active", "false"); });
      btn.setAttribute("data-active", "true");
      document.getElementById("panel-" + btn.getAttribute("data-tab")).setAttribute("data-active", "true");
    });
  });

  // --- Playground ---
  var urlInput = document.getElementById("pgUrl");
  var typeSelect = document.getElementById("pgType");
  var qualitySelect = document.getElementById("pgQuality");
  var cookiesSelect = document.getElementById("pgCookies");
  var playlistCheck = document.getElementById("pgPlaylist");
  var previewBtn = document.getElementById("pgPreviewBtn");
  var downloadBtn = document.getElementById("pgDownloadBtn");
  var statusEl = document.getElementById("pgStatus");
  var previewEl = document.getElementById("pgPreview");
  var thumbEl = document.getElementById("pgThumb");
  var titleEl = document.getElementById("pgTitle");
  var uploaderEl = document.getElementById("pgUploader");
  var durationEl = document.getElementById("pgDuration");
  var formatsEl = document.getElementById("pgFormats");

  function setStatus(msg, kind) {
    statusEl.textContent = msg || "";
    statusEl.className = kind || "";
  }

  function fmtDuration(sec) {
    if (!sec || isNaN(sec)) return null;
    sec = Math.round(sec);
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var parts = [];
    if (h) parts.push(h);
    parts.push(h ? String(m).padStart(2, "0") : m);
    parts.push(String(s).padStart(2, "0"));
    return parts.join(":");
  }

  // Populate cookies dropdown from the server's cookies/ folder.
  fetch("cookies").then(function (r) { return r.ok ? r.json() : null; }).then(function (data) {
    if (!data || !Array.isArray(data.cookies)) return;
    data.cookies.forEach(function (name) {
      var opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      cookiesSelect.appendChild(opt);
    });
  }).catch(function () { /* cookies listing is optional, ignore failures */ });

  function buildParams() {
    var params = new URLSearchParams();
    params.set("url", urlInput.value.trim());
    params.set("media_type", typeSelect.value);
    params.set("quality", qualitySelect.value);
    if (cookiesSelect.value) params.set("cookies", cookiesSelect.value);
    if (playlistCheck.checked) params.set("playlist", "true");
    return params;
  }

  function validateUrl() {
    var v = urlInput.value.trim();
    if (!v) {
      setStatus("Paste a media URL first.", "error");
      urlInput.focus();
      return false;
    }
    return true;
  }

  previewBtn.addEventListener("click", function () {
    if (!validateUrl()) return;
    previewEl.classList.remove("show");
    setStatus("Fetching info…");
    previewBtn.disabled = true;

    var params = new URLSearchParams();
    params.set("url", urlInput.value.trim());
    if (cookiesSelect.value) params.set("cookies", cookiesSelect.value);
    if (playlistCheck.checked) params.set("playlist", "true");

    fetch("info?" + params.toString())
      .then(function (r) { return r.json().then(function (data) { return { ok: r.ok, data: data }; }); })
      .then(function (res) {
        if (!res.ok || res.data.ok === false) {
          throw new Error((res.data && (res.data.error || res.data.detail)) || "Could not fetch info.");
        }
        var info = res.data.info || res.data;
        titleEl.textContent = info.is_playlist
          ? (info.playlist_title || "Playlist") + " (" + (info.entry_count || 0) + " items)"
          : (info.title || "Untitled");
        uploaderEl.textContent = info.uploader ? "By " + info.uploader : "";
        var d = fmtDuration(info.duration);
        durationEl.textContent = d ? "Duration " + d : "";
        var formats = Array.isArray(info.formats) ? info.formats : [];
        formatsEl.textContent = formats.length ? formats.length + " format(s) available" : "";
        if (info.thumbnail) {
          thumbEl.src = info.thumbnail;
          thumbEl.style.display = "";
        } else {
          thumbEl.style.display = "none";
        }
        previewEl.classList.add("show");
        setStatus("Info loaded.", "success");
      })
      .catch(function (err) {
        setStatus(err.message || "Could not fetch info.", "error");
      })
      .finally(function () {
        previewBtn.disabled = false;
      });
  });

  downloadBtn.addEventListener("click", function () {
    if (!validateUrl()) return;
    setStatus("Starting download — this may take a moment for large files…");
    var params = buildParams();
    // Let the browser handle the actual streaming/save-to-disk itself,
    // exactly like clicking a normal file link — no need to buffer the
    // whole file in JS memory first.
    window.location.href = "download?" + params.toString();
    setTimeout(function () {
      setStatus("If the download didn't start, the URL may be invalid or blocked — check the message on this page or try Preview info first.");
    }, 4000);
  });

  urlInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      downloadBtn.click();
    }
  });
})();
</script>
</body>
</html>
"""
