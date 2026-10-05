package simthinkd;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Port of simthinkd.policy.encode (feature vector per offered row). Parity with Python is checked by tests/test_java_parity.py. */
final class Encoder {
    static final int D = 192;
    static final String[] OPS = {"CLICK", "TYPE_TEXT", "SELECT", "WAIT", "SCROLL_DOWN", "SCROLL_UP", "DONE", "BLOCKED"};
    static final String[] ROLES = {"link", "button", "textbox", "searchbox", "combobox", "checkbox", "option", "radio"};
    private static final Pattern BRACKET = Pattern.compile("^\\[[^\\]]+\\]\\s*");
    private static final int CACHE_MAX = 60000;
    private static final Map<String, float[]> CACHE = new LinkedHashMap<String, float[]>(1024, 0.75f, true) {
        @Override
        protected boolean removeEldestEntry(Map.Entry<String, float[]> e) { return size() > CACHE_MAX; }
    };

    static final class Row {
        final String operation, target;
        final int group;
        final Object criterion;

        Row(String operation, String target, int group, Object criterion) {
            this.operation = operation; this.target = target; this.group = group; this.criterion = criterion;
        }
    }

    static final class Encoded {
        final float[][] x;
        final List<Row> rows;
        final List<String> operations;

        Encoded(float[][] x, List<Row> rows, List<String> operations) { this.x = x; this.rows = rows; this.operations = operations; }
    }

    private Encoder() { }

    static String lower(String s) { return Normalizer.normalize(s, Normalizer.Form.NFKC).toLowerCase(Locale.ROOT); }

    private static boolean isWord(int cp) {
        if (cp == '_') return true;
        int t = Character.getType(cp);
        return Character.isLetter(cp) || t == Character.DECIMAL_DIGIT_NUMBER || t == Character.LETTER_NUMBER || t == Character.OTHER_NUMBER;
    }

    private static boolean isSpace(int cp) {
        // Python str.isspace(): Unicode White_Space plus the ASCII separators 0x1c-0x1f
        return Character.isWhitespace(cp) || Character.isSpaceChar(cp) || (cp >= 0x1c && cp <= 0x1f) || cp == 0x85;
    }

    /** re.findall(r'\w+|[^\w\s]', NFKC(text).lower()) */
    static List<String> tokens(String text) {
        String s = lower(text);
        List<String> out = new ArrayList<>();
        StringBuilder cur = new StringBuilder();
        for (int i = 0; i < s.length(); ) {
            int cp = s.codePointAt(i);
            i += Character.charCount(cp);
            if (isWord(cp)) { cur.appendCodePoint(cp); continue; }
            if (cur.length() > 0) { out.add(cur.toString()); cur.setLength(0); }
            if (!isSpace(cp)) out.add(new String(Character.toChars(cp)));
        }
        if (cur.length() > 0) out.add(cur.toString());
        return out;
    }

    static float[] hashed(String text) {
        synchronized (CACHE) {
            float[] hit = CACHE.get(text);
            if (hit != null) return hit;
        }
        List<String> w = tokens(text);
        List<String> f = new ArrayList<>();
        for (String t : w) f.add("w:" + t);
        for (int i = 0; i + 1 < w.size(); i++) f.add("b:" + w.get(i) + " " + w.get(i + 1));
        for (String t : w) {
            int[] cps = t.codePoints().toArray();
            for (int i = 0; i < Math.max(0, cps.length - 2); i++) f.add("c:" + new String(cps, i, 3));
        }
        float[] r = new float[D];
        for (String v : f) {
            long n = Blake2s.hash4(v);
            r[(int) (n % D)] += (n & 256) != 0 ? 1f : -1f;
        }
        float ss = 0f;
        for (float v : r) ss += v * v;
        float norm = Math.max((float) Math.sqrt(ss), 1f);
        for (int i = 0; i < D; i++) r[i] = r[i] / norm;
        synchronized (CACHE) { CACHE.put(text, r); }
        return r;
    }

    static String text(Object v) { return v instanceof String ? (String) v : Json.py(v); }

    @SuppressWarnings("unchecked")
    static Object withoutIndices(Object v) {
        if (v instanceof Map) {
            Map<String, Object> m = new LinkedHashMap<>();
            for (Map.Entry<String, Object> e : ((Map<String, Object>) v).entrySet()) if (!e.getKey().equals("index")) m.put(e.getKey(), withoutIndices(e.getValue()));
            return m;
        }
        if (v instanceof List) {
            List<Object> a = new ArrayList<>();
            for (Object x : (List<Object>) v) a.add(withoutIndices(x));
            a.sort((p, q) -> Json.codePointCompare(text(p), text(q)));
            return a;
        }
        return v;
    }

    private static double[] overlap(String a, String b) {
        Set<String> aa = new HashSet<>(tokens(a)), bb = new HashSet<>(tokens(b));
        Set<String> in = new HashSet<>(aa);
        in.retainAll(bb);
        boolean contains = !b.isEmpty() && a.toLowerCase(Locale.ROOT).contains(b.toLowerCase(Locale.ROOT));
        return new double[]{in.size() / (double) Math.max(aa.size(), 1), in.size() / (double) Math.max(bb.size(), 1), contains ? 1 : 0};
    }

    private static Set<String> grams(String v) {
        int[] cps = lower(v).codePoints().toArray();
        Set<String> out = new HashSet<>();
        for (int i = 0; i < Math.max(0, cps.length - 1); i++) {
            if (isSpace(cps[i]) && isSpace(cps[i + 1])) continue;
            out.add(new String(cps, i, 2));
        }
        return out;
    }

    private static double[] charOverlap(String a, String b) {
        Set<String> aa = grams(a), bb = grams(b), in = new HashSet<>(aa);
        in.retainAll(bb);
        return new double[]{in.size() / (double) Math.max(aa.size(), 1), in.size() / (double) Math.max(bb.size(), 1)};
    }

    private static boolean truthy(Object v) {
        if (v == null) return false;
        if (v instanceof Boolean) return (Boolean) v;
        if (v instanceof String) return !((String) v).isEmpty();
        if (v instanceof Number) return ((Number) v).doubleValue() != 0;
        if (v instanceof List) return !((List<?>) v).isEmpty();
        if (v instanceof Map) return !((Map<?, ?>) v).isEmpty();
        return true;
    }

    private static String pyStr(Object v) {
        if (v == null) return "None";
        if (v instanceof Boolean) return ((Boolean) v) ? "True" : "False";
        return v instanceof String ? (String) v : Json.py(v);
    }

    @SuppressWarnings("unchecked")
    static Encoded encode(Map<String, Object> body) {
        Map<String, Object> questions = (Map<String, Object>) body.getOrDefault("questions", new LinkedHashMap<>());
        if (!questions.containsKey("operation")) throw new IllegalArgumentException("This decider answers operation/target questions only");
        Map<String, Object> opQ = (Map<String, Object>) questions.get("operation");
        Map<String, Object> opCrit = (Map<String, Object>) opQ.get("criteria");
        List<String> operations = new ArrayList<>(opCrit.keySet());
        List<Row> rows = new ArrayList<>();
        for (int g = 0; g < operations.size(); g++) {
            String op = operations.get(g);
            String head = op.toLowerCase(Locale.ROOT) + "_target";
            if (questions.containsKey(head)) {
                Map<String, Object> crit = (Map<String, Object>) ((Map<String, Object>) questions.get(head)).get("criteria");
                for (Map.Entry<String, Object> e : crit.entrySet()) rows.add(new Row(op, e.getKey(), g, e.getValue()));
            } else {
                Map<String, Object> c = new LinkedHashMap<>();
                c.put("element", op);
                c.put("description", opCrit.get(op));
                rows.add(new Row(op, null, g, c));
            }
        }
        if (rows.isEmpty() || rows.size() > 1500) throw new IllegalArgumentException("Invalid offered action space");
        Map<String, Object> instr = (Map<String, Object>) opQ.getOrDefault("instructions", new LinkedHashMap<>());
        String goal = text(instr.getOrDefault("goal", ""));
        Map<String, Object> state = (Map<String, Object>) body.get("state");
        Object pageObj = state.getOrDefault("page", new LinkedHashMap<>());
        String page = text(pageObj);
        Object recentObj = state.getOrDefault("recent_actions", new ArrayList<>());
        String history = text(recentObj);
        Map<String, Object> pageState = pageObj instanceof Map ? (Map<String, Object>) pageObj : new LinkedHashMap<>();
        String pageText = text(pageState.getOrDefault("title", "")) + "\n" + text(pageState.getOrDefault("text", ""));
        List<Map<String, Object>> recent = new ArrayList<>();
        if (recentObj instanceof List) for (Object a : (List<Object>) recentObj) if (a instanceof Map) recent.add((Map<String, Object>) a);
        List<String> recentLabels = new ArrayList<>();
        for (Map<String, Object> a : recent) recentLabels.add(pyStr(a.getOrDefault("action", "")).trim().toLowerCase(Locale.ROOT));
        double lastChanged = !recent.isEmpty() && truthy(recent.get(recent.size() - 1).get("page_changed")) ? 1 : 0;
        Object elements = withoutIndices(state.getOrDefault("elements", new ArrayList<>()));
        String context = text(elements) + "\n" + text(instr.getOrDefault("rules", ""));
        float[] gH = hashed(goal), pH = hashed(page);
        float[][] shared = {gH, pH, hashed(history), hashed(context)};
        List<String> goalWords = tokens(goal);
        double[] pm1 = overlap(goal, pageText), pm2 = charOverlap(goal, pageText);
        double[] pageMatch = {pm1[0], pm1[1], pm1[2], pm2[0], pm2[1]};
        float[][] x = new float[rows.size()][];
        for (int ri = 0; ri < rows.size(); ri++) {
            Row row = rows.get(ri);
            Map<String, Object> c;
            if (row.criterion instanceof Map) c = (Map<String, Object>) row.criterion;
            else { c = new LinkedHashMap<>(); c.put("element", text(row.criterion)); }
            Object el = c.getOrDefault("element", "");
            String label = BRACKET.matcher(el instanceof String ? (String) el : text(el)).replaceFirst("");
            String value = text(c.getOrDefault("current_value", ""));
            Map<String, Object> localMap = new LinkedHashMap<>(c);
            localMap.put("element", label);
            localMap.put("operation", row.operation);
            String local = text(localMap);
            Set<String> matching = new HashSet<>(tokens(label + " " + value));
            List<Integer> positions = new ArrayList<>();
            for (int i = 0; i < goalWords.size(); i++) if (matching.contains(goalWords.get(i))) positions.add(i);
            StringBuilder focus = new StringBuilder();
            for (int pi = 0; pi < positions.size(); pi++) {
                int i = positions.get(pi);
                if (pi > 0) focus.append(" | ");
                focus.append(String.join(" ", goalWords.subList(Math.max(0, i - 3), Math.min(goalWords.size(), i + 4))));
            }
            List<Double> num = new ArrayList<>();
            for (String op : OPS) num.add(row.operation.equals(op) ? 1.0 : 0.0);
            for (String role : ROLES) num.add(role.equals(c.get("role")) ? 1.0 : 0.0);
            for (String key : new String[]{"checked", "selected", "expanded"})
                for (String flag : new String[]{"true", "false"}) num.add(pyStr(c.getOrDefault(key, "")).toLowerCase(Locale.ROOT).equals(flag) ? 1.0 : 0.0);
            num.add(value.isEmpty() ? 0.0 : 1.0);
            num.add(Math.min(rows.size(), 100) / 100.0);
            num.add(Math.min(positions.size(), 20) / 20.0);
            for (double[] o : new double[][]{overlap(goal, label), overlap(goal, value), overlap(page, label), overlap(history, label)}) for (double d : o) num.add(d);
            float[] lH = hashed(local);
            for (double[] o : new double[][]{charOverlap(goal, label), charOverlap(goal, page)}) for (double d : o) num.add(d);
            String key = label.trim().toLowerCase(Locale.ROOT);
            int seenCount = 0, lastSeen = -1;
            for (int i = 0; i < recentLabels.size(); i++) if (!recentLabels.get(i).isEmpty() && recentLabels.get(i).equals(key)) { seenCount++; lastSeen = i; }
            Integer distance = lastSeen < 0 ? null : recentLabels.size() - 1 - lastSeen;
            num.add(distance == null ? 0.0 : 1.0 / (1.0 + distance));
            num.add(Math.min(seenCount, 5) / 5.0);
            num.add(distance != null && distance == 0 ? 1.0 : 0.0);
            num.add(distance != null && distance == 0 ? lastChanged : 0.0);
            num.add(seenCount >= 2 ? 1.0 : 0.0);
            num.add(Math.min(recentLabels.size(), 10) / 10.0);
            double isDone = row.operation.equals("DONE") ? 1 : 0;
            for (double v : pageMatch) num.add(v);
            for (double v : pageMatch) num.add(isDone * v);
            float[] fH = hashed(focus.toString());
            float[] out = new float[D * 9 + num.size()];
            int k = 0;
            for (float[] sh : shared) { System.arraycopy(sh, 0, out, k, D); k += D; }
            System.arraycopy(lH, 0, out, k, D); k += D;
            System.arraycopy(fH, 0, out, k, D); k += D;
            for (int i = 0; i < D; i++) out[k++] = gH[i] * lH[i];
            for (int i = 0; i < D; i++) out[k++] = gH[i] * pH[i];
            for (int i = 0; i < D; i++) out[k++] = pH[i] * lH[i];
            for (double d : num) out[k++] = (float) d;
            x[ri] = out;
        }
        return new Encoded(x, rows, operations);
    }
}
