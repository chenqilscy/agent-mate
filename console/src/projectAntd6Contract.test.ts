import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const projectSources = [
  "pages/ProjectDetailPage.tsx",
  "components/project/ProjectWorkspace.tsx",
  "components/project/WorkItemExecution.tsx",
].map((relativePath) => ({
  relativePath,
  source: readFileSync(
    fileURLToPath(new URL(relativePath, import.meta.url)),
    "utf8",
  ),
}));

describe("Console project Ant Design 6 contract", () => {
  it("does not use removed List or InputNumber addon APIs", () => {
    for (const { relativePath, source } of projectSources) {
      expect(source, relativePath).not.toMatch(/\baddonAfter\s*=/);
      expect(source, relativePath).not.toMatch(
        /import\s*\{[^}]*\bList\b[^}]*\}\s*from\s*["']antd["']/s,
      );
    }
    expect(projectSources[2].source).toContain("CompatList as List");
  });

  it("uses Timeline item content instead of deprecated children", () => {
    for (const { relativePath, source } of projectSources) {
      for (const timeline of source.match(/<Timeline\b[\s\S]*?\/>/g) || []) {
        expect(timeline, relativePath).not.toMatch(/\bchildren\s*:/);
      }
    }
  });
});
