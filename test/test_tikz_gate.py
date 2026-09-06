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


if __name__ == "__main__":
    unittest.main(verbosity=2)
