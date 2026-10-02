/**
 * Zero-dependency browser port of simthinkd policy encoder and MLP scorer.
 * Blake2s hashing, feature encoding, and neural network inference with exact parity to Python.
 *
 * Usage:
 *   const policy = new SimThinkD(weightsJSON);
 *   const decision = policy.decide(situationString);
 *   console.log(decision.choice, decision.confidence);
 */

// ============================================================================
// Blake2s — 256-bit hash, 4-byte digest (JS port of hashlib.blake2s)
// ============================================================================

class Blake2s {
  constructor() {
    this.reset();
  }

  reset(outlen = 4) {
    // IV from Blake2s spec; h[0] carries the parameter block (no key, fanout 1, depth 1, digest length).
    this.h = new Uint32Array([
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
      0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ]);
    this.h[0] ^= 0x01010000 ^ outlen;
    this.t = new Uint32Array([0, 0]); // 64-bit counter
    this.buf = new Uint8Array(64);
    this.buflen = 0;
    this.outlen = outlen;
  }

  static IV = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
  ];

  // RFC 7693 message schedule (BLAKE2s uses the first 10 rows).
  static SIGMA = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
    [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
    [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
    [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
    [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
    [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
    [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
    [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
  ];

  static rotateRight(x, n) {
    return ((x >>> n) | (x << (32 - n))) >>> 0;
  }

  static add32(...args) {
    let sum = 0;
    for (const x of args) sum = ((sum + x) >>> 0);
    return sum;
  }

  static mix(a, b, c, d, x, y) {
    a = Blake2s.add32(a, b, x);
    d = Blake2s.rotateRight(a ^ d, 16);
    c = Blake2s.add32(c, d);
    b = Blake2s.rotateRight(b ^ c, 12);
    a = Blake2s.add32(a, b, y);
    d = Blake2s.rotateRight(a ^ d, 8);
    c = Blake2s.add32(c, d);
    b = Blake2s.rotateRight(b ^ c, 7);
    return [a, b, c, d];
  }

  compress(last) {
    const v = new Uint32Array([...this.h, ...Blake2s.IV]);
    v[12] ^= this.t[0];
    v[13] ^= this.t[1];
    if (last) v[14] ^= 0xffffffff;

    const m = new Uint32Array(16);
    for (let i = 0; i < 16; i++) {
      m[i] =
        this.buf[i * 4] |
        (this.buf[i * 4 + 1] << 8) |
        (this.buf[i * 4 + 2] << 16) |
        (this.buf[i * 4 + 3] << 24);
    }

    for (let r = 0; r < 10; r++) {
      const sigma = Blake2s.SIGMA[r];
      const mix = (a, b, c, d, x, y) => {
        const res = Blake2s.mix(v[a], v[b], v[c], v[d], m[x], m[y]);
        [v[a], v[b], v[c], v[d]] = res;
      };
      mix(0, 4, 8, 12, sigma[0], sigma[1]);
      mix(1, 5, 9, 13, sigma[2], sigma[3]);
      mix(2, 6, 10, 14, sigma[4], sigma[5]);
      mix(3, 7, 11, 15, sigma[6], sigma[7]);
      mix(0, 5, 10, 15, sigma[8], sigma[9]);
      mix(1, 6, 11, 12, sigma[10], sigma[11]);
      mix(2, 7, 8, 13, sigma[12], sigma[13]);
      mix(3, 4, 9, 14, sigma[14], sigma[15]);
    }

    for (let i = 0; i < 8; i++) {
      this.h[i] ^= v[i] ^ v[i + 8];
    }
  }

  update(data) {
    if (typeof data === "string") {
      data = new TextEncoder().encode(data);
    }

    // The last block is compressed only in digest(), so a full buffer is flushed only when more data follows.
    for (let i = 0; i < data.length; i++) {
      if (this.buflen === 64) {
        this.t[0] = (this.t[0] + 64) >>> 0;
        if (this.t[0] < 64) this.t[1]++;
        this.compress(false);
        this.buflen = 0;
      }
      this.buf[this.buflen++] = data[i];
    }
    return this;
  }

  digest(len = 32) {
    const buf = new Uint8Array(len);
    const savedBuflen = this.buflen;
    const savedt = new Uint32Array(this.t);
    const savedh = new Uint32Array(this.h);

    this.t[0] = (this.t[0] + this.buflen) >>> 0;
    if (this.t[0] < this.buflen) this.t[1]++;

    while (this.buflen < 64) {
      this.buf[this.buflen++] = 0;
    }
    this.compress(true);

    for (let i = 0; i < len; i++) {
      buf[i] = (this.h[i >> 2] >>> (8 * (i & 3))) & 0xff;
    }

    this.buflen = savedBuflen;
    this.t = savedt;
    this.h = savedh;

    return buf;
  }
}

// ============================================================================
// Tokenization & Feature Extraction
// ============================================================================

function normalize(text) {
  // NFKC normalization and lowercase
  return String(text).normalize("NFKC").toLowerCase();
}

export function tokens(text) {
  // Python: re.findall(r'\w+|[^\w\s]', ...)
  // \w matches Unicode letters, digits, underscore
  // [^\w\s] matches any non-word, non-space character
  const normalized = normalize(text);
  const result = [];
  let current = "";

  for (const char of normalized) {
    if (/[\p{L}\p{N}_]/u.test(char)) {
      // Word character
      current += char;
    } else if (/\s/.test(char)) {
      // Whitespace
      if (current) {
        result.push(current);
        current = "";
      }
    } else {
      // Non-word, non-space (punctuation, etc.)
      if (current) {
        result.push(current);
        current = "";
      }
      result.push(char);
    }
  }
  if (current) result.push(current);
  return result;
}

function blake2sHash(value) {
  const h = new Blake2s();
  h.update(value);
  const digest = h.digest(4); // 4 bytes
  const num =
    digest[0] | (digest[1] << 8) | (digest[2] << 16) | (digest[3] << 24);
  const sign = num & 256 ? 1 : -1;
  return { number: num >>> 0, sign };
}

// Python caches hashed() (lru_cache, 60,000 entries); the same goal/action texts repeat every decision.
const HASH_CACHE = new Map();
const HASH_CACHE_MAX = 60000;

export function hashed(text) {
  const hit = HASH_CACHE.get(text);
  if (hit) return hit;
  const out = hashedUncached(text);
  if (HASH_CACHE.size >= HASH_CACHE_MAX) HASH_CACHE.delete(HASH_CACHE.keys().next().value);
  HASH_CACHE.set(text, out);
  return out;
}

function hashedUncached(text) {
  const toks = tokens(text);
  const features = [];

  // Word features
  for (const t of toks) {
    features.push("w:" + t);
  }

  // Bigram features
  for (let i = 0; i < toks.length - 1; i++) {
    features.push("b:" + toks[i] + " " + toks[i + 1]);
  }

  // Character trigram features
  // Python: for i in range(max(0, len(t)-2)) over code points (not UTF-16 units)
  for (const t of toks) {
    const cp = Array.from(t);
    for (let i = 0; i < Math.max(0, cp.length - 2); i++) {
      features.push("c:" + cp.slice(i, i + 3).join(""));
    }
  }

  // Initialize float32 array (D=192)
  const D = 192;
  const result = new Float32Array(D);

  for (const value of features) {
    const { number, sign } = blake2sHash(value);
    const idx = number % D;
    result[idx] += sign;
  }

  // L2 normalize
  let norm = 0;
  for (const v of result) {
    norm += v * v;
  }
  // Python: result /= max(norm, 1.)
  norm = Math.max(Math.fround(Math.sqrt(norm)), 1);
  for (let i = 0; i < result.length; i++) {
    result[i] /= norm;
  }

  return result;
}

// ============================================================================
// Text serialization & utilities
// ============================================================================

// Python json.dumps(value, ensure_ascii=False, sort_keys=True) with default separators (", " and ": ").
function pyJson(value) {
  if (value === null || value === undefined) return "null";
  if (value === true) return "true";
  if (value === false) return "false";
  if (typeof value === "number") return Number.isFinite(value) ? String(value) : value > 0 ? "Infinity" : value < 0 ? "-Infinity" : "NaN";
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return "[" + value.map(pyJson).join(", ") + "]";
  const keys = Object.keys(value).sort(codePointCompare);
  return "{" + keys.map((k) => JSON.stringify(k) + ": " + pyJson(value[k])).join(", ") + "}";
}

function codePointCompare(a, b) {
  const x = Array.from(a), y = Array.from(b);
  for (let i = 0; i < Math.min(x.length, y.length); i++) {
    const d = x[i].codePointAt(0) - y[i].codePointAt(0);
    if (d) return d;
  }
  return x.length - y.length;
}

function textify(value) {
  if (typeof value === "string") return value;
  return pyJson(value);
}

function withoutIndices(value) {
  if (Array.isArray(value)) {
    const arr = value.map(withoutIndices);
    // Python: sorted(..., key=text) — plain code-point order
    return arr.sort((a, b) => codePointCompare(textify(a), textify(b)));
  }
  if (value && typeof value === "object") {
    const obj = {};
    for (const [k, v] of Object.entries(value)) {
      if (k !== "index") {
        obj[k] = withoutIndices(v);
      }
    }
    return obj;
  }
  return value;
}

// ============================================================================
// Overlap metrics
// ============================================================================

function overlap(a, b) {
  const aTokens = new Set(tokens(a));
  const bTokens = new Set(tokens(b));
  const intersection = new Set([...aTokens].filter((x) => bTokens.has(x)));
  const intersectionSize = intersection.size;
  return [
    intersectionSize / Math.max(aTokens.size, 1),
    intersectionSize / Math.max(bTokens.size, 1),
    // Python: float(bool(str(b)) and str(b).casefold() in str(a).casefold())
    String(b) && String(a).toLowerCase().includes(String(b).toLowerCase())
      ? 1.0
      : 0.0,
  ];
}

function charOverlap(a, b) {
  const grams = (v) => {
    const cp = Array.from(normalize(v));
    const result = new Set();
    for (let i = 0; i < Math.max(0, cp.length - 1); i++) {
      const pair = cp[i] + cp[i + 1];
      if (!/^\s+$/u.test(pair)) result.add(pair);
    }
    return result;
  };

  const aGrams = grams(a);
  const bGrams = grams(b);
  const intersection = new Set(
    [...aGrams].filter((x) => bGrams.has(x))
  );

  return [
    intersection.size / Math.max(aGrams.size, 1),
    intersection.size / Math.max(bGrams.size, 1),
  ];
}

// ============================================================================
// Encoding (exact port of policy.encode)
// ============================================================================

const OPS = [
  "CLICK",
  "TYPE_TEXT",
  "SELECT",
  "WAIT",
  "SCROLL_DOWN",
  "SCROLL_UP",
  "DONE",
  "BLOCKED",
];
const ROLES = [
  "link",
  "button",
  "textbox",
  "searchbox",
  "combobox",
  "checkbox",
  "option",
  "radio",
];

function encode(body) {
  const rows = [];
  const questions = body.questions || {};
  const operationQs = questions.operation || {};
  const operations = Object.keys(operationQs.criteria || {});

  // Build rows
  for (const op of operations) {
    const head = op.toLowerCase() + "_target";
    if (questions[head]) {
      const targets = questions[head].criteria || {};
      for (const [key, value] of Object.entries(targets)) {
        rows.push({
          operation: op,
          target: key,
          head: head,
          group: operations.indexOf(op),
          criterion: value,
        });
      }
    } else {
      rows.push({
        operation: op,
        target: null,
        head: null,
        group: operations.indexOf(op),
        criterion: {
          element: op,
          description: operationQs.criteria[op],
        },
      });
    }
  }

  const instructions = operationQs.instructions || {};
  const goal = textify(instructions.goal || "");
  const state = body.state || {};
  const page = state.page || {};
  const pageText = textify(page.title || "") + "\n" + textify(page.text || "");

  // Shared features
  const history = textify(state.recent_actions || []);
  const context = textify(withoutIndices(state.elements || [])) + "\n" + textify(instructions.rules || "");
  const shared = [hashed(goal), hashed(textify(page)), hashed(history), hashed(context)];

  // Recent actions
  const recent = Array.isArray(state.recent_actions) ? state.recent_actions.filter((a) => typeof a === "object") : [];
  const recentLabels = recent.map((a) => String(a.action || "").trim().toLowerCase());
  const lastChanged = recent.length > 0 && recent[recent.length - 1].page_changed ? 1.0 : 0.0;

  const goalWords = tokens(goal);
  const elements = withoutIndices(state.elements || []);

  // Encode each row
  const features = [];
  for (const row of rows) {
    let criterion = row.criterion;
    if (!criterion || typeof criterion !== "object") {
      criterion = { element: textify(criterion || "") };
    }

    const label = (criterion.element || "").replace(/^\[[^\]]+\]\s*/, "");
    const value = textify(criterion.current_value || "");
    const local = { ...criterion, element: label, operation: row.operation };
    const localText = textify(local);

    // Matching positions in goal
    const matching = new Set(tokens(label + " " + value));
    const positions = [];
    for (let i = 0; i < goalWords.length; i++) {
      if (matching.has(goalWords[i])) positions.push(i);
    }

    const focus = positions
      .map((i) => {
        const start = Math.max(0, i - 3);
        const end = i + 4;
        return goalWords.slice(start, end).join(" ");
      })
      .join(" | ");

    // Numeric features
    const numeric = [];

    // Operation one-hot
    for (const op of OPS) numeric.push(row.operation === op ? 1.0 : 0.0);

    // Role one-hot
    for (const role of ROLES) numeric.push((criterion.role || "") === role ? 1.0 : 0.0);

    // Checked/selected/expanded flags
    for (const key of ["checked", "selected", "expanded"]) {
      for (const flag of ["true", "false"]) {
        numeric.push(String(criterion[key] || "").toLowerCase() === flag ? 1.0 : 0.0);
      }
    }

    // Other numeric features
    numeric.push(value ? 1.0 : 0.0);
    numeric.push(Math.min(rows.length, 100) / 100.0);
    numeric.push(Math.min(positions.length, 20) / 20.0);

    // Overlaps
    numeric.push(...overlap(goal, label));
    numeric.push(...overlap(goal, value));
    numeric.push(...overlap(textify(page), label));
    numeric.push(...overlap(history, label));

    // Character overlaps
    numeric.push(...charOverlap(goal, label));
    numeric.push(...charOverlap(goal, textify(page)));

    // Recency
    const key = label.trim().toLowerCase();
    const seen = [];
    for (let i = 0; i < recentLabels.length; i++) {
      if (recentLabels[i] === key) seen.push(i);
    }

    let distance = null;
    if (seen.length > 0) {
      distance = recentLabels.length - 1 - seen[seen.length - 1];
    }

    numeric.push(distance === null ? 0.0 : 1.0 / (1.0 + distance));
    numeric.push(Math.min(seen.length, 5) / 5.0);
    numeric.push(distance === 0 ? 1.0 : 0.0);
    numeric.push(distance === 0 ? lastChanged : 0.0);
    numeric.push(seen.length >= 2 ? 1.0 : 0.0);
    numeric.push(Math.min(recentLabels.length, 10) / 10.0);

    // Page match
    const pageMatch = [...overlap(goal, pageText), ...charOverlap(goal, pageText)];
    numeric.push(...pageMatch);

    // DONE page match interaction
    const isDone = row.operation === "DONE" ? 1.0 : 0.0;
    for (const v of pageMatch) {
      numeric.push(isDone * v);
    }

    // Concatenate all features
    const localHash = hashed(localText);
    const focusHash = hashed(focus);
    const goalHash = hashed(goal);
    const pageHash = hashed(textify(page));

    // Element-wise product of hashed vectors
    const product1 = new Float32Array(192);
    const product2 = new Float32Array(192);
    const product3 = new Float32Array(192);
    for (let i = 0; i < 192; i++) {
      product1[i] = goalHash[i] * localHash[i];
      product2[i] = goalHash[i] * pageHash[i];
      product3[i] = pageHash[i] * localHash[i];
    }

    // Total size: 192*4 (shared) + 192 (local) + 192 (focus) + 192*3 (products) + numeric
    const allFeatures = new Float32Array(192 * 9 + numeric.length);
    let idx = 0;

    // Shared features (4 * 192)
    for (const sh of shared) {
      for (let i = 0; i < 192; i++) allFeatures[idx++] = sh[i];
    }

    // Local hash (192)
    for (let i = 0; i < 192; i++) allFeatures[idx++] = localHash[i];

    // Focus hash (192)
    for (let i = 0; i < 192; i++) allFeatures[idx++] = focusHash[i];

    // Products (3 * 192)
    for (let i = 0; i < 192; i++) allFeatures[idx++] = product1[i];
    for (let i = 0; i < 192; i++) allFeatures[idx++] = product2[i];
    for (let i = 0; i < 192; i++) allFeatures[idx++] = product3[i];

    // Numeric features
    for (const n of numeric) {
      allFeatures[idx++] = n;
    }

    features.push(allFeatures);
  }

  const groups = new Int32Array(rows.length);
  for (let i = 0; i < rows.length; i++) {
    groups[i] = rows[i].group;
  }

  return { features, groups, rows, operations };
}

function matmul(a, b) {
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    sum += a[i] * b[i];
  }
  return sum;
}

// ============================================================================
// Neural Network: scores and distributions
// ============================================================================

function relu(x) {
  return Math.max(0, x);
}

function softmax(v) {
  const vArray = Array.isArray(v) ? v : Array.from(v);
  const max = Math.max(...vArray);
  const exp = vArray.map((x) => Math.exp(x - max));
  const sum = exp.reduce((a, b) => a + b, 0);
  return exp.map((x) => x / sum);
}

function scores(x, weights) {
  const localWeight = weights["local.weight"]; // [128, 1785]
  const localBias = weights["local.bias"]; // [128]
  const contextWeight = weights["context.weight"]; // [96, 384]
  const contextBias = weights["context.bias"]; // [96]
  const scoreWeight = weights["score.weight"]; // [1, 96]
  const scoreBias = weights["score.bias"]; // [1]

  // First layer: x @ W.T + b, then ReLU
  // x: [num_rows, 1785], W: [128, 1785]
  // result: [num_rows, 128]
  const h = [];
  for (let i = 0; i < x.length; i++) {
    const xi = x[i]; // [1785]
    const hi = new Float32Array(localBias.length);
    for (let j = 0; j < localBias.length; j++) {
      let sum = localBias[j];
      for (let k = 0; k < xi.length; k++) {
        sum += xi[k] * localWeight[j][k];
      }
      hi[j] = relu(sum);
    }
    h.push(hi);
  }

  // Context: mean and max of h across rows
  const meanVec = new Float32Array(localBias.length);
  const maxVec = new Float32Array(localBias.length);
  for (let j = 0; j < localBias.length; j++) {
    let m = 0,
      mx = -Infinity;
    for (const hi of h) {
      m += hi[j];
      mx = Math.max(mx, hi[j]);
    }
    meanVec[j] = m / h.length;
    maxVec[j] = mx;
  }

  const context = new Float32Array(meanVec.length + maxVec.length);
  for (let i = 0; i < meanVec.length; i++) {
    context[i] = meanVec[i];
  }
  for (let i = 0; i < maxVec.length; i++) {
    context[meanVec.length + i] = maxVec[i];
  }

  // Second layer: [h, context] @ W.T + b, then ReLU
  // Concatenated: [num_rows, 128 + 128] = [num_rows, 256]
  // W: [96, 384] (wait, this should match: 256? let me check)
  // Actually context is [256] and we repeat it for each row: [num_rows, 256]
  // W is [96, 384] so input should be [num_rows, 384]
  // h[i] is 128-dim, context is 256-dim = 384 total. Good!

  const z = [];
  for (let i = 0; i < h.length; i++) {
    // Concatenate h[i] and context
    const concat = new Float32Array(h[i].length + context.length);
    for (let j = 0; j < h[i].length; j++) {
      concat[j] = h[i][j];
    }
    for (let j = 0; j < context.length; j++) {
      concat[h[i].length + j] = context[j];
    }

    // z = concat @ W.T + b
    const zi = new Float32Array(contextBias.length);
    for (let j = 0; j < contextBias.length; j++) {
      let sum = contextBias[j];
      for (let k = 0; k < concat.length; k++) {
        sum += concat[k] * contextWeight[j][k];
      }
      zi[j] = relu(sum);
    }
    z.push(zi);
  }

  // Score layer: z @ W.T + b
  // z: [num_rows, 96], W: [1, 96], b: [1]
  // result: [num_rows, 1]
  const result = [];
  for (let i = 0; i < z.length; i++) {
    let sum = scoreBias[0];
    for (let j = 0; j < z[i].length; j++) {
      sum += z[i][j] * scoreWeight[0][j];
    }
    result.push(sum);
  }

  return result;
}

function distributions(scoreVals, groups, temperature = 1.0) {
  const scaledScores = scoreVals.map((s) => s / temperature);

  // Operation scores using logsumexp trick
  const uniqueGroups = [...new Set(groups)].sort((a, b) => a - b);
  const opScores = [];
  const conditional = {};

  for (const g of uniqueGroups) {
    const indices = [];
    for (let i = 0; i < groups.length; i++) {
      if (groups[i] === g) indices.push(i);
    }

    const groupScores = indices.map((i) => scaledScores[i]);
    const max = Math.max(...groupScores);
    const expScores = groupScores.map((s) => Math.exp(s - max));
    const mean = expScores.reduce((a, b) => a + b, 0) / expScores.length;
    const opScore = max + Math.log(mean);

    opScores.push(opScore);
    conditional[g] = softmax(groupScores);
  }

  const op = softmax(opScores);

  // Joint distribution
  const joint = new Float32Array(groups.length);
  for (const [gIdx, g] of uniqueGroups.entries()) {
    const condProbs = conditional[g];
    let condIdx = 0;
    for (let i = 0; i < groups.length; i++) {
      if (groups[i] === g) {
        joint[i] = op[gIdx] * condProbs[condIdx++];
      }
    }
  }

  return { op, conditional, joint, opScores };
}

// ============================================================================
// Main Policy Class
// ============================================================================

export class SimThinkD {
  constructor(weightsJSON) {
    this.meta = weightsJSON;
    this.weights = this.parseWeights(weightsJSON.weights);
    this.temperature = weightsJSON.temperature;
  }

  parseWeights(w) {
    // Each array is {shape, b64}: little-endian float32 bytes, base64 (see tools/export_web_weights.py)
    const flat = (key) => {
      const bin = atob(w[key].b64);
      const bytes = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      return new Float32Array(bytes.buffer);
    };
    const [h, width] = w["local.weight"].shape;
    const [c, cin] = w["context.weight"].shape;
    return {
      "local.weight": this.toMatrix(flat("local.weight"), h, width),
      "local.bias": flat("local.bias"),
      "context.weight": this.toMatrix(flat("context.weight"), c, cin),
      "context.bias": flat("context.bias"),
      "score.weight": this.toMatrix(flat("score.weight"), 1, c),
      "score.bias": flat("score.bias"),
    };
  }

  toMatrix(flat, rows, cols) {
    const result = [];
    for (let i = 0; i < rows; i++) {
      const row = new Float32Array(cols);
      for (let j = 0; j < cols; j++) {
        row[j] = flat[i * cols + j];
      }
      result.push(row);
    }
    return result;
  }

  /** Build the decision request for one situation sentence (same as Python Decider.request). */
  request(situation, { tick = 0, actions = null, goal = null } = {}) {
    actions = actions || this.meta.actions || {};
    return {
      model: this.meta.model,
      state: {
        page: { url: this.meta.url, title: String(this.meta.title || "").replace("{tick}", String(tick)), text: situation },
        elements: Object.keys(actions).map((name) => ({ id: name, role: "button", label: name })),
        recent_actions: [],
      },
      questions: {
        operation: {
          type: "choice",
          criteria: Object.fromEntries(Object.entries(actions).map(([name, why]) => [name, { element: `[button] ${name}`, description: why }])),
          instructions: { goal: goal === null ? this.meta.goal || "" : goal },
        },
      },
    };
  }

  /** Protocol-level call: request in, operation answer out (same as Python Decider.predict). */
  predict(body) {
    const { features, groups, operations } = encode(body);
    const { op } = distributions(scores(features, this.weights), Array.from(groups), this.temperature);
    let best = 0;
    for (let i = 1; i < op.length; i++) if (op[i] > op[best]) best = i;
    const probabilities = Object.fromEntries(operations.map((name, i) => [name, op[i]]));
    return { choice: operations[best], confidence: op[best], probabilities };
  }

  /** One decision for one situation sentence; adds the time taken in ms. */
  decide(situation, options = {}) {
    const body = this.request(situation, options);
    const start = performance.now();
    const answer = this.predict(body);
    return { ...answer, ms: performance.now() - start };
  }
}

// Internals exported for the parity test.
export { encode, scores, distributions };
