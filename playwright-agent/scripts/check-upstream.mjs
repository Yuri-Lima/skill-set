#!/usr/bin/env node
/**
 * Diff vendored Playwright Test Agent prompts against a Playwright tag.
 *
 *   node scripts/check-upstream.mjs --check
 *   node scripts/check-upstream.mjs --write
 *
 * Default tag is the installed playwright version, else "main".
 * Official note: regenerate agent definitions whenever Playwright updates.
 * https://playwright.dev/docs/test-agents
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const UPSTREAM = path.join(ROOT, 'upstream', 'playwright-agents');
const FILES = [
  'playwright-test-planner.agent.md',
  'playwright-test-generator.agent.md',
  'playwright-test-healer.agent.md',
];

const args = process.argv.slice(2);
const write = args.includes('--write');
const check = args.includes('--check') || !write;
const tag = argValue('--tag') ?? detectPlaywrightTag();

const base =
  `https://raw.githubusercontent.com/microsoft/playwright/${tag}` +
  '/packages/playwright/src/agents';

fs.mkdirSync(UPSTREAM, { recursive: true });

let drift = 0;
for (const name of FILES) {
  const url = `${base}/${name}`;
  const dest = path.join(UPSTREAM, name);
  let remote;
  try {
    remote = await fetchText(url);
  } catch (err) {
    console.error(`fetch failed ${url}: ${err.message}`);
    process.exit(2);
  }

  const local = fs.existsSync(dest) ? fs.readFileSync(dest, 'utf8') : '';
  const remoteTools = toolsLine(remote);
  const localTools = toolsLine(local);

  if (local === remote) {
    console.log(`ok    ${name}  (${tag})`);
    continue;
  }

  drift += 1;
  console.log(`drift ${name}  (${tag})`);
  if (localTools !== remoteTools) {
    console.log(`  local tools:  ${localTools || '(none)'}`);
    console.log(`  remote tools: ${remoteTools || '(none)'}`);
  }
  if (write) {
    fs.writeFileSync(dest, remote);
    console.log(`  wrote ${dest}`);
  }
}

fs.writeFileSync(
  path.join(UPSTREAM, 'PIN.md'),
  `# Vendored from microsoft/playwright @ ${tag}\n\nSource: ${base}/\nDocs: https://playwright.dev/docs/test-agents\n\nRe-run \`node scripts/check-upstream.mjs --write --tag <tag>\` after bumping Playwright.\n`,
);

if (check && drift && !write) {
  console.error(`\n${drift} file(s) differ. Re-run with --write after reviewing.`);
  process.exit(1);
}

function toolsLine(md) {
  const m = String(md).match(/^tools:\n((?:  - .+\n)+)/m);
  if (!m) return '';
  return m[1]
    .split('\n')
    .map((l) => l.replace(/^\s*-\s*/, '').trim())
    .filter(Boolean)
    .join(', ');
}

function detectPlaywrightTag() {
  try {
    const pkgPath = path.join(ROOT, 'node_modules', 'playwright', 'package.json');
    const ver = JSON.parse(fs.readFileSync(pkgPath, 'utf8')).version;
    return `v${ver}`;
  } catch {
    return 'main';
  }
}

function argValue(flag) {
  const i = args.indexOf(flag);
  return i === -1 ? undefined : args[i + 1];
}

async function fetchText(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.text();
}
