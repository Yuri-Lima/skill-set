import assert from 'node:assert/strict';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { test } from 'node:test';
import { highlightRegion, resolveTarget } from '../src/index.mjs';

async function loadChromium() {
  try {
    return (await import('playwright')).chromium;
  } catch {
    return null;
  }
}

const chromium = await loadChromium();
const maybe = chromium ? test : test.skip;

maybe('resolveTarget is strict and prefers unique contracts', async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await (await browser.newContext()).newPage();
  const file = pathToFileURL(
    path.resolve(import.meta.dirname, 'fixtures/login.html'),
  ).href;
  await page.goto(file);

  const email = await resolveTarget(page, { by: 'label', name: 'Email' });
  assert.equal(email.status, 'ok');
  assert.equal(email.used, 'page.getByLabel("Email")');

  const ghost = await resolveTarget(page, { testId: 'ghost' });
  assert.equal(ghost.status, 'ok');
  assert.equal(ghost.used, 'page.getByTestId("ghost")');

  const submits = await resolveTarget(page, { by: 'role', role: 'button', name: 'Submit' });
  assert.equal(submits.status, 'ambiguous');
  assert.ok(submits.count >= 2);
  assert.ok(submits.candidates.length >= 2);

  const missing = await resolveTarget(page, { by: 'label', name: 'No such field' });
  assert.equal(missing.status, 'not_found');

  const card = await resolveTarget(page, {
    by: 'text',
    name: 'Cash on hand',
    closest: '[data-slot="card"]',
  });
  assert.equal(card.status, 'ok');
  const painted = await highlightRegion(page, {
    kind: 'after',
    text: 'Cash on hand',
    closest: '[data-slot="card"]',
  });
  assert.equal(painted, true);
  const marked = await page.locator('[data-review-highlight="after"]').count();
  assert.equal(marked, 1);

  await browser.close();
});
