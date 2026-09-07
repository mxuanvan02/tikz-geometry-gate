#!/usr/bin/env python3
"""Doi chieu clone <-> ban cai skill. Exit 0 khi khop, 1 khi lech, 2 khi dung sai.

Ly do co script nay: mot lan scan \"0 finding G8/G9 tren hinh that\" duoc suy ra
tu ban cai CHUA duoc sync (mtime 09-06, thieu ca G8 lan G9). Ket luan \"hinh
sach\" khi ay vo gia tri. Moi lan sync xong PHAI chay script nay; moi lan tin
ket qua scan PHAI chay script nay truoc.

Khong dung `diff -qr` lam cong cu chinh: no khong phan biet file sinh ra luc
chay (fixtures/_build, __pycache__) voi file that su lech, va no khong kiem
`--list-checks` — tuc la khong kiem HANH VI, chi kiem byte.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

#: Nguon su that cua "file nao thuoc skill": moi file nguon trong clone,
#: khong phai danh sach cung. Danh sach cung vua miss `references/*.md`
#: (4 file tai lieu chi ton tai tren dia, chua bao gio duoc commit) va se
#: miss moi file moi ve sau. Glob o day la hop dong: them file dung cho,
#: script tu bat.
GLOBS = (
    "SKILL.md",
    "README.md",
    "LICENSE",
    "requirements.txt",
    "scripts/*.py",
    "test/*.py",
    "fixtures/*.tex",
    "references/*.md",
    "templates/*",
)

DEFAULT_INSTALL = Path.home() / ".hermes" / "skills" / "tikz-geometry-gate"


def tracked_relpaths(root: Path) -> list[str]:
    out: set[str] = set()
    for pattern in GLOBS:
        for p in root.glob(pattern):
            if p.is_file():
                out.add(str(p.relative_to(root)))
    return sorted(out)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def list_checks(gate: Path) -> list[str]:
    r = subprocess.run(
        [sys.executable, str(gate), "--list-checks"],
        capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"--list-checks exit {r.returncode}: {r.stderr or r.stdout}")
    data = json.loads(r.stdout)
    return [c["id"] for c in data["checks"]]


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    clone = Path(argv[0]).resolve() if argv else Path(__file__).resolve().parent.parent
    install = Path(argv[1]).resolve() if len(argv) > 1 else DEFAULT_INSTALL

    if not clone.is_dir() or not install.is_dir():
        print(json.dumps({"ok": False, "stage": "args",
                          "error": f"thieu thu muc: clone={clone} install={install}"},
                         ensure_ascii=False))
        return 2

    # Hop cua file o CA HAI BEN: file chi co o mot ben phai bi bao thieu,
    # khong duoc bo qua. Lay glob tu clone lam goc, roi them file o install
    # khop cung pattern — de bat ca file moi o clone chua dua sang, lan file
    # chi co o ban cai (nhu references/*.md truoc khi duoc commit).
    rels = set(tracked_relpaths(clone)) | set(tracked_relpaths(install))
    missing_clone, missing_install, mismatch = [], [], []
    for rel in sorted(rels):
        a, b = clone / rel, install / rel
        if not a.exists():
            missing_clone.append(rel)
            continue
        if not b.exists():
            missing_install.append(rel)
            continue
        if sha256(a) != sha256(b):
            mismatch.append(rel)

    clone_ids = list_checks(clone / "scripts" / "tikz_gate.py")
    install_ids = list_checks(install / "scripts" / "tikz_gate.py")
    checks_match = clone_ids == install_ids

    ok = not (missing_clone or missing_install or mismatch) and checks_match
    report = {
        "ok": ok,
        "clone": str(clone),
        "install": str(install),
        "checksClone": clone_ids,
        "checksInstall": install_ids,
        "missingInClone": missing_clone,
        "missingInInstall": missing_install,
        "shaMismatch": mismatch,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
