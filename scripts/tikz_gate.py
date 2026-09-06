#!/usr/bin/env python3
"""tikz-geometry-gate: cong duyet hinh hoc cho hinh TikZ/PDF.

Doc hinh hoc THAT tu PDF content stream (khong dung anh, khong dung vision),
phat hien 6 nhom loi bo cuc va tra exit code != 0 khi fail.

Checks:
  G1 edge-through-block   mui ten xuyen/de len block khong phai dau mut
  G2 label-block-straddle nhan chong len vien block (khong phai nhan cua block)
  G3 label-label-overlap  hai nhan chong nhau
  G4 out-of-bounds        phan tu tran khoi trang / vung noi dung
  G5 tiny-text            chu nho hon san (mac dinh 6pt)
  G6 label-edge-clash     nhan de len than mui ten (khong co mask trang)

Usage:
  tikz_gate.py <file.pdf> [--json] [--min-font 6] [--eps 6] [--page 0]
                          [--annotate out.png] [--strict]
Exit: 0 pass, 1 co loi, 2 loi dung tool.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field, asdict

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union

# ---- nguong mac dinh (pt) --------------------------------------------------
ARROWHEAD_MAX = 12.0     # canh toi da cua tam giac dau mui ten
BLOCK_MIN_AREA = 400.0   # dien tich toi thieu de coi la block
ENDPOINT_EPS = 6.0       # ban kinh bo qua quanh dau mut edge
THROUGH_MIN_LEN = 2.0    # do dai toi thieu nam trong block moi bao loi
LABEL_PAD = 0.5          # noi long bbox chu (chong false positive do hinting)
MIN_FONT = 6.0
EDGE_CLASH_MIN = 1.0     # dien tich giao toi thieu label-edge
SUBSCRIPT_MAX_CHARS = 4  # sub/superscript hop le toi da may ky tu
SCRIPT_SIZE_RATIO = 0.85  # span nho <= 85% span goc -> coi la sub/superscript
SUBSCRIPT_FLOOR_RATIO = 0.55  # sub nho hon 55% body font -> teo that, bao loi
MASK_COVER_RATIO = 0.75  # mask che >=75% dien tich nhan -> coi la co mask


@dataclass
class Finding:
    code: str
    severity: str
    message: str
    evidence: dict = field(default_factory=dict)
    fixes: list = field(default_factory=list)


@dataclass
class Elem:
    kind: str            # block | boundary | edge | arrowhead | mask
    bbox: tuple
    geom: object = None  # shapely
    dashed: bool = False
    poly: list = field(default_factory=list)  # diem cho edge
    zorder: int = -1     # thu tu ve trong content stream (nho = ve truoc)


def _r(v, n=1):
    return round(float(v), n)


def _bbox_tuple(rect):
    return (_r(rect.x0), _r(rect.y0), _r(rect.x1), _r(rect.y1))


def _flatten_items(items):
    """Tra ve danh sach polyline (list diem) tu drawing items."""
    lines = []
    cur = []
    for it in items:
        op = it[0]
        if op == "l":
            p, q = it[1], it[2]
            if cur and (abs(cur[-1][0] - p.x) > 0.01 or abs(cur[-1][1] - p.y) > 0.01):
                if len(cur) >= 2:
                    lines.append(cur)
                cur = []
            if not cur:
                cur.append((p.x, p.y))
            cur.append((q.x, q.y))
        elif op == "c":
            # Bezier -> lay 4 diem control lam xap xi
            pts = [(it[i].x, it[i].y) for i in range(1, 5)]
            if not cur:
                cur = [pts[0]]
            cur.extend(pts[1:])
        elif op == "re":
            r = it[1]
            lines.append([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1), (r.x0, r.y0)])
        elif op == "qu":
            q = it[1]
            pts = [(p.x, p.y) for p in (q.ul, q.ur, q.lr, q.ll, q.ul)]
            lines.append(pts)
    if len(cur) >= 2:
        lines.append(cur)
    return lines


def classify(page, block_min_area=BLOCK_MIN_AREA, arrowhead_max=ARROWHEAD_MAX):
    """Phan loai drawing thanh block / boundary / edge / arrowhead / mask."""
    blocks, boundaries, edges, heads, masks = [], [], [], [], []
    for zi, d in enumerate(page.get_drawings()):
        r = d["rect"]
        w, h = r.width, r.height
        area = w * h
        dashes = d.get("dashes") or ""
        dashed = bool(dashes) and dashes.strip() not in ("", "[] 0")
        typ = d["type"]
        polys = _flatten_items(d["items"])

        # dau mui ten: fill nho, khong stroke
        if typ == "f" and max(w, h) <= arrowhead_max:
            heads.append(Elem("arrowhead", _bbox_tuple(r), box(r.x0, r.y0, r.x1, r.y1),
                                zorder=zi))
            continue

        # mask trang phia sau nhan (fill trang, chi 1 re)
        fill = d.get("fill")
        is_white = fill is not None and all(c > 0.95 for c in fill)
        if typ == "f" and is_white:
            masks.append(Elem("mask", _bbox_tuple(r), box(r.x0, r.y0, r.x1, r.y1),
                               zorder=zi))
            continue

        # block: co fill (f/fs) va du to
        if typ in ("f", "fs") and area >= block_min_area:
            e = Elem("boundary" if dashed else "block", _bbox_tuple(r),
                     box(r.x0, r.y0, r.x1, r.y1), dashed=dashed, zorder=zi)
            (boundaries if dashed else blocks).append(e)
            continue

        # edge: stroke-only
        if typ == "s":
            for pl in polys:
                if len(pl) < 2:
                    continue
                try:
                    ls = LineString(pl)
                except Exception:
                    continue
                if ls.length < 1.0:
                    continue
                edges.append(Elem("edge", _bbox_tuple(r), ls, dashed=dashed,
                                  poly=[(_r(x), _r(y)) for x, y in pl],
                                  zorder=zi))
            continue

        # fs nho: coi la block nho van kiem
        if typ == "fs":
            e = Elem("boundary" if dashed else "block", _bbox_tuple(r),
                     box(r.x0, r.y0, r.x1, r.y1), dashed=dashed, zorder=zi)
            (boundaries if dashed else blocks).append(e)

    return blocks, boundaries, edges, heads, masks


def text_spans(page, pad=LABEL_PAD):
    out = []
    raw = page.get_text("rawdict")
    for blk in raw["blocks"]:
        if blk.get("type") != 0:
            continue
        for ln in blk.get("lines", []):
            for sp in ln.get("spans", []):
                txt = "".join(c.get("c", "") for c in sp.get("chars", []))
                if not txt.strip():
                    continue
                b = sp["bbox"]
                out.append({
                    "text": txt,
                    "size": float(sp.get("size", 0)),
                    "font": sp.get("font", ""),
                    "bbox": (_r(b[0]), _r(b[1]), _r(b[2]), _r(b[3])),
                    "geom": box(b[0] + pad, b[1] + pad, b[2] - pad, b[3] - pad),
                })
    return out


# ---- checks ---------------------------------------------------------------

def check_edge_through_block(edges, blocks, eps=ENDPOINT_EPS,
                             min_len=THROUGH_MIN_LEN):
    """G1: mui ten xuyen than block.

    Mui ten hop le luon bat dau/ket thuc o VIEN block, nen phan giao chi nam
    trong ban kinh eps quanh dau mut. Giao o giua than edge = loi.
    """
    out = []
    for ei, e in enumerate(edges):
        ls = e.geom
        p0, p1 = Point(ls.coords[0]), Point(ls.coords[-1])
        for bi, b in enumerate(blocks):
            inter = ls.intersection(b.geom)
            if inter.is_empty:
                continue
            segs = [inter] if inter.geom_type == "LineString" else list(
                getattr(inter, "geoms", []))
            for s in segs:
                if s.geom_type != "LineString" or s.length < min_len:
                    continue
                # bo qua neu toan bo phan giao gan dau mut
                if max(p0.distance(s), p1.distance(s)) < 1e-9:
                    mid = s.interpolate(0.5, normalized=True)
                    if min(p0.distance(mid), p1.distance(mid)) <= eps:
                        continue
                mid = s.interpolate(0.5, normalized=True)
                if min(p0.distance(mid), p1.distance(mid)) <= eps:
                    continue
                out.append(Finding(
                    "G1/edge-through-block", "error",
                    f"mui ten #{ei} xuyen qua block #{bi} "
                    f"({s.length:.1f}pt nam trong block, xa dau mut "
                    f"{min(p0.distance(mid), p1.distance(mid)):.1f}pt)",
                    {"edgeIndex": ei, "blockIndex": bi,
                     "blockBbox": b.bbox, "edgePoly": e.poly[:8],
                     "insideLengthPt": _r(s.length),
                     "midPoint": [_r(mid.x), _r(mid.y)]},
                    ["doi lai duong di (via/bend) de vong ngoai block",
                     "doi vi tri block", "doi fromSide/toSide cua mui ten"]))
                break
    return out


def check_label_block(spans, blocks):
    """G2: nhan chong vien block (mot phan trong, mot phan ngoai)."""
    out = []
    for si, sp in enumerate(spans):
        for bi, b in enumerate(blocks):
            g = sp["geom"]
            if not g.intersects(b.geom):
                continue
            if b.geom.contains(g):
                continue  # nhan cua chinh block -> hop le
            inter = g.intersection(b.geom).area
            if inter <= 0.5:
                continue
            frac = inter / max(g.area, 1e-9)
            out.append(Finding(
                "G2/label-block-straddle", "error",
                f"nhan {sp['text'][:28]!r} chong vien block #{bi} "
                f"({frac*100:.0f}% dien tich nhan nam trong block)",
                {"spanIndex": si, "text": sp["text"], "labelBbox": sp["bbox"],
                 "blockIndex": bi, "blockBbox": b.bbox,
                 "overlapFraction": _r(frac, 3)},
                ["day nhan ra ngoai block", "dat nhan o giua doan khac",
                 "them mask trang phia sau nhan"]))
    return out


_ACCENT_CHARS = set(
    "\u0300\u0301\u0302\u0303\u0304\u0306\u0307\u0308\u030a\u030b\u030c"
    "\u0323\u0327\u031b"          # dot below, cedilla, horn (tieng Viet)
    "\u02c6\u02c7\u02d8\u02d9\u02da\u02dc\u00b4\u0060"  # dang spacing (TeX)
)


def _is_accent_pair(ta: str, tb: str) -> bool:
    """Dau phu chong ky tu goc la HOP LE, khong phai loi bo cuc.

    TeX ve x-hat (\\hat{x}) va nhieu chu Viet bang cach dat dau LEN TREN
    ky tu goc, nen hai span co bbox chong nhau gan hoan toan. Truong hop nay
    phai bo qua, neu khong gate se bao loi o moi cong thuc va moi chu co dau.
    """
    for a, b in ((ta, tb), (tb, ta)):
        s = a.strip()
        if s and len(s) <= 2 and all(c in _ACCENT_CHARS for c in s):
            return True
    return False


def _is_script_pair(a: dict, b: dict) -> bool:
    """Subscript/superscript ke sat ky tu goc la HOP LE.

    R_t, B_t, lambda^B: span chi so nho hon ro ret va nam ngay canh (hoac
    hoi chong) span goc. Chi coi la hop le khi span nho ngan (<= 3 ky tu) va
    nho hon span kia mot ti le ro rang.
    """
    small, big = (a, b) if a["size"] <= b["size"] else (b, a)
    if small["size"] <= 0 or big["size"] <= 0:
        return False
    if small["size"] / big["size"] > SCRIPT_SIZE_RATIO:
        return False
    if len(small["text"].strip()) > SUBSCRIPT_MAX_CHARS:
        return False
    # phai ke sat theo chieu ngang: khoang cach mep duoi 2pt
    gap = max(small["bbox"][0] - big["bbox"][2], big["bbox"][0] - small["bbox"][2])
    return gap <= 2.0


def check_label_label(spans):
    """G3: hai nhan chong nhau."""
    out = []
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            a, b = spans[i], spans[j]
            if not a["geom"].intersects(b["geom"]):
                continue
            inter = a["geom"].intersection(b["geom"]).area
            if inter <= 0.5:
                continue
            # (1) dau to hop / dau phu chong ky tu goc la HOP LE:
            #     x-hat, chu Viet dung combining accent, dau mu trong TikZ.
            if _is_accent_pair(a["text"], b["text"]):
                continue
            # (2) subscript / superscript: chu nho hon ro ret + ke sat nhau
            #     theo chieu ngang -> hop le (R_t, B_t, lambda^B).
            if _is_script_pair(a, b):
                continue
            # (3) cung dong text, ke nhau (kerning lam bbox cham nhau)
            if abs(a["bbox"][1] - b["bbox"][1]) < 0.6 and \
               (abs(a["bbox"][2] - b["bbox"][0]) < 1.5 or
                    abs(b["bbox"][2] - a["bbox"][0]) < 1.5):
                continue
            out.append(Finding(
                "G3/label-label-overlap", "error",
                f"nhan {a['text'][:20]!r} chong nhan {b['text'][:20]!r} "
                f"({inter:.1f}pt2)",
                {"spanA": i, "textA": a["text"], "bboxA": a["bbox"],
                 "spanB": j, "textB": b["text"], "bboxB": b["bbox"],
                 "overlapAreaPt2": _r(inter)},
                ["tang khoang cach node", "doi vi tri mot trong hai nhan"]))
    return out


def check_bounds(page, elems, spans, margin=0.0):
    """G4: phan tu tran khoi trang."""
    out = []
    pr = page.rect
    page_box = box(pr.x0 + margin, pr.y0 + margin, pr.x1 - margin, pr.y1 - margin)
    for name, items in (("drawing", elems), ("label", spans)):
        for i, it in enumerate(items):
            bbox = it.bbox if isinstance(it, Elem) else it["bbox"]
            g = box(*bbox)
            if page_box.contains(g):
                continue
            outside = g.difference(page_box).area
            if outside <= 0.5:
                continue
            desc = it.kind if isinstance(it, Elem) else repr(it["text"][:24])
            out.append(Finding(
                "G4/out-of-bounds", "error",
                f"{name} {desc} tran khoi trang ({outside:.1f}pt2 ben ngoai)",
                {"index": i, "kind": name, "bbox": list(bbox),
                 "pageRect": [_r(pr.x0), _r(pr.y0), _r(pr.x1), _r(pr.y1)],
                 "outsideAreaPt2": _r(outside)},
                ["giam kich thuoc hinh", "tang le trang",
                 "dat lai vi tri phan tu"]))
    return out


def check_tiny_text(spans, min_font=MIN_FONT, base_font=None):
    """G5: chu nho hon san.

    Sub/superscript trong cong thuc toan (R_t, B_t, lambda^B) VON DI nho hon
    body font — do la typography dung, khong phai loi. Chi bao loi khi chu
    nho hon san MA khong phai sub/superscript, tuc la:
      - dai hon SUBSCRIPT_MAX_CHARS ky tu, HOAC
      - nho hon SUBSCRIPT_FLOOR_RATIO lan body font (teo qua muc, thuong do
        \resizebox lam co ca hinh).
    """
    out = []
    sizes = [sp["size"] for sp in spans if sp["size"] > 0]
    if base_font is None:
        # MODE (size pho bien nhat), khong phai MAX: tieu de dung \large se
        # lam max lech len, keo hard_floor len theo va bao sai moi subscript.
        if sizes:
            from collections import Counter
            rounded = Counter(round(s, 1) for s in sizes)
            base_font = rounded.most_common(1)[0][0]
        else:
            base_font = min_font
    hard_floor = base_font * SUBSCRIPT_FLOOR_RATIO
    for i, sp in enumerate(spans):
        if sp["size"] >= min_font:
            continue
        txt = sp["text"].strip()
        is_script = (len(txt) <= SUBSCRIPT_MAX_CHARS
                     and sp["size"] >= hard_floor)
        if is_script:
            continue
        out.append(Finding(
            "G5/tiny-text", "error",
            f"chu {sp['text'][:28]!r} chi {sp['size']:.2f}pt, duoi san "
            f"{min_font:.1f}pt",
            {"spanIndex": i, "text": sp["text"], "sizePt": _r(sp["size"], 2),
             "minimumPt": min_font, "bbox": sp["bbox"]},
            ["tang font trong hinh", "bo \\resizebox, dung tikzscale",
             "chia hinh thanh nhieu panel"]))
    return out


def check_label_edge(spans, edges, masks, min_area=EDGE_CLASH_MIN):
    """G6: nhan de len than mui ten ma khong co mask trang HIEU LUC.

    THU TU VE LA QUYET DINH. Mask trang chi che duoc duong khi no duoc ve SAU
    duong do (zorder lon hon). Trong TikZ, node dat trong `\\draw ... node[...]`
    duoc ve NGAY TRONG luc ve duong, nen mask cua no thuong nam TRUOC cac
    duong ve o dong sau -> khong che duoc gi. Bo qua mask theo dien tich ma
    khong xet zorder se sinh FALSE NEGATIVE: gate bao pass nhung mat nguoi
    van thay duong xuyen qua chu.
    """
    out = []
    for si, sp in enumerate(spans):
        g = sp["geom"]
        if g.area <= 0:
            continue
        for ei, e in enumerate(edges):
            if not g.intersects(e.geom):
                continue
            inter = g.intersection(e.geom)
            length = inter.length if hasattr(inter, "length") else 0.0
            if length < min_area:
                continue
            # chi tinh mask duoc ve SAU edge nay -> moi thuc su che duoc
            covering = [m for m in masks if m.zorder > e.zorder]
            covered = 0.0
            if covering:
                mu = unary_union([m.geom for m in covering])
                covered = mu.intersection(g).area / g.area
            if covered >= MASK_COVER_RATIO:
                continue
            # co mask nhung ve TRUOC edge -> noi ro de nguoi sua dung cach
            stale = [m for m in masks
                     if m.zorder < e.zorder and m.geom.intersects(g)]
            fixes = ["day nhan ra khoi duong", "doi duong di (via/bend)"]
            if stale:
                msg_extra = (" (co mask trang nhung ve TRUOC duong nen khong "
                             "che duoc)")
                fixes.insert(0, "ve lai nhan SAU khi ve duong: tach node ra "
                                "\\node[fill=white] o dong rieng sau \\draw")
            else:
                msg_extra = ""
                fixes.insert(0, "them mask trang phia sau nhan (fill=white) "
                                "va dat node SAU duong")
            out.append(Finding(
                "G6/label-edge-clash", "error",
                f"nhan {sp['text'][:24]!r} de len mui ten #{ei} "
                f"({length:.1f}pt duong di qua chu){msg_extra}",
                {"spanIndex": si, "text": sp["text"], "labelBbox": sp["bbox"],
                 "edgeIndex": ei, "crossLengthPt": _r(length),
                 "edgeZOrder": e.zorder,
                 "coveringMaskFraction": _r(covered, 3),
                 "staleMaskZOrders": [m.zorder for m in stale]},
                fixes))
    return out


# ---- driver ---------------------------------------------------------------

def analyze(pdf_path, page_no=0, min_font=MIN_FONT, eps=ENDPOINT_EPS,
            margin=0.0, block_min_area=BLOCK_MIN_AREA):
    doc = fitz.open(pdf_path)
    if page_no >= doc.page_count:
        raise ValueError(f"page {page_no} khong ton tai (co {doc.page_count})")
    page = doc[page_no]
    blocks, boundaries, edges, heads, masks = classify(
        page, block_min_area=block_min_area)
    spans = text_spans(page)

    findings = []
    findings += check_edge_through_block(edges, blocks, eps=eps)
    findings += check_label_block(spans, blocks)
    findings += check_label_label(spans)
    findings += check_bounds(page, blocks + boundaries + edges, spans,
                             margin=margin)
    findings += check_tiny_text(spans, min_font=min_font)
    findings += check_label_edge(spans, edges, masks)

    pr = page.rect
    inventory = {
        "blocks": len(blocks), "boundaries": len(boundaries),
        "edges": len(edges), "arrowheads": len(heads),
        "masks": len(masks), "labels": len(spans),
        "pageWidthPt": _r(pr.width), "pageHeightPt": _r(pr.height),
        "minFontPt": _r(min(([s["size"] for s in spans] or [0])), 2),
    }
    doc.close()
    return findings, inventory, (blocks, boundaries, edges, spans)


def annotate(pdf_path, out_png, findings, page_no=0, zoom=3.0):
    """Ve khung do quanh vung loi de nguoi soi bang mat."""
    doc = fitz.open(pdf_path)
    page = doc[page_no]
    for f in findings:
        ev = f.evidence
        rects = []
        for key in ("blockBbox", "labelBbox", "bbox", "bboxA", "bboxB"):
            if key in ev and isinstance(ev[key], (list, tuple)) and len(ev[key]) == 4:
                rects.append(fitz.Rect(*ev[key]))
        for r in rects:
            page.draw_rect(r, color=(1, 0, 0), width=0.8)
        if "midPoint" in ev:
            x, y = ev["midPoint"]
            page.draw_circle(fitz.Point(x, y), 4, color=(1, 0, 0), width=1.2)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(out_png)
    doc.close()
    return out_png


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tikz_gate")
    ap.add_argument("pdf")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--min-font", type=float, default=MIN_FONT)
    ap.add_argument("--eps", type=float, default=ENDPOINT_EPS)
    ap.add_argument("--margin", type=float, default=0.0)
    ap.add_argument("--block-min-area", type=float, default=BLOCK_MIN_AREA)
    ap.add_argument("--page", type=int, default=0)
    ap.add_argument("--annotate", default=None)
    args = ap.parse_args(argv)

    try:
        findings, inventory, _ = analyze(
            args.pdf, page_no=args.page, min_font=args.min_font,
            eps=args.eps, margin=args.margin,
            block_min_area=args.block_min_area)
    except Exception as exc:
        print(json.dumps({"ok": False, "stage": "analyze",
                          "error": str(exc)}, ensure_ascii=False))
        return 2

    png = None
    if args.annotate and findings:
        png = annotate(args.pdf, args.annotate, findings, page_no=args.page)

    errors = [f for f in findings if f.severity == "error"]
    ok = not errors
    report = {
        "schemaVersion": 1,
        "tool": "tikz-geometry-gate",
        "ok": ok,
        "pdf": args.pdf,
        "page": args.page,
        "inventory": inventory,
        "errorCount": len(errors),
        "findings": [asdict(f) for f in findings],
        "annotated": png,
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"tikz-geometry-gate: {'PASS' if ok else 'FAIL'}  {args.pdf} (trang {args.page})")
        inv = inventory
        print(f"  kiem ke: {inv['blocks']} block, {inv['boundaries']} boundary, "
              f"{inv['edges']} edge, {inv['labels']} nhan, "
              f"font nho nhat {inv['minFontPt']}pt")
        if not findings:
            print("  khong phat hien loi hinh hoc.")
        for f in findings:
            print(f"  [{f.code}] {f.message}")
            for fx in f.fixes[:2]:
                print(f"      -> {fx}")
        if png:
            print(f"  anh khoanh loi: {png}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
