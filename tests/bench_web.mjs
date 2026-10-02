// Time the JavaScript decider on the 1,050 recorded Doom states (each state new to the cache), one at a time.
// node tests/bench_web.mjs
import fs from "fs";
import { SimThinkD } from "../web/simthinkd.js";
const d = new SimThinkD(JSON.parse(fs.readFileSync(new URL("../web/weights/doom-defend.json", import.meta.url), "utf8")));
const rows = JSON.parse(fs.readFileSync(new URL("../src/simthinkd/data/doom_defend_states.json", import.meta.url), "utf8")).rows;
for (const r of rows.slice(0, 20)) d.predict(r.body);
const t = [];
let agree = 0;
for (const r of rows) {
  const s = performance.now();
  const a = d.predict(r.body);
  t.push(performance.now() - s);
  agree += a.choice === r.teacher;
}
t.sort((a, b) => a - b);
console.log(JSON.stringify({ states: rows.length, p50_ms: +t[t.length >> 1].toFixed(3), p95_ms: +t[Math.floor(t.length * 0.95)].toFixed(3),
  within_one_tick: t.filter((x) => x <= 1000 / 35).length / t.length, teacher_agreement: +(agree / rows.length).toFixed(4) }));
