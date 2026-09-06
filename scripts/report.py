#!/usr/bin/env python3
"""In bao cao gon tu output JSON cua tikz_gate."""
import json
import subprocess
import sys
from collections import Counter

pdf = sys.argv[1] if len(sys.argv) > 1 else "fixtures/orig-wrap.pdf"
res = subprocess.run(
    [".venv/bin/python", "tikz_gate.py", pdf, "--json"],
    capture_output=True, text=True, cwd="/home/hitokiri/tikzgate")
try:
    data = json.loads(res.stdout)
except json.JSONDecodeError:
    print("KHONG PARSE DUOC JSON")
    print("STDOUT:", res.stdout[:2000])
    print("STDERR:", res.stderr[:2000])
    sys.exit(1)

print(f"=== {pdf} ===")
print(f"exit={res.returncode}  ok={data.get('ok')}")
inv = data.get("inventory")
if inv:
    print("--- INVENTORY ---")
    for k, v in inv.items():
        print(f"  {k:16} {v}")
if "error" in data:
    print("  ERROR:", data["error"])

findings = data.get("findings", [])
print(f"--- {data.get('errorCount', len(findings))} FINDING ---")
for code, n in Counter(f["code"] for f in findings).most_common():
    print(f"  {n:3}  {code}")
print("--- CHI TIET ---")
for f in findings:
    ev = f.get("evidence", {})
    bits = []
    for key in ("text", "textA", "textB", "sizePt", "insideLengthPt",
                "crossLengthPt", "overlapFraction", "overlapAreaPt2",
                "outsideAreaPt2"):
        if key in ev:
            bits.append(f"{key}={ev[key]!r}")
    print(f"  {f['code']:34} {' '.join(bits)}")
