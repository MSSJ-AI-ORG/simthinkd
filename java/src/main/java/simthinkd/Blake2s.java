package simthinkd;

import java.nio.charset.StandardCharsets;

/** BLAKE2s (RFC 7693), unkeyed, short digests — the feature hash of the encoder (Python hashlib.blake2s(digest_size=4)). */
final class Blake2s {
    private static final int[] IV = {0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    private static final int[][] SIGMA = {
        {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15},
        {14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3},
        {11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4},
        {7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8},
        {9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13},
        {2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9},
        {12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11},
        {13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10},
        {6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5},
        {10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0},
    };

    private Blake2s() { }

    /** First 4 digest bytes as an unsigned little-endian number (int.from_bytes(..., 'little')). */
    static long hash4(String value) {
        byte[] data = value.getBytes(StandardCharsets.UTF_8);
        int[] h = IV.clone();
        h[0] ^= 0x01010000 ^ 4;
        long t = 0;
        int off = 0;
        byte[] block = new byte[64];
        // all full blocks except the last one
        while (data.length - off > 64) {
            System.arraycopy(data, off, block, 0, 64);
            t += 64;
            compress(h, block, t, false);
            off += 64;
        }
        int rem = data.length - off;
        java.util.Arrays.fill(block, (byte) 0);
        System.arraycopy(data, off, block, 0, rem);
        t += rem;
        compress(h, block, t, true);
        return h[0] & 0xffffffffL;
    }

    private static void compress(int[] h, byte[] b, long t, boolean last) {
        int[] v = new int[16];
        System.arraycopy(h, 0, v, 0, 8);
        System.arraycopy(IV, 0, v, 8, 8);
        v[12] ^= (int) t;
        v[13] ^= (int) (t >>> 32);
        if (last) v[14] = ~v[14];
        int[] m = new int[16];
        for (int i = 0; i < 16; i++) {
            m[i] = (b[4 * i] & 0xff) | (b[4 * i + 1] & 0xff) << 8 | (b[4 * i + 2] & 0xff) << 16 | (b[4 * i + 3] & 0xff) << 24;
        }
        for (int r = 0; r < 10; r++) {
            int[] s = SIGMA[r];
            g(v, 0, 4, 8, 12, m[s[0]], m[s[1]]);
            g(v, 1, 5, 9, 13, m[s[2]], m[s[3]]);
            g(v, 2, 6, 10, 14, m[s[4]], m[s[5]]);
            g(v, 3, 7, 11, 15, m[s[6]], m[s[7]]);
            g(v, 0, 5, 10, 15, m[s[8]], m[s[9]]);
            g(v, 1, 6, 11, 12, m[s[10]], m[s[11]]);
            g(v, 2, 7, 8, 13, m[s[12]], m[s[13]]);
            g(v, 3, 4, 9, 14, m[s[14]], m[s[15]]);
        }
        for (int i = 0; i < 8; i++) h[i] ^= v[i] ^ v[i + 8];
    }

    private static void g(int[] v, int a, int b, int c, int d, int x, int y) {
        v[a] = v[a] + v[b] + x;
        v[d] = Integer.rotateRight(v[d] ^ v[a], 16);
        v[c] = v[c] + v[d];
        v[b] = Integer.rotateRight(v[b] ^ v[c], 12);
        v[a] = v[a] + v[b] + y;
        v[d] = Integer.rotateRight(v[d] ^ v[a], 8);
        v[c] = v[c] + v[d];
        v[b] = Integer.rotateRight(v[b] ^ v[c], 7);
    }
}
