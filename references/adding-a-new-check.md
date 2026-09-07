# Thêm một check mới vào gate (quy trình đã chạy thật cho G8)

Quy trình này đã dùng để thêm `G8/edge-border-run`. Làm đúng thứ tự, vì hai bước
verify ở giữa là nơi lộ ra hai bug cũ mà không bước nào khác bắt được.

## 0. Trước khi viết code: đo baseline

```bash
cd ~/skill_repos/tikz-geometry-gate
python -m pytest test/ -q          # ghi lại con số, ví dụ "84 passed, 1 skipped"
git status                          # phải biết có gì đang dở
git diff                            # ĐỌC bản vá chưa commit trước khi xây lên trên
```

Bỏ bước `git diff` là cách chắc chắn nhất để xây lên một bản vá đang hỏng. Ở G8,
bước này lộ ra bản vá `rot90` cho G5 đang là **cờ chết** (xem §5).

## 1. Hằng số ngưỡng — khai ở đầu file, kèm lý do bằng số

Đặt cạnh khối `EDGE_OVERLAP_*`. Mỗi hằng số một comment nói *tại sao con số đó*,
không phải *nó là gì*.

```python
EDGE_BORDER_TOL = 2.0       # mui ten cach vien khung <= 2pt => coi nhu trung
EDGE_BORDER_MIN_LEN = 12.0  # chay doc vien >= 12pt moi bao loi
```

## 2. Nhận diện đối tượng bằng CẤU TRÚC, không bằng ngưỡng độ lớn

Bài học từ `container_indices()`. Cần biết "hình nào là khung bao":

- **Sai**: `area >= NGƯỠNG` → sơ đồ có một node đơn lẻ rất to bị coi oan là khung
  bao, rồi check mới báo sai mọi mũi tên chạm vào node đó.
- **Sai**: phần giao diện tích > 0 → hai block cạnh nhau chạm viền nhau do làm
  tròn góc.
- **Đúng**: *tâm* của hình khác nằm trong lòng nó. Tâm không bao giờ lồng nhau
  với hình bên cạnh.
- Phải loại trường hợp **cùng một hình vẽ hai lần** (fill rồi stroke → hai bbox
  trùng nhau trong sai số ~2pt). Không loại thì mỗi hình tự nhận là khung bao của
  chính nó.

## 3. Hàm check — tái dùng helper hình học có sẵn

Đừng viết lại. Gate đã có: `_segments()`, `_seg_angle_deg()`, `_angles_parallel()`,
`_r()`, `Finding`. Khung chuẩn của một check:

```python
for ei, e in enumerate(edges):
    if ei in ignore_edges or not e.poly:
        continue
    # 1. lọc nhanh bằng bbox trước khi tính hình học (đắt)
    # 2. chỉ xét khi gần song song
    # 3. buffer + intersection, so chiều dài với min_len
    # 4. giữ `best` = ca nặng nhất, báo MỘT finding cho mỗi cặp
```

Ba thứ bắt buộc có trong `Finding`:

- `evidence` phải chỉ được **chỗ sửa**: toạ độ đoạn, tên cạnh (`tren`/`duoi`/
  `trai`/`phai`), chiều dài phần trùng, `bbox` để `--annotate` khoanh được.
- `fixes` là câu lệnh TikZ cụ thể, không phải lời khuyên chung.
- Tham số `ignore_edges` để hợp tác với `rule_edge_indices` (gạch typography).

Kiểu annotation cho tham số tập hợp: `ignore_edges: "set | frozenset" = frozenset()`
— để `frozenset()` trần thì linter báo khi caller truyền `set`.

## 4. Fixture: một file `.tex`, TỐI THIỂU ba ca

```
Ca 1, 2: LỖI  — mỗi ca một biến thể (viền trên, viền trái)
Ca 3:    HỢP LỆ — và phải ghi rõ trong comment "nếu gate báo ở đây thì ngưỡng quá chặt"
```

Ca hợp lệ quan trọng hơn ca lỗi: nó là nơi lộ ra false positive. Ở G8, chính ca 3
làm lộ bug G1 báo oan khung bao.

Repo **không commit PDF** — `build_fixture()` trong test tự compile từ `.tex`.

## 5. Verify — hai bước, không được bỏ bước nào

**5a. Check mới có bắt được không**

```bash
pdflatex -interaction=nonstopmode -output-directory=fixtures/_build fixtures/<ten>.tex
python -c "
import sys; sys.path.insert(0,'scripts')
import tikz_gate as G
f,inv,_ = G.analyze('fixtures/_build/<ten>.pdf')
print(inv)
for x in f: print(x.code, '|', x.message)
"
```

**5b. Check mới có báo oan trên fixture CŨ không** — bước này hay bị bỏ:

```bash
for t in good-rabs defect-rabs stale-mask-rabs bad edge-overlap; do
  # chạy analyze, in tổng số lỗi + đếm theo mã + số containers
done
```

Đọc kết quả đúng cách: `good-rabs` phải `ok=True` **và** `containers=2`. Nếu
`containers=0` thì check mới im lặng vì *không thấy gì*, chứ không phải vì *không
có lỗi* — đó là verify giả.

## 6. Cờ chết: bẫy hạ tầng nghiêm trọng nhất

Bản vá đọc một khoá mà **không nơi nào set** thì vô hiệu hoàn toàn và **im lặng**.
Đã xảy ra thật: `real_font_size()` đọc `span["rot90"]`, nhưng cả hai backend
`text_spans_*` đều không đặt khoá đó → bản vá G5 cho nhãn trục dọc không chạy một
lần nào.

Quy tắc: sửa bên **tiêu thụ** thì phải kiểm bên **sản xuất** ngay trong cùng lượt.

```bash
grep -n '<ten_khoa>' scripts/tikz_gate.py
# phải thấy ở CẢ hai chỗ: nơi đọc, VÀ nơi ghi vào dict span
```

Và ghim bằng test, không chỉ sửa:

```python
def test_every_span_has_rot90_key(self):
    missing = [s["text"] for s in spans if "rot90" not in s]
    self.assertEqual(missing, [], "moi span phai co khoa rot90")
```

Lưu ý: khi thêm khoá vào span của backend pdfplumber, phải thêm khoá đó vào **điều
kiện gộp char** (`same = ...`) nữa — hai char khác `rot90` không được gộp thành một
span.

## 7. Test — bốn nhóm, nhóm 2 là nhóm giữ giá trị lâu nhất

1. **Hình học tổng hợp** (`mk_block`/`mk_edge`/`mk_span`, không cần LaTeX): ca lỗi
   theo từng biến thể.
2. **Hồi quy cho ca HỢP LỆ**: `test_edge_inside_frame_is_ok`,
   `test_perpendicular_crossing_border_is_ok`, `test_short_touch_below_threshold_is_ok`.
3. **Nhận diện đối tượng**: khung bao, hai block cạnh nhau, node to đơn lẻ, hình vẽ
   hai lần.
4. **PDF thật**: đếm đúng số finding trên fixture, **và** khẳng định không sinh
   finding của check khác (`test_no_g1_false_positive_on_container`).

Khi bỏ qua một lớp đối tượng (như G1 miễn khung bao), phải có test khẳng định việc
bỏ qua đó **không làm mất khả năng bắt lỗi thật**:

```python
def test_edge_through_ordinary_block_still_flagged(self):
    ...
    hit = {f.evidence["blockIndex"] for f in out}
    self.assertNotIn(2, hit, "khung bao khong duoc bao")
```

## 8. Tài liệu — bốn chỗ, thiếu chỗ nào cũng thành sai

1. Docstring đầu `tikz_gate.py`: dòng "phat hien N nhom loi" **và** danh sách check.
2. `SKILL.md`: bảng check + tiêu đề "N nhóm check".
3. `README.md`: bảng check + tiêu đề.
4. Nếu check mới sinh ra một *ngoại lệ* cho check cũ: viết hẳn một mục giải thích.
   Người sửa gate về sau sẽ tưởng ngoại lệ đó là bug và xoá đi.

Grep để không sót: `grep -rn "Sáu nhóm\|Bảy nhóm\|nhom loi" --include=*.md --include=*.py .`

## 9. Giao hàng

```bash
git checkout -b feat/<ten-check>
git diff --cached -U0 | grep -nEi '(hitokiri|/home/|token|secret|password)'  # phải trống
git add -A && git commit && git push -u origin feat/<ten-check>
```

PR + merge qua REST API (snap `gh` mù thư mục ẩn nên không dùng `gh pr create`).
Script dùng lại được: `~/skill_repos/_merge_pr.py` — đọc token từ
`~/snap/gh/current/.config/gh/hosts.yml`, không in token ra.

Sau merge: **sync 2 chiều** clone ↔ `~/.hermes/skills/tikz-geometry-gate/`.
Bản cài có thể chứa file mà clone chưa có (ở G8: `references/archify-crosstool-comparison.md`).
`diff -rq` trước khi rsync, đừng copy một chiều.

Kiểm bằng shell — dựng chuỗi lấy token trong `$(...)` lồng heredoc rất dễ hỏng cú
pháp; viết script `.py` riêng rồi chạy thì chắc hơn.
