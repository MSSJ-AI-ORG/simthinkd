package simthinkd;

import java.io.DataInputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * SimThink D in-process runtime for Java (no dependencies, Java 8+). Same weights, same request, same answer as the Python
 * decider: the weights come from tools/export_java_weights.py (a header line with the source npz SHA-256, then float32
 * arrays). Thread-safe: predict keeps no shared mutable state except the hashed-feature cache, which is synchronised.
 *
 *   SimThinkD d = SimThinkD.load("ecg_target_v2.smtd");
 *   Map<String, Object> answers = d.predict(requestMap);   // same "answers" block as POST /v1/systemone
 *   int k = d.chooseIndex(requestMap, "attack_target");     // index of the chosen candidate in criteria order
 */
public final class SimThinkD {
    private final float[][] w1, w2;
    private final float[] b1, b2, w3;
    private final float b3;
    private final double temperature;
    public final String sourceSha256;

    private SimThinkD(float[][] w1, float[] b1, float[][] w2, float[] b2, float[] w3, float b3, double temperature, String sha) {
        this.w1 = w1; this.b1 = b1; this.w2 = w2; this.b2 = b2; this.w3 = w3; this.b3 = b3; this.temperature = temperature; this.sourceSha256 = sha;
    }

    @SuppressWarnings("unchecked")
    public static SimThinkD load(String path) throws IOException {
        try (DataInputStream in = new DataInputStream(new FileInputStream(path))) {
            String header = readLine(in);
            if (!header.startsWith("SMTD1 ")) throw new IOException("not a SimThink D Java weights file");
            Map<String, Object> h = (Map<String, Object>) Json.parse(header.substring(6));
            Map<String, float[]> flat = new LinkedHashMap<>();
            Map<String, int[]> shapes = new LinkedHashMap<>();
            for (Object o : (List<Object>) h.get("arrays")) {
                Map<String, Object> a = (Map<String, Object>) o;
                List<Object> sh = (List<Object>) a.get("shape");
                int[] shape = new int[sh.size()];
                int n = 1;
                for (int i = 0; i < shape.length; i++) { shape[i] = ((Number) sh.get(i)).intValue(); n *= shape[i]; }
                byte[] buf = new byte[n * 4];
                in.readFully(buf);
                float[] f = new float[n];
                ByteBuffer.wrap(buf).order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer().get(f);
                flat.put((String) a.get("name"), f);
                shapes.put((String) a.get("name"), shape);
            }
            return new SimThinkD(matrix(flat.get("local.weight"), shapes.get("local.weight")), flat.get("local.bias"),
                    matrix(flat.get("context.weight"), shapes.get("context.weight")), flat.get("context.bias"),
                    flat.get("score.weight"), flat.get("score.bias")[0], ((Number) h.get("temperature")).doubleValue(), (String) h.get("source_sha256"));
        }
    }

    private static String readLine(DataInputStream in) throws IOException {
        java.io.ByteArrayOutputStream b = new java.io.ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1 && c != '\n') b.write(c);
        return new String(b.toByteArray(), StandardCharsets.UTF_8);
    }

    private static float[][] matrix(float[] f, int[] shape) {
        float[][] m = new float[shape[0]][shape[1]];
        for (int i = 0; i < shape[0]; i++) System.arraycopy(f, i * shape[1], m[i], 0, shape[1]);
        return m;
    }

    private static double dot(float[] a, float[] w) {
        double s = 0;
        for (int i = 0; i < a.length; i++) s += a[i] * (double) w[i];
        return s;
    }

    double[] scores(float[][] x) {
        int n = x.length, hd = b1.length;
        float[][] h = new float[n][hd];
        for (int i = 0; i < n; i++) for (int j = 0; j < hd; j++) h[i][j] = (float) Math.max(0, dot(x[i], w1[j]) + b1[j]);
        float[] ctx = new float[2 * hd];
        for (int j = 0; j < hd; j++) {
            double m = 0;
            float mx = Float.NEGATIVE_INFINITY;
            for (int i = 0; i < n; i++) { m += h[i][j]; mx = Math.max(mx, h[i][j]); }
            ctx[j] = (float) (m / n);
            ctx[hd + j] = mx;
        }
        double[] out = new double[n];
        float[] z = new float[hd + 2 * hd];
        for (int i = 0; i < n; i++) {
            System.arraycopy(h[i], 0, z, 0, hd);
            System.arraycopy(ctx, 0, z, hd, 2 * hd);
            double s = b3;
            for (int j = 0; j < b2.length; j++) s += (float) Math.max(0, dot(z, w2[j]) + b2[j]) * (double) w3[j];
            out[i] = s;
        }
        return out;
    }

    private static double[] softmax(double[] v) {
        double mx = Double.NEGATIVE_INFINITY;
        for (double x : v) mx = Math.max(mx, x);
        double[] e = new double[v.length];
        double s = 0;
        for (int i = 0; i < v.length; i++) { e[i] = Math.exp(v[i] - mx); s += e[i]; }
        for (int i = 0; i < v.length; i++) e[i] /= s;
        return e;
    }

    /** The protocol "answers" block (operation, plus "op_target" when targets were offered). */
    public Map<String, Object> predict(Map<String, Object> body) {
        Encoder.Encoded enc = Encoder.encode(body);
        double[] sc = scores(enc.x);
        int nOps = enc.operations.size();
        double[] opScores = new double[nOps];
        List<double[]> cond = new ArrayList<>();
        List<List<Integer>> where = new ArrayList<>();
        for (int g = 0; g < nOps; g++) {
            List<Integer> idx = new ArrayList<>();
            for (int i = 0; i < enc.rows.size(); i++) if (enc.rows.get(i).group == g) idx.add(i);
            double[] s = new double[idx.size()];
            double mx = Double.NEGATIVE_INFINITY;
            for (int k = 0; k < s.length; k++) { s[k] = sc[idx.get(k)] / temperature; mx = Math.max(mx, s[k]); }
            double mean = 0;
            for (double v : s) mean += Math.exp(v - mx);
            opScores[g] = mx + Math.log(mean / s.length);
            cond.add(softmax(s));
            where.add(idx);
        }
        double[] op = softmax(opScores);
        int top = 0;
        for (int g = 1; g < nOps; g++) if (op[g] > op[top]) top = g;
        Map<String, Object> answers = new LinkedHashMap<>();
        Map<String, Object> probs = new LinkedHashMap<>();
        for (int g = 0; g < nOps; g++) probs.put(enc.operations.get(g), op[g]);
        Map<String, Object> opAns = new LinkedHashMap<>();
        opAns.put("choice", enc.operations.get(top));
        opAns.put("probabilities", probs);
        opAns.put("confidence", op[top]);
        answers.put("operation", opAns);
        List<Integer> idx = where.get(top);
        if (enc.rows.get(idx.get(0)).target != null) {
            double[] c = cond.get(top);
            int best = 0;
            for (int k = 1; k < c.length; k++) if (c[k] > c[best]) best = k;
            Map<String, Object> tp = new LinkedHashMap<>();
            for (int k = 0; k < c.length; k++) tp.put(enc.rows.get(idx.get(k)).target, c[k]);
            Map<String, Object> tAns = new LinkedHashMap<>();
            tAns.put("choice", enc.rows.get(idx.get(best)).target);
            tAns.put("probabilities", tp);
            tAns.put("confidence", c[best]);
            answers.put(enc.operations.get(top).toLowerCase(java.util.Locale.ROOT) + "_target", tAns);
        }
        return answers;
    }

    /** Chosen candidate index for a target question (criteria order), or -1 if that question was not answered. */
    @SuppressWarnings("unchecked")
    public int chooseIndex(Map<String, Object> body, String targetHead) {
        Map<String, Object> a = predict(body);
        Object t = a.get(targetHead);
        if (t == null) return -1;
        String choice = (String) ((Map<String, Object>) t).get("choice");
        Map<String, Object> q = (Map<String, Object>) ((Map<String, Object>) body.get("questions")).get(targetHead);
        int i = 0;
        for (String k : ((Map<String, Object>) q.get("criteria")).keySet()) { if (k.equals(choice)) return i; i++; }
        return -1;
    }

    /** Command-line parity driver: reads request JSON lines, prints one JSON answer line each. */
    @SuppressWarnings("unchecked")
    public static void main(String[] args) throws IOException {
        SimThinkD d = load(args[0]);
        java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(System.in, StandardCharsets.UTF_8));
        java.io.PrintStream out = new java.io.PrintStream(System.out, true, "UTF-8");
        String line;
        while ((line = r.readLine()) != null) {
            if (line.trim().isEmpty()) continue;
            long t0 = System.nanoTime();
            Map<String, Object> ans = d.predict((Map<String, Object>) Json.parse(line));
            Map<String, Object> rec = new LinkedHashMap<>(ans);
            rec.put("_ms", (System.nanoTime() - t0) / 1e6);
            out.println(Json.py(rec));
        }
    }
}
