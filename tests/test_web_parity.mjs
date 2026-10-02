// Runs the JavaScript decider on the cases written by test_web_parity.py and compares with the Python answers.
// node tests/test_web_parity.mjs tests/.parity-data/cases.json
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { SimThinkD } from "../web/simthinkd.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const cases = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const deciders = {};
for (const name of ["doom-defend", "doom-corridor"]) {
  deciders[name] = new SimThinkD(JSON.parse(fs.readFileSync(path.join(root, "web", "weights", `${name}.json`), "utf8")));
}
let same = 0, maxDiff = 0, worst = null;
const mismatches = [];
for (const [i, c] of cases.entries()) {
  const js = deciders[c.preset].predict(c.body);
  if (js.choice === c.python.choice) same++;
  else mismatches.push({ i, js: js.choice, py: c.python.choice });
  for (const [k, p] of Object.entries(c.python.probabilities)) {
    const d = Math.abs(p - js.probabilities[k]);
    if (d > maxDiff) { maxDiff = d; worst = i; }
  }
}
console.log(JSON.stringify({ cases: cases.length, same_choice: same, max_probability_difference: maxDiff, worst_case: worst,
  mismatches: mismatches.slice(0, 10) }));
process.exit(same === cases.length ? 0 : 1);
