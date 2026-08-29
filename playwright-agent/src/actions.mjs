import { assertResolved, resolveTarget } from './locators.mjs';

export const ACTIONS = ['click', 'fill', 'check', 'uncheck', 'select', 'press', 'hover'];

export async function performAction(page, spec, opts = {}) {
  const action = spec.action;
  if (!ACTIONS.includes(action) && action !== 'goto') {
    throw new Error(`unknown action: ${action}`);
  }

  if (action === 'press' && !spec.target) {
    await page.keyboard.press(spec.value ?? spec.key);
    return { status: 'ok', action, used: 'page.keyboard.press' };
  }

  const resolved = await resolveTarget(page, spec.target, opts);
  assertResolved(resolved, action);
  const locator = resolved.locator;

  switch (action) {
    case 'click':
      await locator.click(spec.options ?? {});
      break;
    case 'fill':
      await locator.fill(String(spec.value ?? ''));
      break;
    case 'check':
      await locator.check();
      break;
    case 'uncheck':
      await locator.uncheck();
      break;
    case 'select':
      await locator.selectOption(spec.value);
      break;
    case 'press':
      await locator.press(spec.value ?? spec.key);
      break;
    case 'hover':
      await locator.hover();
      break;
    default:
      break;
  }

  return {
    status: 'ok',
    action,
    used: resolved.used,
    generated: resolved.generated,
    target: resolved.target,
  };
}
