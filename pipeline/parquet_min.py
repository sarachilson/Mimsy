"""Minimal pure-Python Parquet reader for one BYTE_ARRAY column (no pyarrow available). Supports snappy/uncompressed,
data pages v1/v2, PLAIN and dictionary encodings, flat optional columns."""
import struct, sys

class R:
    def __init__(s, b, p=0): s.b, s.p = b, p
    def byte(s): v = s.b[s.p]; s.p += 1; return v
    def varint(s):
        r = sh = 0
        while True:
            c = s.b[s.p]; s.p += 1; r |= (c & 0x7F) << sh
            if c < 0x80: return r
            sh += 7
    def zz(s): v = s.varint(); return (v >> 1) ^ -(v & 1)
    def val(s, t):
        if t in (1, 2): return t == 1
        if t == 3: return s.byte()
        if t in (4, 5, 6): return s.zz()
        if t == 7: s.p += 8; return None
        if t == 8: n = s.varint(); v = s.b[s.p:s.p + n]; s.p += n; return bytes(v)
        if t in (9, 10):
            h = s.byte(); n = h >> 4; et = h & 15
            if n == 15: n = s.varint()
            if et in (1, 2): return [s.byte() == 1 for _ in range(n)]
            return [s.val(et) for _ in range(n)]
        if t == 12: return s.struct()
        raise ValueError(t)
    def struct(s):
        d = {}; fid = 0
        while True:
            h = s.byte()
            if h == 0: return d
            delta = h >> 4; t = h & 15
            fid = fid + delta if delta else s.zz()
            d[fid] = s.val(t)

def snappy(b):
    r = R(b); n = r.varint(); out = bytearray(); p = r.p; L = len(b)
    while p < L:
        c = b[p]; p += 1; t = c & 3
        if t == 0:
            ln = c >> 2
            if ln >= 60:
                k = ln - 59; ln = int.from_bytes(b[p:p + k], "little"); p += k
            ln += 1; out += b[p:p + ln]; p += ln
        else:
            if t == 1: ln = ((c >> 2) & 7) + 4; off = ((c >> 5) << 8) | b[p]; p += 1
            elif t == 2: ln = (c >> 2) + 1; off = b[p] | (b[p + 1] << 8); p += 2
            else: ln = (c >> 2) + 1; off = int.from_bytes(b[p:p + 4], "little"); p += 4
            st = len(out) - off
            if off >= ln: out += out[st:st + ln]
            else:
                for i in range(ln): out.append(out[st + i])
    assert len(out) == n, (len(out), n)
    return bytes(out)

def hybrid(b, bw, count=None):
    """RLE / bit-packed hybrid -> list of ints (whole buffer, or first `count`)."""
    r = R(b); out = []; nb = (bw + 7) // 8; mask = (1 << bw) - 1
    while r.p < len(b) and (count is None or len(out) < count):
        h = r.varint()
        if h & 1:
            ng = h >> 1; nbytes = ng * bw; v = int.from_bytes(b[r.p:r.p + nbytes], "little"); r.p += nbytes
            for i in range(ng * 8): out.append((v >> (i * bw)) & mask)
        else:
            v = int.from_bytes(b[r.p:r.p + nb], "little"); r.p += nb; out.extend([v] * (h >> 1))
    return out if count is None else out[:count]

def plain(b, n=None):
    out = []; p = 0; L = len(b)
    while p < L and (n is None or len(out) < n):
        ln = struct.unpack_from("<I", b, p)[0]; p += 4; out.append(b[p:p + ln]); p += ln
    return out

def meta(path):
    f = open(path, "rb"); f.seek(-8, 2); n = struct.unpack("<I", f.read(4))[0]; f.seek(-8 - n, 2)
    return f, R(f.read(n)).struct()

def column(path, name):
    f, m = meta(path)
    for rg in m[4]:
        for cc in rg[1]:
            cm = cc[3]
            if cm[3][-1].decode() != name: continue
            codec = cm[4]; start = cm.get(11) or cm[9]; f.seek(start); buf = f.read(cm[7]); p = 0; dic = None; got = 0
            dec = (lambda x: x) if codec == 0 else snappy
            assert codec in (0, 1), f"codec {codec} not supported"
            while got < cm[5]:
                r = R(buf, p); h = r.struct(); p = r.p; body = buf[p:p + h[3]]; p += h[3]
                if h[1] == 2: dic = plain(dec(body)); continue
                if h[1] == 0:
                    d = dec(body); nv = h[5][1]; enc = h[5][2]
                    ln = struct.unpack_from("<I", d, 0)[0]; nn = sum(hybrid(d[4:4 + ln], 1, nv)); vals = d[4 + ln:]
                elif h[1] == 3:
                    v2 = h[8]; nv = v2[1]; nn = nv - v2[2]; enc = v2[4]; lv = v2[5] + v2[6]
                    vals = body[lv:]; vals = dec(vals) if v2.get(7, True) else vals
                else: continue
                got += nv
                if enc == 0: yield from plain(vals, nn)
                else: yield from (dic[i] for i in hybrid(vals[1:], vals[0], nn))

if __name__ == "__main__":
    f, m = meta(sys.argv[1])
    print("rows", m[3], "row groups", len(m[4]))
    for cc in m[4][0][1]: cm = cc[3]; print(cm[3], "type", cm[1], "codec", cm[4], "enc", cm[2], "bytes", cm[7])
