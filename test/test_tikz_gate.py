#!/usr/bin/env python3
"""Unit test cho tikz-geometry-gate.

Chay: python -m unittest test_tikz_gate -v
Test dung hinh hoc tong hop (khong can compile LaTeX) cho phan logic,
va fixture PDF that cho phan doc PDF.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FIXTURES = REPO / "fixtures"
sys.path.insert(0, str(REPO / "scripts"))


def build_fixture(tex_name: str) -> Path:
    """Compile fixtures/<tex_name> -> PDF trong thu muc tam, cache lai.

    Repo khong commit PDF: fixture PDF duoc dung tu .tex de test chay duoc
    tren may sach (chi can pdflatex + tikz).
    """
    tex = FIXTURES / tex_name
    if not tex.exists():
        raise unittest.SkipTest(f"thieu fixture {tex}")
    outdir = FIXTURES / "_build"
    outdir.mkdir(exist_ok=True)
    pdf = outdir / (tex.stem + ".pdf")
    if pdf.exists() and pdf.stat().st_mtime > tex.stat().st_mtime:
        return pdf
    proc = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "-halt-on-error",
         f"-output-directory={outdir}", str(tex)],
        capture_output=True, text=True)
    if not pdf.exists():
        raise unittest.SkipTest(f"pdflatex khong dung duoc: {proc.stdout[-400:]}")
    return pdf


from shapely.geometry import LineString, box  # noqa: E402

import tikz_gate as G  # noqa: E402


def mk_block(x0, y0, x1, y1):
    return G.Elem("block", (x0, y0, x1, y1), box(x0, y0, x1, y1))


def mk_edge(points):
    ls = LineString(points)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return G.Elem("edge", (min(xs), min(ys), max(xs), max(ys)), ls, poly=points)


def mk_span(text, x0, y0, x1, y1, size=10.0):
    return {
        "text": text, "size": size, "font": "Test",
        "bbox": (x0, y0, x1, y1),
        "geom": box(x0 + G.LABEL_PAD, y0 + G.LABEL_PAD,
                    x1 - G.LABEL_PAD, y1 - G.LABEL_PAD),
    }


class TestG1EdgeThroughBlock(unittest.TestCase):
    """G1: mui ten xuyen than block — check quan trong nhat."""

    def test_edge_crossing_middle_is_error(self):
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(20, 60), (300, 60)])  # xuyen ngang giua block
        out = G.check_edge_through_block([edge], [blk])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G1/edge-through-block")
        self.assertGreater(out[0].evidence["insideLengthPt"], 90)

    def test_edge_touching_border_is_ok(self):
        """Mui ten hop le ket thuc o VIEN block -> khong bao loi."""
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(20, 60), (100, 60)])  # dung lai o vien trai
        out = G.check_edge_through_block([edge], [blk])
        self.assertEqual(out, [])

    def test_edge_starting_at_border_is_ok(self):
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(200, 60), (320, 60)])  # bat dau tu vien phai
        out = G.check_edge_through_block([edge], [blk])
        self.assertEqual(out, [])

    def test_edge_far_from_block_is_ok(self):
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(20, 200), (300, 200)])
        out = G.check_edge_through_block([edge], [blk])
        self.assertEqual(out, [])

    def test_grazing_shorter_than_threshold_is_ok(self):
        """Cham nhe 1pt (do lam tron toa do) khong phai loi."""
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(99, 60), (101, 60)])
        out = G.check_edge_through_block([edge], [blk], min_len=2.0)
        self.assertEqual(out, [])

    def test_vertical_edge_through_block(self):
        blk = mk_block(100, 40, 200, 80)
        edge = mk_edge([(150, 10), (150, 200)])
        out = G.check_edge_through_block([edge], [blk])
        self.assertEqual(len(out), 1)


class TestG2LabelBlock(unittest.TestCase):
    def test_label_straddling_border_is_error(self):
        blk = mk_block(100, 40, 200, 80)
        sp = mk_span("nhan", 80, 50, 130, 62)  # nua trong nua ngoai
        out = G.check_label_block([sp], [blk])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G2/label-block-straddle")

    def test_label_fully_inside_is_ok(self):
        """Nhan cua chinh block -> hop le."""
        blk = mk_block(100, 40, 200, 80)
        sp = mk_span("nhan", 120, 50, 180, 65)
        out = G.check_label_block([sp], [blk])
        self.assertEqual(out, [])

    def test_label_fully_outside_is_ok(self):
        blk = mk_block(100, 40, 200, 80)
        sp = mk_span("nhan", 10, 50, 60, 65)
        out = G.check_label_block([sp], [blk])
        self.assertEqual(out, [])


class TestG3LabelLabel(unittest.TestCase):
    def test_real_overlap_is_error(self):
        a = mk_span("Alpha", 100, 50, 160, 62)
        b = mk_span("Beta", 120, 52, 180, 64)
        out = G.check_label_label([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G3/label-label-overlap")

    def test_accent_over_base_is_ok(self):
        """x-hat: dau mu chong ky tu goc la typography dung."""
        base = mk_span("x", 125.0, 26.8, 130.3, 35.8, size=8.97)
        accent = mk_span("\u02c6", 125.6, 26.8, 130.2, 35.8, size=8.97)
        out = G.check_label_label([base, accent])
        self.assertEqual(out, [], "dau mu khong duoc coi la loi")

    def test_vietnamese_combining_accent_is_ok(self):
        base = mk_span("e", 50.0, 20.0, 56.0, 30.0)
        accent = mk_span("\u0323", 50.5, 20.0, 55.5, 30.0)
        out = G.check_label_label([base, accent])
        self.assertEqual(out, [])

    def test_subscript_adjacent_is_ok(self):
        """R_t: chi so nho ke sat ky tu goc."""
        base = mk_span("R", 100.0, 40.0, 108.0, 52.0, size=10.0)
        sub = mk_span("t", 108.2, 44.0, 112.0, 54.0, size=7.0)
        out = G.check_label_label([base, sub])
        self.assertEqual(out, [])

    def test_side_by_side_kerning_is_ok(self):
        a = mk_span("Aa", 100, 50, 120, 62)
        b = mk_span("Bb", 120.5, 50, 140, 62)
        out = G.check_label_label([a, b])
        self.assertEqual(out, [])


class TestG5TinyText(unittest.TestCase):
    def test_body_text_below_floor_is_error(self):
        sp = mk_span("Duong day chinh", 10, 10, 90, 18, size=4.2)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G5/tiny-text")

    def test_math_subscript_is_ok(self):
        """B_t o 5.98pt voi body 8.97pt la sub hop le, khong phai loi."""
        sp = mk_span("t", 10, 10, 14, 18, size=5.98)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=8.97)
        self.assertEqual(out, [])

    def test_subscript_shrunk_too_far_is_error(self):
        """Sub nho hon 55% body -> teo that (thuong do resizebox)."""
        sp = mk_span("t", 10, 10, 14, 18, size=2.5)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0)
        self.assertEqual(len(out), 1)

    def test_long_text_never_treated_as_script(self):
        sp = mk_span("khong phai chi so", 10, 10, 90, 18, size=5.5)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=8.0)
        self.assertEqual(len(out), 1)

    def test_normal_size_is_ok(self):
        sp = mk_span("Binh thuong", 10, 10, 90, 22, size=10.0)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0)
        self.assertEqual(out, [])


class TestG6LabelEdge(unittest.TestCase):
    def test_edge_through_label_is_error(self):
        """Truong hop anh Van nhan manh: duong di xuyen qua chu."""
        sp = mk_span("Polling", 76.9, 193.8, 103.1, 202.8)
        edge = mk_edge([(98.8, 115.8), (98.8, 260.3)])
        out = G.check_label_edge([sp], [edge], [])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G6/label-edge-clash")

    def test_white_mask_drawn_after_edge_is_ok(self):
        """Mask trang ve SAU duong -> che duoc duong, chu doc duoc."""
        sp = mk_span("Data", 90, 190, 110, 202)
        edge = mk_edge([(100, 150), (100, 250)])
        edge.zorder = 5
        mask = G.Elem("mask", (88, 188, 112, 204), box(88, 188, 112, 204),
                      zorder=9)
        out = G.check_label_edge([sp], [edge], [mask])
        self.assertEqual(out, [], "mask ve sau duong thi chu van doc duoc")

    def test_stale_mask_drawn_before_edge_is_error(self):
        """REGRESSION (anh Van phat hien): mask ve TRUOC duong -> duong van de
        len mask, chu VAN bi xuyen. Gate cu bao ok=true o day = false negative.
        """
        sp = mk_span("Polling", 90, 190, 110, 202)
        edge = mk_edge([(100, 150), (100, 250)])
        edge.zorder = 9
        mask = G.Elem("mask", (88, 188, 112, 204), box(88, 188, 112, 204),
                      zorder=3)
        out = G.check_label_edge([sp], [edge], [mask])
        self.assertEqual(len(out), 1, "mask ve truoc duong khong cuu duoc chu")
        self.assertEqual(out[0].code, "G6/label-edge-clash")
        self.assertEqual(out[0].evidence["staleMaskZOrders"], [3])

    def test_partial_mask_below_ratio_is_error(self):
        sp = mk_span("Data", 90, 190, 130, 202)
        edge = mk_edge([(100, 150), (100, 250)])
        edge.zorder = 5
        mask = G.Elem("mask", (88, 188, 96, 204), box(88, 188, 96, 204),
                      zorder=9)
        out = G.check_label_edge([sp], [edge], [mask])
        self.assertEqual(len(out), 1)

    def test_label_beside_edge_is_ok(self):
        sp = mk_span("Label", 120, 190, 160, 202)
        edge = mk_edge([(100, 150), (100, 250)])
        out = G.check_label_edge([sp], [edge], [])
        self.assertEqual(out, [])


class TestG4Bounds(unittest.TestCase):
    def test_element_outside_page_is_error(self):
        class FakePage:
            rect = type("R", (), {"x0": 0, "y0": 0, "x1": 200, "y1": 100,
                                  "width": 200, "height": 100})()
        sp = mk_span("tran", 180, 40, 260, 55)
        out = G.check_bounds(FakePage(), [], [sp])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G4/out-of-bounds")

    def test_element_inside_page_is_ok(self):
        class FakePage:
            rect = type("R", (), {"x0": 0, "y0": 0, "x1": 200, "y1": 100,
                                  "width": 200, "height": 100})()
        sp = mk_span("trong", 20, 40, 80, 55)
        out = G.check_bounds(FakePage(), [], [sp])
        self.assertEqual(out, [])


class TestClassifyRealPdf(unittest.TestCase):
    """Doc PDF that: phan loai block/edge/arrowhead."""

    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("defect-rabs.tex")
        if not cls.pdf.exists():
            raise unittest.SkipTest(f"thieu fixture {cls.pdf}")

    def test_classify_finds_blocks_and_edges(self):
        findings, inv, _ = G.analyze(str(self.pdf))
        self.assertGreaterEqual(inv["blocks"], 4, "phai tim thay cac block")
        self.assertGreaterEqual(inv["edges"], 5, "phai tim thay cac mui ten")
        self.assertGreaterEqual(inv["arrowheads"], 5)
        self.assertGreaterEqual(inv["boundaries"], 1, "khung net dut IoT Gateway")

    def test_detects_known_real_defect(self):
        """Hinh that co loi: duong 'Data Transmissions' xuyen nhan 'Polling'."""
        findings, _, _ = G.analyze(str(self.pdf))
        codes = [f.code for f in findings]
        self.assertIn("G6/label-edge-clash", codes)
        clash = [f for f in findings if f.code == "G6/label-edge-clash"]
        texts = [f.evidence["text"] for f in clash]
        self.assertTrue(any("Polling" in t for t in texts),
                        f"phai bat duoc nhan Polling, thay: {texts}")

    def test_no_accent_false_positive_on_real_pdf(self):
        """x-hat trong hinh that khong duoc bao G3."""
        findings, _, _ = G.analyze(str(self.pdf))
        g3 = [f for f in findings if f.code == "G3/label-label-overlap"]
        for f in g3:
            pair = (f.evidence["textA"], f.evidence["textB"])
            self.assertNotIn("x", pair,
                             f"x-hat bi bao sai: {pair}")


class TestCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("defect-rabs.tex")
        if not cls.pdf.exists():
            raise unittest.SkipTest("thieu fixture")

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "tikz_gate.py"), *args],
            capture_output=True, text=True)

    def test_json_output_is_valid(self):
        r = self._run(str(self.pdf), "--json")
        data = json.loads(r.stdout)
        self.assertIn("inventory", data)
        self.assertIn("findings", data)
        self.assertEqual(data["schemaVersion"], 1)

    def test_exit_code_nonzero_when_failing(self):
        r = self._run(str(self.pdf), "--json")
        self.assertEqual(r.returncode, 1, "co loi -> exit 1")

    def test_missing_file_exits_2(self):
        r = self._run("khong-ton-tai.pdf", "--json")
        self.assertEqual(r.returncode, 2)

    def test_annotate_writes_png(self):
        out = FIXTURES / "_build" / "_test_annot.png"
        if out.exists():
            out.unlink()
        self._run(str(self.pdf), "--json", "--annotate", str(out))
        self.assertTrue(out.exists(), "phai ghi duoc PNG khoanh loi")
        self.assertGreater(out.stat().st_size, 1000)
        out.unlink()


class TestPdfPlumberSpanGrouping(unittest.TestCase):
    """REGRESSION: hai bug gom char cua backend pdfplumber.

    pdfplumber khong co khai niem 'span', phai gom char tay. Hai bug da gap:

    Bug 1 (sort theo toa do): neu sort char theo (top, x0) truoc khi gom thi
    hai nhan CHONG NHAU o cung dong bi tron lan roi gop thanh MOT span ->
    G3/label-label-overlap khong con thay gi de so sanh (false negative).
    page.chars von da theo thu tu content stream, khong duoc sort lai.

    Bug 2 (nhay lui): dieu kien gop dung (x0 - cur_x1) <= nguong. Khi span moi
    bat dau LUI ve ben trai (x0 - cur_x1 am, vi du -72pt cho nhan chong nhau),
    bieu thuc van dung -> gop sai. Phai chan gap am.
    """

    @classmethod
    def setUpClass(cls):
        if G._active_backend() != "pdfplumber":
            raise unittest.SkipTest("chi ap dung cho backend pdfplumber")
        cls.pdf = build_fixture("bad.tex")

    def test_overlapping_labels_stay_separate_spans(self):
        import pdfplumber
        with pdfplumber.open(str(self.pdf)) as pdf:
            spans = G.text_spans(pdf.pages[0])
        texts = [s["text"] for s in spans]
        # fixture co 2 nhan 'Overlapping label one' / '... two' de chong nhau.
        merged = [t for t in texts if t.count("Overlapping") > 1]
        self.assertEqual(merged, [],
                         f"khong duoc gop 2 nhan chong nhau thanh 1 span: {texts}")
        self.assertGreaterEqual(len([t for t in texts if "Overlapping" in t]), 2,
                                f"phai giu du 2 nhan rieng: {texts}")

    def test_g3_still_detects_overlap_on_real_pdf(self):
        findings, inv, _ = G.analyze(str(self.pdf))
        codes = [f.code for f in findings]
        self.assertIn("G3/label-label-overlap", codes,
                      "gom span sai se lam G3 mat hoan toan (false negative)")


class TestBackendParity(unittest.TestCase):
    """Hai backend phai cho CUNG ket luan tren cung fixture.

    Neu lech, tuc la mot backend bo sot loi. Test nay la canh cho moi thay doi
    o classify_*/text_spans_* ve sau.
    """

    FIXTURES = ("good-rabs.tex", "defect-rabs.tex", "stale-mask-rabs.tex", "bad.tex")

    def _run(self, tex, backend):
        pdf = build_fixture(tex)
        env = dict(os.environ)
        env["TIKZGATE_PDF_BACKEND"] = backend
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "tikz_gate.py"),
             str(pdf), "--json"],
            capture_output=True, text=True, env=env)
        if not r.stdout.strip():
            raise unittest.SkipTest(f"backend {backend} khong chay duoc")
        return json.loads(r.stdout)

    def test_same_verdict_and_codes(self):
        try:
            import pdfplumber  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("thieu pdfplumber")
        if G.fitz is None:
            raise unittest.SkipTest("thieu pymupdf, khong so sanh duoc")
        from collections import Counter
        for tex in self.FIXTURES:
            with self.subTest(fixture=tex):
                a = self._run(tex, "pymupdf")
                b = self._run(tex, "pdfplumber")
                self.assertEqual(a["ok"], b["ok"], f"{tex}: verdict lech")
                ca = Counter(f["code"] for f in a["findings"])
                cb = Counter(f["code"] for f in b["findings"])
                self.assertEqual(ca, cb, f"{tex}: bo loi lech {ca} vs {cb}")


class TestAnnotateWithoutPyMuPDF(unittest.TestCase):
    """annotate() phai chay duoc khi CHI co pdfplumber (khong co PyMuPDF).

    Neu khong, skill se buoc phai keo PyMuPDF (AGPL-3.0) vao chi de ve khung do.
    """

    def test_annotate_pdftocairo_path(self):
        import shutil
        if not shutil.which("pdftocairo"):
            raise unittest.SkipTest("thieu pdftocairo")
        try:
            import PIL  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("thieu Pillow")
        pdf = build_fixture("defect-rabs.tex")
        findings, _, _ = G.analyze(str(pdf))
        self.assertGreater(len(findings), 0, "fixture phai co loi de khoanh")
        out = FIXTURES / "_build" / "_test_annot_cairo.png"
        if out.exists():
            out.unlink()
        G._annotate_pdftocairo(str(pdf), str(out), findings, 0, 3.0)
        self.assertTrue(out.exists(), "phai ghi duoc PNG bang pdftocairo")
        self.assertGreater(out.stat().st_size, 1000)
        out.unlink()



class TestPageKindDetection(unittest.TestCase):
    """Phan biet trang tai lieu that vs hinh crop roi."""

    def test_a4_is_document(self):
        kind, preset = G.page_kind(595.3, 841.9)
        self.assertEqual(kind, "document")
        self.assertEqual(preset, "a4")

    def test_letter_is_document(self):
        kind, preset = G.page_kind(612.0, 792.0)
        self.assertEqual(kind, "document")
        self.assertEqual(preset, "letter")

    def test_beamer_16x9_is_document(self):
        """REGRESSION: so THAT do tu `\\documentclass[aspectratio=169]{beamer}`.

        Bug da gap: preset ghi 362.8x204.5 (doan sai) nen slide 16:9 that
        (160x90mm = 453.5x255.1pt) bi nhan la 'standalone' -> moi loi font
        tren slide tut xuong warning va bi bo qua.
        """
        kind, preset = G.page_kind(453.5, 255.1)
        self.assertEqual(kind, "document")
        self.assertEqual(preset, "beamer-16x9")

    def test_beamer_4x3_is_document(self):
        """So THAT do tu beamer mac dinh (128x96mm)."""
        kind, preset = G.page_kind(362.8, 272.1)
        self.assertEqual(kind, "document")
        self.assertEqual(preset, "beamer-4x3")

    def test_old_wrong_beamer_size_is_not_a_preset(self):
        """362.8x204.5 la so SAI cu — khong duoc coi la preset nao."""
        kind, preset = G.page_kind(362.8, 204.5)
        self.assertEqual(kind, "standalone")
        self.assertIsNone(preset)

    def test_cropped_figure_is_standalone(self):
        """Hinh standalone crop sat noi dung -> khong khop preset nao."""
        kind, preset = G.page_kind(466.8, 267.4)
        self.assertEqual(kind, "standalone")
        self.assertIsNone(preset)

    def test_tolerance_absorbs_rounding(self):
        kind, preset = G.page_kind(595.0, 842.0)
        self.assertEqual(kind, "document")


class TestG5ScaleAware(unittest.TestCase):
    """REGRESSION: font do tren hinh ROI khong phai font nguoi doc nhin thay.

    Do bang so that: arch_diagram font min 4.98pt tren hinh roi, nhung chi
    2.67pt khi nhung vao A4 (ty le 0.536).
    """

    def test_standalone_unknown_scale_is_warning_not_error(self):
        """Chua biet he so thu nho -> canh bao, KHONG ket luan la loi."""
        sp = mk_span("nhan dai khong phai chi so", 10, 10, 90, 16, size=5.0)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0,
                                scale=1.0, kind="standalone")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "warning")
        self.assertFalse(out[0].evidence["scaleKnown"])

    def test_document_page_is_error(self):
        """Trang tai lieu that -> font do duoc la font that -> loi."""
        sp = mk_span("nhan dai khong phai chi so", 10, 10, 90, 16, size=5.0)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0,
                                scale=1.0, kind="document", preset="a4")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "error")

    def test_scale_shrinks_effective_font_into_error(self):
        """8.97pt x 0.536 = 4.81pt < san 6pt -> loi that."""
        sp = mk_span("Greenhouse", 10, 10, 90, 20, size=8.97)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=8.97,
                                scale=0.536, kind="standalone")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].severity, "error")
        self.assertAlmostEqual(out[0].evidence["effectivePt"], 4.81, places=1)
        self.assertTrue(out[0].evidence["scaleKnown"])

    def test_scale_up_keeps_readable_font_clean(self):
        """Hinh ve nho roi phong to len -> khong phai loi."""
        sp = mk_span("Greenhouse", 10, 10, 90, 20, size=4.0)
        out = G.check_tiny_text([sp], min_font=6.0, base_font=4.0,
                                scale=2.0, kind="standalone")
        self.assertEqual(out, [])

    def test_subscript_judged_on_intrinsic_size_not_scaled(self):
        """Sub/superscript loc theo ty le NOI BO hinh, khong theo scale."""
        sub = mk_span("t", 10, 10, 14, 16, size=5.98)
        out = G.check_tiny_text([sub], min_font=6.0, base_font=8.97,
                                scale=0.536, kind="standalone")
        self.assertEqual(out, [], "chi so nho la typography dung")


class TestCliScaleFlag(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("defect-rabs.tex")

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "tikz_gate.py"), *args],
            capture_output=True, text=True)

    def test_scale_flag_changes_verdict(self):
        """--scale phai lam thay doi so luong G5 tim duoc."""
        a = json.loads(self._run(str(self.pdf), "--json").stdout)
        b = json.loads(self._run(str(self.pdf), "--json", "--scale", "0.5").stdout)
        na = sum(1 for f in a["findings"] if f["code"] == "G5/tiny-text")
        nb = sum(1 for f in b["findings"] if f["code"] == "G5/tiny-text")
        self.assertGreater(nb, na, "thu nho 0.5 phai lo ra nhieu chu qua nho")

    def test_report_carries_page_kind(self):
        d = json.loads(self._run(str(self.pdf), "--json").stdout)
        self.assertIn("pageKind", d["inventory"])
        self.assertIn("warningCount", d)

    def test_rejects_bad_scale(self):
        r = self._run(str(self.pdf), "--json", "--scale", "0")
        self.assertEqual(r.returncode, 2)

class TestG7EdgeEdgeOverlap(unittest.TestCase):
    """G7: hai mui ten chay trung/song song sat nhau -> khong doc duoc duong.

    Phan biet ro voi CAT NHAU: cat vuong goc la binh thuong trong so do,
    chi bao loi khi hai duong chay SONG SONG va SAT nhau tren mot doan dai.
    """

    def test_identical_edges_is_error(self):
        """Hai mui ten trung khit hoan toan."""
        e1 = mk_edge([(60, 18), (168, 18)])
        e2 = mk_edge([(60, 18), (168, 18)])
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G7/edge-edge-overlap")
        self.assertGreater(out[0].evidence["overlapLengthPt"], 100)

    def test_parallel_1pt_apart_is_error(self):
        """Song song cach 1pt: nguoi doc thay mot duong day, khong phan biet duoc."""
        e1 = mk_edge([(60, 89), (168, 89)])
        e2 = mk_edge([(60, 88), (168, 88)])
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(len(out), 1)

    def test_perpendicular_crossing_is_ok(self):
        """REGRESSION: cat vuong goc la BINH THUONG, khong duoc bao loi."""
        e1 = mk_edge([(60, 100), (168, 100)])
        e2 = mk_edge([(114, 60), (114, 140)])
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(out, [], "cat vuong goc khong phai loi bo cuc")

    def test_parallel_far_apart_is_ok(self):
        """Song song nhung cach xa -> hai duong phan biet duoc, hop le."""
        e1 = mk_edge([(60, 100), (168, 100)])
        e2 = mk_edge([(60, 120), (168, 120)])
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(out, [])

    def test_short_touch_below_threshold_is_ok(self):
        """Cham nhau doan rat ngan (goc re) -> khong phai loi."""
        e1 = mk_edge([(100, 100), (110, 100)])
        e2 = mk_edge([(100, 100), (104, 100)])
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(out, [])

    def test_dashed_over_solid_is_ok(self):
        """Duong net dut ve tren duong lien la thu phap co y, khong bao loi."""
        e1 = mk_edge([(60, 100), (168, 100)])
        e2 = mk_edge([(60, 100), (168, 100)])
        e2.dashed = True
        out = G.check_edge_edge([e1, e2])
        self.assertEqual(out, [])


class TestG7RealFixture(unittest.TestCase):
    """G7 tren PDF that: bat 2 ca chong, bo qua ca cat vuong goc."""

    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("edge-overlap.tex")

    def test_catches_two_overlaps_not_the_crossing(self):
        findings, inv, _ = G.analyze(str(self.pdf))
        g7 = [f for f in findings if f.code == "G7/edge-edge-overlap"]
        self.assertEqual(len(g7), 2,
                         "phai bat dung 2 ca chong, khong bat ca cat vuong goc")
        for f in g7:
            self.assertGreater(f.evidence["overlapLengthPt"], 50)


class TestRuleEdgeFiltering(unittest.TestCase):
    """REGRESSION: gach typography cua LaTeX khong phai duong so do.

    Do bang so that tren ban thao: tieuluan p15 co 9 'edge' nhung 0 block,
    0 arrowhead — do la 2 khung chu nhat cua bieu do + gach truc. Gate bao 16
    loi G6 vi cac so lieu 1.10/0.58/... nam tren khung. VietLegalShift p4 co 4
    'edge' ngang la gach PHAN SO cua cong thuc toan.

    Dau hieu phan biet: duong so do co arrowhead SAT dau mut; gach typography
    khong co.
    """

    def test_page_without_blocks_or_heads_has_all_edges_as_rules(self):
        """Trang khong block, khong arrowhead -> moi edge la gach ke."""
        edges = [mk_edge([(130, 225), (130, 573)]),
                 mk_edge([(130, 573), (312, 573)])]
        out = G.rule_edge_indices(edges, blocks=[], heads=[])
        self.assertEqual(out, {0, 1}, "khong co so do thi khong co mui ten nao")

    def test_edge_with_attached_arrowhead_is_not_a_rule(self):
        """Mui ten that: arrowhead nam sat dau mut -> KHONG bi loc."""
        edges = [mk_edge([(216, 68), (216, 96)])]
        head = G.Elem("arrowhead", (214, 92, 218, 97),
                      box(214, 92, 218, 97))
        out = G.rule_edge_indices(edges, blocks=[], heads=[head])
        self.assertNotIn(0, out, "edge co arrowhead sat dau mut la mui ten that")

    def test_diagram_edge_without_head_survives_when_blocks_exist(self):
        """Hinh co block: duong khong dau mui ten van duoc kiem (khong loc oan).

        Trong arch_diagram co duong noi khong ve arrowhead o mot dau; day la
        duong so do that, khong duoc coi la gach ke.
        """
        edges = [mk_edge([(46, 191), (170, 191)])]
        blk = mk_block(40, 100, 200, 180)
        head = G.Elem("arrowhead", (44, 187, 48, 192), box(44, 187, 48, 192))
        out = G.rule_edge_indices(edges, blocks=[blk], heads=[head])
        self.assertNotIn(0, out)

    def test_g6_skips_ignored_edges(self):
        """G6 phai bo qua edge nam trong ignore_edges."""
        sp = mk_span("1.10", 475.5, 267.0, 486.0, 271.7)
        edge = mk_edge([(464.7, 268.7), (477.7, 268.7)])
        without = G.check_label_edge([sp], [edge], [])
        self.assertEqual(len(without), 1, "khong loc thi bao loi")
        withfilter = G.check_label_edge([sp], [edge], [],
                                        ignore_edges={0})
        self.assertEqual(withfilter, [], "loc roi thi khong bao")


class TestGateAfterBuildHook(unittest.TestCase):
    """Hook latexmk: gate tu chay sau moi lan build.

    Da chay THAT tren tieuluan.pdf 28 trang: exit 1, xuat p007.png + p015.png.
    Test nay canh 5 hanh vi hop dong cua hook, khong phai chi syntax.
    """

    HOOK = REPO / "scripts" / "gate_after_build.py"

    @classmethod
    def setUpClass(cls):
        if not cls.HOOK.exists():
            raise unittest.SkipTest("thieu scripts/gate_after_build.py")
        cls.bad = build_fixture("defect-rabs.tex")
        cls.good = build_fixture("good-rabs.tex")

    def _run(self, *args, env_extra=None):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(REPO / "scripts")
        if env_extra:
            env.update(env_extra)
        return subprocess.run([sys.executable, str(self.HOOK), *args],
                              capture_output=True, text=True, env=env)

    def test_dirty_pdf_exits_1(self):
        r = self._run(str(self.bad))
        self.assertEqual(r.returncode, 1, f"co loi -> exit 1\n{r.stdout}{r.stderr}")

    def test_clean_pdf_exits_0(self):
        r = self._run(str(self.good))
        self.assertEqual(r.returncode, 0, f"sach -> exit 0\n{r.stdout}{r.stderr}")

    def test_missing_pdf_exits_2(self):
        r = self._run("/tmp/khong-ton-tai-bao-gio.pdf")
        self.assertEqual(r.returncode, 2)

    def test_gate_soft_does_not_block_build(self):
        """GATE_SOFT=1: van bao loi nhung KHONG chan build (exit 0)."""
        r = self._run(str(self.bad), env_extra={"GATE_SOFT": "1"})
        self.assertEqual(r.returncode, 0, "GATE_SOFT=1 phai exit 0")
        self.assertIn("loi", r.stdout.lower())

    def test_annotates_failing_page(self):
        """Trang loi phai duoc xuat PNG khoanh do."""
        outdir = Path(str(self.bad) + ".gate")
        if outdir.exists():
            for p in outdir.glob("*.png"):
                p.unlink()
        self._run(str(self.bad))
        pngs = sorted(outdir.glob("*.png")) if outdir.exists() else []
        self.assertTrue(pngs, "phai xuat PNG cho trang loi")
        self.assertGreater(pngs[0].stat().st_size, 1000)


class TestUnitConversionBpToTexPt(unittest.TestCase):
    """REGRESSION: PDF ghi co chu bang BIG POINT, TeX dung PRINTER POINT.

    Da verify TAI MAY bang mutool tren VietLegalShift/main.pdf: toan bo Tf
    operand la 5.9776 / 7.9701 / 10.9091 / 11.9552 / 14.3462 / 17.2154 /
    20.6625 — tuc la 6 / 8 / 10.95 / 12 / 14.4 / 17.28 / 20.74 TeX pt.
    Gate cu so 5.9776 < 6.0 roi bao loi: sai 0.37% do lech don vi, va no
    misfire tren MOI co chu nam dung tren nguong, trong MOI file LaTeX.
    """

    def test_factor_is_72_over_7227(self):
        self.assertAlmostEqual(G.BP_TO_TEXPT, 72.27 / 72.0, places=9)

    def test_six_texpt_reads_as_598_bp(self):
        """6.00 TeX pt hien thanh 5.98 trong PDF — quan sat that cua gate."""
        self.assertAlmostEqual(G.to_texpt(5.9776), 6.0, places=3)

    def test_twelve_texpt_reads_as_1196_bp(self):
        self.assertAlmostEqual(G.to_texpt(11.9552), 12.0, places=3)

    def test_598_is_not_below_six_pt_floor(self):
        """Chu 5.98bp = 6.00pt KHONG duoi san 6pt. Day la false positive cu."""
        sp = mk_span("1", 10, 10, 14, 16, size=5.9776)
        sp["font"] = "WZCXRH+CMR6"
        out = G.check_tiny_text([sp], min_font=6.0, base_font=9.9626,
                                kind="document")
        self.assertEqual(out, [], "6.00 TeX pt la dung san, khong phai loi")

    def test_genuinely_tiny_text_still_flagged(self):
        """2.18bp = 2.19pt thi KHONG khop design size nao -> loi that."""
        sp = mk_span("l", 10, 10, 12, 13, size=2.18)
        sp["font"] = "BMQQDV+DejaVuSans"
        out = G.check_tiny_text([sp], min_font=6.0, base_font=9.9626,
                                kind="document")
        self.assertEqual(len(out), 1, "2.19pt phai bao loi")


class TestCmDesignSizes(unittest.TestCase):
    """Co thiet ke Computer Modern: 5/6/7/8/9/10/10.95/12/14.4/17.28/20.74."""

    def test_design_sizes_recognised(self):
        for pt in (5, 6, 7, 8, 9, 10, 10.95, 12):
            self.assertTrue(G.is_cm_design_size(pt), f"{pt}pt la design size")

    def test_non_design_size_rejected(self):
        for pt in (2.188, 2.519, 3.4, 4.2):
            self.assertFalse(G.is_cm_design_size(pt), f"{pt}pt khong phai")


class TestMathExtensionFontExempt(unittest.TestCase):
    """CMEX10 = TeX math family 3 (font ky hieu mo rong).

    Da verify TAI MAY:
      cmex10.pfb dong 52-53: cid 16 = parenleftBig, cid 17 = parenrightBig
      cmex10.tfm: CHARWD 0.597em, CHARHT 0.04em, CHARDP 1.760em
    Dau ngoac SAU 1.76 lan co chu duoi baseline, nen bbox cua no BAO TRUM
    ca cong thuc ben trong. Chong nhan la TAT NHIEN, dung thiet ke TeX.
    """

    def test_cmex_recognised(self):
        """Font CHI chua ky hieu gian kich thuoc -> mien theo TEN font.

        Da do bang tftopl tren may (max CHARHT+CHARDP, don vi em):
          cmex10 3.710  <- bbox bao trum cong thuc, phai mien
          cmsy10 1.710 | msam10 1.465 | msbm10 1.339 | cmmi10 1.000
        Chi cmex/lmex (va cac font *Size* cua OpenType math) vuot 2em.
        """
        for f in ("BGQDBJ+CMEX10", "cmex10", "LMEX10",
                  "STIXSizeOneSym", "XITSSizeOneSym"):
            self.assertTrue(G.is_math_ext_font(f), f)

    def test_ordinary_math_font_not_exempt_by_name(self):
        """CMMI/CMSY/MSAM la font toan CO THUONG -> khong mien theo ten.

        BUG DA GAP (anh Van phat hien bang mat): 'cmmi' tung nam trong regex,
        nen chu 'i' nghieng cua CMMI10 duoc mien oan va gate BO SOT loi that
        'i' chong 'CO' (14.5pt2) trong fig2_turn_geometry.
        """
        for f in ("VEABLN+CMMI10", "XX+CMSY10", "msam10", "msbm10"):
            self.assertFalse(G.is_math_ext_font(f), f)

    def test_text_font_not_exempt(self):
        for f in ("WZCXRH+CMR6", "DejaVuSans", "TimesNewRomanPSMT", ""):
            self.assertFalse(G.is_math_ext_font(f), f)

    def test_inline_math_font_not_exempt_by_name(self):
        """REGRESSION (anh Van phat hien bang mat): CMMI10 KHONG duoc mien.

        CMMI10 la font toan NGHIENG CO THUONG — chua i, j, x, alpha... o co
        binh thuong. Truoc day regex co 'cmmi' nen moi chu 'i' trong cong thuc
        duoc mien khoi G3 -> gate bo sot chinh cho chu do 'CO(i)' de len chu
        'i' trong fig2_turn_geometry, ma mat nguoi thay ngay.

        Font toan OpenType (XITSMath, LatinModernMath) cung vay: mot file chua
        CA chu nghieng thuong LAN ngoac lon, nen mien theo ten la qua rong.
        Phai mien theo HINH HOC (is_oversized_glyph) chu khong theo ten.
        """
        for f in ("VEABLN+CMMI10", "CMMI12", "cmsy10", "XITSMath-Regular",
                  "LatinModernMath-Regular"):
            self.assertFalse(G.is_math_ext_font(f), f)

    def test_oversized_glyph_exempt_by_geometry(self):
        """Ngoac lon nhan dien qua ty le cao/co chu, khong can biet ten font."""
        # CHARDP 1.76em + CHARHT 0.04em => cao ~1.8 lan co chu
        big = mk_span("(", 296, 178, 304, 200, size=11.9552)
        big["font"] = "XITSMath-Regular"
        self.assertTrue(G.is_oversized_glyph(big))
        self.assertTrue(G.is_large_math_glyph(big))

    def test_normal_glyph_not_oversized(self):
        """Chu thuong cao ~1.0 lan co chu -> khong mien."""
        normal = mk_span("i", 25.5, 93.3, 28.9, 103.3, size=9.9626)
        normal["font"] = "VEABLN+CMMI10"
        self.assertFalse(G.is_oversized_glyph(normal))
        self.assertFalse(G.is_large_math_glyph(normal))

    def test_g3_flags_inline_math_over_text(self):
        """Ca THAT trong fig2: 'CO' (Times 6.97pt) de len 'i' (CMMI10 9.96pt).

        Da do tu PDF that: 'i' bbox=(25.5,93.3,28.9,103.3), 'CO'
        bbox=(19.3,95.6,29.0,102.6) -> giao 14.5pt2. Mat nguoi thay ro.
        """
        a = mk_span("i", 25.5, 93.3, 28.9, 103.3, size=9.9626)
        a["font"] = "VEABLN+CMMI10"
        b = mk_span("CO", 19.3, 95.6, 29.0, 102.6, size=6.9738)
        b["font"] = "KHDWKU+TimesNewRomanPSMT"
        out = G.check_label_label([a, b])
        self.assertEqual(len(out), 1, "phai bat duoc chu de len chu")
        self.assertEqual(out[0].code, "G3/label-label-overlap")

    def test_g3_skips_math_ext_glyph(self):
        """nhan 'd' chong '(cid:16)' cua CMEX10 -> khong bao loi."""
        a = mk_span("d", 300, 180, 306, 192)
        a["font"] = "PPLYPY+DejaVuSerif"
        b = mk_span("(cid:16)", 296, 178, 304, 200, size=11.9552)
        b["font"] = "BGQDBJ+CMEX10"
        out = G.check_label_label([a, b])
        self.assertEqual(out, [], "ngoac lon CMEX phai duoc mien")

    def test_g3_still_flags_two_text_labels(self):
        a = mk_span("Overlapping", 60, 100, 160, 112)
        a["font"] = "DejaVuSans"
        b = mk_span("Overlapping", 70, 100, 170, 112)
        b["font"] = "DejaVuSans"
        out = G.check_label_label([a, b])
        self.assertEqual(len(out), 1, "hai nhan chu that van phai bao")

    def test_g5_skips_math_ext_glyph(self):
        sp = mk_span("(cid:16)", 296, 178, 304, 200, size=2.0)
        sp["font"] = "BGQDBJ+CMEX10"
        out = G.check_tiny_text([sp], min_font=6.0, base_font=10.0,
                                kind="document")
        self.assertEqual(out, [], "glyph CMEX: co chu la tham so scale")


class TestContainerDetection(unittest.TestCase):
    """Nhan biet KHUNG BAO bang cau truc (chua tam hinh khac), khong bang dien tich.

    Dung nguong dien tich la sai: mot so do co the co mot node don le rat to
    (vi du block 'Ket luan' chiem ca hang), va no khong phai khung bao.
    """

    def test_frame_containing_two_blocks_is_container(self):
        inner_a = mk_block(20, 20, 80, 50)
        inner_b = mk_block(100, 20, 160, 50)
        frame = mk_block(10, 10, 170, 60)
        got = G.container_indices([inner_a, inner_b, frame])
        self.assertEqual(got, {2}, "chi khung ngoai la container")

    def test_two_sibling_blocks_are_not_containers(self):
        """REGRESSION: hai block canh nhau khong long nhau."""
        a = mk_block(20, 20, 80, 50)
        b = mk_block(100, 20, 160, 50)
        self.assertEqual(G.container_indices([a, b]), set())

    def test_large_lone_block_is_not_container(self):
        """Mot block to nhung khong chua gi -> KHONG phai khung bao."""
        big = mk_block(10, 10, 400, 200)
        far = mk_block(500, 300, 560, 330)
        self.assertEqual(G.container_indices([big, far]), set())

    def test_same_shape_drawn_twice_is_not_container(self):
        """Fill roi stroke cung mot hinh -> bbox trung, khong phai long nhau."""
        a = mk_block(10, 10, 170, 60)
        b = mk_block(10.5, 10.5, 169.5, 59.5)
        self.assertEqual(G.container_indices([a, b]), set())


class TestG8EdgeBorderRun(unittest.TestCase):
    """G8: mui ten chay DOC VIEN khung bao -> hoa vao vien, khong tach duoc.

    G1 khong bat duoc (mui ten khong xuyen than khung), G7 khong bat duoc
    (vien khung la block, khong nam trong danh sach edges).
    """

    def setUp(self):
        # khung bao 10..170 x 10..60, chua hai block con
        self.inner_a = mk_block(20, 20, 80, 50)
        self.inner_b = mk_block(100, 20, 160, 50)
        self.frame = mk_block(10, 10, 170, 60)
        self.shapes = [self.inner_a, self.inner_b, self.frame]

    def test_runs_along_top_border_is_error(self):
        e = mk_edge([(30, 10.5), (150, 10.5)])
        out = G.check_edge_border_run([e], self.shapes)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].code, "G8/edge-border-run")
        self.assertEqual(out[0].evidence["side"], "tren")
        self.assertGreater(out[0].evidence["overlapLengthPt"], 100)

    def test_runs_along_left_border_is_error(self):
        e = mk_edge([(10.8, 15), (10.8, 55)])
        out = G.check_edge_border_run([e], self.shapes)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].evidence["side"], "trai")

    def test_edge_inside_frame_is_ok(self):
        """REGRESSION: duong noi hai node cung nhom di trong long khung -> HOP LE."""
        e = mk_edge([(80, 35), (100, 35)])
        self.assertEqual(G.check_edge_border_run([e], self.shapes), [])

    def test_edge_far_outside_is_ok(self):
        e = mk_edge([(30, 200), (150, 200)])
        self.assertEqual(G.check_edge_border_run([e], self.shapes), [])

    def test_short_touch_below_threshold_is_ok(self):
        """Cham vien mot doan ngan (duong vua roi khoi khung) -> khong phai loi."""
        e = mk_edge([(30, 10.5), (38, 10.5)])
        self.assertEqual(G.check_edge_border_run([e], self.shapes), [])

    def test_perpendicular_crossing_border_is_ok(self):
        """Duong CAT vuong goc qua vien la binh thuong, khong phai chay doc."""
        e = mk_edge([(90, 0), (90, 100)])
        self.assertEqual(G.check_edge_border_run([e], self.shapes), [])

    def test_no_container_means_no_finding(self):
        """Khong co khung bao thi G8 khong co gi de xet."""
        e = mk_edge([(30, 10.5), (150, 10.5)])
        out = G.check_edge_border_run([e], [self.inner_a, self.inner_b])
        self.assertEqual(out, [])

    def test_ignore_edges_is_respected(self):
        e = mk_edge([(30, 10.5), (150, 10.5)])
        out = G.check_edge_border_run([e], self.shapes, ignore_edges={0})
        self.assertEqual(out, [])


class TestG1IgnoresContainers(unittest.TestCase):
    """REGRESSION do bang so that tren fixture border-run.pdf.

    Mui ten noi hai node NAM TRONG cung mot khung nhom bat buoc phai di qua
    LONG khung do. G1 doc phan giao ay thanh "xuyen qua block" va bao loi tren
    MOI so do dung fit+backgrounds. Do that truoc khi sua: edge
    [(64.6, 253.6) -> (81.8, 253.6)] bi bao xuyen block #10 17.2pt, ma block
    #10 chinh la khung bao.
    """

    def setUp(self):
        self.inner_a = mk_block(20, 20, 80, 50)
        self.inner_b = mk_block(100, 20, 160, 50)
        self.frame = mk_block(10, 10, 170, 60)
        self.blocks = [self.inner_a, self.inner_b, self.frame]

    def test_edge_crossing_container_body_is_not_g1(self):
        e = mk_edge([(80, 35), (100, 35)])
        out = G.check_edge_through_block([e], self.blocks, ignore_blocks={2})
        self.assertEqual(out, [], "di qua long khung nhom khong phai loi G1")

    def test_edge_through_ordinary_block_still_flagged(self):
        """Bo qua khung bao KHONG duoc lam mat kha nang bat loi that."""
        e = mk_edge([(0, 35), (200, 35)])
        out = G.check_edge_through_block([e], self.blocks, ignore_blocks={2})
        codes = [f.code for f in out]
        self.assertTrue(codes, "van phai bat mui ten xuyen block thuong")
        self.assertTrue(all(c == "G1/edge-through-block" for c in codes))
        hit = {f.evidence["blockIndex"] for f in out}
        self.assertNotIn(2, hit, "khung bao khong duoc bao")


class TestG8RealFixture(unittest.TestCase):
    """G8 tren PDF that: bat 2 ca chay doc vien, khong bao ca di trong long."""

    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("border-run.tex")

    def test_catches_two_border_runs(self):
        findings, inv, _ = G.analyze(str(self.pdf))
        g8 = [f for f in findings if f.code == "G8/edge-border-run"]
        self.assertEqual(len(g8), 2, "phai bat dung 2 ca chay doc vien")
        self.assertEqual(inv["containers"], 3, "3 khung nhom trong fixture")
        for f in g8:
            self.assertGreater(f.evidence["overlapLengthPt"],
                               G.EDGE_BORDER_MIN_LEN)

    def test_no_g1_false_positive_on_container(self):
        """Ca 3 cua fixture von HOP LE: khong duoc sinh loi G1 nao."""
        findings, _, _ = G.analyze(str(self.pdf))
        g1 = [f for f in findings if f.code == "G1/edge-through-block"]
        self.assertEqual(g1, [], "khung nhom khong duoc bao G1")


class TestRot90FlagIsWired(unittest.TestCase):
    """REGRESSION: co `rot90` tung la CO CHET.

    `real_font_size()` doc `span["rot90"]`, nhung khong backend nao set co do,
    nen ban va G5 cho nhan truc doc hoan toan vo hieu. Test nay canh viec ca
    hai backend deu phai dat khoa `rot90` vao moi span.
    """

    @classmethod
    def setUpClass(cls):
        cls.pdf = build_fixture("bad.tex")

    def test_every_span_has_rot90_key(self):
        page, holder, close = G._open_page(str(self.pdf), 0)
        try:
            spans = G.text_spans(page)
        finally:
            close()
        self.assertTrue(spans, "fixture phai co nhan")
        missing = [s["text"] for s in spans if "rot90" not in s]
        self.assertEqual(missing, [], "moi span phai co khoa rot90")

    def test_real_font_size_uses_bbox_when_rotated(self):
        """Chu quay 90 do: co chu that lay tu be ngang bbox, khong tu `size`."""
        sp = mk_span("l", 507.8, 481.2, 515.6, 483.4, size=2.18)
        self.assertAlmostEqual(G.real_font_size(sp), 2.18, places=2)
        sp["rot90"] = True
        self.assertAlmostEqual(G.real_font_size(sp), 7.8, places=1)

    def test_horizontal_span_unchanged(self):
        sp = mk_span("abc", 100, 100, 130, 110, size=10.0)
        sp["rot90"] = False
        self.assertAlmostEqual(G.real_font_size(sp), 10.0, places=6)


if __name__ == "__main__":
    unittest.main(verbosity=2)
