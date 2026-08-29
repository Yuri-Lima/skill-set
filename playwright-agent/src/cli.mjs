#!/usr/bin/env node
import fs from 'node:fs';
import { ensureDaemon, request } from './session.mjs';

const argv = process.argv.slice(2);
const { flags, rest } = parseArgs(argv);

if (rest[0] === 'help' || flags.help || rest.length === 0) {
  printHelp();
  process.exit(0);
}

const session = flags.session ?? process.env.PLAYWRIGHT_AGENT_SESSION ?? 'default';
const cmd = rest[0];

try {
  const result = await dispatch(cmd, rest.slice(1), flags, session);
  const code = result?.status && result.status !== 'ok' ? 1 : 0;
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  process.exit(code);
} catch (err) {
  process.stderr.write(`${JSON.stringify({ status: 'error', error: err.message }, null, 2)}\n`);
  process.exit(1);
}

async function dispatch(cmd, args, flags, session) {
  if (cmd === 'open' || cmd === 'goto' || cmd === 'navigate') {
    await ensureDaemon(session, { headed: Boolean(flags.headed) });
    const url = args[0];
    if (!url) throw new Error('open <url> required');
    return request(session, {
      cmd: 'open',
      url: withProtocol(url),
      headed: Boolean(flags.headed),
      seed: flags.seed,
    });
  }

  if (cmd === 'close' || cmd === 'quit' || cmd === 'exit') {
    return request(session, { cmd: 'close' });
  }

  if (cmd === 'state') return request(session, { cmd: 'state' });
  if (cmd === 'shot' || cmd === 'screenshot') {
    return request(session, { cmd: 'shot', path: args[0] ?? flags.path, full: Boolean(flags.full) });
  }
  if (cmd === 'codegen') {
    return request(session, { cmd: 'codegen', path: args[0] ?? flags.path });
  }

  if (cmd === 'resolve') {
    return request(session, { cmd: 'resolve', target: targetFrom(flags, args), opts: optsFrom(flags) });
  }

  if (cmd === 'click' || cmd === 'fill' || cmd === 'check' || cmd === 'uncheck' || cmd === 'select' || cmd === 'hover' || cmd === 'press') {
    return request(session, {
      cmd: 'act',
      action: cmd,
      target: targetFrom(flags, args, cmd === 'fill' || cmd === 'select' || cmd === 'press' ? 1 : 0),
      value: valueFrom(cmd, args, flags),
      opts: optsFrom(flags),
      comment: flags.comment,
    });
  }

  if (cmd === 'act') {
    const action = args[0];
    if (!action) throw new Error('act <click|fill|check|uncheck|select|press|hover>');
    return request(session, {
      cmd: 'act',
      action,
      target: targetFrom(flags, args.slice(1), action === 'fill' || action === 'select' || action === 'press' ? 1 : 0),
      value: valueFrom(action, args.slice(1), flags),
      opts: optsFrom(flags),
      comment: flags.comment,
    });
  }

  if (cmd === 'assert') {
    const kind = args[0] ?? flags.assert;
    if (!kind) throw new Error('assert <visible|hidden|text|value|url|enabled|checked>');
    return request(session, {
      cmd: 'assert',
      assert: kind,
      target: kind === 'url' ? undefined : targetFrom(flags, args.slice(1), kind === 'text' || kind === 'value' ? 1 : 0),
      value: flags.value ?? (kind === 'text' || kind === 'value' || kind === 'url' ? args.at(-1) : undefined),
      pattern: flags.pattern ?? (kind === 'url' ? args[1] : undefined),
      opts: optsFrom(flags),
    });
  }

  throw new Error(`unknown command: ${cmd}`);
}

function targetFrom(flags, args, reservedTail = 0) {
  const target = {};
  if (flags.by) target.by = flags.by;
  if (flags.role) target.role = flags.role;
  if (flags.name) target.name = flags.name;
  if (flags.testid || flags['test-id']) target.testId = flags.testid ?? flags['test-id'];
  if (flags.selector) target.selector = flags.selector;
  if (flags.placeholder) {
    target.by = target.by ?? 'placeholder';
    target.name = flags.placeholder;
  }
  if (flags.label) {
    target.by = target.by ?? 'label';
    target.name = flags.label;
  }
  if (flags.text && !target.name) target.name = flags.text;
  if (flags.exact) target.exact = true;
  if (flags.closest) target.closest = flags.closest;
  if (flags.scope) target.scope = { selector: flags.scope, by: 'css' };

  const positional = args.slice(0, Math.max(0, args.length - reservedTail));
  if (!target.by && !target.testId && !target.selector && !target.role && positional[0]) {
    const token = positional[0];
    if (token.startsWith('#') || token.startsWith('.') || token.startsWith('[')) {
      target.by = 'css';
      target.selector = token;
    }
  }
  return target;
}

function valueFrom(action, args, flags) {
  if (flags.value != null) return flags.value;
  if (action === 'fill' || action === 'select' || action === 'press') return args.at(-1);
  return undefined;
}

function optsFrom(flags) {
  return {
    strategy: flags.strategy ?? 'preferTestId',
    allowMultiple: Boolean(flags.multiple),
  };
}

function withProtocol(url) {
  if (/^[a-z]+:\/\//i.test(url) || url.startsWith('file:') || url.startsWith('about:')) return url;
  if (url.startsWith('/')) return `file://${url}`;
  return `https://${url}`;
}

function parseArgs(list) {
  const flags = {};
  const rest = [];
  for (let i = 0; i < list.length; i += 1) {
    const token = list[i];
    if (token === '--headed' || token === '--full' || token === '--exact' || token === '--multiple' || token === '--help' || token === '-h') {
      flags[token.replace(/^--/, '').replace(/^-/, '')] = true;
      if (token === '-h') flags.help = true;
      continue;
    }
    if (token.startsWith('--')) {
      const key = token.slice(2);
      const next = list[i + 1];
      if (next == null || next.startsWith('--')) {
        flags[key] = true;
      } else {
        flags[key] = next;
        i += 1;
      }
      continue;
    }
    rest.push(token);
  }
  return { flags, rest };
}

function printHelp() {
  const text = fs.readFileSync(new URL('../SKILL.md', import.meta.url), 'utf8');
  const usage = text.split('## Commands')[1]?.split('## ')[0] ?? text;
  process.stdout.write(`playwright-agent — locator contracts, not snapshot refs\n\nCommands${usage}`);
}
