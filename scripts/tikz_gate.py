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
import os
import sys
from dataclasses import dataclass, field, asdict

# Backend doc PDF. Mac dinh pdfplumber (MIT) de skill co the public;
# PyMuPDF (AGPL-3.0) chi dung khi dat ARCHIFY_PDF_BACKEND=pymupdf hoac khi
# thieu pdfplumber. Ca hai deu phai cho zorder (thu tu ve trong content
# stream) — thieu zorder la mat check G6 mask.
BACKEND = os.environ.get("TIKZGATE_PDF_BACKEND", "").strip().lower()

fitz = None
pdfplumber = None

if BACKEND != "pymupdf":
    try:
        import pdfplumber  # type: ignore
        BACKEND = "pdfplumber"
    except ImportError:  # pragma: no cover
        BACKEND = ""

if BACKEND != "pdfplumber":
    try:
        import pymupdf as fitz  # type: ignore
        BACKEND = "pymupdf"
    except ImportError:  # pragma: no cover
        try:
            import fitz  # type: ignore
            BACKEND = "pymupdf"
        except ImportError:
            raise SystemExit(
                "can pdfplumber (khuyen dung, MIT) hoac pymupdf: "
                "pip install pdfplumber shapely"
            )

from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import unary_union


def _active_backend() -> str:
    """Ten backend dang dung: 'pdfplumber' hoac 'pymupdf'.

    Tach thanh ham (khong doc BACKEND truc tiep) de test co the monkeypatch
    va de _open_page / annotate cung dung mot nguon su that.
    """
    return BACKEND


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


def _flatten_items_pymupdf(items):
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


def classify_pymupdf(page, block_min_area=BLOCK_MIN_AREA,
                     arrowhead_max=ARROWHEAD_MAX):
    """Phan loai drawing (backend PyMuPDF)."""
    blocks, boundaries, edges, heads, masks = [], [], [], [], []
    for zi, d in enumerate(page.get_drawings()):
        r = d["rect"]
        w, h = r.width, r.height
        area = w * h
        dashes = d.get("dashes") or ""
        dashed = bool(dashes) and dashes.strip() not in ("", "[] 0")
        typ = d["type"]
        polys = _flatten_items_pymupdf(d["items"])

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


def text_spans_pymupdf(page, pad=LABEL_PAD):
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


# ---- backend: pdfplumber (MIT, mac dinh) ----------------------------------

def _pp_color_is_white(c):
    """non_stroking_color trong pdfplumber co the la float, tuple, hoac None."""
    if c is None:
        return False
    if isinstance(c, (int, float)):
        return float(c) > 0.95
    try:
        vals = [float(v) for v in c]
    except (TypeError, ValueError):
        return False
    if not vals:
        return False
    if len(vals) == 4:      # CMYK: trang = 0,0,0,0
        return all(v < 0.05 for v in vals)
    return all(v > 0.95 for v in vals)


def _pp_dashed(dash):
    """LTCurve.dashing_style = (pattern, phase). Rong/None = lien tuc."""
    if not dash:
        return False
    pattern = dash[0] if isinstance(dash, (tuple, list)) else dash
    if pattern is None:
        return False
    try:
        return any(float(v) > 0 for v in pattern)
    except (TypeError, ValueError):
        return False


def _pp_polylines(pts):
    """LTCurve.pts -> danh sach polyline (pdfminer da flatten Bezier)."""
    clean = []
    for p in pts or []:
        try:
            clean.append((float(p[0]), float(p[1])))
        except (TypeError, ValueError, IndexError):
            continue
    return [clean] if len(clean) >= 2 else []


def classify_pdfplumber(page, block_min_area=BLOCK_MIN_AREA,
                        arrowhead_max=ARROWHEAD_MAX):
    """Phan loai drawing (backend pdfplumber).

    zorder lay tu thu tu duyet page.layout, VON GIU dung thu tu content
    stream — bat buoc cho check G6 (mask chi che duoc khi ve SAU duong).
    Toa do doi sang goc TREN-trai de trung he voi PyMuPDF.
    """
    from pdfminer.layout import LTChar, LTCurve

    blocks, boundaries, edges, heads, masks = [], [], [], [], []
    H = float(page.height)

    def flip(x0, y0, x1, y1):
        """pdfminer y tinh tu DUOI len; doi sang tren-xuong."""
        return (float(x0), H - float(y1), float(x1), H - float(y0))

    zi = -1
    stack = list(getattr(page.layout, "_objs", []) or [])
    ordered = []
    while stack:
        obj = stack.pop(0)
        if isinstance(obj, LTChar):
            continue
        if isinstance(obj, LTCurve):
            ordered.append(obj)
            continue
        kids = getattr(obj, "_objs", None)
        if kids:
            stack = list(kids) + stack

    for obj in ordered:
        zi += 1
        bb = flip(obj.x0, obj.y0, obj.x1, obj.y1)
        w, h = bb[2] - bb[0], bb[3] - bb[1]
        area = w * h
        filled = bool(getattr(obj, "fill", False))
        stroked = bool(getattr(obj, "stroke", False))
        dashed = _pp_dashed(getattr(obj, "dashing_style", None))
        pts = [(x, H - y) for x, y in
               ((float(p[0]), float(p[1])) for p in (obj.pts or []))]
        bbox = (_r(bb[0]), _r(bb[1]), _r(bb[2]), _r(bb[3]))
        geom_box = box(*bb) if w > 0 and h > 0 else None

        # dau mui ten: fill nho, khong stroke
        if filled and not stroked and max(w, h) <= arrowhead_max:
            heads.append(Elem("arrowhead", bbox, geom_box or box(
                bb[0], bb[1], bb[0] + 0.01, bb[1] + 0.01), zorder=zi))
            continue

        # mask trang
        if filled and not stroked and _pp_color_is_white(
                getattr(obj, "non_stroking_color", None)):
            masks.append(Elem("mask", bbox, geom_box or box(
                bb[0], bb[1], bb[0] + 0.01, bb[1] + 0.01), zorder=zi))
            continue

        # block / boundary: co fill va du to
        if filled and area >= block_min_area and geom_box is not None:
            e = Elem("boundary" if dashed else "block", bbox, geom_box,
                     dashed=dashed, zorder=zi)
            (boundaries if dashed else blocks).append(e)
            continue

        # edge: stroke-only
        if stroked and not filled:
            for pl in _pp_polylines(pts):
                try:
                    ls = LineString(pl)
                except Exception:
                    continue
                if ls.length < 1.0:
                    continue
                edges.append(Elem("edge", bbox, ls, dashed=dashed,
                                  poly=[(_r(x), _r(y)) for x, y in pl],
                                  zorder=zi))
            continue

        # fill+stroke nho: van coi la block
        if filled and geom_box is not None:
            e = Elem("boundary" if dashed else "block", bbox, geom_box,
                     dashed=dashed, zorder=zi)
            (boundaries if dashed else blocks).append(e)

    return blocks, boundaries, edges, heads, masks


def text_spans_pdfplumber(page, pad=LABEL_PAD):
    """Gom char thanh span theo font+size+dong (backend pdfplumber).

    pdfplumber khong co khai niem 'span' nhu PyMuPDF, nen phai gom tay:
    cung fontname + size + baseline, va khoang cach ngang khong qua rong.
    """
    # KHONG sort theo toa do. page.chars da theo THU TU STREAM, tuc la char
    # trong cung mot lenh ve chu (Tj) nam lien nhau. Sort theo (top, x0) se
    # tron char cua HAI NHAN CHONG NHAU o cung dong thanh mot span duy nhat
    # -> mat sach check G3. Day dung la loi da gap: fixture bad.tex bao 5 loi
    # G3 voi PyMuPDF nhung 0 loi khi con sort.
    chars = list(page.chars)
    spans, cur = [], None

    def flush():
        nonlocal cur
        if cur and cur["text"].strip():
            x0, y0, x1, y1 = cur["x0"], cur["y0"], cur["x1"], cur["y1"]
            spans.append({
                "text": cur["text"],
                "size": cur["size"],
                "font": cur["font"],
                "bbox": (_r(x0), _r(y0), _r(x1), _r(y1)),
                "geom": box(x0 + pad, y0 + pad, max(x1 - pad, x0 + pad + 0.01),
                            max(y1 - pad, y0 + pad + 0.01)),
            })
        cur = None

    for c in chars:
        txt = c.get("text") or ""
        size = float(c.get("size") or 0)
        font = c.get("fontname") or ""
        x0, x1 = float(c["x0"]), float(c["x1"])
        top, bottom = float(c["top"]), float(c["bottom"])
        gap = x0 - cur["x1"] if cur is not None else 0.0
        # BUG DA GAP: dieu kien chi kiem gap <= nguong se dung voi ca gap AM
        # lon, nen hai nhan chong nhau tren cung mot dong bi gop thanh MOT
        # span -> G3 mat hoan toan kha nang phat hien. Phai chan nhay LUI:
        # chi cho phep kerning am nhe (~1pt), con lui nhieu la nhan khac.
        # Nguong tien cung phai nho de tach theo TU (khop voi span cua
        # PyMuPDF), vi khoang trang giua tu trong PDF TikZ thuong khong co
        # char space that ma chi la gap ~3pt.
        same = (cur is not None
                and abs(cur["size"] - size) < 0.05
                and cur["font"] == font
                and abs(cur["top"] - top) < 0.6
                and -1.0 <= gap <= max(1.5, size * 0.15))
        if not same:
            flush()
            cur = {"text": "", "size": size, "font": font, "top": top,
                   "x0": x0, "y0": top, "x1": x1, "y1": bottom}
        cur["text"] += txt
        cur["x1"] = max(cur["x1"], x1)
        cur["y0"] = min(cur["y0"], top)
        cur["y1"] = max(cur["y1"], bottom)
    flush()
    return spans


# ---- dispatcher ------------------------------------------------------------

def classify(page, block_min_area=BLOCK_MIN_AREA, arrowhead_max=ARROWHEAD_MAX):
    """Phan loai phan tu, tu dong chon backend theo loai `page`."""
    if hasattr(page, "get_drawings"):
        return classify_pymupdf(page, block_min_area, arrowhead_max)
    return classify_pdfplumber(page, block_min_area, arrowhead_max)


def text_spans(page, pad=LABEL_PAD):
    """Trich nhan, tu dong chon backend theo loai `page`."""
    if hasattr(page, "get_text"):
        return text_spans_pymupdf(page, pad)
    return text_spans_pdfplumber(page, pad)


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

class _PageBox:
    """Bao boc page cua ca hai backend de check_bounds dung chung interface."""

    def __init__(self, x0, y0, x1, y1):
        self.rect = _Rect(x0, y0, x1, y1)


class _Rect:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    @property
    def width(self):
        return self.x1 - self.x0

    @property
    def height(self):
        return self.y1 - self.y0


def _open_page(pdf_path, page_no):
    """Mo trang PDF bang backend dang hoat dong.

    Tra ve (page, page_rect_like, closer). pdfplumber la mac dinh (MIT);
    PyMuPDF (AGPL) chi dung khi TIKZGATE_PDF_BACKEND=pymupdf.
    """
    if _active_backend() == "pymupdf":
        doc = fitz.open(pdf_path)
        if page_no >= doc.page_count:
            raise ValueError(
                f"page {page_no} khong ton tai (co {doc.page_count})")
        page = doc[page_no]
        return page, page, doc.close
    import pdfplumber
    pdf = pdfplumber.open(pdf_path)
    if page_no >= len(pdf.pages):
        pdf.close()
        raise ValueError(f"page {page_no} khong ton tai (co {len(pdf.pages)})")
    page = pdf.pages[page_no]
    holder = _PageBox(float(page.bbox[0]), float(page.bbox[1]),
                      float(page.bbox[2]), float(page.bbox[3]))
    return page, holder, pdf.close


def analyze(pdf_path, page_no=0, min_font=MIN_FONT, eps=ENDPOINT_EPS,
            margin=0.0, block_min_area=BLOCK_MIN_AREA):
    page, page_holder, close = _open_page(pdf_path, page_no)
    blocks, boundaries, edges, heads, masks = classify(
        page, block_min_area=block_min_area)
    spans = text_spans(page)

    findings = []
    findings += check_edge_through_block(edges, blocks, eps=eps)
    findings += check_label_block(spans, blocks)
    findings += check_label_label(spans)
    findings += check_bounds(page_holder, blocks + boundaries + edges, spans,
                             margin=margin)
    findings += check_tiny_text(spans, min_font=min_font)
    findings += check_label_edge(spans, edges, masks)

    pr = page_holder.rect
    inventory = {
        "blocks": len(blocks), "boundaries": len(boundaries),
        "edges": len(edges), "arrowheads": len(heads),
        "masks": len(masks), "labels": len(spans),
        "pageWidthPt": _r(pr.width), "pageHeightPt": _r(pr.height),
        "minFontPt": _r(min(([s["size"] for s in spans] or [0])), 2),
    }
    close()
    return findings, inventory, (blocks, boundaries, edges, spans)


def _annotate_rects(findings):
    """Gom bbox va diem giua tu findings de ve khung."""
    out = []
    for f in findings:
        ev = f.evidence
        rects, dots = [], []
        for key in ("blockBbox", "labelBbox", "bbox", "bboxA", "bboxB"):
            v = ev.get(key)
            if isinstance(v, (list, tuple)) and len(v) == 4:
                rects.append(tuple(float(x) for x in v))
        mp = ev.get("midPoint")
        if isinstance(mp, (list, tuple)) and len(mp) == 2:
            dots.append((float(mp[0]), float(mp[1])))
        out.append((rects, dots))
    return out


def _annotate_pymupdf(pdf_path, out_png, findings, page_no, zoom):
    doc = fitz.open(pdf_path)
    page = doc[page_no]
    for rects, dots in _annotate_rects(findings):
        for r in rects:
            page.draw_rect(fitz.Rect(*r), color=(1, 0, 0), width=0.8)
        for x, y in dots:
            page.draw_circle(fitz.Point(x, y), 4, color=(1, 0, 0), width=1.2)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    pix.save(out_png)
    doc.close()
    return out_png


def _annotate_pdftocairo(pdf_path, out_png, findings, page_no, zoom):
    """Khong co PyMuPDF: render bang pdftocairo roi ve khung bang Pillow.

    Toa do PDF goc o goc DUOI-trai theo quy uoc PDF, nhung ca hai backend cua
    gate deu tra bbox theo he TREN-trai (pdfplumber dung top/bottom, PyMuPDF
    cung vay), nen chi can nhan zoom.
    """
    import shutil
    import subprocess
    import tempfile

    if shutil.which("pdftocairo") is None:
        raise RuntimeError("thieu pdftocairo (poppler-utils) de --annotate")
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("thieu Pillow de --annotate") from exc

    dpi = int(round(72 * zoom))
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "page")
        subprocess.run(
            ["pdftocairo", "-png", "-r", str(dpi),
             "-f", str(page_no + 1), "-l", str(page_no + 1),
             "-singlefile", str(pdf_path), base],
            check=True, capture_output=True)
        png = base + ".png"
        if not os.path.exists(png):
            raise RuntimeError("pdftocairo khong tao duoc PNG")
        img = Image.open(png).convert("RGB")
        drw = ImageDraw.Draw(img)
        s = dpi / 72.0
        for rects, dots in _annotate_rects(findings):
            for x0, y0, x1, y1 in rects:
                drw.rectangle([x0 * s, y0 * s, x1 * s, y1 * s],
                              outline=(255, 0, 0), width=max(1, int(s)))
            for x, y in dots:
                r = 4 * s
                drw.ellipse([x * s - r, y * s - r, x * s + r, y * s + r],
                            outline=(255, 0, 0), width=max(1, int(s)))
        img.save(out_png)
    return out_png


def annotate(pdf_path, out_png, findings, page_no=0, zoom=3.0):
    """Ve khung do quanh vung loi de nguoi soi bang mat.

    Dung PyMuPDF khi co (nhanh hon), nguoc lai dung pdftocairo + Pillow de
    khong buoc phai cai PyMuPDF (AGPL) chi de xuat anh.
    """
    if _active_backend() == "pymupdf" and fitz is not None:
        return _annotate_pymupdf(pdf_path, out_png, findings, page_no, zoom)
    return _annotate_pdftocairo(pdf_path, out_png, findings, page_no, zoom)



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
