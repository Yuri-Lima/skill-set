/**
 * Helpers for a timed live-UI recording (human cursor + clicks + typing).
 *
 * Ticket-specific runners should import these and call `recordTicket`.
 * Do not put ticket locators in this file.
 */
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { requireDemoAuth } from './resolve-demo-auth.mjs';
import { assertResolved, resolveTarget } from '../../playwright-agent/src/index.mjs';

export async function loadChromium() {
  try {
    return (await import('playwright')).chromium;
  } catch {
    const pwUrl = pathToFileURL(
      path.resolve(
        process.cwd(),
        'apps/web/node_modules/@playwright/test/index.mjs',
      ),
    ).href;
    return (await import(pwUrl)).chromium;
  }
}

export function demoBaseUrl() {
  return process.env.PLAYWRIGHT_BASE_URL ?? 'http://127.0.0.1:3000';
}

export async function injectCursor(page) {
  await page.addInitScript(() => {
    const boot = () => {
      if (document.getElementById('demo-cursor')) return;
      const c = document.createElement('div');
      c.id = 'demo-cursor';
      c.innerHTML =
        '<svg width="28" height="28" viewBox="0 0 24 24"><path fill="#111" stroke="#fff" stroke-width="1.4" d="M4 3.5 18 13l-6.2 1.4 2.6 6.2-2.7 1.1-2.6-6.2L4 20.5z"/></svg>';
      Object.assign(c.style, {
        position: 'fixed',
        left: '40px',
        top: '40px',
        zIndex: '2147483647',
        pointerEvents: 'none',
        transition: 'left 160ms ease-out, top 160ms ease-out',
        filter: 'drop-shadow(0 2px 4px rgba(0,0,0,.35))',
      });
      document.documentElement.appendChild(c);
      window.__demoCursor = (x, y) => {
        c.style.left = `${x}px`;
        c.style.top = `${y}px`;
      };
      window.__demoClick = () => {
        const ring = document.createElement('div');
        Object.assign(ring.style, {
          position: 'fixed',
          left: c.style.left,
          top: c.style.top,
          width: '18px',
          height: '18px',
          marginLeft: '-4px',
          marginTop: '-4px',
          border: '2px solid #16a34a',
          borderRadius: '999px',
          zIndex: '2147483646',
          pointerEvents: 'none',
          opacity: '0.95',
          transform: 'scale(0.4)',
          transition: 'transform 280ms ease-out, opacity 280ms ease-out',
        });
        document.documentElement.appendChild(ring);
        requestAnimationFrame(() => {
          ring.style.transform = 'scale(2.2)';
          ring.style.opacity = '0';
        });
        setTimeout(() => ring.remove(), 320);
      };
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', boot);
    } else {
      boot();
    }
  });
}

export async function moveTo(page, locator) {
  const box = await locator.boundingBox();
  if (!box) throw new Error('no bounding box');
  const x = box.x + box.width / 2;
  const y = box.y + Math.min(box.height / 2, 14);
  await page.mouse.move(x, y, { steps: 18 });
  await page.evaluate(
    ({ x: cx, y: cy }) => {
      if (window.__demoCursor) window.__demoCursor(cx, cy);
    },
    { x, y },
  );
  return { x, y };
}

export async function clickHuman(page, locator) {
  await moveTo(page, locator);
  await page.waitForTimeout(140);
  await page.evaluate(() => {
    if (window.__demoClick) window.__demoClick();
  });
  await locator.click({ delay: 70 });
}

/** Origin is when Eve's first word starts. `until(ms)` waits until that offset. */
export function makeClock(originMs = Date.now()) {
  return {
    originMs,
    async until(page, ms) {
      const left = Number(ms) - (Date.now() - originMs);
      if (left > 0) await page.waitForTimeout(left);
    },
  };
}

/** Green outline on the control she is naming (vertical edit). */
export async function outline(page, locator) {
  await locator.evaluate((el) => {
    el.style.outline = '2px solid #16a34a';
    el.style.outlineOffset = '3px';
    el.style.borderRadius = '6px';
  });
}

export async function typeHuman(page, locator, text) {
  await clickHuman(page, locator);
  await page.waitForTimeout(180);
  await locator.fill('');
  await locator.pressSequentially(text, { delay: 95 });
}

function submitPattern(auth) {
  const raw = auth.submitName ?? /sign in|log in|entrar/i;
  if (raw instanceof RegExp) return raw;
  const text = String(raw);
  const match = text.match(/^\/(.+)\/([a-z]*)$/i);
  return match ? new RegExp(match[1], match[2]) : new RegExp(text, 'i');
}

function emailTarget(auth) {
  if (auth.emailTarget) return auth.emailTarget;
  if (auth.emailLabel) return { by: 'label', name: auth.emailLabel };
  return { by: 'css', selector: auth.emailSelector ?? '#email' };
}

function passwordTarget(auth) {
  if (auth.passwordTarget) return auth.passwordTarget;
  if (auth.passwordLabel) return { by: 'label', name: auth.passwordLabel };
  return { by: 'css', selector: auth.passwordSelector ?? '#password' };
}

export async function login(browser, nextPath = '/') {
  const auth = requireDemoAuth();
  if (auth.method === 'none') {
    return { cookies: [], origins: [] };
  }
  if (auth.method === 'storage_state') {
    const file = auth.storageStatePath;
    if (!file || !fs.existsSync(file)) {
      throw new Error(
        'demo-auth method=storage_state but storageStatePath is missing. Ask the user for a Playwright storageState JSON or pick another method.',
      );
    }
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  }
  if (auth.method !== 'password') {
    throw new Error(
      `Unsupported demo-auth method "${auth.method}". Ask the user to pick password, storage_state, or none.`,
    );
  }
  if (!auth.email || !auth.password) {
    throw new Error(
      'demo-auth method=password needs email and password. Ask the user for a temporary/fake account.',
    );
  }
  const base = demoBaseUrl();
  const loginPath = auth.loginPath ?? '/login';
  const next = encodeURIComponent(nextPath);
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'light',
  });
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  await page.goto(`${base}${loginPath}?next=${next}`, {
    waitUntil: 'domcontentloaded',
  });
  const email = await resolveTarget(page, emailTarget(auth));
  assertResolved(email, 'login email');
  await email.locator.fill(auth.email);
  const password = await resolveTarget(page, passwordTarget(auth));
  assertResolved(password, 'login password');
  await password.locator.fill(auth.password);
  const submit = await resolveTarget(page, {
    by: 'role',
    role: 'button',
    name: submitPattern(auth),
  });
  assertResolved(submit, 'login submit');
  await submit.locator.click();
  await page.waitForURL((url) => !url.pathname.includes(loginPath), {
    timeout: 45_000,
  });
  const state = await context.storageState();
  await context.close();
  return state;
}

export async function recordTicket(browser, {
  storage,
  outWebm,
  route,
  ready,
  run,
}) {
  const videoDir = `${outWebm}.dir`;
  fs.rmSync(videoDir, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(outWebm), { recursive: true });
  fs.mkdirSync(videoDir, { recursive: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    colorScheme: 'light',
    storageState: storage,
    recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
  });
  const tPage = Date.now();
  const page = await context.newPage();
  page.setDefaultTimeout(60_000);
  await injectCursor(page);
  await page.goto(`${demoBaseUrl()}${route}`, {
    waitUntil: 'domcontentloaded',
  });
  await ready(page);
  const tReady = Date.now();
  await page.waitForTimeout(400);
  const tRun = Date.now();
  const clock = makeClock(tRun);
  if (run.length >= 2) {
    await run(page, clock);
  } else {
    await run(page);
  }
  await page.waitForTimeout(700);
  const tEnd = Date.now();
  await context.close();
  const files = fs.readdirSync(videoDir).filter((f) => f.endsWith('.webm'));
  if (!files[0]) throw new Error(`no webm written under ${videoDir}`);
  fs.renameSync(path.join(videoDir, files[0]), outWebm);
  fs.rmSync(videoDir, { recursive: true, force: true });
  const sync = {
    runMs: tRun - tPage,
    readyMs: tReady - tPage,
    endMs: tEnd - tPage,
    prerollAfterReadyMs: 400,
    holdMs: 700,
  };
  fs.writeFileSync(`${outWebm}.sync.json`, JSON.stringify(sync, null, 2));
  return outWebm;
}
