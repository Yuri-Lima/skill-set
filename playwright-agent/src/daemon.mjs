#!/usr/bin/env node
import fs from 'node:fs';
import http from 'node:http';
import { createJournal, appendStep, journalToSpec } from './record.mjs';
import { performAction } from './actions.mjs';
import { performAssert } from './verify.mjs';
import { resolveTarget } from './locators.mjs';
import { journalPath, sessionDir, writeMeta } from './session.mjs';

const args = process.argv.slice(2);
const port = Number(argValue('--port') ?? 0);
const session = argValue('--session') ?? 'default';
const headed = process.env.PLAYWRIGHT_AGENT_HEADED === '1';

if (!port) {
  console.error('daemon: --port required');
  process.exit(2);
}

let browser;
let context;
let page;
let journal = loadJournal();

const server = http.createServer(async (req, res) => {
  try {
    const body = await readBody(req);
    const result = await handle(body);
    send(res, 200, result);
  } catch (err) {
    send(res, err.statusCode ?? 400, {
      status: 'error',
      error: err.message,
      result: err.result ?? undefined,
    });
  }
});

server.listen(port, '127.0.0.1', () => {
  writeMeta(session, { port, pid: process.pid, headed });
});

function argValue(flag) {
  const i = args.indexOf(flag);
  return i === -1 ? undefined : args[i + 1];
}

function send(res, code, obj) {
  const text = JSON.stringify(obj);
  res.writeHead(code, { 'content-type': 'application/json' });
  res.end(text);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => {
      const text = Buffer.concat(chunks).toString('utf8') || '{}';
      try {
        resolve(JSON.parse(text));
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

async function handle(body) {
  const cmd = body.cmd;
  if (cmd === 'ping') return { status: 'ok' };

  if (cmd === 'open') {
    await ensurePage(body);
    await page.goto(body.url, { waitUntil: 'domcontentloaded' });
    appendStep(journal, { kind: 'goto', url: body.url, comment: body.comment ?? `open ${body.url}` });
    persistJournal();
    return { status: 'ok', url: page.url(), title: await page.title() };
  }

  if (cmd === 'seed') {
    await ensurePage(body);
    return { status: 'ok', url: page.url() };
  }

  if (!page && cmd !== 'close') {
    const err = new Error('no page — run open first');
    err.statusCode = 409;
    throw err;
  }

  if (cmd === 'act') {
    const result = await performAction(page, body, body.opts ?? {});
    appendStep(journal, {
      kind: 'act',
      action: body.action,
      target: result.target,
      value: body.value,
      used: result.used,
      generated: result.generated,
      comment: body.comment,
    });
    persistJournal();
    return { ...result, url: page.url() };
  }

  if (cmd === 'assert') {
    const result = await performAssert(page, body, body.opts ?? {});
    appendStep(journal, {
      kind: 'assert',
      assert: body.assert ?? body.kind,
      target: body.target,
      value: body.value,
      pattern: body.pattern ?? body.url,
      used: result.used,
      expected: result.expected,
      comment: body.comment,
    });
    persistJournal();
    return { ...result, url: page.url() };
  }

  if (cmd === 'resolve') {
    const result = await resolveTarget(page, body.target, body.opts ?? {});
    const { locator, ...rest } = result;
    return rest;
  }

  if (cmd === 'state') {
    return {
      status: 'ok',
      url: page.url(),
      title: await page.title(),
      session,
    };
  }

  if (cmd === 'shot') {
    const dest = body.path ?? defaultShotPath();
    await page.screenshot({ path: dest, fullPage: Boolean(body.full) });
    appendStep(journal, { kind: 'shot', path: dest });
    persistJournal();
    return { status: 'ok', path: dest };
  }

  if (cmd === 'codegen') {
    const spec = journalToSpec(journal);
    if (body.path) fs.writeFileSync(body.path, spec);
    return { status: 'ok', spec, path: body.path ?? null };
  }

  if (cmd === 'close') {
    persistJournal();
    await context?.close().catch(() => {});
    await browser?.close().catch(() => {});
    setTimeout(() => process.exit(0), 50);
    return { status: 'ok' };
  }

  throw new Error(`unknown cmd: ${cmd}`);
}

async function ensurePage(body) {
  if (page) return;
  const { chromium } = await import('playwright');
  browser = await chromium.launch({
    headless: body.headed === true ? false : !headed,
  });
  const storageState = body.seed && fs.existsSync(body.seed) ? body.seed : undefined;
  context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    storageState,
  });
  page = await context.newPage();
  page.setDefaultTimeout(body.timeout ?? 25_000);
  journal.seed = body.seed ?? journal.seed;
}

function loadJournal() {
  const file = journalPath(session);
  if (fs.existsSync(file)) {
    try {
      return JSON.parse(fs.readFileSync(file, 'utf8'));
    } catch {
      // fall through
    }
  }
  return createJournal({ seed: null, title: session });
}

function persistJournal() {
  fs.mkdirSync(sessionDir(session), { recursive: true });
  fs.writeFileSync(journalPath(session), JSON.stringify(journal, null, 2));
}

function defaultShotPath() {
  return `${sessionDir(session)}/shot-${Date.now()}.png`;
}
