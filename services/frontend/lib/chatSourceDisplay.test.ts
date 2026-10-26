import assert from "node:assert/strict";
import test from "node:test";

import {
  getListingSourceDetails,
  getSourceKind,
  getSourceTitle,
  getMarketSourceSummary,
} from "./chatSourceDisplay.ts";
import type { ChatSource } from "./types";

test("classifies grounded legal article sources by domain", () => {
  const source: ChatSource = {
    type: "article",
    domain: "legal",
    title: "Dieu kien chuyen nhuong",
  };

  assert.equal(getSourceKind(source), "legal");
  assert.equal(getSourceTitle(source), "Dieu kien chuyen nhuong");
});

test("classifies grounded market metric sources as market data", () => {
  const source: ChatSource = {
    type: "market_metric",
    domain: "market",
    metadata: { metric: "avg_price_per_m2", value: 64, unit: "million VND/m2" },
  };

  assert.equal(getSourceKind(source), "market");
  assert.equal(getMarketSourceSummary(source), "avg_price_per_m2: 64 million VND/m2");
});

test("keeps zero-valued market metric values", () => {
  const source: ChatSource = {
    type: "market_metric",
    domain: "market",
    metadata: { metric: "sample_count", value: 0, unit: "records" },
  };

  assert.equal(getMarketSourceSummary(source), "sample_count: 0 records");
});

test("reads listing price and area from grounded metadata fallback", () => {
  const source: ChatSource = {
    type: "listing",
    domain: "property",
    metadata: { price_text: "4.8 ty", area_text: "75 m2" },
  };

  assert.deepEqual(getListingSourceDetails(source), ["4.8 ty", "75 m2"]);
});
