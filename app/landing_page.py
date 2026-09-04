"""HTML for the root ("/") landing page.

Kept as a plain string (no template engine dependency, no new requirements)
so it can be served straight from app/main.py, matching the approach used
for the /logs viewer in logs_page.py. Purely informational — it documents
the same endpoints that used to be dumped as plain text at "/".
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

  main{max-width:860px;margin:0 auto;padding:32px 24px 64px;}

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

  @media (max-width:520px){
    header{padding:16px;}
    main{padding:24px 16px 48px;}
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
  </main>

  <footer>Interactive Swagger docs are available at <a href="docs">/docs</a>.</footer>
</body>
</html>
"""
