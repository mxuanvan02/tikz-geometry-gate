# tikz-geometry-gate

Cổng duyệt hình học tự động cho hình TikZ/LaTeX.

Đọc toạ độ **thật** từ PDF content stream — không dùng ảnh, không dùng vision model —
rồi phát hiện 6 nhóm lỗi bố cục và trả exit code khác 0 khi fail.

## Vì sao cần

Không có tool mã nguồn mở nào làm việc này:

| Tool | Làm gì | Thiếu gì |
|---|---|---|
| Graphviz `overlap=false`, D2/TALA, ELK | *tránh* overlap khi sinh layout | không kiểm tra hình đã vẽ |
| `aclpubcheck` | lề, font size, font embedding | không kiểm mũi tên đè block |
| TikZ | vẽ đúng những gì bạn ra lệnh | không có collision detection |

TikZ vẽ đẹp và phù hợp học thuật (font khớp bản thảo, math thật, vector cùng engine với
văn bản). Vấn đề duy nhất: không ai chặn khi mũi tên đi xuyên qua block hoặc qua nhãn.
Skill này lấp đúng chỗ đó.

## Cài

```bash
pip install -r requirements.txt   # pymupdf + shapely
```

## Dùng

```bash
pdflatex -interaction=nonstopmode figure.tex
python scripts/tikz_gate.py figure.pdf --json
python scripts/tikz_gate.py figure.pdf --json --annotate loi.png   # khoanh đỏ vùng lỗi
```

Exit: `0` pass, `1` có lỗi, `2` lỗi dùng tool.

## Chín nhóm check

| Mã | Bắt gì |
|---|---|
| `G1/edge-through-block` | mũi tên xuyên/đè block không phải đầu mút (miễn khung bao) |
| `G2/label-block-straddle` | nhãn chồng viền block |
| `G3/label-label-overlap` | hai nhãn chồng nhau |
| `G4/out-of-bounds` | phần tử tràn khỏi trang |
| `G5/tiny-text` | chữ nhỏ hơn sàn (bắt chữ teo do `\resizebox`) |
| `G6/label-edge-clash` | nhãn bị đường đi xuyên qua, không có mask che |
| `G7/edge-edge-overlap` | hai mũi tên chạy trùng/song song sát nhau trên đoạn dài |
| `G8/edge-border-run` | mũi tên chạy dọc viền khung bao (`\node[fit=…]`), hoà vào viền nhóm |
| `G9/route-micro-step` | bậc thang tí hon giữa hai đoạn dài (trông như lỗi render) |
| `G9/route-axis-jitter` | route định là vuông góc nhưng một đoạn lệch vài phần độ |

## Chọn check và ngưỡng

```bash
python scripts/tikz_gate.py --list-checks               # danh sách check + tên ngưỡng
python scripts/tikz_gate.py fig.pdf --only G1,G8        # chỉ chạy hai check
python scripts/tikz_gate.py fig.pdf --skip G5
python scripts/tikz_gate.py fig.pdf --config nguong.json
```

`--config` nhận object phẳng `{tên: số > 0}`. Khoá sai hoặc giá trị không hợp lệ → **exit 2**, không im lặng bỏ qua.

## Output

```json
{
  "schemaVersion": 1,
  "tool": "tikz-geometry-gate",
  "ok": false,
  "errorCount": 2,
  "inventory": {"blocks": 5, "edges": 8, "labels": 64, "minFontPt": 4.98},
  "findings": [
    {
      "code": "G6/label-edge-clash",
      "severity": "error",
      "message": "nhan 'Polling' de len mui ten #5 (8.0pt duong di qua chu)",
      "evidence": {
        "labelBbox": [76.9, 193.8, 103.1, 202.8],
        "edgeIndex": 5,
        "crossLengthPt": 8.0,
        "edgeZOrder": 16,
        "staleMaskZOrders": [13]
      },
      "fixes": ["them mask trang phia sau nhan (fill=white) va dat node SAU duong", "..."]
    }
  ]
}
```

Mỗi finding có `evidence` kèm toạ độ chính xác và `fixes` gợi ý — sửa được ngay, không phải đoán.

## Bẫy quan trọng nhất: thứ tự vẽ

Mask trắng chỉ che được đường nếu vẽ **SAU** đường trong content stream.
`node[fill=white]` gắn trong một `\draw` sẽ vẽ trước các `\draw` phía sau → đường vẫn đè lên chữ.

```latex
% SAI — mask vẽ trước, đường sau vẫn đè lên
\draw[thick] (a.west) -- (0,-2.5) node[midway, fill=white] {Nhãn};
\draw[->] (c.east) -- (2,0) -- (2,-5.1) -- (d.south);

% ĐÚNG — node riêng ở cuối tikzpicture
\draw[thick] (a.west) -- (0,-2.5);
\draw[->] (c.east) -- (2,0) -- (2,-5.1) -- (d.south);
\node[fill=white, inner sep=2pt, align=center] at (1.9,-2.5) {Nhãn};
```

Gate so `zorder` mask với `zorder` edge. Bản đầu tiên không làm vậy nên báo `ok=true`
cho hình vẫn lỗi — có test hồi quy canh đúng trường hợp này.

## Test

```bash
python -m unittest discover -s test -t . -v
```

52 test. Fixture PDF được dựng từ `.tex` nên chạy được trên máy sạch (cần `pdflatex` + tikz).

## Hạn chế

1. Heuristic G1 chưa kiểm chứng trên hình có node lồng nhau nhiều tầng. Đường lùi:
   xuất bbox từ TikZ bằng `\pgfpointanchor` + `remember picture` (2 lượt compile).
2. Bézier xấp xỉ bằng 4 điểm control → mũi tên `bend` cong mạnh có thể lệch vài pt.
3. PyMuPDF là **AGPL-3.0**. Chạy nội bộ thì không sao; nếu public thì đổi sang
   `pdfplumber` (MIT) — mất khả năng phân giải Bézier tốt.

## License

MIT (code trong repo này). Lưu ý PyMuPDF là AGPL-3.0.
