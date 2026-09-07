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

## Tám nhóm check

| Mã | Bắt gì |
|---|---|
| `G1/edge-through-block` | mũi tên xuyên/đè block không phải đầu mút |
| `G2/label-block-straddle` | nhãn chồng viền block (một phần trong, một phần ngoài) |
| `G3/label-label-overlap` | hai nhãn chồng nhau |
| `G4/out-of-bounds` | phần tử tràn khỏi trang |
| `G5/tiny-text` | chữ nhỏ hơn sàn (bắt được chữ teo do `\resizebox`) |
| `G6/label-edge-clash` | nhãn bị đường đi xuyên qua, không có mask che |
| `G7/edge-edge-overlap` | hai mũi tên chạy trùng/song song sát nhau trên đoạn dài |
| `G8/edge-border-run` | mũi tên chạy dọc viền khung bao (`\node[fit=…]`), hoà vào viền nhóm |

## Nguyên lý G1 (quan trọng nhất)

PDF không giữ ID node, nên không biết mũi tên nào *thuộc về* block nào. Heuristic thay thế:

> Mũi tên được phép giao vùng trong của block **chỉ khi** điểm giao nằm trong bán kính `eps` của một trong hai đầu mút. Mọi giao ở giữa thân mũi tên là **lỗi**.

Vì mũi tên hợp lệ luôn bắt đầu/kết thúc ở *viền* block, còn mũi tên đè sai luôn cắt *ngang thân*. Nhờ vậy không cần trích metadata từ `.tex`.

### Ngoại lệ bắt buộc: khung bao

Heuristic trên **sai** với khung nhóm (`\node[fit=…]` + thư viện `backgrounds`). Đường nối hai node *nằm trong cùng một nhóm* buộc phải đi qua lòng khung, nên G1 đọc phần giao đó thành "xuyên qua block" và báo lỗi trên mọi sơ đồ dùng `fit`. Đo bằng số thật trên `fixtures/border-run.pdf` trước khi sửa: edge `[(64.6, 253.6) → (81.8, 253.6)]` bị báo xuyên block #10 17.2pt, mà block #10 chính là khung bao.

`container_indices()` nhận diện khung bao bằng **cấu trúc**: một hình là khung bao khi *tâm* của hình khác nằm trong lòng nó. Không dùng ngưỡng diện tích — sơ đồ có một node đơn lẻ rất to sẽ bị coi oan là khung bao, và G8 sẽ báo sai mọi mũi tên chạm vào node đó. Không dùng phần giao diện tích — hai block cạnh nhau có thể chạm viền nhau do làm tròn góc, nhưng tâm thì không bao giờ nằm trong nhau.

Khung bao có check riêng là **G8**, đúng bản chất hơn: vấn đề của khung nhóm không phải bị xuyên qua, mà là *bị hoà vào viền*.

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

## Gate tự động sau mỗi lần build (latexmk)

```bash
# chay tay tren PDF nhieu trang
python scripts/gate_after_build.py duong-dan.pdf

# bien moi truong
GATE_SOFT=1   # co loi van exit 0 (canh bao, khong chan build)
GATE_ARGS="--min-font 7 --scale 0.46"   # truyen tham so cho gate
```

Cắm vào `latexmk`: copy `templates/latexmkrc.example` thành `.latexmkrc` trong
thư mục dự án. Hook quét **mọi trang**, xuất PNG khoanh đỏ vào
`<ten>.pdf.gate/pNNN.png`, exit `1` khi có lỗi (trừ `GATE_SOFT=1`), exit `2` khi
thiếu file.

## Bẫy đã gặp — phần chạy trên bản thảo thật

**9. Gate là gate cho HÌNH, không phải linter typography.** Chạy trên trang bản
thảo đầy đủ thì G2/G3/G6 nổ trên chữ thân bài: `'REVIEW'` chạm dấu `'.'`,
`'ngày'` chạm `','` — do kerning làm bbox hai span chạm nhau. Trang chữ thuần
(0 block, 0 edge, 414 nhãn) báo lỗi là vô nghĩa. Cách sửa: chỉ xét nhãn nằm
trong vùng có drawing (`figure_regions`), và loại cặp có một bên chỉ là dấu câu.

**10. Ba trạng thái của `regions`, không phải hai.** Docstring cũ nói
`regions is None → không lọc`, nhưng `None` lại chính là giá trị
`figure_regions` trả về khi trang KHÔNG có drawing. Kết quả: đúng lúc cần bỏ
qua hết thì gate xét hết. Phải tách rõ: `NO_FILTER` = hình standalone, kiểm
toàn bộ; `None` = trang tài liệu không có hình → bỏ qua; geometry = chỉ kiểm
trong vùng.

**11. Gạch phân số và khung biểu đồ của LaTeX bị nhận là mũi tên.** Trang có
biểu đồ báo 16 lỗi G6 vì số liệu `1.10`, `0.58`… nằm trên khung; trang có công
thức báo lỗi vì gạch phân số. Dấu hiệu phân biệt: **đường sơ đồ có arrowhead
gắn sát đầu mút** (hình thật: 6/8 edge), gạch typography thì không và thường là
một đoạn trục chuẩn hoặc khung chữ nhật. Xem `rule_edge_indices`.

**12. Đồng bộ bản cài trước khi đo lại.** Sửa code ở clone rồi chạy script quét
trỏ vào `~/.hermes/skills/...` sẽ đo lại chính code cũ — kết quả "y nguyên" là
giả. So `sha256` clone vs bản cài trước khi tin số đo. `rsync --exclude` bảo vệ
file khỏi `--delete`, nên `__pycache__` và `fixtures/_build` phải xoá tay.

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

## Bẫy 9: PDF ghi cỡ chữ theo BIG POINT, TeX dùng PRINTER POINT

**Đã verify tại máy, không phải suy đoán.** PDF ghi toán hạng `Tf` theo **big point**
(1 inch = 72 bp); TeX dùng **printer point** (1 inch = 72.27 pt). Hệ số `72/72.27 = 0.996264`.

Hệ quả: mọi cỡ chữ TeX hiện ra trong PDF **nhỏ hơn 0.37%**:

| TeX pt | PDF (bp) |
|---|---|
| 5 | 4.98 |
| 6 | **5.98** |
| 7 | 6.97 |
| 8 | 7.97 |
| 9 | 8.97 |
| 10 | 9.96 |
| 10.95 | 10.91 |
| 12 | **11.96** |

Nếu sàn font là 6pt mà so trực tiếp với 5.98 thì gate **báo oan mọi chữ 6pt trong
mọi tài liệu LaTeX**. Đây là lỗi đơn vị 0.37%, không phải phát hiện typography.

Verify tại máy:
```bash
mutool draw -F trace file.pdf 2>/dev/null | grep -o 'size="[0-9.]*"' | sort -u
# -> 5.9776, 7.9701, 10.9091, 11.9552 ... (chính là 6/8/10.95/12 TeX pt)
```

Gate phải quy đổi `to_texpt(size_bp)` trước khi so sánh, và cộng `FONT_EPS = 0.05pt`
để chữ nằm đúng ngưỡng không bị fail do làm tròn.

## Bẫy 10: cỡ chữ nhỏ trong công thức toán là CHUẨN LaTeX, không phải lỗi

`fontmath.ltx` trên máy (dòng 81-82) quy định:

```latex
\DeclareMathSizes{\@xipt}{\@xipt}{8}{6}     % 11pt -> script 8pt, scriptscript 6pt
\DeclareMathSizes{\@xiipt}{\@xiipt}{8}{6}   % 12pt -> script 8pt, scriptscript 6pt
```

Vậy với bản thảo 11pt/12pt, **scriptscript = 6pt là đúng chuẩn**. Và `\@xipt = 10.95`
(`latex.ltx` dòng 8913) — "11pt" thật ra là 10.95pt.

Thêm nữa, Computer Modern có **bản vẽ riêng cho từng cỡ** (optical sizing): CMR6
không phải "CMR10 thu nhỏ" mà là bản vẽ riêng cho 6pt — nét dày hơn, x-height cao
hơn, counter mở hơn. Nên CMR6 ở 6pt **dễ đọc hơn** CMR10 co xuống 6pt.

Gate phải miễn chữ có cỡ khớp **cỡ thiết kế CM** (5, 6, 7, 8, 9, 10, 10.95, 12,
14.4, 17.28, 20.74, 24.88) khi chuỗi ngắn như chỉ số.

Verify:
```bash
grep -n 'DeclareMathSizes' "$(kpsewhich fontmath.ltx)"
grep -n '@xipt' "$(kpsewhich latex.ltx)"
```

## Bẫy 11: font toán mở rộng (CMEX) có bbox sâu gấp nhiều lần cỡ chữ

`(cid:16)` / `(cid:17)` trong font `CMEX10` **không phải glyph lỗi mã hoá**. Verify
bằng `t1disasm cmex10.pfb`:

```
dup 16 /parenleftBig put
dup 17 /parenrightBig put
```

Đó là dấu ngoặc lớn của `\left( ... \right)`. TFM (`tftopl cmex10.tfm`):

```
CHARACTER O 20   (CHARWD R 0.597)  (CHARHT R 0.040)  (CHARDP R 1.760)
```

**Sâu 1.76 lần cỡ chữ dưới baseline.** Bbox của nó bao trọn cả công thức bên trong,
nên "nhãn chồng nhãn" là **tất nhiên, đúng thiết kế** — không phải lỗi bố cục.

TeX căn dấu ngoặc theo *math axis* (không phải baseline), và `var_delimiter`
(TeXbook Appendix G, Rule 19) hoặc chọn một biến thể rời rạc, hoặc **xếp chồng nhiều
glyph** (top/extension/bottom). Vậy một cặp ngoặc có thể ra 2-6 glyph.

Gate phải miễn hoàn toàn font toán mở rộng: `cmex`, `lmex`, `stixsize*`,
`latinmodernmath`, `xitsmath`, `msam`, `msbm`, và OMX encoding.

Verify:
```bash
t1disasm "$(kpsewhich cmex10.pfb)" | grep -n 'parenleftBig'
tftopl "$(kpsewhich cmex10.tfm)" | grep -A3 'CHARACTER O 20'
```

## Cơ sở lý thuyết cho G1 (mũi tên xuyên block)

Điểm mạnh nhất để giữ G1 ở mức `error`: trong lý thuyết graph drawing, đây **không
phải tiêu chí thẩm mỹ** mà là vi phạm **định nghĩa của một bản vẽ**. Định nghĩa
chuẩn (Di Battista, Eades, Tamassia, Tollis, *Graph Drawing*, Prentice Hall 1999,
Ch. 1) yêu cầu mỗi cạnh là một cung Jordan giữa hai đỉnh **mà phần trong không chứa
đỉnh nào**. Cạnh cắt nhau là *chi phí cần tối thiểu hoá*; cạnh xuyên đỉnh thì
**không hợp lệ ngay từ định nghĩa**.

Hệ quả thực hành: mọi engine layout đều coi đây là ràng buộc cứng. Sugiyama (1981)
chèn *dummy vertex* cho mọi cạnh vượt tầng chính là để cạnh dài không đi qua node
thật. Graphviz có `esep`/`sep` (mặc định 3-4pt) làm khoảng hở khi định tuyến.

**Ngoại lệ cần biết** — cạnh chồng node là *hợp lệ* khi:
1. có quy ước phân biệt tường minh (mask trắng, ngắt đường, z-order);
2. phần bị chồng **không phải điểm nối** (khung `fit`, vùng bao, nhãn trục);
3. vị trí node bị ràng buộc từ bên ngoài (bản đồ, floorplan).

Với hình TikZ viết tay thì **không ngoại lệ nào tự động đúng**, nên G1 = `error` là
hợp lý. Nhưng hình khoa học (hình học phân tử, mạch điện) có thể thuộc ngoại lệ (2):
cần cách khai báo miễn trừ, không nên sửa hình.

**Điều KHÔNG được nói:** không có thí nghiệm có đối chứng nào đo *mức độ* thiệt hại
của cạnh-xuyên-node. Purchase (1997, 2002) xếp hạng các tiêu chí thẩm mỹ nhưng
**không** đưa tiêu chí này vào — vì nó bị loại từ tầng định nghĩa. Đừng viện dẫn
Purchase để bảo vệ G1.

## Bẫy 12: bbox chồng nhau KHÔNG chứng minh chữ bị chồng

Trong OpenType: `advanceWidth = lsb + inkWidth + rsb`, và **`lsb`/`rsb` được phép
âm**. Nên:

- bbox advance chồng nhau: bình thường (kerning `AV`, `To`).
- bbox ink chồng nhau: vẫn có thể bình thường (dấu tổ hợp, dấu tiếng Việt xếp tầng,
  `\overline`, `\sqrt`, chỉ số trên/dưới).

Chữ Việt xếp 2 tầng dấu (ẩ = a + circumflex + hook) khi ở dạng NFD sẽ ra **glyph có
advance = 0** nhưng ink khác 0, đặt ngay trên ký tự gốc. Mọi phép so bbox từng cặp
sẽ báo 2-3 "lỗi" cho **mỗi chữ có dấu**.

Quy tắc: **không bao giờ so bbox trong cùng một nhãn**. Gộp glyph advance = 0 vào
glyph trước nó, và chỉ so *giữa các nhãn khác nhau*.

**9. Miễn font toán theo TÊN là quá rộng — phải đo hình học.** Bản đầu em cho cả `cmmi` vào danh sách miễn, mà `CMMI10` là font **toán nghiêng cỡ thường** (chữ `i`, `x`, `n` trong công thức). Kết quả: gate bỏ sót đúng ca người dùng thấy bằng mắt — nhãn `i` bị chữ `CO` đè 14.5pt². Đã đo bằng `tftopl` trên máy:

| font | max CHARHT+CHARDP |
|---|---|
| `cmex10` | **3.71em** ← font mở rộng thật |
| `cmsy10` | 1.71em |
| `msam10` | 1.47em |
| `msbm10` | 1.34em |
| `cmmi10` / `cmr10` | 1.00em |

Chỉ `cmex`/`lmex`/`STIXSize*`/`XITSSize*` là font **chỉ chứa** ký hiệu giãn kích thước. Với font toán OpenType (`XITSMath-Regular` chứa cả chữ nghiêng lẫn ngoặc lớn) thì tên font vô dụng — phải nhận diện theo **tỉ lệ chiều cao bbox / cỡ chữ** của từng glyph (`is_oversized_glyph`).

**10. `\draw (b0)--(b1)` với `b0` là TOẠ ĐỘ, không phải TÊN NODE.** Đây là lỗi thật tìm được trong `fig2_turn_geometry.tex`: node tên `nb0` nhưng `\draw` dùng `(b0)` — toạ độ thô. TikZ vẽ **tâm đến tâm**, đường xuyên qua thân vòng tròn. Nối bằng tên node `(nb0)--(nb1)` thì TikZ tự cắt ở viền. Sửa 4 dòng → 9 lỗi về 0.

**11. Bản thảo nhúng PDF, không nhúng .tex.** Sửa `.tex` của hình rồi build bản thảo vẫn ra y nguyên lỗi cũ, vì `tieuluan.tex` dùng `\includegraphics{fig2_turn_geometry.pdf}`. Phải rebuild PDF của hình **và** đồng bộ mọi bản copy của PDF đó (ở đây có 6 bản trên máy) trước khi build bản thảo.
