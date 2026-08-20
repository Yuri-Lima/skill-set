/**
 * Video overlay: box the issue region and pin a caption.
 * Red = before / broken. Green = after / fixed.
 */
import { HIGHLIGHT, highlightRegion } from './highlight-ui.mjs';

export { HIGHLIGHT, highlightRegion };

/**
 * Outline a widget and pin a label above it for the rest of the recording.
 *
 * @param {import('playwright').Page} page
 * @param {{
 *   kind: 'before' | 'after',
 *   label: string,
 *   selector?: string,
 *   text?: string | RegExp,
 *   closest?: string,
 * }} opts
 */
export async function labelIssueArea(page, opts) {
  const kind = opts.kind ?? 'before';
  const paint = HIGHLIGHT[kind] ?? HIGHLIGHT.before;
  const textSource =
    opts.text instanceof RegExp ? opts.text.source : opts.text ?? '';
  const textFlags = opts.text instanceof RegExp ? opts.text.flags : 'i';

  let outlined = await highlightRegion(page, {
    kind,
    selector: opts.selector,
    text: opts.text,
    closest: opts.closest,
  });

  if (!outlined && textSource) {
    outlined = await page.evaluate(
      ({ source, flags, closest, kind: k }) => {
        const re = new RegExp(source, flags || 'i');
        const nodes = [
          ...document.querySelectorAll(
            'p, div, span, li, small, strong, [role="alert"], [role="status"]',
          ),
        ];
        const hit = nodes.find((el) => {
          const t = (el.textContent || '').trim();
          return re.test(t) && t.length < 240;
        });
        if (!(hit instanceof HTMLElement)) return false;
        const box =
          (closest && hit.closest(closest) instanceof HTMLElement
            ? hit.closest(closest)
            : hit);
        if (!(box instanceof HTMLElement)) return false;
        box.setAttribute('data-review-highlight', k);
        return true;
      },
      { source: textSource, flags: textFlags, closest: opts.closest ?? null, kind },
    );
  }

  await page.evaluate(
    ({ color, label, outlined: hit }) => {
      document.getElementById('issue-area-badge')?.remove();
      document.getElementById('issue-area-veil')?.remove();
      const target = document.querySelector('[data-review-highlight]');
      const pad = 10;

      if (target instanceof HTMLElement) {
        const r = target.getBoundingClientRect();
        const x1 = Math.max(0, r.left - pad);
        const y1 = Math.max(0, r.top - pad);
        const x2 = Math.min(window.innerWidth, r.right + pad);
        const y2 = Math.min(window.innerHeight, r.bottom + pad);
        const veil = document.createElement('div');
        veil.id = 'issue-area-veil';
        Object.assign(veil.style, {
          position: 'fixed',
          left: `${x1}px`,
          top: `${y1}px`,
          width: `${Math.max(8, x2 - x1)}px`,
          height: `${Math.max(8, y2 - y1)}px`,
          zIndex: '2147483645',
          pointerEvents: 'none',
          borderRadius: '10px',
          boxShadow: `0 0 0 3px ${color}, 0 0 0 9999px rgba(0,0,0,0.45)`,
        });
        document.documentElement.appendChild(veil);
        target.style.outline = `3px solid ${color}`;
        target.style.outlineOffset = '4px';
      }

      const badge = document.createElement('div');
      badge.id = 'issue-area-badge';
      badge.textContent = hit ? label : `${label} (region not found)`;
      Object.assign(badge.style, {
        position: 'fixed',
        zIndex: '2147483646',
        background: color,
        color: '#fff',
        font: '700 14px/1.25 ui-sans-serif, system-ui, sans-serif',
        padding: '8px 12px',
        borderRadius: '8px',
        pointerEvents: 'none',
        boxShadow: '0 4px 14px rgba(0,0,0,.35)',
        maxWidth: 'min(420px, calc(100vw - 24px))',
      });
      if (target instanceof HTMLElement) {
        const r = target.getBoundingClientRect();
        const left = Math.max(12, Math.min(r.left, window.innerWidth - 440));
        const top = r.top >= 52 ? r.top - 44 : Math.max(12, r.top + 8);
        badge.style.left = `${left}px`;
        badge.style.top = `${top}px`;
      } else {
        badge.style.left = '16px';
        badge.style.top = '16px';
      }
      document.documentElement.appendChild(badge);
    },
    { color: paint.color, label: opts.label, outlined },
  );
  return outlined;
}
