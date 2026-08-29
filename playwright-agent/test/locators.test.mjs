import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  emitLocator,
  inferTarget,
  normalizeTarget,
} from '../src/locators.mjs';
import { appendStep, createJournal, journalToSpec } from '../src/record.mjs';

test('normalizeTarget lifts testId / selector / text', () => {
  assert.deepEqual(normalizeTarget({ testId: 'cash' }).by, 'testid');
  assert.equal(normalizeTarget({ testId: 'cash' }).name, 'cash');
  assert.equal(normalizeTarget({ selector: '#email' }).by, 'css');
  assert.equal(normalizeTarget({ text: 'Next due' }).by, 'text');
  assert.equal(normalizeTarget('#email').by, 'css');
});

test('inferTarget skips strategies that lack data', () => {
  const raw = { name: 'Email' };
  assert.equal(inferTarget(raw, 'role'), null);
  assert.equal(inferTarget(raw, 'label').by, 'label');
  assert.equal(inferTarget({ role: 'button', name: 'Go' }, 'role').by, 'role');
});

test('emitLocator prints official-style Playwright calls', () => {
  assert.equal(
    emitLocator({ by: 'label', name: 'Email' }),
    'page.getByLabel("Email")',
  );
  assert.equal(
    emitLocator({ by: 'role', role: 'button', name: 'Sign in' }),
    'page.getByRole("button", { name: "Sign in" })',
  );
  assert.equal(
    emitLocator({ by: 'testid', name: 'cash' }),
    'page.getByTestId("cash")',
  );
  assert.equal(
    emitLocator({ by: 'text', name: 'Next due', closest: '[data-slot="card"]' }),
    'page.locator("[data-slot=\\"card\\"]").filter({ has: page.getByText("Next due") })',
  );
  assert.equal(
    emitLocator({
      by: 'role',
      role: 'button',
      name: 'Save',
      scope: { by: 'css', selector: '[data-issue-row]' },
    }),
    'page.locator("[data-issue-row]").getByRole("button", { name: "Save" })',
  );
});

test('journalToSpec records getBy* and never networkidle', () => {
  const journal = createJournal({ seed: 'auth.json', title: 'login' });
  appendStep(journal, { kind: 'goto', url: 'https://app.example/login' });
  appendStep(journal, {
    kind: 'act',
    action: 'fill',
    value: 'user@test.com',
    used: 'page.getByLabel("Email")',
  });
  appendStep(journal, {
    kind: 'assert',
    assert: 'url',
    pattern: '**/dashboard',
  });
  const spec = journalToSpec(journal);
  assert.match(spec, /page\.getByLabel\("Email"\)\.fill\("user@test.com"\)/);
  assert.match(spec, /toHaveURL/);
  assert.doesNotMatch(spec, /networkidle/);
  assert.match(spec, /seed: auth.json/);
});
