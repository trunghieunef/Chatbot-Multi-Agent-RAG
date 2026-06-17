import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/chatbot/ChatWidget.tsx", import.meta.url),
  "utf8"
);

test("chat panel is centered on mobile and anchored right on desktop", () => {
  const panelClass = source.match(/className="([^"]*fixed[^"]*rounded-2xl[^"]*)"/)?.[1] || "";

  assert.match(panelClass, /\bleft-4\b/);
  assert.match(panelClass, /\bright-4\b/);
  assert.match(panelClass, /\bsm:left-auto\b/);
  assert.match(panelClass, /\bsm:right-6\b/);
});
