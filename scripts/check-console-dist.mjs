import { createHash } from "node:crypto";
import { mkdtempSync, readdirSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, relative, resolve } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repo = resolve(fileURLToPath(new URL("..", import.meta.url)));
const committed = join(repo, "server", "web", "console-dist");
const scratch = mkdtempSync(join(tmpdir(), "agentmate-console-dist-"));
const generated = join(scratch, "dist");

function snapshot(root) {
  const files = [];
  function walk(directory) {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const path = join(directory, entry.name);
      if (entry.isDirectory()) walk(path);
      else if (entry.isFile()) {
        files.push([
          relative(root, path).replaceAll("\\", "/"),
          createHash("sha256").update(readFileSync(path)).digest("hex"),
        ]);
      }
    }
  }
  walk(root);
  return files.sort(([left], [right]) => left.localeCompare(right));
}

try {
  const vite = join(repo, "node_modules", "vite", "bin", "vite.js");
  const result = spawnSync(
    process.execPath,
    [vite, "build", "--config", join(repo, "vite.console.config.ts"), "--outDir", generated],
    { cwd: repo, stdio: "inherit" },
  );
  if (result.status !== 0) process.exit(result.status ?? 1);

  const expected = snapshot(generated);
  const actual = snapshot(committed);
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    const actualMap = new Map(actual);
    const expectedMap = new Map(expected);
    const changed = [...new Set([...actualMap.keys(), ...expectedMap.keys()])]
      .filter((name) => actualMap.get(name) !== expectedMap.get(name));
    console.error("Console dist is stale. Run `pnpm build:console` and commit the generated files.");
    for (const name of changed.slice(0, 30)) console.error(`- ${name}`);
    process.exitCode = 1;
  } else {
    console.log(`Console dist matches source (${actual.length} files).`);
  }
} finally {
  rmSync(scratch, { recursive: true, force: true });
}
