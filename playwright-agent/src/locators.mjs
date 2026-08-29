/**
 * Locator contract → Playwright locator. Strict: 0 matches fail, 2+ fail
 * with engine-generated candidates. The model does not pick DOM nodes.
 */

export const STRATEGIES = {
  preferTestId: ['testid', 'css', 'role', 'label', 'placeholder', 'text', 'alt', 'title'],
  preferUserFacing: ['role', 'label', 'placeholder', 'text', 'alt', 'title', 'testid', 'css'],
};

const BY_ALIASES = {
  'test-id': 'testid',
  testid: 'testid',
  testId: 'testid',
  role: 'role',
  label: 'label',
  placeholder: 'placeholder',
  text: 'text',
  alt: 'alt',
  title: 'title',
  css: 'css',
  selector: 'css',
};

/**
 * @typedef {{
 *   by?: string,
 *   name?: string | RegExp,
 *   role?: string,
 *   testId?: string,
 *   selector?: string,
 *   exact?: boolean,
 *   scope?: object,
 *   closest?: string,
 *   text?: string | RegExp,
 * }} Target
 */

export function quote(value) {
  if (value instanceof RegExp) return String(value);
  return JSON.stringify(String(value));
}

export function normalizeTarget(raw = {}) {
  if (typeof raw === 'string') {
    if (raw.startsWith('#') || raw.startsWith('.') || raw.startsWith('[')) {
      return { by: 'css', selector: raw, name: raw };
    }
    return { by: 'text', name: raw };
  }

  const testId = raw.testId ?? raw.testid ?? raw['test-id'];
  const selector = raw.selector ?? (raw.by === 'css' ? raw.name : undefined);
  let by = raw.by ? BY_ALIASES[raw.by] ?? raw.by : undefined;

  if (!by) {
    if (testId) by = 'testid';
    else if (selector) by = 'css';
    else if (raw.role) by = 'role';
    else if (raw.text) by = 'text';
    else if (raw.name && raw.placeholder) by = 'placeholder';
  }

  const name = raw.name ?? testId ?? raw.text ?? selector;

  return {
    by,
    name,
    role: raw.role,
    testId: testId ?? (by === 'testid' ? name : undefined),
    selector: selector ?? (by === 'css' ? name : undefined),
    exact: raw.exact,
    scope: raw.scope ? normalizeTarget(raw.scope) : undefined,
    closest: raw.closest,
    text: raw.text,
  };
}

export function inferTarget(raw, by) {
  const base = normalizeTarget(raw);
  if (by === 'testid') {
    const id = base.testId ?? (typeof base.name === 'string' ? base.name : undefined);
    if (!id || typeof id !== 'string') return null;
    return { ...base, by: 'testid', name: id, testId: id };
  }
  if (by === 'css') {
    const sel = base.selector;
    if (!sel) return null;
    return { ...base, by: 'css', name: sel, selector: sel };
  }
  if (by === 'role') {
    if (!base.role) return null;
    return { ...base, by: 'role' };
  }
  if (by === 'label' || by === 'placeholder' || by === 'text' || by === 'alt' || by === 'title') {
    if (base.name == null && base.text == null) return null;
    return { ...base, by, name: base.name ?? base.text };
  }
  return null;
}

/**
 * Build a Playwright locator. `root` is a Page or Locator.
 */
export function toLocator(root, raw) {
  const target = normalizeTarget(raw);
  if (!target.by) {
    throw new Error('target.by is required (testid, role, label, placeholder, text, alt, title, css)');
  }

  let ctx = root;
  if (target.scope) {
    ctx = toLocator(root, target.scope);
  }

  let locator;
  switch (target.by) {
    case 'testid':
      locator = ctx.getByTestId(target.name);
      break;
    case 'role':
      locator = ctx.getByRole(target.role, nameOpts(target));
      break;
    case 'label':
      locator = ctx.getByLabel(target.name, exactOpts(target));
      break;
    case 'placeholder':
      locator = ctx.getByPlaceholder(target.name, exactOpts(target));
      break;
    case 'text':
      locator = ctx.getByText(target.name, exactOpts(target));
      break;
    case 'alt':
      locator = ctx.getByAltText(target.name, exactOpts(target));
      break;
    case 'title':
      locator = ctx.getByTitle(target.name, exactOpts(target));
      break;
    case 'css':
      locator = ctx.locator(target.selector);
      break;
    default:
      throw new Error(`unknown by: ${target.by}`);
  }

  if (target.closest) {
    locator = ctx.locator(target.closest).filter({ has: locator });
  }
  return locator;
}

function nameOpts(target) {
  const opts = {};
  if (target.name != null) opts.name = target.name;
  if (target.exact) opts.exact = true;
  return opts;
}

function exactOpts(target) {
  return target.exact ? { exact: true } : {};
}

export function emitLocator(raw, root = 'page') {
  const target = normalizeTarget(raw);
  let ctx = root;
  if (target.scope) {
    ctx = emitLocator(target.scope, root);
  }

  let inner;
  switch (target.by) {
    case 'testid':
      inner = `${ctx}.getByTestId(${quote(target.name)})`;
      break;
    case 'role': {
      const opts = [];
      if (target.name != null) opts.push(`name: ${quote(target.name)}`);
      if (target.exact) opts.push('exact: true');
      inner = `${ctx}.getByRole(${quote(target.role)}${opts.length ? `, { ${opts.join(', ')} }` : ''})`;
      break;
    }
    case 'label':
      inner = `${ctx}.getByLabel(${quote(target.name)}${target.exact ? ', { exact: true }' : ''})`;
      break;
    case 'placeholder':
      inner = `${ctx}.getByPlaceholder(${quote(target.name)}${target.exact ? ', { exact: true }' : ''})`;
      break;
    case 'text':
      inner = `${ctx}.getByText(${quote(target.name)}${target.exact ? ', { exact: true }' : ''})`;
      break;
    case 'alt':
      inner = `${ctx}.getByAltText(${quote(target.name)}${target.exact ? ', { exact: true }' : ''})`;
      break;
    case 'title':
      inner = `${ctx}.getByTitle(${quote(target.name)}${target.exact ? ', { exact: true }' : ''})`;
      break;
    case 'css':
      inner = `${ctx}.locator(${quote(target.selector)})`;
      break;
    default:
      throw new Error(`cannot emit locator without by: ${JSON.stringify(raw)}`);
  }

  if (target.closest) {
    return `${ctx}.locator(${quote(target.closest)}).filter({ has: ${inner} })`;
  }
  return inner;
}

export async function describeMatches(locator, count, limit = 8) {
  const n = Math.min(count, limit);
  const out = [];
  for (let i = 0; i < n; i += 1) {
    const el = locator.nth(i);
    const info = await el.evaluate((node) => ({
      tag: node.tagName.toLowerCase(),
      role: node.getAttribute('role') || '',
      name: (
        node.getAttribute('aria-label') ||
        node.getAttribute('alt') ||
        (node.innerText || '').trim()
      ).slice(0, 80),
      testId: node.getAttribute('data-testid') || '',
      id: node.id || '',
    }));
    let generated = el.toString();
    try {
      if (typeof el.normalize === 'function') {
        generated = (await el.normalize()).toString();
      }
    } catch {
      // normalize is best-effort
    }
    out.push({ index: i, ...info, generated });
  }
  return out;
}

async function inspect(page, target, opts = {}) {
  const locator = toLocator(page, target);
  const count = await locator.count();
  const used = emitLocator(target);
  if (count === 0) {
    return { status: 'not_found', count, target, used, locator };
  }
  if (count > 1 && !opts.allowMultiple) {
    const candidates = await describeMatches(locator, count);
    return { status: 'ambiguous', count, target, used, locator, candidates };
  }
  let generated = used;
  try {
    if (typeof locator.normalize === 'function') {
      generated = (await locator.normalize()).toString();
    }
  } catch {
    generated = locator.toString();
  }
  return { status: 'ok', count, target, used, generated, locator };
}

/**
 * Resolve a target against a live page. If `by` is omitted, walk the
 * strategy ladder and stop at the first unique match.
 */
export async function resolveTarget(page, raw, opts = {}) {
  const strategy = opts.strategy ?? 'preferTestId';
  const order = STRATEGIES[strategy];
  if (!order) throw new Error(`unknown strategy: ${strategy}`);

  const normalized = normalizeTarget(raw);
  if (normalized.by) {
    return inspect(page, normalized, opts);
  }

  const attempts = [];
  let firstAmbiguous = null;
  for (const by of order) {
    const candidate = inferTarget(normalized, by);
    if (!candidate) continue;
    const result = await inspect(page, candidate, opts);
    attempts.push({ by, status: result.status, count: result.count, used: result.used });
    if (result.status === 'ok') {
      return { ...result, attempts };
    }
    if (result.status === 'ambiguous' && !firstAmbiguous) {
      firstAmbiguous = { ...result, attempts };
    }
  }

  if (firstAmbiguous) return firstAmbiguous;
  return {
    status: 'not_found',
    count: 0,
    target: normalized,
    used: null,
    locator: null,
    attempts,
  };
}

export function assertResolved(result, label = 'target') {
  if (result.status === 'ok') return result;
  const extra =
    result.status === 'ambiguous'
      ? ` candidates=${JSON.stringify(result.candidates, null, 2)}`
      : result.attempts
        ? ` attempts=${JSON.stringify(result.attempts)}`
        : '';
  const err = new Error(`${label}: ${result.status}${extra}`);
  err.result = result;
  throw err;
}
