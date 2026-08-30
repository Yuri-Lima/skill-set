import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { existsSync, mkdtempSync, writeFileSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname } from "node:path";
import {
  findingsFile,
  formatIdentity,
  homeDir,
  parseFrontmatter,
  readIdentity,
  slugify,
  suggestIdentity,
  tagFor,
  validateSlug,
} from "./lib.mjs";

const here = dirname(fileURLToPath(import.meta.url));

describe("slugify / validateSlug", () => {
  it("slugifies a display name", () => {
    assert.equal(slugify("Acme CRM"), "acme-crm");
    assert.equal(slugify("Phoenix"), "phoenix");
  });
  it("rejects empty and illegal slugs", () => {
    assert.equal(validateSlug("phx"), true);
    assert.equal(validateSlug("acme-crm"), true);
    assert.equal(validateSlug("Acme"), false);
    assert.equal(validateSlug(""), false);
    assert.equal(validateSlug("-x"), false);
  });
});

describe("identity owns the namespace", () => {
  it("tag, findings, and home come from the slug", () => {
    assert.equal(tagFor("acme"), "by grok_acme_hunter");
    assert.equal(tagFor("acme-crm"), "by grok_acme_crm_hunter");
    assert.equal(findingsFile("acme"), ".acme-new-findings.md");
    assert.ok(homeDir("acme").endsWith(".acme-agents"));
  });
  it("suggests display names and a short slug", () => {
    const s = suggestIdentity({
      readmeTitle: "Phoenix ERP",
      packageName: "@phoenix/app",
      remoteRepo: "PHXGMBH/phoenix",
      folder: "bug-hunter-YL",
    });
    assert.ok(s.displayCandidates.includes("Phoenix ERP"));
    assert.ok(s.slugCandidates.includes("phoenix") || s.slugCandidates.includes("phx"));
  });
});

describe("identity file", () => {
  it("round-trips name and slug", () => {
    const dir = mkdtempSync(join(tmpdir(), "bh-id-"));
    try {
      mkdirSync(join(dir, ".bug-hunter"));
      writeFileSync(join(dir, ".bug-hunter", "identity.md"), formatIdentity({ name: "Acme CRM", slug: "acme" }));
      const id = readIdentity(dir);
      assert.equal(id.name, "Acme CRM");
      assert.equal(id.slug, "acme");
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("write-knowledge identity is blocking", () => {
  it("refuses from-answers without identity", () => {
    const dir = mkdtempSync(join(tmpdir(), "bh-no-id-"));
    try {
      let code = 0;
      try {
        execFileSync(process.execPath, [join(here, "write-knowledge.mjs"), "from-answers", "--dir", dir, "--answers", "/dev/null"], {
          encoding: "utf8",
          stdio: ["ignore", "pipe", "pipe"],
        });
      } catch (e) {
        code = e.status;
      }
      assert.notEqual(code, 0);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
  it("writes identity.md only", () => {
    const dir = mkdtempSync(join(tmpdir(), "bh-idw-"));
    try {
      execFileSync(process.execPath, [join(here, "write-knowledge.mjs"), "identity", "--dir", dir, "--name", "Acme CRM", "--slug", "acme"], {
        encoding: "utf8",
        env: { ...process.env, HOME: dir },
      });
      const text = readFileSync(join(dir, ".bug-hunter", "identity.md"), "utf8");
      const { meta } = parseFrontmatter(text);
      assert.equal(meta.name, "Acme CRM");
      assert.equal(meta.slug, "acme");
      assert.equal(existsSync(join(dir, ".bug-hunter", "knowledge.md")), false);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("hunt profile omits unconfirmed grounds", () => {
  it("does not add money when hotSpots omit it", () => {
    const dir = mkdtempSync(join(tmpdir(), "bh-ans-"));
    try {
      const env = { ...process.env, HOME: dir };
      execFileSync(process.execPath, [join(here, "write-knowledge.mjs"), "identity", "--dir", dir, "--name", "Acme CRM", "--slug", "acme"], { env });
      const answers = join(dir, "answers.json");
      writeFileSync(
        answers,
        JSON.stringify({
          packageManager: "npm",
          hotSpots: ["skipped-tests", "leaks"],
          prHost: "none",
          ticketHost: "none",
        })
      );
      execFileSync(process.execPath, [join(here, "write-knowledge.mjs"), "from-answers", "--dir", dir, "--answers", answers], { env });
      const profile = readFileSync(join(dir, ".bug-hunter", "hunt-profile.md"), "utf8");
      assert.match(profile, /skipped\/disabled/);
      assert.doesNotMatch(profile, /rounding|currency|invoice/);
      const knowledge = readFileSync(join(dir, ".bug-hunter", "knowledge.md"), "utf8");
      assert.match(knowledge, /Acme CRM/);
      assert.match(knowledge, /by grok_acme_hunter/);
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("prompts are generic", () => {
  it("orchestrator and hunter do not name a product or host", () => {
    const orch = readFileSync(join(here, "..", "references", "orchestrator.md"), "utf8");
    const hunter = readFileSync(join(here, "..", "references", "hunter.md"), "utf8");
    for (const text of [orch, hunter]) {
      assert.doesNotMatch(text, /Phoenix/);
      assert.doesNotMatch(text, /YouTrack/);
      assert.doesNotMatch(text, /Gitea/);
      assert.doesNotMatch(text, /yarn only/i);
    }
  });
});

describe("probe fixture", () => {
  it("sees a yarn monorepo", () => {
    const fixture = join(here, "..", "evals", "fixtures", "scan-node-monorepo");
    const raw = execFileSync(process.execPath, [join(here, "probe-project.mjs"), "--dir", fixture], { encoding: "utf8" });
    const probe = JSON.parse(raw);
    assert.ok(probe.lockfiles.includes("yarn"));
    assert.ok(probe.workspaces.length > 0);
    assert.equal(probe.packageName, "scan-demo");
  });
});
