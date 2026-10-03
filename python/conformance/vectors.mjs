// Runs python/conformance/vectors.json against a JavaScript/TypeScript build of the SDK: vector(fn, args) must give the
// Python reference's output. Used by scenario.mjs and scenario.ts in native mode.
import { readFileSync } from "node:fs";

// 2.0 and 2 are the same number to a model (JavaScript cannot tell them apart): number spellings are not compared.
const ZERO = /(?<![\d.])(-?\d+)\.0(?![\d])/g;

function same(a, b) {
  if (typeof a === "string" && typeof b === "string") return a.replace(ZERO, "$1") === b.replace(ZERO, "$1");
  if (a === undefined) a = null;
  if (b === undefined) b = null;
  if (typeof a === "number" && typeof b === "number") return a === b || Math.abs(a - b) <= 1e-9 * Math.max(1, Math.abs(a), Math.abs(b));
  if (Array.isArray(a) || Array.isArray(b)) {
    return Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((x, i) => same(x, b[i]));
  }
  if (a && b && typeof a === "object" && typeof b === "object") {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return ka.length === kb.length && ka.every((k, i) => k === kb[i] && same(a[k], b[k]));
  }
  return a === b;
}

/** [passed, total, failures] */
export function runVectors(vector, path = new URL("./vectors.json", import.meta.url)) {
  const all = JSON.parse(readFileSync(path, "utf8"));
  const failures = [];
  let passed = 0;
  for (const v of all) {
    let got;
    try { got = vector(v.fn, v.args); } catch (e) { got = "THREW " + (e && e.stack ? e.stack.split("\n").slice(0, 3).join(" | ") : e); }
    if (same(got, v.out)) passed++;
    else failures.push({ fn: v.fn, args: v.args, want: v.out, got });
  }
  return [passed, all.length, failures];
}

/** Prints "vectors: N/N" (stdout) and the first failures (stderr). */
export function reportVectors(vector) {
  const [passed, total, failures] = runVectors(vector);
  console.log("vectors: " + passed + "/" + total);
  for (const f of failures.slice(0, Number(process.env.KINLOOM_VECTOR_FAILURES || 8))) {
    console.error("VECTOR " + f.fn + " " + JSON.stringify(f.args).slice(0, 400) + "\n  want: " + JSON.stringify(f.want).slice(0, 600) +
      "\n  got:  " + JSON.stringify(f.got).slice(0, 600));
  }
}
