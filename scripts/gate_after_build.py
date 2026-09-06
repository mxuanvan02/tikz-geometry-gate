#!/usr/bin/env python3
"""gate-after-build: chay tikz-geometry-gate sau moi lan build LaTeX.

Dung duoc 3 cach:

1) Hook trong .latexmkrc (khuyen dung):
       $success_cmd = "python3 /path/scripts/gate_after_build.py %D";
       $failure_cmd = "";
   %D la ten file PDF latexmk vua tao.

2) Goi tay sau build:
       latexmk -pdf main.tex && python3 scripts/gate_after_build.py main.pdf

3) Trong Makefile:
       build: ; latexmk -pdf $(DOC).tex && $(GATE_HOOK) $(DOC).pdf

Hanh vi:
  - Quet MOI trang cua PDF (khong chi trang 0).
  - In bang gon gon: trang nao loi gi.
  - Xuat PNG khoanh do vao <pdf>.gate/ cho tung trang co loi.
  - Exit 0 khi sach, 1 khi co loi, 2 khi loi dung tool.
  - GATE_SOFT=1 -> luon exit 0 (chi canh bao, khong chan build).
  - GATE_ARGS   -> tham so them truyen cho gate, vi du "--min-font 7".
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
GATE = HERE / "tikz_gate.py"


def npages(pdf: Path) -> int:
    """So trang, uu tien pdfinfo; fallback ve backend PDF cua gate."""
    try:
        r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True,
                           text=True, timeout=60)
        for ln in r.stdout.splitlines():
            if ln.startswith("Pages:"):
                return int(ln.split()[-1])
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        pass
    try:
        sys.path.insert(0, str(HERE))
        import tikz_gate as G  # noqa
        if G._active_backend() == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(str(pdf)) as d:
                return len(d.pages)
        import pymupdf
        with pymupdf.open(str(pdf)) as d:
            return d.page_count
    except Exception:
        return 1


def run_page(pdf: Path, page: int, extra: list[str], annot: Path | None):
    cmd = [sys.executable, str(GATE), str(pdf), "--json", "--page", str(page)]
    cmd += extra
    if annot is not None:
        cmd += ["--annotate", str(annot)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(r.stdout), r.returncode
    except json.JSONDecodeError:
        return None, r.returncode


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("gate-after-build: can duong dan PDF", file=sys.stderr)
        return 2
    pdf = Path(argv[0]).resolve()
    if not pdf.exists():
        print(f"gate-after-build: khong thay {pdf}", file=sys.stderr)
        return 2

    extra = argv[1:] + (os.environ.get("GATE_ARGS", "").split()
                        if os.environ.get("GATE_ARGS") else [])
    soft = os.environ.get("GATE_SOFT", "") == "1"
    outdir = pdf.with_suffix(pdf.suffix + ".gate")

    n = npages(pdf)
    rows, total_err, total_warn, tool_err = [], 0, 0, 0
    for pg in range(n):
        annot = None
        data, rc = run_page(pdf, pg, extra, None)
        if data is None or "findings" not in data:
            tool_err += 1
            rows.append((pg, "ERR", Counter(), 0, 0, None))
            continue
        errs = [f for f in data["findings"] if f["severity"] == "error"]
        warns = [f for f in data["findings"] if f["severity"] == "warning"]
        total_err += len(errs)
        total_warn += len(warns)
        png = None
        if errs:
            outdir.mkdir(exist_ok=True)
            annot = outdir / f"p{pg:03d}.png"
            _, _ = run_page(pdf, pg, extra, annot)
            png = annot if annot.exists() else None
        codes = Counter(f["code"] for f in errs)
        rows.append((pg, "FAIL" if errs else "ok", codes,
                     len(errs), len(warns), png))

    bad = [r for r in rows if r[1] != "ok"]
    print(f"tikz-geometry-gate: {pdf.name} — {n} trang, "
          f"{len(bad)} trang co van de, {total_err} loi, {total_warn} canh bao")
    for pg, kq, codes, ne, nw, png in rows:
        if kq == "ok":
            continue
        detail = ", ".join(f"{c.split('/')[1]}={v}"
                           for c, v in sorted(codes.items())) or "loi dung tool"
        line = f"  trang {pg}: {kq}  {ne} loi  {detail}"
        if png:
            line += f"  -> {png}"
        print(line)
    if not bad:
        print("  hinh hoc sach.")

    if tool_err:
        return 2
    if total_err and not soft:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
