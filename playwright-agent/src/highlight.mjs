import { resolveTarget } from './locators.mjs';

export const DEFAULT_HIGHLIGHT = {
  before: { color: '#dc2626', style: 'solid' },
  after: { color: '#16a34a', style: 'solid' },
  context: { color: '#2563eb', style: 'dashed' },
};

/**
 * Resolve via the locator engine, then outline the unique node.
 * Returns false on not_found / ambiguous — never paints the first match.
 */
export async function highlightRegion(page, raw, opts = {}) {
  const palette = opts.palette ?? DEFAULT_HIGHLIGHT;
  const kind = raw.kind ?? opts.kind ?? 'after';
  const paint = palette[kind] ?? palette.after;
  const resolved = await resolveTarget(page, raw, opts);

  if (resolved.status !== 'ok') return false;

  return resolved.locator.evaluate(
    (node, p) => {
      if (!(node instanceof HTMLElement)) return false;
      node.style.outline = `3px ${p.style} ${p.color}`;
      node.style.outlineOffset = '6px';
      node.setAttribute('data-review-highlight', p.kind);
      node.scrollIntoView({ block: 'center', inline: 'nearest' });
      return true;
    },
    { ...paint, kind },
  );
}
