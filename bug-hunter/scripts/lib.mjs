// Shared identity + path helpers for the bug-hunter skill.
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export const SLUG_RE = /^[a-z][a-z0-9-]{0,31}$/;

export function slugify(name) {
  const s = String(name || "")
    .trim()
    .toLowerCase()
    .replace(/['"]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
  if (SLUG_RE.test(s)) return s;
  const fallback = s.replace(/-/g, "").slice(0, 32);
  return SLUG_RE.test(fallback) ? fallback : "";
}

export function validateSlug(slug) {
  return SLUG_RE.test(String(slug || ""));
}

export function tagFor(slug) {
  return `by grok_${String(slug).replace(/-/g, "_")}_hunter`;
}

export function homeDir(slug) {
  return join(homedir(), `.${slug}-agents`);
}

export function findingsFile(slug) {
  return `.${slug}-new-findings.md`;
}

export function parseFrontmatter(text) {
  const m = String(text || "").match(/^---\n([\s\S]*?)\n---\n?([\s\S]*)$/);
  if (!m) return { meta: {}, body: String(text || "") };
  const meta = {};
  for (const line of m[1].split("\n")) {
    const i = line.indexOf(":");
    if (i < 1) continue;
    meta[line.slice(0, i).trim()] = line.slice(i + 1).trim();
  }
  return { meta, body: m[2] };
}

export function readIdentity(repoDir) {
  const path = join(repoDir, ".bug-hunter", "identity.md");
  if (!existsSync(path)) return null;
  const { meta } = parseFrontmatter(readFileSync(path, "utf8"));
  const name = meta.name || "";
  const slug = meta.slug || "";
  if (!name || !validateSlug(slug)) return null;
  return { name, slug, path };
}

export function formatIdentity({ name, slug }) {
  const day = new Date().toISOString().slice(0, 10);
  return `---\nname: ${name}\nslug: ${slug}\ncreated: ${day}\n---\n\nDisplay name and hunter slug for this repo. Do not edit the slug after the first hunt — it owns \`~/.${slug}-agents/\`.\n`;
}

export function suggestIdentity(probe) {
  const display = [];
  const add = (v) => {
    const s = String(v || "").trim();
    if (s && !display.includes(s)) display.push(s);
  };
  add(probe.readmeTitle);
  for (const word of String(probe.readmeTitle || "").split(/\s+/)) {
    if (word.length >= 3 && /[A-Za-z]/.test(word)) add(word.replace(/[^A-Za-z0-9.-]/g, ""));
  }
  if (probe.packageName && !probe.packageName.startsWith("@")) add(probe.packageName);
  if (probe.packageName && probe.packageName.includes("/")) {
    add(probe.packageName.split("/").pop());
    add(probe.packageName.split("/")[0].replace(/^@/, ""));
  }
  if (probe.remoteRepo) add(probe.remoteRepo.split("/").pop());
  add(probe.remoteRepo);
  add(probe.folder);
  const slugs = [];
  for (const d of display) {
    const sl = slugify(d);
    if (sl && !slugs.includes(sl)) slugs.push(sl);
  }
  // Prefer a short 2–4 letter form of the first display name when it is one word.
  if (display[0]) {
    const word = display[0].replace(/[^A-Za-z]/g, "");
    if (word.length >= 4) {
      const short = word.slice(0, 3).toLowerCase();
      if (validateSlug(short) && !slugs.includes(short)) slugs.push(short);
    }
  }
  return { displayCandidates: display, slugCandidates: slugs };
}

export function renderTemplate(text, vars) {
  return String(text).replace(/\{\{([A-Z0-9_]+)\}\}/g, (_, k) =>
    Object.prototype.hasOwnProperty.call(vars, k) ? String(vars[k]) : `{{${k}}}`
  );
}

export function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--") {
      out._.push(...argv.slice(i + 1));
      break;
    }
    if (a.startsWith("--")) {
      const eq = a.indexOf("=");
      if (eq > 2) {
        out[a.slice(2, eq)] = a.slice(eq + 1);
      } else {
        const key = a.slice(2);
        const next = argv[i + 1];
        if (next && !next.startsWith("--")) {
          out[key] = next;
          i++;
        } else {
          out[key] = true;
        }
      }
    } else {
      out._.push(a);
    }
  }
  return out;
}
