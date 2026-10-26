import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const root = process.cwd();
const read = (path) => readFileSync(join(root, path), "utf8");

test("global theme uses beige surfaces with blue accents", () => {
  const globals = read("app/globals.css");

  assert.match(globals, /--background:\s*#f6efe3;/);
  assert.match(globals, /--card:\s*#fff9ef;/);
  assert.match(globals, /--muted:\s*#ece1d1;/);
  assert.match(globals, /--border:\s*#dfd1bd;/);
  assert.match(globals, /--primary:\s*#8fb7d9;/);
  assert.match(globals, /--primary-hover:\s*#6fa0ca;/);
  assert.match(globals, /--primary-foreground:\s*#244761;/);
  assert.match(globals, /--accent:\s*#244761;/);
  assert.match(globals, /--accent-light:\s*#d7e8f5;/);
});

test("home page hero and CTA avoid the old red orange slate palette", () => {
  const home = read("app/page.tsx");

  assert.doesNotMatch(home, /from-red-400/);
  assert.doesNotMatch(home, /to-orange-300/);
  assert.doesNotMatch(home, /from-slate-900/);
  assert.doesNotMatch(home, /to-slate-800/);
});

test("home page hero keeps dark text on a light low-contrast background", () => {
  const home = read("app/page.tsx");

  assert.match(home, /from-accent-light via-background to-card/);
  assert.match(home, /text-accent\/80/);
  assert.doesNotMatch(home, /from-accent via-primary to-accent-light/);
  assert.doesNotMatch(home, /text-primary-foreground\/75/);
});
