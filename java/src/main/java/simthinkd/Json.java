package simthinkd;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Minimal JSON for the SimThink D Java runtime: a parser (objects keep key order, like Python dicts) and a writer that
 * reproduces Python's json.dumps(value, ensure_ascii=False, sort_keys=True) byte for byte for the value types the
 * encoder serialises (objects, arrays, strings, booleans, null, integers). Floats are written like Python repr for the
 * common cases; requests normally carry none.
 */
public final class Json {
    private final String s;
    private int i;

    private Json(String s) { this.s = s; }

    public static Object parse(String text) {
        Json p = new Json(text);
        p.ws();
        Object v = p.value();
        p.ws();
        if (p.i != p.s.length()) throw new IllegalArgumentException("trailing data at " + p.i);
        return v;
    }

    private void ws() { while (i < s.length() && Character.isWhitespace(s.charAt(i))) i++; }

    private Object value() {
        char c = s.charAt(i);
        if (c == '{') return object();
        if (c == '[') return array();
        if (c == '"') return string();
        if (s.startsWith("true", i)) { i += 4; return Boolean.TRUE; }
        if (s.startsWith("false", i)) { i += 5; return Boolean.FALSE; }
        if (s.startsWith("null", i)) { i += 4; return null; }
        return number();
    }

    private Map<String, Object> object() {
        Map<String, Object> m = new LinkedHashMap<>();
        i++;
        ws();
        if (s.charAt(i) == '}') { i++; return m; }
        while (true) {
            ws();
            String k = string();
            ws();
            if (s.charAt(i++) != ':') throw new IllegalArgumentException("expected : at " + i);
            ws();
            m.put(k, value());
            ws();
            char c = s.charAt(i++);
            if (c == '}') return m;
            if (c != ',') throw new IllegalArgumentException("expected , at " + i);
        }
    }

    private List<Object> array() {
        List<Object> a = new ArrayList<>();
        i++;
        ws();
        if (s.charAt(i) == ']') { i++; return a; }
        while (true) {
            ws();
            a.add(value());
            ws();
            char c = s.charAt(i++);
            if (c == ']') return a;
            if (c != ',') throw new IllegalArgumentException("expected , at " + i);
        }
    }

    private String string() {
        if (s.charAt(i) != '"') throw new IllegalArgumentException("expected string at " + i);
        i++;
        StringBuilder b = new StringBuilder();
        while (true) {
            char c = s.charAt(i++);
            if (c == '"') return b.toString();
            if (c != '\\') { b.append(c); continue; }
            char e = s.charAt(i++);
            switch (e) {
                case '"': b.append('"'); break;
                case '\\': b.append('\\'); break;
                case '/': b.append('/'); break;
                case 'b': b.append('\b'); break;
                case 'f': b.append('\f'); break;
                case 'n': b.append('\n'); break;
                case 'r': b.append('\r'); break;
                case 't': b.append('\t'); break;
                case 'u': b.append((char) Integer.parseInt(s.substring(i, i + 4), 16)); i += 4; break;
                default: throw new IllegalArgumentException("bad escape at " + i);
            }
        }
    }

    private Object number() {
        int st = i;
        while (i < s.length() && "+-0123456789.eE".indexOf(s.charAt(i)) >= 0) i++;
        String t = s.substring(st, i);
        if (t.indexOf('.') < 0 && t.indexOf('e') < 0 && t.indexOf('E') < 0) return Long.parseLong(t);
        return Double.parseDouble(t);
    }

    /** Python json.dumps(v, ensure_ascii=False, sort_keys=True). */
    public static String py(Object v) {
        StringBuilder b = new StringBuilder();
        write(b, v);
        return b.toString();
    }

    @SuppressWarnings("unchecked")
    private static void write(StringBuilder b, Object v) {
        if (v == null) { b.append("null"); return; }
        if (v instanceof Boolean) { b.append(((Boolean) v) ? "true" : "false"); return; }
        if (v instanceof Long || v instanceof Integer) { b.append(v.toString()); return; }
        if (v instanceof Double || v instanceof Float) { b.append(pyFloat(((Number) v).doubleValue())); return; }
        if (v instanceof String) { str(b, (String) v); return; }
        if (v instanceof List) {
            b.append('[');
            boolean first = true;
            for (Object x : (List<Object>) v) { if (!first) b.append(", "); first = false; write(b, x); }
            b.append(']');
            return;
        }
        Map<String, Object> m = (Map<String, Object>) v;
        List<String> keys = new ArrayList<>(m.keySet());
        keys.sort(Json::codePointCompare);
        b.append('{');
        boolean first = true;
        for (String k : keys) {
            if (!first) b.append(", ");
            first = false;
            str(b, k);
            b.append(": ");
            write(b, m.get(k));
        }
        b.append('}');
    }

    private static String pyFloat(double d) {
        if (Double.isNaN(d)) return "NaN";
        if (Double.isInfinite(d)) return d > 0 ? "Infinity" : "-Infinity";
        if (d == Math.rint(d) && Math.abs(d) < 1e16) return String.format(java.util.Locale.ROOT, "%.1f", d);
        return Double.toString(d);
    }

    private static void str(StringBuilder b, String v) {
        b.append('"');
        for (int k = 0; k < v.length(); k++) {
            char c = v.charAt(k);
            switch (c) {
                case '"': b.append("\\\""); break;
                case '\\': b.append("\\\\"); break;
                case '\n': b.append("\\n"); break;
                case '\r': b.append("\\r"); break;
                case '\t': b.append("\\t"); break;
                case '\b': b.append("\\b"); break;
                case '\f': b.append("\\f"); break;
                default:
                    if (c < 0x20) b.append(String.format("\\u%04x", (int) c));
                    else b.append(c);
            }
        }
        b.append('"');
    }

    /** Python string order (code points), not Java's UTF-16 order. */
    public static int codePointCompare(String a, String b) {
        int ia = 0, ib = 0;
        while (ia < a.length() && ib < b.length()) {
            int ca = a.codePointAt(ia), cb = b.codePointAt(ib);
            if (ca != cb) return Integer.compare(ca, cb);
            ia += Character.charCount(ca);
            ib += Character.charCount(cb);
        }
        return Integer.compare(a.length() - ia, b.length() - ib);
    }
}
