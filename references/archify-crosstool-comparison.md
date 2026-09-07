# Đối chiếu gate ↔ archify: check nào trùng, thiếu, và KHÔNG được nhập

Đối chiếu bằng code thật, không bằng tài liệu. Nguồn:

- archify: `scripts/check-render-output.mjs` (9 artifact check, hàm `addCheck`),
  `renderers/shared/geometry.mjs` (6 mã `composition/*`), `bin/archify.mjs`
  (bảng mã lỗi + receipt).
- gate: `scripts/tikz_gate.py` (G1..G7).

Lệnh lấy danh sách (chạy trong clone archify, **phải** loại `node_modules` —
`simple-icons` có một file 5.2 MB một dòng làm ngập mọi grep):

```bash
grep -rn "addCheck(" scripts/check-render-output.mjs
grep -rho "composition/[a-z-]*" renderers/shared/geometry.mjs | sort -u
grep -rho "'[a-z]*/[a-z-]*'" bin/archify.mjs | sort -u
```

## 1. Bảng đối chiếu

| archify | gate | Kết luận |
|---|---|---|
| `composition/ambiguous-corridor` | **G7** edge-edge-overlap | TRÙNG |
| `composition/proper-crossing` | — | thiếu, nhưng xem §4 |
| `composition/container-border-run` | — | **THIẾU → G8** |
| `composition/micro-segment`, `composition/short-interior-segment` | — | **THIẾU → G9** |
| `composition/label-route-clearance` | G6 label-edge-clash | gate mạnh hơn: G6 xét mask + zorder |
| `desktop-readability` (projected font px) | G5 tiny-text | **gate mạnh hơn**, xem §3 |
| `single_svg`, `finite_svg` | — | không áp được: đặc thù artifact HTML |
| `legend_clearance` | — | có thể suy ra từ G1 nếu coi legend là block |
| `orthogonal_arrows` | — | **KHÔNG ĐƯỢC NHẬP**, xem §4 |

## 2. Hai check nên thêm

### G8 — edge chạy dọc viền khung (`container-border-run`)

G1 chỉ bắt mũi tên **xuyên** block. Không bắt mũi tên **áp sát viền** một đoạn
dài — người đọc không phân biệt được đâu là viền khung, đâu là đường nối.

Hay gặp nhất ở sơ đồ dùng `\usetikzlibrary{fit,backgrounds}`: khung `fit` bao
một nhóm node, rồi một `\draw` đi vòng ra ngoài và chạy sát mép khung.

Dữ liệu cần đã có sẵn trong gate: `blocks` (có cả `boundary` dạng dashed) và
`edges`. Thuật toán như archify: với mỗi cạnh của mỗi frame, chiếu các đoạn của
edge lên cạnh đó, cộng chiều dài phần nằm trong dải `±tol`; vượt ngưỡng
`overlapLength` thì báo lỗi. Archify báo kèm `frameName`, `side`, `segmentIndex`,
`overlapStart/End` — nên bắt chước để `evidence` chỉ được chỗ sửa.

Lưu ý riêng cho TikZ: khung `fit` thường là `boundary` (dashed). Cạnh đi dọc
viền `boundary` vẫn là lỗi, nhưng phải cho miễn trừ khi cạnh **kết thúc** ở
viền đó (giống `eps` của G1) — nếu không sẽ báo oan mọi mũi tên nối vào khung.

### G9 — nhịp đường đi (`micro-segment` / `short-interior-segment`)

Một route có bậc thang 2pt trông như lỗi render. Ngưỡng của archify: đoạn quá
ngắn ở **giữa** route (`short-interior-segment`) nặng hơn đoạn ngắn ở đầu/cuối
(`micro-segment`), vì đầu/cuối có thể là phần nối vào viền node.

Ở TikZ, nguyên nhân thường là toạ độ viết tay lệch nhau vài pt
(`(2,0) -- (2.02,-1)`), hoặc `to[out=..,in=..]` sinh đoạn nối rất ngắn.

## 3. Chỗ gate ĐÃ mạnh hơn — đừng thay bằng cách của archify

`desktop-readability` của archify chỉ so một ngưỡng px cố định
(`MIN_PROJECTED_NODE_TEXT_PX`). Gate có ba tầng và **không phán khi không đủ dữ
kiện**:

- `floor_for_page()` / `relative_font_floor()`: quy đổi theo bề rộng trang thật;
- `--scale`: quy đổi hệ số `\resizebox` / `\includegraphics`;
- `kind == "standalone"` mà không biết scale → `severity = "warning"`, không fail.

Xem bẫy 7 trong SKILL.md: cùng một hình cho 4.98pt lúc standalone và 2.67pt sau
khi nhúng. Ngưỡng px cố định không phân biệt được hai trạng thái đó.

## 4. `orthogonal_arrows` — KHÔNG được nhập

Archify buộc mọi mũi tên phải vuông góc (`diagonalStraightSegments` → lỗi nếu
có đoạn chéo). Hợp lý cho sơ đồ kiến trúc phần mềm, **sai cho hình khoa học**:
sơ đồ toán, hình học, luồng dữ liệu chéo tầng đều dùng đường chéo và Bézier hợp
lệ. Nhập check này vào gate sẽ báo sai hàng loạt trên đúng loại hình gate phục
vụ.

`proper-crossing` (hai đường cắt nhau): archify coi là **lỗi** ở mức showcase.
Với hình khoa học nên **đếm làm chỉ số**, không fail cứng — cắt nhau đôi khi
không tránh được. Nhưng 12 chỗ cắt trên một hình là dấu hiệu layout sai, nên
báo dạng thống kê kèm ngưỡng cảnh báo. Cơ sở lý thuyết: xem mục "Cơ sở lý
thuyết cho G1" trong SKILL.md — cạnh cắt nhau là *chi phí cần tối thiểu hoá*,
cạnh xuyên đỉnh mới là *bất hợp lệ từ định nghĩa*. Hai mức khác nhau, gate phải
giữ khác nhau.

## 5. Khác biệt kiến trúc quyết định trải nghiệm sửa lỗi

| | archify | gate |
|---|---|---|
| Thời điểm kiểm | **trước** render, trên spec JSON | **sau** render, trên PDF |
| Finding trỏ về | `id` của node/relationship trong spec | toạ độ trong PDF |
| Sửa được ngay? | có — sửa đúng field | phải tự dò `\draw` nào |

Hệ quả: finding của gate đúng nhưng **khó dùng**. Muốn cải thiện thì đọc `.tex`
song song với PDF và gắn finding vào số dòng. Cách khả thi mà không cần parse
TikZ đầy đủ: đối chiếu toạ độ PDF với toạ độ ghi trong `\draw`/`\node` sau khi
áp `xshift/yshift/scale` của môi trường — hoặc dùng đường ground-truth có sẵn
trong SKILL.md (`\pgfpointanchor` + `\immediate\write`) để lấy bbox kèm tên
node, rồi map ngược.

## 6. Hai thứ đáng học ngoài phần check

**Receipt kiểm được.** Archify không chỉ in lỗi; `deliver` phát ra receipt JSON
có `artifact.sha256`, `artifact.bytes`, `validation.checksPassed/checkCount`,
`completeness`, `proofLevel`. Test `real-repository-proof.test.mjs` khẳng định
artifact **tái tạo đúng byte** từ input đã ghim. Áp vào luận văn: mỗi hình một
receipt đính kèm, cùng `.tex` → cùng PDF → cùng sha256. Khớp với nguyên tắc
bằng chứng: số nào trong bản thảo cũng phải có đường về script sinh ra nó.

**Diff hình giữa hai bản.** `archify compare` sinh artifact ba trạng thái
(thêm / bỏ / giữ) kèm receipt tái lập được. Hiện gate không trả lời được câu
"sửa hình 3 có làm hỏng hình khác không?" ngoài cách mở ra nhìn. `diff-pdf` là
đường tắt, nhưng một diff **có cấu trúc** (theo block/edge/label) sẽ nói được
*cái gì* đổi, không chỉ *có đổi*.
