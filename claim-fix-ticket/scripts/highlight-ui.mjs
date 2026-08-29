/**
 * Outline the smallest UI region a review-impact finding touches.
 * Targeting goes through playwright-agent (strict locators). Palette stays here.
 *
 *   import { highlightRegion, HIGHLIGHT } from './highlight-ui.mjs';
 *
 *   await highlightRegion(page, {
 *     kind: 'after',
 *     text: /cash on hand/i,
 *     closest: '[data-slot="card"], .rounded-xl, .rounded-lg',
 *   });
 */

import { highlightRegion as paintRegion } from '../../playwright-agent/src/index.mjs';

export const HIGHLIGHT = {
  before: { color: '#dc2626', style: 'solid' },
  after: { color: '#16a34a', style: 'solid' },
  context: { color: '#2563eb', style: 'dashed' },
};

const DEFAULT_CLOSEST =
  '[data-slot="card"], [role="alert"], form, table, .rounded-xl, .rounded-lg';

/**
 * @param {import('playwright').Page} page
 * @param {{
 *   kind?: 'before' | 'after' | 'context',
 *   testId?: string,
 *   selector?: string,
 *   text?: string | RegExp,
 *   closest?: string,
 * }} target
 * @returns {Promise<boolean>}
 */
export async function highlightRegion(page, target) {
  const kind = target.kind ?? 'after';
  const closest =
    target.closest ??
    (target.testId || target.selector ? undefined : DEFAULT_CLOSEST);
  return paintRegion(
    page,
    {
      kind,
      testId: target.testId,
      selector: target.selector,
      text: target.text,
      closest,
    },
    { palette: HIGHLIGHT, strategy: 'preferTestId' },
  );
}
