"""Turns story.json panels into a pen-drawn silent video (assets/story.mp4) plus timing.json.
Run from the project folder:
  python -I <skill>/scripts/draw.py preview   -> preview.jpg, line art beside colour for every panel
  python -I <skill>/scripts/draw.py           -> full video"""
import json, subprocess, sys, wave
import cv2
import numpy as np

W, H, FPS = 1920, 1080, 30
PAPER = np.array([236, 247, 251], np.float32)  # BGR
BOX = (1560, 850)   # panel fits here, above the caption
TOP = 30
LEAD = 0.45         # page slide, then voice starts

STORY = json.load(open("story.json", encoding="utf8"))
PANELS = STORY["panels"]
TAIL = STORY.get("tail", 2.2)  # hold on the last panel


def wav_len(name):
    with wave.open(f"assets/voice/{name}.wav") as w:
        return w.getnframes() / w.getframerate()


def prepare(panel):
    path = panel.get("image") or STORY["source"]
    # imdecode instead of imread: imread cannot open non-ASCII paths on Windows
    src = cv2.imdecode(np.fromfile(path, np.uint8), cv2.IMREAD_COLOR)
    if src is None:
        sys.exit(f"cannot read image: {path}")
    if panel.get("crop"):
        x0, y0, x1, y1 = panel["crop"]
        src = src[y0:y1, x0:x1]
    p = src
    s = min(BOX[0] / p.shape[1], BOX[1] / p.shape[0])
    big = cv2.resize(p, None, fx=s, fy=s, interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(big, (0, 0), 2.2 * s / 2)
    col = cv2.addWeighted(big, 1.6, blur, -0.6, 0)
    h, w = col.shape[:2]
    ox, oy = (W - w) // 2, TOP + (BOX[1] - h) // 2
    gray = cv2.cvtColor(col, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 40, 9)
    block = int(15 * s) | 1
    ink = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, block, 11)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = st[:, cv2.CC_STAT_AREA] >= int(10 * s * s)
    keep[0] = False
    ink = (keep[lab] * 255).astype(np.uint8)
    soft = cv2.GaussianBlur(ink, (0, 0), 1.0).astype(np.float32)[..., None] / 255
    line = np.tile(PAPER, (h, w, 1)) * (1 - soft) + np.array([52, 44, 42], np.float32) * soft
    return col.astype(np.float32), line.astype(np.float32), ink, ox, oy


def stroke_order(ink):
    cs, _ = cv2.findContours(ink, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    cs = [c[:, 0, :] for c in cs if len(c) >= 14]
    starts = np.array([c[0] for c in cs], np.float32)
    used = np.zeros(len(cs), bool)
    cur = np.array([0, 0], np.float32)
    out = []
    for _ in cs:
        d = ((starts - cur) ** 2).sum(1)
        d[used] = 1e18
        i = int(d.argmin())
        used[i] = True
        out.append(cs[i])
        cur = cs[i][-1].astype(np.float32)
    return out


def zigzag(w, h):
    sp = max(46, min(w, h) // 9)
    pts, y, flip = [], -sp // 2, False
    while y < h + sp:
        pts.append((w + 20, y) if flip else (-20, y))
        pts.append((-20, y + sp // 2) if flip else (w + 20, y + sp // 2))
        y += sp
        flip = not flip
    return np.array(pts, np.int32), sp


def make_pen():
    k = 4
    c = np.zeros((420 * k, 300 * k, 4), np.uint8)
    # nib at (40,380); pen leans up and to the right by 35 degrees
    a = np.radians(35)
    ax = np.array([np.sin(a), -np.cos(a)])
    nr = np.array([np.cos(a), np.sin(a)])
    nib = np.array([40.0, 380.0])
    def quad(d0, d1, w0, w1, color):
        p = [nib + ax * d0 - nr * w0, nib + ax * d0 + nr * w0, nib + ax * d1 + nr * w1, nib + ax * d1 - nr * w1]
        q = (np.array(p) * k).astype(np.int32)
        cv2.fillConvexPoly(c, q, color, cv2.LINE_AA)
        cv2.polylines(c, [q], True, (42, 44, 52, 255), 4 * k, cv2.LINE_AA)
    quad(250, 300, 17, 17, (42, 44, 52, 255))
    quad(44, 252, 18, 18, (250, 250, 250, 255))
    quad(22, 44, 12, 12, (150, 143, 138, 255))
    quad(0, 22, 1.5, 8, (42, 44, 52, 255))
    return cv2.resize(c, None, fx=1 / k, fy=1 / k, interpolation=cv2.INTER_AREA).astype(np.float32), (40, 380)


PEN, PEN_NIB = make_pen()


def put_pen(frame, x, y):
    px, py = int(x) - PEN_NIB[0], int(y) - PEN_NIB[1]
    ph, pw = PEN.shape[:2]
    x0, y0, x1, y1 = max(px, 0), max(py, 0), min(px + pw, W), min(py + ph, H)
    if x0 >= x1 or y0 >= y1:
        return
    sp = PEN[y0 - py:y1 - py, x0 - px:x1 - px]
    a = sp[..., 3:] / 255
    frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - a) + sp[..., :3] * a


def blank():
    return np.tile(PAPER, (H, W, 1))


def draw_panel(emit, prev, panel, dur, first):
    name = panel["name"]
    col, line, ink, ox, oy = prepare(panel)
    h, w = col.shape[:2]
    slide = 0 if first else int(0.4 * FPS)
    for f in range(slide):  # new page slides over the old one
        t = (f + 1) / slide
        t = t * t * (3 - 2 * t)
        x = int(W * (1 - t))
        fr = prev.copy()
        fr[:, x:] = PAPER
        if x > 0:
            sh = min(36, x)
            fr[:, x - sh:x] *= np.linspace(1, 0.72, sh)[None, :, None]
        emit(fr)
    total = int(round(dur * FPS)) - slide
    active = total - (int(TAIL * FPS) if name == PANELS[-1]["name"] else 0)
    n_line = int(active * 0.42)
    n_col = int(active * 0.24)
    strokes = stroke_order(ink)
    pts = sum(len(s) for s in strokes)
    per = max(1, pts // max(1, n_line - 4))
    reveal = np.zeros((h, w), np.uint8)
    canvas = blank()
    pos = np.array([W + 300.0, H + 200.0])
    si, pi = 0, 0
    base = np.tile(PAPER, (h, w, 1))
    for f in range(n_line):
        budget, tip = per, None
        while budget > 0 and si < len(strokes):
            s = strokes[si]
            take = s[pi:pi + budget + 1]
            if len(take) > 1:
                cv2.polylines(reveal, [take.astype(np.int32)], False, 255, 10, cv2.LINE_8)
            tip = take[-1]
            budget -= len(take)
            pi += len(take) - 1
            if pi >= len(s) - 1:
                si, pi = si + 1, 0
        if si >= len(strokes) or f == n_line - 1:
            reveal[:] = 255
        m = reveal[..., None].astype(np.float32) / 255
        canvas[oy:oy + h, ox:ox + w] = base * (1 - m) + line * m
        if tip is not None:
            pos = pos * 0.45 + (np.array([ox + tip[0], oy + tip[1]], float)) * 0.55
        fr = canvas.copy()
        put_pen(fr, *pos)
        emit(fr)
    zig, sp = zigzag(w, h)
    segs = np.linalg.norm(np.diff(zig, axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(segs)])
    paint = np.zeros((h, w), np.uint8)
    last = zig[0].astype(float)
    for f in range(n_col):
        l = cum[-1] * (f + 1) / n_col
        i = min(int(np.searchsorted(cum, l)) - 1, len(segs) - 1)
        i = max(i, 0)
        cur = zig[i] + (zig[i + 1] - zig[i]) * ((l - cum[i]) / segs[i])
        pieces = [last.astype(np.int32)] + [zig[j] for j in range(i + 1) if cum[j] > cum[-1] * f / n_col] + [cur.astype(np.int32)]
        cv2.polylines(paint, [np.array(pieces, np.int32)], False, 255, int(sp * 1.7), cv2.LINE_AA)
        last = cur
        if f == n_col - 1:
            paint[:] = 255
        m = cv2.GaussianBlur(paint, (0, 0), 5).astype(np.float32)[..., None] / 255
        if f == n_col - 1:
            m[:] = 1
        canvas[oy:oy + h, ox:ox + w] = line * (1 - m) + col * m
        pos = pos * 0.45 + np.array([ox + np.clip(cur[0], 0, w), oy + np.clip(cur[1], 0, h)]) * 0.55
        fr = canvas.copy()
        put_pen(fr, *pos)
        emit(fr)
    away = np.array([W + 420.0, H + 150.0])
    for f in range(total - n_line - n_col):
        pos = pos + (away - pos) * 0.22
        fr = canvas.copy()
        put_pen(fr, *pos)
        emit(fr)
    return canvas


def plan():
    t, out = 0.0, []
    for i, p in enumerate(PANELS):
        said = bool(p.get("narration"))
        v = wav_len(p["name"]) if said else 0
        d = max(p.get("min", 3.2), LEAD + v + 0.35)
        if i == len(PANELS) - 1:
            d += TAIL
        out.append({"name": p["name"], "start": round(t, 3), "dur": round(d, 3), "voice": said, "voice_len": round(v, 3),
                    "caption": p.get("caption") or p.get("narration")})
        t += d
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "preview":
        rows = []
        for p in PANELS:
            col, line, *_ = prepare(p)
            sc = 360 / col.shape[0]
            a = cv2.resize(line, None, fx=sc, fy=sc)
            b = cv2.resize(col, None, fx=sc, fy=sc)
            pad = np.full((360, 8, 3), 255, np.float32)
            rows.append(np.hstack([a, pad, b, pad]))
        lines, cur, cw = [], [], 0
        for r in rows:
            if cw + r.shape[1] > 2300 and cur:
                lines.append(cur); cur, cw = [], 0
            cur.append(r); cw += r.shape[1]
        lines.append(cur)
        rs = []
        for l in lines:
            x = np.hstack(l)
            x = np.hstack([x, np.full((360, 2400 - x.shape[1], 3), 255, np.float32)])
            rs.append(x)
        cv2.imwrite("preview.jpg", np.clip(np.vstack(rs), 0, 255).astype(np.uint8))
        sys.exit()
    timing = plan()
    json.dump(timing, open("timing.json", "w", encoding="utf8"), ensure_ascii=False, indent=1)
    ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "assets/story.mp4"], stdin=subprocess.PIPE)
    emit = lambda fr: ff.stdin.write(np.clip(fr, 0, 255).astype(np.uint8).tobytes())
    prev = blank()
    for i, (p, t) in enumerate(zip(PANELS, timing)):
        prev = draw_panel(emit, prev, p, t["dur"], i == 0)
        print(p["name"], t["dur"], flush=True)
    ff.stdin.close()
    ff.wait()
    print("total", timing[-1]["start"] + timing[-1]["dur"])
