import { emitLocator } from './locators.mjs';
import { emitAssert } from './verify.mjs';

export function createJournal({ seed = null, title = 'recorded session' } = {}) {
  return {
    title,
    seed,
    steps: [],
  };
}

export function appendStep(journal, step) {
  journal.steps.push({ at: new Date().toISOString(), ...step });
  return journal;
}

export function journalToSpec(journal) {
  const title = journal.title ?? 'recorded session';
  const lines = ['// spec: recorded'];
  if (journal.seed) lines.push(`// seed: ${journal.seed}`);
  lines.push(
    '',
    "import { test, expect } from '@playwright/test';",
    '',
    `test.describe(${JSON.stringify(title)}, () => {`,
    `  test('flow', async ({ page }) => {`,
  );

  let n = 0;
  for (const step of journal.steps) {
    if (step.kind === 'comment') {
      lines.push(`    // ${step.text}`);
      continue;
    }
    n += 1;
    const label = step.comment ?? stepLabel(step);
    lines.push(`    // ${n}. ${label}`);
    lines.push(`    ${emitStep(step)}`);
    lines.push('');
  }

  if (journal.steps.length === 0) {
    lines.push('    // no steps recorded');
  }

  lines.push('  });');
  lines.push('});');
  lines.push('');
  const body = lines.join('\n');
  if (/networkidle/.test(body)) {
    throw new Error('journal emitted networkidle; that API is banned');
  }
  return body;
}

function stepLabel(step) {
  if (step.kind === 'goto') return `open ${step.url}`;
  if (step.kind === 'act') return `${step.action} ${step.used ?? ''}`.trim();
  if (step.kind === 'assert') return `assert ${step.assert}`;
  if (step.kind === 'shot') return 'screenshot';
  return step.kind;
}

function emitStep(step) {
  if (step.kind === 'goto') {
    return `await page.goto(${JSON.stringify(step.url)});`;
  }
  if (step.kind === 'act') {
    const loc = step.used ?? emitLocator(step.target);
    if (step.action === 'fill') {
      return `await ${loc}.fill(${JSON.stringify(step.value ?? '')});`;
    }
    if (step.action === 'press') {
      return `await ${loc}.press(${JSON.stringify(step.value ?? step.key)});`;
    }
    if (step.action === 'select') {
      return `await ${loc}.selectOption(${JSON.stringify(step.value)});`;
    }
    if (step.action === 'check' || step.action === 'uncheck' || step.action === 'click' || step.action === 'hover') {
      return `await ${loc}.${step.action}();`;
    }
    return `await ${loc}.${step.action}();`;
  }
  if (step.kind === 'assert') {
    const fromCatalog = emitAssert(step);
    if (fromCatalog) return fromCatalog;
    const loc = step.used ?? (step.target ? emitLocator(step.target) : 'page');
    if (step.assert === 'visible') return `await expect(${loc}).toBeVisible();`;
    if (step.assert === 'hidden') return `await expect(${loc}).toBeHidden();`;
    if (step.assert === 'enabled') return `await expect(${loc}).toBeEnabled();`;
    if (step.assert === 'checked') return `await expect(${loc}).toBeChecked();`;
    if (step.assert === 'value') {
      return `await expect(${loc}).toHaveValue(${JSON.stringify(step.expected ?? step.value)});`;
    }
    if (step.assert === 'text') {
      return `await expect(${loc}).toContainText(${JSON.stringify(step.expected ?? step.value)});`;
    }
  }
  if (step.kind === 'shot') {
    return `await page.screenshot({ path: ${JSON.stringify(step.path ?? 'shot.png')} });`;
  }
  return `// unknown step ${step.kind}`;
}
