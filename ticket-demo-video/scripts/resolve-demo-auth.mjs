/**
 * Resolve how this workspace signs in for a demo recording.
 *
 * First run: scan the project and print suggestions. The agent must ask
 * the user which method to use and for temporary credentials, then write
 * docs/review-impact/demo-auth.json (gitignored). login() reads that file.
 *
 *   node resolve-demo-auth.mjs --scan
 */
import fs from 'node:fs';
import path from 'node:path';

export const AUTH_CONFIG_PATH = path.join(
  process.cwd(),
  'docs/review-impact/demo-auth.json',
);

const LOGIN_ROUTE_HINTS = [
  'login',
  'sign-in',
  'signin',
  'auth/login',
  'auth/sign-in',
];

const PROVIDER_HINTS = [
  { id: 'supabase', re: /supabase/i, method: 'password', note: 'Supabase email/password or magic link' },
  { id: 'next-auth', re: /next-auth|nextauth|auth\.js/i, method: 'password', note: 'Auth.js / NextAuth credentials or OAuth' },
  { id: 'clerk', re: /clerk/i, method: 'password', note: 'Clerk hosted sign-in' },
  { id: 'auth0', re: /auth0/i, method: 'password', note: 'Auth0 hosted login' },
  { id: 'keycloak', re: /keycloak/i, method: 'password', note: 'Keycloak' },
];

const SKIP_DIRS = new Set([
  'node_modules',
  '.git',
  '.next',
  'dist',
  'build',
  'coverage',
  '.venv',
  'venv',
  '__pycache__',
]);

function isCandidate(relPath) {
  const p = relPath.replaceAll('\\', '/').toLowerCase();
  const base = path.basename(p);
  if (/\.env(\..+)?\.example$|\.env\.sample$/.test(base)) return true;
  if (base === 'demo-user.md') return true;
  return LOGIN_ROUTE_HINTS.some(
    (h) => p.includes(`/${h}/`) || p.includes(`/${h}.`) || p.endsWith(`/${h}`),
  );
}

function walk(dir, acc, root, depth = 0) {
  if (depth > 12 || acc.length > 80) return acc;
  let entries = [];
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const ent of entries) {
    if (ent.isDirectory() && (SKIP_DIRS.has(ent.name) || ent.name.startsWith('.'))) {
      continue;
    }
    const full = path.join(dir, ent.name);
    if (ent.isDirectory()) {
      walk(full, acc, root, depth + 1);
      continue;
    }
    if (isCandidate(path.relative(root, full))) acc.push(full);
  }
  return acc;
}

function readIfExists(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch {
    return '';
  }
}

export function scanDemoAuth(root = process.cwd()) {
  const files = walk(root, [], root);
  const rel = (abs) => path.relative(root, abs);
  const hints = [];

  const demoUser = files.find((f) => /demo-user\.md$/i.test(f));
  if (demoUser) {
    hints.push({
      kind: 'docs',
      path: rel(demoUser),
      note: 'Project documents a demo user — ask before using those credentials',
    });
  }

  const envExamples = files.filter((f) =>
    /\.env(\..+)?\.example$|\.env\.sample$/i.test(path.basename(f)),
  );
  const envBlob = envExamples.map(readIfExists).join('\n');
  for (const provider of PROVIDER_HINTS) {
    if (provider.re.test(envBlob)) {
      hints.push({
        kind: 'provider',
        id: provider.id,
        method: provider.method,
        note: provider.note,
        from: envExamples.map(rel),
      });
    }
  }

  const loginFiles = files.filter((f) => {
    const p = rel(f).replaceAll('\\', '/').toLowerCase();
    return LOGIN_ROUTE_HINTS.some(
      (h) => p.includes(`/${h}/`) || p.endsWith(`/${h}.tsx`) || p.endsWith(`/${h}.ts`),
    );
  });
  for (const f of loginFiles.slice(0, 8)) {
    hints.push({
      kind: 'route',
      path: rel(f),
      method: 'password',
      note: 'Looks like a sign-in page',
    });
  }

  const suggestedMethod = loginFiles.length || envBlob
    ? 'password'
    : 'none';
  let loginPathGuess = '/';
  if (loginFiles.some((f) => /\/login\//i.test(rel(f)))) loginPathGuess = '/login';
  else if (loginFiles.some((f) => /sign-?in/i.test(rel(f)))) loginPathGuess = '/sign-in';

  return {
    configPath: path.relative(root, AUTH_CONFIG_PATH),
    suggestedMethod,
    loginPathGuess,
    hints,
    envPresent: Boolean(process.env.DEMO_EMAIL && process.env.DEMO_PASSWORD),
    configPresent: fs.existsSync(AUTH_CONFIG_PATH),
  };
}

export function loadDemoAuth() {
  if (process.env.DEMO_EMAIL && process.env.DEMO_PASSWORD) {
    return {
      method: 'password',
      loginPath: process.env.DEMO_LOGIN_PATH ?? '/login',
      email: process.env.DEMO_EMAIL,
      password: process.env.DEMO_PASSWORD,
      emailSelector: process.env.DEMO_EMAIL_SELECTOR ?? '#email',
      passwordSelector: process.env.DEMO_PASSWORD_SELECTOR ?? '#password',
      submitName: process.env.DEMO_SUBMIT_NAME ?? /sign in|log in|entrar/i,
      source: 'env',
    };
  }
  if (fs.existsSync(AUTH_CONFIG_PATH)) {
    const raw = JSON.parse(fs.readFileSync(AUTH_CONFIG_PATH, 'utf8'));
    return { ...raw, source: 'file' };
  }
  return null;
}

export function saveDemoAuth(config) {
  fs.mkdirSync(path.dirname(AUTH_CONFIG_PATH), { recursive: true });
  const out = { ...config };
  delete out.source;
  fs.writeFileSync(AUTH_CONFIG_PATH, `${JSON.stringify(out, null, 2)}\n`);
  return AUTH_CONFIG_PATH;
}

export function requireDemoAuth() {
  const auth = loadDemoAuth();
  if (auth) return auth;
  const scan = scanDemoAuth();
  const err = new Error(
    [
      'Demo auth is not configured for this project.',
      'Ask the user which sign-in method to use and for a temporary/fake account.',
      `Write the answer to ${scan.configPath} (gitignored) or set DEMO_EMAIL + DEMO_PASSWORD.`,
      `Scan suggested method=${scan.suggestedMethod} loginPath=${scan.loginPathGuess}.`,
      scan.hints.length
        ? `Hints: ${scan.hints.map((h) => h.path || h.id || h.note).join('; ')}`
        : 'Hints: no login route or auth provider found — confirm if the flow is public.',
    ].join(' '),
  );
  err.code = 'AUTH_NOT_CONFIGURED';
  err.scan = scan;
  throw err;
}

if (process.argv[1]?.includes('resolve-demo-auth') && process.argv.includes('--scan')) {
  process.stdout.write(`${JSON.stringify(scanDemoAuth(), null, 2)}\n`);
}
