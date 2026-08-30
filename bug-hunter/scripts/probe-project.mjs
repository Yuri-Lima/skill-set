#!/usr/bin/env node
// Scan a repo. Prints JSON. No network. Does not write.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { basename, join, relative } from "node:path";
import { execSync } from "node:child_process";
import {
  findingsFile,
  homeDir,
  parseArgs,
  readIdentity,
  tagFor,
} from "./lib.mjs";

const args = parseArgs(process.argv.slice(2));
const root = args.dir || args._[0] || process.cwd();

function sh(cmd) {
  try {
    return execSync(cmd, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
  } catch {
    return "";
  }
}

function read(rel) {
  const p = join(root, rel);
  if (!existsSync(p)) return null;
  try {
    return readFileSync(p, "utf8");
  } catch {
    return null;
  }
}

function exists(rel) {
  return existsSync(join(root, rel));
}

function listDirs(rel, max = 40) {
  const p = join(root, rel);
  if (!existsSync(p)) return [];
  try {
    return readdirSync(p, { withFileTypes: true })
      .filter((d) => d.isDirectory() && !d.name.startsWith(".") && d.name !== "node_modules")
      .map((d) => join(rel, d.name).replace(/\\/g, "/"))
      .slice(0, max);
  } catch {
    return [];
  }
}

function firstHeading(md) {
  if (!md) return "";
  const m = md.match(/^#\s+(.+)$/m);
  return m ? m[1].trim() : "";
}

function json(rel) {
  const t = read(rel);
  if (!t) return null;
  try {
    return JSON.parse(t);
  } catch {
    return null;
  }
}

function lockfiles() {
  const hits = [];
  if (exists("yarn.lock")) hits.push("yarn");
  if (exists("package-lock.json")) hits.push("npm");
  if (exists("pnpm-lock.yaml")) hits.push("pnpm");
  if (exists("bun.lock") || exists("bun.lockb")) hits.push("bun");
  if (exists("Pipfile.lock") || exists("poetry.lock") || exists("uv.lock")) hits.push("python");
  if (exists("go.sum")) hits.push("go");
  if (exists("Cargo.lock")) hits.push("cargo");
  return hits;
}

function languages() {
  const langs = [];
  if (exists("package.json") || exists("tsconfig.json")) langs.push("javascript/typescript");
  if (exists("pyproject.toml") || exists("requirements.txt") || exists("setup.py")) langs.push("python");
  if (exists("go.mod")) langs.push("go");
  if (exists("Cargo.toml")) langs.push("rust");
  if (exists("Gemfile")) langs.push("ruby");
  if (exists("pom.xml") || exists("build.gradle") || exists("build.gradle.kts")) langs.push("jvm");
  return langs;
}

function portsFromText(text, source) {
  if (!text) return [];
  const out = [];
  const re = /^([A-Z][A-Z0-9_]*(?:PORT|PORT_\w*))\s*=\s*["']?(\d{2,5})["']?/gm;
  let m;
  while ((m = re.exec(text))) {
    out.push({ name: m[1], value: m[2], source });
  }
  const loose = /^([A-Z][A-Z0-9_]*)\s*=\s*["']?(\d{4,5})["']?/gm;
  while ((m = loose.exec(text))) {
    if (/PORT|LISTEN|BIND/i.test(m[1]) && !out.some((p) => p.name === m[1])) {
      out.push({ name: m[1], value: m[2], source });
    }
  }
  return out;
}

function countMatches(pattern, glob) {
  const cmd = `rg -l --glob '${glob}' --glob '!node_modules/**' --glob '!.git/**' --glob '!dist/**' -e '${pattern}' . 2>/dev/null | wc -l`;
  const n = Number(sh(cmd));
  return Number.isFinite(n) ? n : 0;
}

function siblingPlugins() {
  const hints = [];
  for (const dir of ["packages", "plugins", "packages-standalone"]) {
    const kids = listDirs(dir, 80);
    const names = kids.map((k) => basename(k).toLowerCase());
    const shops = names.filter((n) => /shopify|shopware|woocommerce|magento|amazon/.test(n));
    if (shops.length >= 2) hints.push({ dir, siblings: shops });
  }
  return hints;
}

const pkg = json("package.json") || {};
const remote = sh("git remote get-url origin");
const remoteRepo = (remote.match(/[:/]([^/]+\/[^/]+?)(?:\.git)?$/) || [])[1] || "";
const defaultBranch =
  sh("git symbolic-ref --short refs/remotes/origin/HEAD").replace(/^origin\//, "") ||
  sh("git rev-parse --abbrev-ref origin/HEAD").replace(/^origin\//, "") ||
  "";
const currentBranch = sh("git branch --show-current");
const scripts = pkg.scripts && typeof pkg.scripts === "object" ? Object.keys(pkg.scripts) : [];
const workspaces = Array.isArray(pkg.workspaces)
  ? pkg.workspaces
  : pkg.workspaces && pkg.workspaces.packages
    ? pkg.workspaces.packages
    : [];

const envFiles = [".env.example", ".env.sample", ".env.template"]
  .concat(
    ["packages/dev-server/.env.example", "apps/api/.env.example"].filter(exists)
  )
  .filter((f, i, a) => exists(f) && a.indexOf(f) === i);

const ports = envFiles.flatMap((f) => portsFromText(read(f), f));

const identity = readIdentity(root);

const probe = {
  root,
  folder: basename(root),
  packageName: pkg.name || "",
  packageManagerField: pkg.packageManager || "",
  lockfiles: lockfiles(),
  languages: languages(),
  workspaces,
  scripts,
  packages: listDirs("packages").concat(listDirs("apps")),
  readmeTitle: firstHeading(read("README.md")),
  hasAgentsMd: exists("AGENTS.md"),
  hasContributing: exists("CONTRIBUTING.md") || exists("CONTRIBUTING"),
  ci: {
    github: exists(".github/workflows"),
    gitlab: exists(".gitlab-ci.yml"),
    gitea: exists(".gitea"),
    circle: exists(".circleci"),
  },
  remote,
  remoteRepo,
  defaultBranch,
  currentBranch,
  ports,
  skippedTestFiles: countMatches("\\b(xit|xdescribe|it\\.skip|describe\\.skip|test\\.skip)\\b", "*.{js,ts,jsx,tsx,mjs,cjs}"),
  todoFiles: countMatches("\\b(TODO|FIXME)\\b", "*.{js,ts,jsx,tsx,py,go,rs,md}"),
  siblingPlugins: siblingPlugins(),
  hints: {
    monorepo: workspaces.length > 0 || listDirs("packages").length > 1,
    concurrency: countMatches("setInterval\\(|setTimeout\\([^,]+,[^)]+\\)", "*.{js,ts}") > 0,
    money: countMatches("\\b(currency|tax|invoice|skonto|rounding|Decimal)\\b", "*.{js,ts,py}") > 0,
    leaks: countMatches("addEventListener\\(|\\.subscribe\\(", "*.{js,ts}") > 0,
  },
};

if (args.status) {
  const slug = identity ? identity.slug : null;
  const home = slug ? homeDir(slug) : null;
  const status = {
    identity,
    knowledge: exists(".bug-hunter/knowledge.md"),
    profile: exists(".bug-hunter/hunt-profile.md"),
    brief: exists(".bug-hunter/hunt-brief.md"),
    home,
    ledgerLines: 0,
    lessonRules: 0,
    currentBranch,
  };
  if (home && existsSync(join(home, "hunted-ledger.md"))) {
    status.ledgerLines = readFileSync(join(home, "hunted-ledger.md"), "utf8")
      .split("\n")
      .filter((l) => /^\d{4}-\d{2}-\d{2}\s+\|/.test(l)).length;
  }
  if (home && existsSync(join(home, "lessons.md"))) {
    status.lessonRules = (readFileSync(join(home, "lessons.md"), "utf8").match(/^## /gm) || []).length;
  }
  if (identity) {
    status.tag = tagFor(identity.slug);
    status.findings = findingsFile(identity.slug);
  }
  console.log(JSON.stringify(status, null, 2));
  process.exit(0);
}

console.log(JSON.stringify(probe, null, 2));
