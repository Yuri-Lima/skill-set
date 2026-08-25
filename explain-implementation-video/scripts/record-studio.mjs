/**
 * Record the decision studio board. Resolves Playwright from the repo cwd
 * (a user-level ticket-demo-video install cannot).
 *
 *   node record-studio.mjs --html board.html --beats beats.json \
 *     --out studio.webm --duration 86
 */
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

function arg(name, fallback = '') {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : fallback;
}

const htmlIn = path.resolve(arg('--html'));
const beatsIn = path.resolve(arg('--beats'));
const outWebm = path.resolve(arg('--out'));
const durationSec = Number(arg('--duration', '40'));

if (!htmlIn || !beatsIn || !outWebm) {
  console.error(
    'usage: record-studio.mjs --html board.html --beats beats.json --out studio.webm --duration 86',
  );
  process.exit(2);
}

const require = createRequire(path.join(process.cwd(), 'package.json'));
const { chromium } = await import(pathToFileURL(require.resolve('playwright')).href);

const beats = JSON.parse(fs.readFileSync(beatsIn, 'utf8'));
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'studio-'));
const htmlOut = path.join(tmp, 'board.html');
const src = fs.readFileSync(htmlIn, 'utf8');
const injected = src.replace(
  '<body>',
  `<body data-beats='${JSON.stringify(beats).replaceAll("'", "&#39;")}'>`,
);
fs.writeFileSync(htmlOut, injected);

const videoDir = `${outWebm}.dir`;
fs.rmSync(videoDir, { recursive: true, force: true });
fs.mkdirSync(path.dirname(outWebm), { recursive: true });
fs.mkdirSync(videoDir, { recursive: true });

let browser;
try {
  browser = await chromium.launch({ headless: true });
} catch {
  browser = await chromium.launch({ headless: true, channel: 'chrome' });
}
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
fs.renameSync(path.join(videoDir, files[0]), outWebm);
fs.rmSync(videoDir, { recursive: true, force: true });
fs.rmSync(tmp, { recursive: true, force: true });
console.log('recorded', outWebm);
