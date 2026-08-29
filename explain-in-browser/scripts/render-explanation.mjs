#!/usr/bin/env node
/**
 * Render markdown to a self-contained reading page and open it.
 *
 *   node render-explanation.mjs --in path.md [--out path.html] [--title T] [--no-open]
 *   cat notes.md | node render-explanation.mjs --title T
 */
import { spawn } from 'node:child_process';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { basename, dirname, extname, join, resolve } from 'node:path';
import { stdin } from 'node:process';

export function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function applyInline(text) {
  const parts = [];
  const src = String(text);
  let i = 0;
  while (i < src.length) {
    if (src.startsWith('`', i)) {
      const end = src.indexOf('`', i + 1);
      if (end !== -1) {
        parts.push(`<code>${escapeHtml(src.slice(i + 1, end))}</code>`);
        i = end + 1;
        continue;
      }
    }
    if (src.startsWith('[', i)) {
      const m = src.slice(i).match(/^\[([^\]]+)\]\(([^)]+)\)/);
      if (m) {
        const href = escapeHtml(m[2]);
        parts.push(`<a href="${href}">${applyInline(m[1])}</a>`);
        i += m[0].length;
        continue;
      }
    }
    if (src.startsWith('**', i)) {
      const end = src.indexOf('**', i + 2);
      if (end !== -1) {
        parts.push(`<strong>${applyInline(src.slice(i + 2, end))}</strong>`);
        i = end + 2;
        continue;
      }
    }
    if (src.startsWith('*', i) && !src.startsWith('**', i)) {
      const end = src.indexOf('*', i + 1);
      if (end !== -1) {
        parts.push(`<em>${applyInline(src.slice(i + 1, end))}</em>`);
        i = end + 1;
        continue;
      }
    }
    const next = src.slice(i).search(/`|\*\*|\[|\*/);
    const chunk = next === -1 ? src.slice(i) : src.slice(i, i + next);
    parts.push(escapeHtml(chunk));
    i = next === -1 ? src.length : i + next;
  }
  return parts.join('');
}

function isTableSeparator(line) {
  return /^\s*\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/.test(line);
}

function splitRow(line) {
  let s = line.trim();
  if (s.startsWith('|')) s = s.slice(1);
  if (s.endsWith('|')) s = s.slice(0, -1);
  return s.split('|').map((cell) => cell.trim());
}

export function markdownToHtml(markdown) {
  const lines = String(markdown).replace(/\r\n/g, '\n').split('\n');
  const out = [];
  let i = 0;
  let paragraph = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    out.push(`<p>${applyInline(paragraph.join(' '))}</p>`);
    paragraph = [];
  };

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('```')) {
      flushParagraph();
      const lang = escapeHtml(line.slice(3).trim());
      const buf = [];
      i += 1;
      while (i < lines.length && !lines[i].startsWith('```')) {
        buf.push(lines[i]);
        i += 1;
      }
      const cls = lang ? ` class="language-${lang}"` : '';
      out.push(`<pre><code${cls}>${escapeHtml(buf.join('\n'))}</code></pre>`);
      i += 1;
      continue;
    }

    if (/^\s*\|/.test(line) && i + 1 < lines.length && isTableSeparator(lines[i + 1])) {
      flushParagraph();
      const headers = splitRow(line);
      i += 2;
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i]) && !isTableSeparator(lines[i])) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      const thead = headers.map((h) => `<th>${applyInline(h)}</th>`).join('');
      const tbody = rows
        .map((row) => `<tr>${row.map((c) => `<td>${applyInline(c)}</td>`).join('')}</tr>`)
        .join('');
      out.push(`<div class="table-wrap"><table><thead><tr>${thead}</tr></thead><tbody>${tbody}</tbody></table></div>`);
      continue;
    }

    if (/^#{1,6}\s+/.test(line)) {
      flushParagraph();
      const level = line.match(/^#+/)[0].length;
      out.push(`<h${level}>${applyInline(line.replace(/^#{1,6}\s+/, ''))}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      out.push('<ul>');
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        out.push(`<li>${applyInline(lines[i].replace(/^\s*[-*]\s+/, ''))}</li>`);
        i += 1;
      }
      out.push('</ul>');
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      flushParagraph();
      out.push('<ol>');
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        out.push(`<li>${applyInline(lines[i].replace(/^\s*\d+\.\s+/, ''))}</li>`);
        i += 1;
      }
      out.push('</ol>');
      continue;
    }

    if (/^>\s?/.test(line)) {
      flushParagraph();
      const quotes = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) {
        quotes.push(lines[i].replace(/^>\s?/, ''));
        i += 1;
      }
      out.push(`<blockquote>${applyInline(quotes.join(' '))}</blockquote>`);
      continue;
    }

    if (/^\s*---\s*$/.test(line)) {
      flushParagraph();
      out.push('<hr />');
      i += 1;
      continue;
    }

    if (!line.trim()) {
      flushParagraph();
      i += 1;
      continue;
    }

    paragraph.push(line.trim());
    i += 1;
  }
  flushParagraph();
  return out.join('\n');
}

export function titleFromMarkdown(markdown, fallback = 'Explanation') {
  const m = String(markdown).match(/^#\s+(.+)$/m);
  return (m ? m[1] : fallback).trim() || fallback;
}

export function playerScript() {
  return [
    '(function () {',
    '  var synth = window.speechSynthesis;',
    '  var bar = document.getElementById("player");',
    '  if (!synth || !bar) return;',
    '  var main = document.querySelector("main");',
    '  if (!main) return;',
    '  var nodes = main.querySelectorAll("p, li, blockquote, h2, h3");',
    '  var items = [];',
    '  for (var i = 0; i < nodes.length; i++) {',
    '    var el = nodes[i];',
    '    if (el.closest("pre, table")) continue;',
    '    var text = (el.innerText || "").replace(/\\s+/g, " ").trim();',
    '    if (!text) continue;',
    '    el.classList.add("speakable");',
    '    var btn = document.createElement("button");',
    '    btn.type = "button";',
    '    btn.className = "speak-one";',
    '    btn.setAttribute("aria-label", "Listen from this paragraph");',
    '    btn.textContent = "▶";',
    '    el.insertBefore(btn, el.firstChild);',
    '    items.push({ el: el, text: text, btn: btn });',
    '  }',
    '  if (!items.length) {',
    '    bar.hidden = true;',
    '    return;',
    '  }',
    '  var index = 0;',
    '  var playing = false;',
    '  var playBtn = document.getElementById("play-all");',
    '  var pauseBtn = document.getElementById("pause");',
    '  var stopBtn = document.getElementById("stop");',
    '  var rateEl = document.getElementById("rate");',
    '  var statusEl = document.getElementById("player-status");',
    '  function setStatus(msg) { if (statusEl) statusEl.textContent = msg; }',
    '  function clearHi() {',
    '    for (var j = 0; j < items.length; j++) items[j].el.classList.remove("speaking");',
    '  }',
    '  function mark(i) {',
    '    clearHi();',
    '    if (items[i]) {',
    '      items[i].el.classList.add("speaking");',
    '      items[i].el.scrollIntoView({ block: "nearest", behavior: "smooth" });',
    '    }',
    '  }',
    '  function stop() {',
    '    synth.cancel();',
    '    playing = false;',
    '    clearHi();',
    '    setStatus("Stopped");',
    '  }',
    '  function speakAt(start) {',
    '    synth.cancel();',
    '    index = start;',
    '    playing = true;',
    '    speakNext();',
    '  }',
    '  function speakNext() {',
    '    if (!playing) return;',
    '    if (index >= items.length) {',
    '      playing = false;',
    '      clearHi();',
    '      setStatus("Done");',
    '      return;',
    '    }',
    '    var item = items[index];',
    '    mark(index);',
    '    setStatus("Playing " + (index + 1) + " / " + items.length);',
    '    var u = new SpeechSynthesisUtterance(item.text);',
    '    u.rate = rateEl ? parseFloat(rateEl.value) || 1 : 1;',
    '    u.onend = function () {',
    '      if (!playing) return;',
    '      index += 1;',
    '      speakNext();',
    '    };',
    '    u.onerror = function () {',
    '      if (!playing) return;',
    '      index += 1;',
    '      speakNext();',
    '    };',
    '    synth.speak(u);',
    '  }',
    '  playBtn.addEventListener("click", function () { speakAt(0); });',
    '  pauseBtn.addEventListener("click", function () {',
    '    if (!playing) return;',
    '    if (synth.paused) { synth.resume(); setStatus("Playing"); }',
    '    else { synth.pause(); setStatus("Paused"); }',
    '  });',
    '  stopBtn.addEventListener("click", stop);',
    '  for (var k = 0; k < items.length; k++) {',
    '    (function (n) {',
    '      items[n].btn.addEventListener("click", function (ev) {',
    '        ev.preventDefault();',
    '        ev.stopPropagation();',
    '        speakAt(n);',
    '      });',
    '    })(k);',
    '  }',
    '  window.addEventListener("beforeunload", stop);',
    '})();',
  ].join('\n');
}

export function wrapPage(title, bodyHtml) {
  const safeTitle = escapeHtml(title);
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${safeTitle}</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #121018;
      --fg: #ece8f4;
      --muted: #9b93ab;
      --accent: #c084fc;
      --rule: #2a2438;
      --code-bg: #1c1828;
      --link: #d8b4fe;
      --speak: #2a1f3d;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); }
    body {
      font: 18px/1.65 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }
    header {
      border-bottom: 1px solid var(--rule);
      padding: 1.25rem 1.5rem 1rem;
    }
    header p {
      margin: 0.35rem 0 0;
      color: var(--muted);
      font-size: 0.8rem;
    }
    #player {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem 0.75rem;
      margin-top: 0.85rem;
    }
    #player button, #player select {
      background: var(--code-bg);
      color: var(--fg);
      border: 1px solid var(--rule);
      border-radius: 6px;
      padding: 0.35rem 0.7rem;
      font: inherit;
      font-size: 0.85rem;
      cursor: pointer;
    }
    #player button:hover, .speak-one:hover { border-color: var(--accent); }
    #player-status { color: var(--muted); font-size: 0.8rem; }
    main {
      max-width: 68ch;
      margin: 0 auto;
      padding: 2rem 1.5rem 4rem;
    }
    h1, h2, h3, h4 { line-height: 1.25; font-weight: 650; }
    h1 { font-size: 2rem; margin: 0 0 1rem; }
    h2 { font-size: 1.35rem; margin: 2rem 0 0.75rem; }
    h3 { font-size: 1.15rem; margin: 1.5rem 0 0.5rem; }
    p { margin: 0.85rem 0; }
    a { color: var(--link); }
    ul, ol { padding-left: 1.3rem; }
    li { margin: 0.3rem 0; }
    hr { border: 0; border-top: 1px solid var(--rule); margin: 2rem 0; }
    blockquote {
      margin: 1rem 0;
      padding: 0.15rem 0 0.15rem 1rem;
      border-left: 3px solid var(--accent);
      color: var(--muted);
    }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.88em;
      background: var(--code-bg);
      padding: 0.1em 0.35em;
      border-radius: 4px;
    }
    pre {
      background: var(--code-bg);
      border: 1px solid var(--rule);
      border-radius: 8px;
      padding: 0.9rem 1rem;
      overflow-x: auto;
    }
    pre code { padding: 0; background: none; }
    .table-wrap { overflow-x: auto; margin: 1rem 0; }
    table { border-collapse: collapse; width: 100%; font-size: 0.95rem; }
    th, td { border: 1px solid var(--rule); padding: 0.45rem 0.65rem; text-align: left; }
    th { background: var(--code-bg); }
    .speakable { position: relative; padding-left: 1.6rem; border-radius: 6px; }
    .speakable.speaking { background: var(--speak); outline: 1px solid var(--accent); }
    .speak-one {
      position: absolute;
      left: 0;
      top: 0.15em;
      width: 1.3rem;
      height: 1.3rem;
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--muted);
      cursor: pointer;
      font-size: 0.7rem;
      line-height: 1.3rem;
    }
    .speakable:hover .speak-one, .speakable.speaking .speak-one { color: var(--accent); }
    @media print {
      :root { color-scheme: light; --bg: #fff; --fg: #111; --muted: #444; --rule: #ccc; --code-bg: #f4f4f4; --link: #4a1a7a; }
      #player, .speak-one { display: none; }
      .speakable { padding-left: 0; }
    }
  </style>
</head>
<body>
  <header>
    <strong>${safeTitle}</strong>
    <p>Opened by explain-in-browser · read or listen</p>
    <div id="player">
      <button type="button" id="play-all">Play all</button>
      <button type="button" id="pause">Pause</button>
      <button type="button" id="stop">Stop</button>
      <label>Rate
        <select id="rate">
          <option value="0.9">0.9×</option>
          <option value="1" selected>1×</option>
          <option value="1.15">1.15×</option>
        </select>
      </label>
      <span id="player-status">Click Play all, or ▶ on a paragraph</span>
    </div>
  </header>
  <main>
${bodyHtml}
  </main>
  <script>
${playerScript()}
  </script>
</body>
</html>
`;
}

export function parseArgs(argv) {
  const args = { in: null, out: null, title: null, open: true };
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === '--in') args.in = argv[++i];
    else if (a === '--out') args.out = argv[++i];
    else if (a === '--title') args.title = argv[++i];
    else if (a === '--no-open') args.open = false;
    else if (a === '-h' || a === '--help') args.help = true;
    else throw new Error(`unknown arg: ${a}`);
  }
  return args;
}

function readStdin() {
  return new Promise((resolveStdin, reject) => {
    const chunks = [];
    stdin.setEncoding('utf8');
    stdin.on('data', (c) => chunks.push(c));
    stdin.on('end', () => resolveStdin(chunks.join('')));
    stdin.on('error', reject);
  });
}

function openFile(path) {
  const spec =
    process.platform === 'darwin'
      ? ['open', [path]]
      : process.platform === 'win32'
        ? ['cmd', ['/c', 'start', '', path]]
        : ['xdg-open', [path]];
  const child = spawn(spec[0], spec[1], { detached: true, stdio: 'ignore' });
  child.unref();
}

export async function renderExplanation({ markdown, inPath, outPath, title, open }) {
  const resolvedTitle = title || titleFromMarkdown(markdown);
  const html = wrapPage(resolvedTitle, markdownToHtml(markdown));
  let dest = outPath;
  if (!dest) {
    if (inPath) dest = join(dirname(inPath), `${basename(inPath, extname(inPath))}.html`);
    else dest = join(process.cwd(), '.grok', 'explanations', `explain-${Date.now()}.html`);
  }
  dest = resolve(dest);
  await mkdir(dirname(dest), { recursive: true });
  await writeFile(dest, html, 'utf8');
  if (open) openFile(dest);
  return dest;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    process.stdout.write(
      'Usage: render-explanation.mjs --in file.md [--out file.html] [--title T] [--no-open]\n',
    );
    return;
  }
  let markdown = '';
  if (args.in) markdown = await readFile(resolve(args.in), 'utf8');
  else if (!stdin.isTTY) markdown = await readStdin();
  else throw new Error('pass --in file.md or pipe markdown on stdin');
  if (!markdown.trim()) throw new Error('markdown is empty');
  const dest = await renderExplanation({
    markdown,
    inPath: args.in ? resolve(args.in) : null,
    outPath: args.out,
    title: args.title,
    open: args.open,
  });
  process.stdout.write(`${dest}\n`);
}

const isMain =
  Boolean(process.argv[1]) &&
  import.meta.url === new URL(`file://${resolve(process.argv[1])}`).href;

if (isMain) {
  main().catch((err) => {
    process.stderr.write(`${err.message}\n`);
    process.exit(1);
  });
}
