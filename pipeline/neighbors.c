// Orthographic neighbourhood metrics (exact) for pseudoword banks.
// Strings are pre-encoded as dense symbol ids (uint8) by the Python side.
// Distance: Levenshtein via Myers/Hyyro bit-parallel algorithm (query length <= 64).
// For each query: OLD-k (mean distance to k closest lexicon words), nearest word
// (smallest distance; ties -> lower lexicon index = higher frequency), Coltheart N
// (# words at distance 1), and # of N that are flagged (e.g. high-frequency).
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static inline int myers(const uint64_t *peq, int m, const uint8_t *t, int n) {
    uint64_t pv = ~0ULL, mv = 0, last = 1ULL << (m - 1);
    int score = m;
    for (int j = 0; j < n; j++) {
        uint64_t eq = peq[t[j]];
        uint64_t xv = eq | mv;
        uint64_t xh = (((eq & pv) + pv) ^ pv) | eq;
        uint64_t ph = mv | ~(xh | pv);
        uint64_t mh = pv & xh;
        if (ph & last) score++;
        else if (mh & last) score--;
        ph = (ph << 1) | 1;
        mh <<= 1;
        pv = mh | ~(xv | ph);
        mv = ph & xv;
    }
    return score;
}

// lexicon: concatenated symbols lex_data, offsets lex_off (n_lex+1), sorted any order;
// len_order: lexicon indices grouped by length; len_start[L]..len_start[L+1] (L up to maxlen)
// flags: per lexicon word (1 = counts toward flagged neighbour count)
void neighbors(
    const uint8_t *q_data, const int64_t *q_off, int n_q,
    const uint8_t *lex_data, const int64_t *lex_off,
    const int32_t *len_order, const int64_t *len_start, int maxlen,
    const uint8_t *flags, int alphabet, int k,
    double *out_old, int32_t *out_nearest, int32_t *out_nearest_d,
    int32_t *out_n1, int32_t *out_n1flag)
{
    #pragma omp parallel for schedule(dynamic, 64)
    for (int qi = 0; qi < n_q; qi++) {
        const uint8_t *q = q_data + q_off[qi];
        int m = (int)(q_off[qi + 1] - q_off[qi]);
        uint64_t *peq = calloc(alphabet, sizeof(uint64_t));
        for (int i = 0; i < m; i++) peq[q[i]] |= 1ULL << i;
        // max-heap of k best distances, kept as simple array (k small)
        int best[64]; int nb = 0; int kth = 1 << 30;
        int nd = 1 << 30, nidx = -1, n1 = 0, n1f = 0;
        for (int step = 0; ; step++) {
            int dl = (step + 1) / 2 * ((step % 2) ? 1 : -1);  // 0, +1, -1, +2, -2, ...
            int adl = dl < 0 ? -dl : dl;
            if (nb == k && adl > kth && adl > 1 && adl > nd) break;
            if (adl > 64) break;
            int L = m + dl;
            if (L < 1 || L > maxlen) {
                if (m - adl < 1 && m + adl > maxlen) break;
                continue;
            }
            for (int64_t p = len_start[L]; p < len_start[L + 1]; p++) {
                int wi = len_order[p];
                int d = myers(peq, m, lex_data + lex_off[wi], L);
                if (d == 1) { n1++; if (flags[wi]) n1f++; }
                if (d < nd || (d == nd && wi < nidx)) { nd = d; nidx = wi; }
                if (nb < k) {
                    best[nb++] = d;
                    if (nb == k) { kth = 0; for (int i = 0; i < k; i++) if (best[i] > kth) kth = best[i]; }
                } else if (d < kth) {
                    for (int i = 0; i < k; i++) if (best[i] == kth) { best[i] = d; break; }
                    kth = 0; for (int i = 0; i < k; i++) if (best[i] > kth) kth = best[i];
                }
            }
        }
        double s = 0; for (int i = 0; i < nb; i++) s += best[i];
        out_old[qi] = nb ? s / nb : -1;
        out_nearest[qi] = nidx; out_nearest_d[qi] = nd;
        out_n1[qi] = n1; out_n1flag[qi] = n1f;
        free(peq);
    }
}
