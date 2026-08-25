import assert from 'node:assert/strict';
import { test } from 'node:test';
import { detectProvider, parseGitRemote, parseTarget } from './detect-host.mjs';

test('parseGitRemote https and ssh', () => {
  assert.deepEqual(parseGitRemote('https://github.com/acme/app.git'), {
    host: 'github.com',
    owner: 'acme',
    repo: 'app',
  });
  assert.deepEqual(parseGitRemote('git@nova.teachx.ai:trace-analysis/ipt.git'), {
    host: 'nova.teachx.ai',
    owner: 'trace-analysis',
    repo: 'ipt',
  });
});

test('detectProvider from host and href', () => {
  assert.equal(detectProvider('github.com', 'https://github.com/acme/app/pull/12'), 'github');
  assert.equal(
    detectProvider('nova.teachx.ai', 'https://nova.teachx.ai/g/p/-/merge_requests/54'),
    'gitlab',
  );
  assert.equal(detectProvider('gitlab.example.com', ''), 'gitlab');
  assert.equal(detectProvider('codeberg.org', 'https://codeberg.org/acme/app/pulls/3'), 'gitea');
  assert.equal(detectProvider('git.example.com', 'https://git.example.com/acme/app/pull/9'), 'unknown-pull');
  assert.equal(detectProvider('git.example.com', ''), 'unknown');
});

test('parseTarget prefers a pasted URL', () => {
  const gh = parseTarget('please claim https://github.com/acme/app/pull/12');
  assert.equal(gh.provider, 'github');
  assert.equal(gh.number, '12');
  assert.equal(gh.slug, 'acme/app');

  const gl = parseTarget(
    'https://nova.teachx.ai/trace-analysis/ipt/-/merge_requests/54',
  );
  assert.equal(gl.provider, 'gitlab');
  assert.equal(gl.number, '54');
  assert.equal(gl.slug, 'trace-analysis/ipt');

  const tea = parseTarget('https://codeberg.org/acme/app/pulls/3');
  assert.equal(tea.provider, 'gitea');
  assert.equal(tea.number, '3');
});

test('parseTarget inherits origin when only !N / N is given', () => {
  const fromBang = parseTarget('!54', 'https://gitlab.com/acme/app.git');
  assert.equal(fromBang.provider, 'gitlab');
  assert.equal(fromBang.number, '54');
  assert.equal(fromBang.slug, 'acme/app');

  const fromBare = parseTarget('claim 12', 'https://github.com/acme/app.git');
  assert.equal(fromBare.provider, 'github');
  assert.equal(fromBare.number, '12');
});
