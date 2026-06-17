import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

const root = process.cwd();
const read = (path) => readFileSync(join(root, path), "utf8");

test("content detail routes and helpers exist", () => {
  assert.equal(existsSync(join(root, "app/tin-tuc/[id]/page.tsx")), true);
  assert.equal(existsSync(join(root, "app/du-an/[id]/page.tsx")), true);

  const api = read("lib/api.ts");
  assert.match(api, /getArticleDetail/);
  assert.match(api, /getProjectDetail/);
});

test("landing pages link to internal detail routes", () => {
  assert.match(read("app/tin-tuc/page.tsx"), /`\/tin-tuc\/\$\{article\.id\}`/);
  assert.match(read("app/du-an/page.tsx"), /`\/du-an\/\$\{project\.id\}`/);
});

test("detail pages keep Vietnamese accented labels", () => {
  const article = read("app/tin-tuc/[id]/page.tsx");
  const project = read("app/du-an/[id]/page.tsx");

  assert.match(article, /Tin tức/);
  assert.match(article, /Bài viết liên quan/);
  assert.match(project, /Tổng quan/);
  assert.match(project, /Thông tin chi tiết/);
});
