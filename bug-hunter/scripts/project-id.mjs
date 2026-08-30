#!/usr/bin/env node
// Suggest display name + slug from a probe. Or validate a slug.
import { parseArgs, slugify, suggestIdentity, validateSlug } from "./lib.mjs";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const args = parseArgs(process.argv.slice(2));

if (args.validate) {
  const slug = args.validate === true ? args._[0] : args.validate;
  const ok = validateSlug(slug);
  console.log(ok ? `ok ${slug}` : `invalid ${slug || ""}`);
  process.exit(ok ? 0 : 1);
}

if (args.slugify) {
  const name = args.slugify === true ? args._.join(" ") : args.slugify;
  const sl = slugify(name);
  console.log(sl);
  process.exit(sl ? 0 : 1);
}

let probe;
if (args.probe) {
  const { readFileSync } = await import("node:fs");
  probe = JSON.parse(readFileSync(args.probe, "utf8"));
} else {
  const raw = execFileSync(process.execPath, [join(here, "probe-project.mjs"), ...(args.dir ? ["--dir", args.dir] : [])], {
    encoding: "utf8",
  });
  probe = JSON.parse(raw);
}

const suggested = suggestIdentity(probe);
console.log(JSON.stringify({ ...suggested, probeHints: { folder: probe.folder, packageName: probe.packageName, readmeTitle: probe.readmeTitle, remoteRepo: probe.remoteRepo } }, null, 2));
