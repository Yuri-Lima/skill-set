#!/usr/bin/env node
// Write identity, knowledge.md, hunt-profile.md, and the agent-home fallback stack.
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  findingsFile,
  formatIdentity,
  homeDir,
  parseArgs,
  readIdentity,
  renderTemplate,
  tagFor,
  validateSlug,
} from "./lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const refs = join(here, "..", "references");
const args = parseArgs(process.argv.slice(2));
const cmd = args._[0];
const repo = args.dir || process.cwd();

const GROUNDS = {
  "skipped-tests":
    "- Test suites that fail, do not compile, or are skipped/disabled.",
  concurrency:
    "- Concurrency and distributed-safety hazards: in-process timers, shared mutable state, missing locks — anything per-process is suspect on a multi-worker runtime.",
  "swallowed-errors":
    "- Swallowed errors: empty catch blocks, floating promises, `.catch(() => {})`.",
  money:
    "- Money / quantity / date arithmetic: rounding, currency, timezone, tax.",
  leaks:
    "- Resource leaks: connections, subscriptions, intervals, event listeners opened and never closed.",
  todos: "- TODO/FIXME comments that describe real defects.",
  "sibling-plugins":
    "- Divergence between sibling plugins that should share a pattern — a fix applied to one and missed in the others is a bug.",
};

function die(msg) {
  console.error(`✗ ${msg}`);
  process.exit(1);
}

function write(rel, text, { home = false, slug } = {}) {
  const path = home ? join(homeDir(slug), rel) : join(repo, rel);
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, text.endsWith("\n") ? text : text + "\n");
  return path;
}

function loadTemplate(name) {
  return readFileSync(join(refs, name), "utf8");
}

function bullets(items, fallback = "_(none yet)_") {
  if (!items || !items.length) return fallback;
  return items.map((x) => (String(x).startsWith("-") ? x : `- ${x}`)).join("\n");
}

function mark(text, kind) {
  return `${text} \`[${kind}]\``;
}

if (cmd === "identity") {
  const name = args.name;
  const slug = args.slug;
  if (!name) die("--name is required");
  if (!validateSlug(slug)) die(`--slug must match [a-z][a-z0-9-]{0,31} (got ${slug || "empty"})`);
  const existing = readIdentity(repo);
  if (existing && existing.slug !== slug && !args.force) {
    die(`identity already exists as ${existing.name}/${existing.slug} (pass --force to replace)`);
  }
  const idPath = write(".bug-hunter/identity.md", formatIdentity({ name, slug }));
  mkdirSync(homeDir(slug), { recursive: true });
  console.log(`wrote ${idPath}`);
  console.log(`home  ${homeDir(slug)}`);
  process.exit(0);
}

if (cmd === "from-answers") {
  const id = readIdentity(repo);
  if (!id) die("no .bug-hunter/identity.md — run identity first");
  if (!args.answers) die("--answers FILE is required");
  const answers = JSON.parse(readFileSync(args.answers, "utf8"));
  let probe = {};
  if (args.probe) probe = JSON.parse(readFileSync(args.probe, "utf8"));

  const date = new Date().toISOString().slice(0, 10);
  const vars = {
    NAME: id.name,
    SLUG: id.slug,
    DATE: date,
    TAG: tagFor(id.slug),
    FINDINGS: findingsFile(id.slug),
  };

  const layoutBits = [];
  if (probe.languages?.length) layoutBits.push(mark(`Languages: ${probe.languages.join(", ")}`, "V"));
  if (probe.lockfiles?.length) layoutBits.push(mark(`Lockfiles imply: ${probe.lockfiles.join(", ")}`, "V"));
  if (answers.packageManager) layoutBits.push(mark(`Package manager: ${answers.packageManager}`, answers.packageManager && probe.lockfiles?.includes(answers.packageManager) ? "V" : "R"));
  if (probe.workspaces?.length) layoutBits.push(mark(`Workspaces: ${probe.workspaces.join(", ")}`, "V"));
  if (probe.packages?.length) layoutBits.push(mark(`Top-level packages: ${probe.packages.join(", ")}`, "V"));
  if (probe.hasAgentsMd) layoutBits.push(mark("Repo has `AGENTS.md`", "V"));

  const cmdBits = [];
  if (answers.testOne) cmdBits.push(mark(`One-package / focused test: \`${answers.testOne}\``, "R"));
  if (answers.typecheck) cmdBits.push(mark(`Typecheck: \`${answers.typecheck}\``, "R"));
  if (answers.e2e) cmdBits.push(mark(`E2E: \`${answers.e2e}\``, "R"));
  if (answers.forbidden?.length) {
    cmdBits.push(mark(`Forbidden: ${answers.forbidden.map((c) => `\`${c}\``).join(", ")}`, "R"));
  }
  if (answers.start?.length) {
    cmdBits.push(mark(`Start: ${answers.start.map((c) => `\`${c}\``).join(" · ")}`, "R"));
  }

  const portBits = [];
  const ports = answers.ports || probe.ports || [];
  if (!ports.length) portBits.push(mark("No ports recorded — still never assume 3000 is free", "I"));
  for (const p of ports) {
    const src = p.source ? ` (from ${p.source})` : "";
    const ex = p.exclusive ? "; exclusive to this worktree" : "";
    portBits.push(mark(`${p.name}: **${p.value}**${src}${ex}`, p.source ? "V" : "R"));
  }
  portBits.push(mark("Before binding: `lsof -nP -iTCP:<port> -sTCP:LISTEN`. Leave nothing you started listening.", "I"));

  const gitBits = [];
  if (answers.huntBranch) gitBits.push(mark(`Hunt branch: \`${answers.huntBranch}\``, "R"));
  if (answers.baseBranch) gitBits.push(mark(`Base branch: \`${answers.baseBranch}\``, "R"));
  if (answers.fixFrom) gitBits.push(mark(`Cut \`fix/*\` from \`${answers.fixFrom}\``, "R"));
  gitBits.push(mark("Hunters: no git commands. Orchestrator only publishes.", "I"));
  if (answers.terminalBranch) {
    gitBits.push(mark("Hunt branch is **terminal** — do not merge it, do not branch off its tip, do not fight the hook.", "R"));
  }

  const pubBits = [];
  pubBits.push(mark(`PR host: ${answers.prHost || "none"}`, "R"));
  pubBits.push(mark(`Ticket host: ${answers.ticketHost || "none"}`, "R"));
  pubBits.push(mark(`Auto-publish: ${answers.autoPublish ? "on" : "off"}`, "R"));
  pubBits.push(mark(`Ticket tag: \`${tagFor(id.slug)}\``, "I"));
  if (answers.ticketHost === "youtrack" && answers.youtrack) {
    if (answers.youtrack.instance) pubBits.push(mark(`YouTrack instance: ${answers.youtrack.instance}`, "R"));
    if (answers.youtrack.project) pubBits.push(mark(`YouTrack project: ${answers.youtrack.project}`, "R"));
  }
  if (answers.prHost === "gitea" && answers.gitea) {
    if (answers.gitea.instance) pubBits.push(mark(`Gitea instance: ${answers.gitea.instance}`, "R"));
    if (answers.gitea.repo) pubBits.push(mark(`Gitea repo: ${answers.gitea.repo}`, "R"));
  }

  const knowledge = renderTemplate(loadTemplate("knowledge.template.md"), {
    ...vars,
    LAYOUT: bullets(layoutBits),
    COMMANDS: bullets(cmdBits),
    PORTS: bullets(portBits),
    GIT: bullets(gitBits),
    PUBLISH: bullets(pubBits),
    HOUSE_RULES: bullets(answers.houseRules),
    OUT_OF_SEASON: bullets(answers.outOfSeason),
    LESSON_SOURCE: answers.lessonQuery
      ? mark(answers.lessonQuery, "R")
      : mark("No lesson host configured — maintain `lessons.md` by hand or via `bug-hunter-learn`.", "I"),
  });

  const groundLines = (answers.hotSpots || [])
    .filter((k) => GROUNDS[k])
    .map((k) => GROUNDS[k]);
  const profile = renderTemplate(loadTemplate("hunt-profile.template.md"), {
    ...vars,
    GROUNDS: groundLines.length ? groundLines.join("\n") : "_(none confirmed — hunt only what hunt-brief.md names)_",
  });

  const kPath = write(".bug-hunter/knowledge.md", knowledge);
  const pPath = write(".bug-hunter/hunt-profile.md", profile);
  if (!existsSync(join(repo, ".bug-hunter", "hunt-brief.md"))) {
    write(
      ".bug-hunter/hunt-brief.md",
      `# Hunt focus — ${id.name}\n\n<!-- empty = whole profile in season -->\n\n## Focus\n\n`
    );
  }
  const stackPath = write(`${id.slug}-stack.md`, knowledge, { home: true, slug: id.slug });

  const home = homeDir(id.slug);
  mkdirSync(home, { recursive: true });
  if (!existsSync(join(home, "hunted-ledger.md"))) {
    writeFileSync(
      join(home, "hunted-ledger.md"),
      `# Hunted Ledger — ${id.name}\n# <date> | <status: fixed|ticketed|unverified|ledgered> | <package/file> | <one-line> | <PR/ticket>\n`
    );
  }
  if (!existsSync(join(home, "lessons.md"))) {
    const seeds = (answers.notBugs || [])
      .map((r, i) => `## SEED-${i + 1} — onboard\nSource: pinned\nRule: ${r}\nHash: onboard\n`)
      .join("\n");
    writeFileSync(
      join(home, "lessons.md"),
      `# Lessons — anti-patterns the ${id.name} hunter must NOT re-file\n# Last synced: ${date}\n\n${seeds || "_(no lessons yet)_\n"}`
    );
  }

  console.log(`wrote ${kPath}`);
  console.log(`wrote ${pPath}`);
  console.log(`home  ${stackPath}`);
  process.exit(0);
}

die(`unknown command '${cmd || ""}' — expected identity | from-answers`);
