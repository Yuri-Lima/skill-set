import { spawn } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HOME = process.env.PLAYWRIGHT_AGENT_HOME
  ?? path.join(os.homedir(), '.playwright-agent');

export function sessionDir(name = 'default') {
  return path.join(HOME, 'sessions', sanitize(name));
}

export function sessionMetaPath(name) {
  return path.join(sessionDir(name), 'meta.json');
}

function sanitize(name) {
  return String(name).replace(/[^a-zA-Z0-9._-]/g, '_') || 'default';
}

export function readMeta(name) {
  const file = sessionMetaPath(name);
  if (!fs.existsSync(file)) return null;
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch {
    return null;
  }
}

export function writeMeta(name, meta) {
  const dir = sessionDir(name);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(sessionMetaPath(name), JSON.stringify(meta, null, 2));
}

export function journalPath(name) {
  return path.join(sessionDir(name), 'journal.json');
}

export async function request(name, body, { timeoutMs = 45_000 } = {}) {
  const meta = readMeta(name);
  if (!meta?.port) {
    const err = new Error(`no session "${name}" — run: playwright-agent open <url>`);
    err.code = 'NO_SESSION';
    throw err;
  }
  return httpJson(meta.port, body, timeoutMs);
}

export async function ensureDaemon(name, { headed = false } = {}) {
  const meta = readMeta(name);
  if (meta?.port && (await isAlive(meta.port))) return meta;

  const port = await freePort();
  const daemon = fileURLToPath(new URL('./daemon.mjs', import.meta.url));
  const child = spawn(process.execPath, [daemon, '--port', String(port), '--session', name], {
    detached: true,
    stdio: 'ignore',
    env: {
      ...process.env,
      PLAYWRIGHT_AGENT_HEADED: headed ? '1' : '0',
    },
  });
  child.unref();
  writeMeta(name, { port, pid: child.pid, headed: Boolean(headed) });

  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (await isAlive(port)) return readMeta(name);
    await sleep(80);
  }
  throw new Error(`daemon for session "${name}" did not start on port ${port}`);
}

async function isAlive(port) {
  try {
    const res = await httpJson(port, { cmd: 'ping' }, 800);
    return res?.status === 'ok';
  } catch {
    return false;
  }
}

function httpJson(port, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const payload = JSON.stringify(body);
    const req = http.request(
      {
        host: '127.0.0.1',
        port,
        path: '/',
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          'content-length': Buffer.byteLength(payload),
        },
        timeout: timeoutMs,
      },
      (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          const text = Buffer.concat(chunks).toString('utf8');
          try {
            resolve(JSON.parse(text || '{}'));
          } catch {
            reject(new Error(`daemon returned non-JSON: ${text.slice(0, 200)}`));
          }
        });
      },
    );
    req.on('error', reject);
    req.on('timeout', () => {
      req.destroy();
      reject(new Error('daemon request timed out'));
    });
    req.write(payload);
    req.end();
  });
}

function freePort() {
  return new Promise((resolve, reject) => {
    const s = http.createServer();
    s.listen(0, '127.0.0.1', () => {
      const { port } = s.address();
      s.close((err) => (err ? reject(err) : resolve(port)));
    });
    s.on('error', reject);
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
