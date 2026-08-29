export {
  STRATEGIES,
  normalizeTarget,
  inferTarget,
  toLocator,
  emitLocator,
  resolveTarget,
  assertResolved,
  describeMatches,
  quote,
} from './locators.mjs';

export { performAction, ACTIONS } from './actions.mjs';
export { performAssert, ASSERTIONS, emitAssert } from './verify.mjs';
export { createJournal, appendStep, journalToSpec } from './record.mjs';
export { highlightRegion, DEFAULT_HIGHLIGHT } from './highlight.mjs';
