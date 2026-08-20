/**
 * Outline the smallest UI region a review-impact finding touches, then screenshot.
 *
 * Import from a capture script:
 *
 *   import { highlightRegion, HIGHLIGHT } from
 *     './highlight-ui.mjs';
 *
 *   await highlightRegion(page, {
 *     kind: 'after',
 *     text: /cash on hand/i,
 *     closest: '[data-slot="card"], .rounded-xl, .rounded-lg',
 *   });
 *   await page.screenshot({ path: 'cash-after.png', fullPage: true });
 *
 * Colors match references/report-template.html (do not invent a second palette).
 */

export const HIGHLIGHT = {
  before: { color: '#dc2626', style: 'solid' },
  after: { color: '#16a34a', style: 'solid' },
  context: { color: '#2563eb', style: 'dashed' },
};

/**
 * @typedef {{
 *   kind?: 'before' | 'after' | 'context',
 *   testId?: string,
 *   selector?: string,
 *   text?: string | RegExp,
 *   closest?: string,
 * }} HighlightTarget
 */

/**
 * Draw a 3px outline on the first matching node.
 * Prefers testId / selector; otherwise finds an element whose text matches
 * and walks up to `closest` (card/row) so the box is the widget, not the page.
 *
 * @param {import('playwright').Page} page
 * @param {HighlightTarget} target
 * @returns {Promise<boolean>} true if a node was outlined
 */
export async function highlightRegion(page, target) {
  const kind = target.kind ?? 'after';
  const paint = HIGHLIGHT[kind] ?? HIGHLIGHT.after;
  const textSource =
    target.text instanceof RegExp ? target.text.source : target.text ?? '';
  const textFlags =
    target.text instanceof RegExp ? target.text.flags : 'i';

  return page.evaluate(
    ({ paint: p, spec }) => {
      const byAttr = spec.testId
        ? document.querySelector(`[data-testid="${spec.testId}"]`)
        : null;
      const bySelector = spec.selector ? document.querySelector(spec.selector) : null;
      let node = byAttr || bySelector;

      if (!node && spec.textSource) {
        const re = new RegExp(spec.textSource, spec.textFlags || 'i');
        const candidates = Array.from(
          document.querySelectorAll('h1, h2, h3, h4, p, span, label, button, [role="alert"], li'),
        );
        const hit = candidates.find((el) => re.test(el.textContent || ''));
        node = hit ?? null;
      }

      if (!node) return false;

      if (spec.closest && node.closest) {
        const parent = node.closest(spec.closest);
        if (parent) node = parent;
      }

      if (!(node instanceof HTMLElement)) return false;
      node.style.outline = `3px ${p.style} ${p.color}`;
      node.style.outlineOffset = '6px';
      node.setAttribute('data-review-highlight', spec.kind || 'after');
      node.scrollIntoView({ block: 'center', inline: 'nearest' });
      return true;
    },
    {
      paint,
      spec: {
        kind,
        testId: target.testId ?? null,
        selector: target.selector ?? null,
        textSource,
        textFlags,
        closest:
          target.closest ??
          (target.testId || target.selector
            ? null
            : '[data-slot="card"], [role="alert"], form, table, .rounded-xl, .rounded-lg'),
      },
    },
  );
}
