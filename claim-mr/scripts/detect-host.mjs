/**
 * Parse a PR/MR URL or `git remote` into { provider, host, owner, repo, number }.
 *
 *   node detect-host.mjs https://github.com/acme/app/pull/12
 *   node detect-host.mjs                 # uses origin
 */
import { execSync } from 'node:child_process';

const NOTE = `**Claimed for review**

I've claimed this MR and am reviewing it now so we avoid duplicate work. Please don't start a parallel full review unless coordinating with me first — happy to take comments/questions while I'm on it.`;

export function parseGitRemote(url) {
  const raw = String(url || '').trim();
  const ssh = raw.match(/^git@([^:]+):(.+?)(?:\.git)?$/);
  const http = raw.match(/^https?:\/\/([^/]+)\/(.+?)(?:\.git)?$/);
  const host = (ssh?.[1] || http?.[1] || '').toLowerCase();
  const path = (ssh?.[2] || http?.[2] || '').replace(/\/+$/, '');
  const [owner, repo] = path.split('/');
  return { host, owner: owner || '', repo: (repo || '').replace(/\.git$/, '') };
}

export function detectProvider(host, href = '') {
  const h = host.toLowerCase();
  const u = href.toLowerCase();
  if (u.includes('/-/merge_requests/') || h.includes('gitlab')) return 'gitlab';
  if (h === 'github.com' || h.endsWith('.ghe.com') || h.includes('github')) {
    return 'github';
  }
  if (
    h.includes('gitea') ||
    h.includes('forgejo') ||
    h === 'codeberg.org' ||
    h.endsWith('.codeberg.org')
  ) {
    return 'gitea';
  }
  if (u.includes('/merge_requests/')) return 'gitlab';
  if (u.includes('/pull/') || u.includes('/pulls/')) return 'unknown-pull';
  return 'unknown';
}

export function parseTarget(input, remoteUrl = '') {
  const text = String(input || '').trim();
  const remote = parseGitRemote(remoteUrl);
  const urlMatch = text.match(/https?:\/\/[^\s)]+/);
  const href = urlMatch ? urlMatch[0] : '';
  let host = remote.host;
  let owner = remote.owner;
  let repo = remote.repo;
  let number = '';

  if (href) {
    try {
      const u = new URL(href);
      host = u.host;
      const parts = u.pathname
        .replace(/\/+$/, '')
        .split('/')
        .filter((p) => p && p !== '-');
      const mr = parts.indexOf('merge_requests');
      const pull = parts.includes('pull')
        ? parts.indexOf('pull')
        : parts.indexOf('pulls');
      if (mr >= 2) {
        owner = parts.slice(0, mr - 1).join('/');
        repo = parts[mr - 1];
        number = parts[mr + 1] || '';
      } else if (pull >= 2) {
        owner = parts.slice(0, pull - 1).join('/');
        repo = parts[pull - 1];
        number = parts[pull + 1] || '';
      }
    } catch {
      /* keep remote */
    }
  }

  const bang = text.match(/!(?<n>\d+)/);
  const bare = text.match(/(?:^|\s)(?<n>\d+)(?:\s|$)/);
  if (!number) number = bang?.groups?.n || bare?.groups?.n || '';

  const provider = detectProvider(host, href);
  return {
    provider,
    host,
    owner,
    repo,
    number,
    slug: owner && repo ? `${owner}/${repo}` : '',
    href,
    note: NOTE,
  };
}

export function originRemote() {
  try {
    return execSync('git remote get-url origin', { encoding: 'utf8' }).trim();
  } catch {
    return '';
  }
}

const invoked = process.argv[1] || '';
if (invoked.endsWith('detect-host.mjs') || invoked.endsWith('detect-host')) {
  const arg = process.argv.slice(2).join(' ');
  process.stdout.write(`${JSON.stringify(parseTarget(arg, originRemote()), null, 2)}\n`);
}
