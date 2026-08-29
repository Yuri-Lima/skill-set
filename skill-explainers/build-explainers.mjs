#!/usr/bin/env node
/**
 * Stitch Eve, record the studio board, compose, publish each explainer.
 *
 *   node skill-explainers/build-explainers.mjs
 *   node skill-explainers/build-explainers.mjs explainer-overview
 *
 * Spoken lines live in scripts/. Eve takes and boards live under
 * docs/review-impact/skill-explainers/ (gitignored). Published mp4s:
 * docs/ticket-demos/explainer-*.mp4
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, '..');
const SCRATCH = path.join(REPO, 'docs', 'review-impact', 'skill-explainers');
const DEMO = path.join(REPO, 'ticket-demo-video', 'scripts');
const MANIFEST = JSON.parse(fs.readFileSync(path.join(HERE, 'manifest.json'), 'utf8'));
const BOARD = path.join(HERE, '_board.html');

function sh(cmd, args, opts = {}) {
  const r = spawnSync(cmd, args, { stdio: 'inherit', ...opts });
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} failed (${r.status})`);
}

function probe(file) {
  const r = spawnSync(
    'ffprobe',
    ['-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', file],
    { encoding: 'utf8' },
  );
  if (r.status !== 0) throw new Error(`ffprobe failed: ${file}`);
  return Number(r.stdout.trim());
}

async function loadChromium() {
  try {
    return (await import('playwright')).chromium;
  } catch {
    const pw = path.join(REPO, 'playwright-agent', 'node_modules', 'playwright', 'index.mjs');
    return (await import(pathToFileURL(pw).href)).chromium;
  }
}

async function recordBoard({ html, beats, copy, out, durationSec }) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'explainer-'));
  const htmlOut = path.join(tmp, 'board.html');
  let src = fs.readFileSync(html, 'utf8');
  const payload = JSON.stringify(beats).replaceAll("'", '&#39;');
  const copyPayload = JSON.stringify(copy).replaceAll("'", '&#39;');
  src = src.replace(
    '<body>',
    `<body data-beats='${payload}' data-copy='${copyPayload}'>`,
  );
  fs.writeFileSync(htmlOut, src);

  const videoDir = `${out}.dir`;
  fs.rmSync(videoDir, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.mkdirSync(videoDir, { recursive: true });

  const chromium = await loadChromium();
  const browser = await chromium.launch({
    headless: true,
    channel: fs.existsSync('/Applications/Google Chrome.app') ? 'chrome' : undefined,
  });
  const context = await browser.newContext({
    viewport: { width: 1280, height: 720 },
    recordVideo: { dir: videoDir, size: { width: 1280, height: 720 } },
  });
  const page = await context.newPage();
  await page.goto(pathToFileURL(htmlOut).href, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(Math.max(400, durationSec * 1000));
  await context.close();
  await browser.close();

  const files = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm'));
  if (!files[0]) throw new Error(`no webm under ${videoDir}`);
  fs.renameSync(path.join(videoDir, files[0]), out);
  fs.rmSync(videoDir, { recursive: true, force: true });
  fs.rmSync(tmp, { recursive: true, force: true });
}

const only = process.argv.slice(2);
const items = only.length
  ? MANIFEST.filter((m) => only.includes(m.slug) || only.includes(m.dir))
  : MANIFEST;

for (const item of items) {
  const dir = path.join(SCRATCH, item.dir);
  const clips = ['eve-01.mp4', 'eve-02.mp4', 'eve-03.mp4'].map((f) => path.join(dir, f));
  for (const c of clips) {
    if (!fs.existsSync(c)) throw new Error(`missing ${c}`);
  }

  const eveFull = path.join(dir, 'eve-full.mp4');
  console.log('\n==', item.slug, 'stitch ==');
  sh('bash', [path.join(DEMO, 'stitch-eve.sh'), '--out', eveFull, ...clips]);

  const d1 = probe(clips[0]);
  const d2 = probe(clips[1]);
  const d3 = probe(clips[2]);
  const beats = [
    { at: 400, action: 'kicker' },
    { at: Math.round(d1 * 1000), action: 'cards' },
    { at: Math.round((d1 + d2) * 1000), action: 'chip' },
    { at: Math.round((d1 + d2) * 1000 + 3500), action: 'footer' },
  ];
  fs.writeFileSync(path.join(dir, 'beats.json'), JSON.stringify(beats, null, 2));

  const studio = path.join(dir, 'studio.webm');
  const duration = d1 + d2 + d3 + 0.6;
  console.log('==', item.slug, 'board', duration.toFixed(1), 's ==');
  await recordBoard({
    html: BOARD,
    beats,
    copy: item.copy,
    out: studio,
    durationSec: duration,
  });

  const composed = path.join(dir, `${item.slug}.mp4`);
  console.log('==', item.slug, 'compose ==');
  sh('bash', [
    path.join(DEMO, 'compose-studio.sh'),
    '--eve',
    eveFull,
    '--studio',
    studio,
    '--out',
    composed,
  ]);

  console.log('==', item.slug, 'publish ==');
  sh('bash', [path.join(DEMO, 'publish-demo.sh'), '--in', composed, '--slug', item.slug], {
    cwd: REPO,
  });
}

console.log('\nall explainers published under docs/ticket-demos/');
