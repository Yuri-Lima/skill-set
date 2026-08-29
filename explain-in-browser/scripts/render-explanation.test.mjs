import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import {
  escapeHtml,
  markdownToHtml,
  parseArgs,
  playerScript,
  renderExplanation,
  titleFromMarkdown,
  wrapPage,
} from './render-explanation.mjs';

test('inline code, bold, link', () => {
  const html = markdownToHtml('Use `open` and **read** the [page](https://x.test).');
  assert.match(html, /<code>open<\/code>/);
  assert.match(html, /<strong>read<\/strong>/);
  assert.match(html, /<a href="https:\/\/x.test">page<\/a>/);
});

test('headings lists tables fences', () => {
  const md = `# Title

## Why

- one
- two

1. first

\`\`\`ts
const x = 1;
\`\`\`

| Layer | Limit |
| --- | --- |
| nginx | 1 GB |
`;
  const html = markdownToHtml(md);
  assert.match(html, /<h1>Title<\/h1>/);
  assert.match(html, /<h2>Why<\/h2>/);
  assert.match(html, /<ul>[\s\S]*<li>one<\/li>/);
  assert.match(html, /<ol>[\s\S]*<li>first<\/li>/);
  assert.match(html, /<pre><code class="language-ts">const x = 1;<\/code><\/pre>/);
  assert.match(html, /<th>Layer<\/th>/);
  assert.match(html, /<td>1 GB<\/td>/);
});

test('escapes raw html in markdown', () => {
  const html = markdownToHtml('Do not <script>alert(1)</script> here.');
  assert.doesNotMatch(html, /<script>/);
  assert.match(html, /&lt;script&gt;/);
  assert.equal(escapeHtml('<x>'), '&lt;x&gt;');
});

test('titleFromMarkdown and parseArgs', () => {
  assert.equal(titleFromMarkdown('# Backup restore\n\nbody'), 'Backup restore');
  assert.equal(titleFromMarkdown('no heading'), 'Explanation');
  const args = parseArgs(['--in', 'a.md', '--title', 'T', '--no-open']);
  assert.deepEqual(args, { in: 'a.md', out: null, title: 'T', open: false });
});

test('renderExplanation writes html without opening', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'explain-in-browser-'));
  const mdPath = join(dir, 'note.md');
  await writeFile(mdPath, '# Hello\n\nA **short** page.\n', 'utf8');
  const dest = await renderExplanation({
    markdown: await readFile(mdPath, 'utf8'),
    inPath: mdPath,
    open: false,
  });
  assert.equal(dest, join(dir, 'note.html'));
  const html = await readFile(dest, 'utf8');
  assert.match(html, /<title>Hello<\/title>/);
  assert.match(html, /<strong>short<\/strong>/);
  assert.match(html, /id="play-all"/);
  assert.match(html, /speechSynthesis/);
  assert.match(html, /Listen from this paragraph/);
});

test('wrapPage embeds click-to-play player, no autoplay', () => {
  const html = wrapPage('T', '<p>Hello</p>');
  assert.match(html, /id="play-all"/);
  assert.match(html, /id="pause"/);
  assert.match(html, /id="stop"/);
  assert.match(playerScript(), /speakAt\(0\)/);
  assert.doesNotMatch(playerScript(), /speakAt\(0\);\s*\}\)\(\)/);
  assert.doesNotMatch(html, /speakAt\(0\);\s*$/m);
});
