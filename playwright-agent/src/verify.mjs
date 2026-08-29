import { assertResolved, resolveTarget } from './locators.mjs';

export const ASSERTIONS = ['visible', 'hidden', 'text', 'value', 'url', 'enabled', 'checked'];

export async function performAssert(page, spec, opts = {}) {
  const kind = spec.assert ?? spec.kind;
  if (!ASSERTIONS.includes(kind)) {
    throw new Error(`unknown assert: ${kind}`);
  }

  if (kind === 'url') {
    const pattern = spec.pattern ?? spec.value ?? spec.url;
    const href = page.url();
    const ok = matchUrl(href, pattern);
    return {
      status: ok ? 'ok' : 'verify_failed',
      assert: 'url',
      expected: String(pattern),
      actual: href,
    };
  }

  const resolved = await resolveTarget(page, spec.target, opts);
  if (kind === 'hidden') {
    if (resolved.status === 'not_found') {
      return { status: 'ok', assert: 'hidden', used: resolved.used };
    }
    const visible = await resolved.locator.isVisible();
    return {
      status: visible ? 'verify_failed' : 'ok',
      assert: 'hidden',
      used: resolved.used,
      actual: visible ? 'visible' : 'hidden',
    };
  }

  assertResolved(resolved, `assert ${kind}`);
  const locator = resolved.locator;

  if (kind === 'visible') {
    const visible = await locator.isVisible();
    return {
      status: visible ? 'ok' : 'verify_failed',
      assert: 'visible',
      used: resolved.used,
      generated: resolved.generated,
    };
  }

  if (kind === 'enabled') {
    const enabled = await locator.isEnabled();
    return {
      status: enabled ? 'ok' : 'verify_failed',
      assert: 'enabled',
      used: resolved.used,
      actual: enabled ? 'enabled' : 'disabled',
    };
  }

  if (kind === 'checked') {
    const checked = await locator.isChecked();
    const want = spec.value !== false;
    return {
      status: checked === want ? 'ok' : 'verify_failed',
      assert: 'checked',
      used: resolved.used,
      expected: want,
      actual: checked,
    };
  }

  if (kind === 'value') {
    const actual = await locator.inputValue();
    const expected = String(spec.value ?? '');
    return {
      status: actual === expected ? 'ok' : 'verify_failed',
      assert: 'value',
      used: resolved.used,
      expected,
      actual,
    };
  }

  if (kind === 'text') {
    const actual = ((await locator.textContent()) ?? '').trim();
    const expected = spec.value ?? spec.text;
    const ok = matchText(actual, expected);
    return {
      status: ok ? 'ok' : 'verify_failed',
      assert: 'text',
      used: resolved.used,
      expected: String(expected),
      actual,
    };
  }

  throw new Error(`unhandled assert: ${kind}`);
}

function matchUrl(href, pattern) {
  if (pattern == null) return Boolean(href);
  if (pattern instanceof RegExp) return pattern.test(href);
  const text = String(pattern);
  if (text.startsWith('/') && text.lastIndexOf('/') > 0) {
    const end = text.lastIndexOf('/');
    return new RegExp(text.slice(1, end), text.slice(end + 1)).test(href);
  }
  if (text.includes('*')) {
    const re = new RegExp(
      `^${text.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*\*/g, '.*').replace(/\*/g, '[^/]*')}$`,
    );
    return re.test(href);
  }
  return href.includes(text);
}

function matchText(actual, expected) {
  if (expected instanceof RegExp) return expected.test(actual);
  return actual.includes(String(expected));
}

export function emitAssert(spec) {
  const kind = spec.assert ?? spec.kind;
  if (kind === 'url') {
    const pattern = spec.pattern ?? spec.value ?? spec.url;
    return `await expect(page).toHaveURL(${pattern instanceof RegExp ? String(pattern) : JSON.stringify(pattern)});`;
  }
  return null;
}
