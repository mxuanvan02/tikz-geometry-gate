---
name: tikz-geometry-gate
description: Cổng duyệt hình học tự động cho hình TikZ/LaTeX. Đọc toạ độ thật từ PDF content stream (không dùng ảnh, không dùng vision) để phát hiện mũi tên xuyên block, nhãn chồng nhau, nhãn bị đường đi đè, phần tử tràn trang, và chữ teo dưới sàn. Dùng khi cần kiểm tra hình TikZ trước khi nộp bản thảo, khi hình có mũi tên/nhãn phức tạp, hoặc khi muốn gate hình học trong CI.
license: MIT
metadata:
  version: "1.0"
  author: hitokiri
---

# TikZ Geometry Gate

Cổng duyệt hình học cho hình TikZ. Giữ TikZ để vẽ (font khớp bản thảo, math thật, vector cùng engine), thêm máy soi lỗi bố cục.

Không có tool mã nguồn mở nào làm việc này: Graphviz/D2/ELK chỉ *tránh* overlap khi layout, `aclpubcheck` chỉ kiểm lề + font size, TikZ không có collision detection. Skill này lấp khoảng trống đó.

## Khi nào dùng

- Trước khi nộp bản thảo có hình TikZ
- Hình có nhiều mũi tên đi vòng, dễ cắt qua block hoặc nhãn
- Hình dùng `\resizebox` (nguy cơ chữ teo dưới sàn đọc được)
- Muốn gate trong CI: exit code `!= 0` khi có lỗi

## Cách chạy

```bash
# 1. Compile hình ra PDF (standalone hoặc trang bản thảo)
pdflatex -interaction=nonstopmode figure.tex

# 2. Chạy gate
python scripts/tikz_gate.py figure.pdf --json

# 3. Xuất ảnh khoanh đỏ vùng lỗi để soi bằng mắt
python scripts/tikz_gate.py figure.pdf --json --annotate loi.png
```

Exit code: `0` pass, `1` có lỗi, `2` lỗi dùng tool.

Biến môi trường: `TIKZGATE_PDF_BACKEND=pymupdf` để đổi backend.

Tuỳ chọn: `--min-font 6` (sàn chữ, pt), `--scale 0.46` (hệ số `\resizebox`/`\includegraphics` khi nhúng hình rời), `--eps 6` (bán kính bỏ qua quanh đầu mút), `--page 0`, `--strict` (coi warning là lỗi).

Gate tự nhận khổ trang: `pageKind=document` (khớp A4/letter/beamer → font đo được là font thật) hoặc `pageKind=standalone` (hình crop rời → cần `--scale` mới kết luận được về font).

## Sáu nhóm check

| Mã | Bắt gì |
|---|---|
| `G1/edge-through-block` | mũi tên xuyên/đè block không phải đầu mút |
| `G2/label-block-straddle` | nhãn chồng viền block (một phần trong, một phần ngoài) |
| `G3/label-label-overlap` | hai nhãn chồng nhau |
| `G4/out-of-bounds` | phần tử tràn khỏi trang |
| `G5/tiny-text` | chữ nhỏ hơn sàn (bắt được chữ teo do `\resizebox`) |
| `G6/label-edge-clash` | nhãn bị đường đi xuyên qua, không có mask che |

## Nguyên lý G1 (quan trọng nhất)

PDF không giữ ID node, nên không biết mũi tên nào *thuộc về* block nào. Heuristic thay thế:

> Mũi tên được phép giao vùng trong của block **chỉ khi** điểm giao nằm trong bán kính `eps` của một trong hai đầu mút. Mọi giao ở giữa thân mũi tên là **lỗi**.

Vì mũi tên hợp lệ luôn bắt đầu/kết thúc ở *viền* block, còn mũi tên đè sai luôn cắt *ngang thân*. Nhờ vậy không cần trích metadata từ `.tex`.

## Phân loại phần tử từ PDF

`page.get_drawings()` cho từng vector item. Quy tắc:

- `type=fs` hoặc `f` diện tích ≥ `BLOCK_MIN_AREA` → **block**; nếu `dashes` khác rỗng → **boundary**
- `type=s` (stroke-only) → **edge** (mũi tên, đường nối)
- `type=f` cạnh ≤ `ARROWHEAD_MAX` → **arrowhead**
- `type=f` fill trắng → **mask** (nền che sau nhãn)
- text span từ `get_text("rawdict")` → **label**, kèm `size` và `bbox`

## Bẫy đã gặp (đọc trước khi sửa gate)

**1. Thứ tự vẽ quyết định mask có tác dụng hay không.** Đây là bug nghiêm trọng nhất từng có trong skill này. Mask trắng chỉ che được đường nếu nó được vẽ **SAU** đường trong content stream. Trong TikZ, `node[fill=white]` gắn *trong* một `\draw` sẽ vẽ trước các `\draw` phía sau nó → đường vẫn đè lên chữ. Gate phải so `zorder` của mask với `zorder` của edge; nếu không sẽ báo `ok=true` cho hình vẫn lỗi (false negative).

Cách sửa hình đúng: tách nhãn thành `\node` riêng đặt ở **cuối** `tikzpicture`, sau mọi `\draw`:

```latex
% Sai: mask vẽ trước đường phía sau
\draw[thick] (a.west) -- (0,-2.5)
  node[midway, fill=white] {Nhãn};
\draw[->] (0,-2.5) -- (b.south);
\draw[->] (c.east) -- (2,0) -- (2,-5.1) -- (d.south);  % đường này đè lên mask

% Đúng: node riêng ở cuối
\draw[thick] (a.west) -- (0,-2.5);
\draw[->] (0,-2.5) -- (b.south);
\draw[->] (c.east) -- (2,0) -- (2,-5.1) -- (d.south);
% ... mọi \draw khác ...
\node[fill=white, inner sep=2pt, align=center] at (1.9,-2.5) {Nhãn};
```

**2. Dấu tổ hợp không phải lỗi chồng nhãn.** TeX vẽ `\hat{x}` và nhiều chữ Việt bằng cách đặt dấu *lên trên* ký tự gốc → hai span chồng nhau gần hoàn toàn. Không lọc thì gate báo lỗi ở mọi công thức và mọi chữ có dấu. Xem `_is_accent_pair`.

**3. Subscript/superscript vốn dĩ nhỏ hơn body font.** `R_t` ở 5.98pt với body 8.97pt là typography đúng, không phải lỗi. So theo *tỉ lệ* với body font (`SUBSCRIPT_FLOOR_RATIO`), không so số tuyệt đối. Body font lấy theo **mode** (size phổ biến nhất), không lấy max — vì tiêu đề lớn sẽ làm lệch ngưỡng.

**4. Mask TikZ không bọc trọn bbox chữ.** `inner sep` nhỏ nên mask che ~80% diện tích span. Ngưỡng `MASK_COVER_RATIO = 0.75`, không đòi bọc trọn.

**5. Bézier xấp xỉ bằng 4 điểm control.** Mũi tên `bend left` cong mạnh có thể lệch vài pt. Nếu cần chính xác: chuyển PDF → SVG bằng `dvisvgm` rồi dùng `svgpathtools.Path.intersect`.

**6. `pdftotext` không dùng để kiểm chữ bị mất.** Nó tách chuỗi ở ranh giới text-run, `Chuẩn hóa` thành `Chuẩ` + `n hóa`. Kiểm trên SVG hoặc trên `rawdict` span.

**7. Không sort char theo toạ độ khi gom span (backend pdfplumber).** `page.chars` đã
theo thứ tự content stream. Sort lại theo `(top, x0)` sẽ trộn hai nhãn *chồng nhau*
ở cùng dòng thành một span → G3 không còn gì để so → **false negative**.

**8. Chặn char nhảy lùi khi gom span.** Điều kiện gộp phải là `0 <= gap <= ngưỡng`.
Nếu chỉ viết `gap <= ngưỡng` thì char của nhãn thứ hai (x0 nhảy lùi, gap âm) vẫn thoả,
hai nhãn chồng nhau bị gộp thành một span và lỗi biến mất. Đây là bug đã làm gate bỏ
sót 5 lỗi G3 + 2 lỗi G6 trên fixture `bad.tex`.

**7. Số pt đo trên hình rời KHÔNG phải font người đọc thấy.** Đo bằng số thật: cùng hình `arch_diagram`, font nhỏ nhất trên hình standalone là **4.98pt**, nhưng khi nhúng vào trang A4 qua `\resizebox{0.46\linewidth}` chỉ còn **2.67pt** (tỉ lệ 0.536). Áp sàn 6pt tuyệt đối lên hình rời vừa bỏ sót (hình rời 6.5pt → thật ra 3.5pt) vừa báo oan. Quy tắc hiện tại:

- trang khớp preset (A4/letter/beamer) → `kind=document`, font đo được là font thật → `severity=error`;
- hình rời + biết `--scale` → quy đổi `font_thật = size × scale` → `severity=error`;
- hình rời + **không** biết scale → `severity=warning`, không fail (trừ `--strict`).

Chính xác nhất: chạy gate trên **trang tài liệu đã build**, không phải trên hình crop.

**8. Preset khổ trang phải lấy từ số thật, không từ ký ức.** Beamer đổi kích thước theo `aspectratio`: 16:9 là **453.5×255.1pt** (160×90mm), 4:3 là **362.8×272.1pt** (128×96mm). Khai sai một preset làm slide thật bị nhận là `standalone` → mọi lỗi font trên slide tụt xuống warning và bị bỏ qua âm thầm. Kiểm bằng cách compile `\documentclass[aspectratio=169]{beamer}` rồi `pdfinfo`.

## Khi heuristic G1 sai

Nếu hình có node lồng nhau phức tạp và G1 báo quá nhiều dương tính giả, xuất ground truth từ TikZ thay vì đoán:

```latex
\begin{tikzpicture}[remember picture]
  ...
  \foreach \n in {a,b,c}{%
    \pgfpointanchor{\n}{south west}\pgfgetlastxy{\sx}{\sy}%
    \pgfpointanchor{\n}{north east}\pgfgetlastxy{\ex}{\ey}%
    \immediate\write\bboxfile{\n \space \sx \space \sy \space \ex \space \ey}%
  }
\end{tikzpicture}
```

Cần 2 lượt compile. Chỉ làm khi heuristic thất bại — đừng làm ngay từ đầu.

## Test

```bash
python -m unittest discover -s test -t . -v
```

52 test, gồm test hồi quy cho bug thứ tự vẽ và test parity giữa hai backend. Fixture PDF được dựng từ `.tex` trong `fixtures/` nên repo chạy được trên máy sạch (chỉ cần `pdflatex` + tikz).

## Phụ thuộc và backend

```
pdfplumber>=0.11   # MIT — backend mặc định
shapely>=2.0
pillow>=10.0       # tuỳ chọn, để --annotate chạy khi không có pymupdf
```

Hai backend đọc PDF, **cùng kết quả** (có test parity canh):

| Backend | License | Khi nào dùng |
|---|---|---|
| `pdfplumber` | MIT | **mặc định** — dùng được cho tool public |
| `pymupdf` | AGPL-3.0 | nhanh hơn; bật bằng `TIKZGATE_PDF_BACKEND=pymupdf` |

Cả hai đều phải cho **zorder** (thứ tự vẽ trong content stream). pdfplumber không có
field zorder sẵn — phải lấy qua `page.layout` (giữ đúng thứ tự stream), **không** dùng
`page.rects` / `page.lines` / `page.curves` vì các list đó tách theo loại, mất thứ tự
tương đối giữa mask và edge. Mất zorder là mất luôn check G6 mask (xem bẫy 1).

## Kết hợp với tool khác

- `aclpubcheck` (https://github.com/acl-org/aclpubcheck): kiểm lề + font size + font embedding theo chuẩn hội nghị. Bổ sung cho G4/G5.
- `diff-pdf`: chặn thay đổi ngoài ý muốn ở hình đã duyệt bằng mắt (regression gate).
- `tikzscale`: thay `\resizebox` để chữ không teo — phòng bệnh cho G5.
- Grep `Overfull \hbox` trong log LaTeX: gate 1 dòng, miễn phí.

## Quy trình nghiệm thu hình TikZ

1. Compile ra PDF.
2. Chạy gate, sửa theo `evidence` (có toạ độ chính xác) và `fixes`.
3. Sửa xong **build lại và chạy gate lại** — sửa `.tex` không có nghĩa là hết lỗi.
4. Xuất `--annotate` và soi bằng mắt. Gate chỉ chứng minh hình học; thẩm mỹ vẫn cần người xem.
5. Kiểm `pdfimages -list` trống (vector thuần) và `pdffonts` nhúng đủ.
