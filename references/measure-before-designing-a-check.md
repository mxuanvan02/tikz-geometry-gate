# Đo trước khi thiết kế tiêu chí (bài học từ G9)

G8 thêm được bằng trực giác vì tiêu chí của nó đơn giản. **G9 thì không**, và lần
làm G9 đã giết hai thiết kế liên tiếp *trước khi* viết code — chỉ nhờ đo số thật
trên fixture. Tài liệu này ghi lại cách đo, để lần thêm check thứ mười không phải
học lại bằng cách viết code sai.

## Quy tắc trung tâm

> Với check dựa trên **ngưỡng hình học**, viết fixture và **đo số thật TRƯỚC khi
> viết hàm check**. Không phải sau.

Lý do không phải là cẩn thận chung chung: ngưỡng trực giác nghe hợp lý thường sai
theo **hướng ngược lại** với dự đoán, và code viết theo trực giác sẽ pass trên
fixture do chính mình tinh chỉnh ngưỡng cho khớp — tức là tự chứng minh chính mình.

## Ba tiêu chí bị số đo giết, theo thứ tự

### Vòng 1: "đoạn ngắn = lỗi" — SAI

Đo trên `fixtures/route-rhythm.pdf`:

| Ca | Ý định | Độ dài các đoạn |
|---|---|---|
| 1 | LỖI bậc thang | `[85.0, 2.0, 80.4]` |
| 4 | HỢP LỆ `rounded corners` | `[79.0, 8.49, 22.0, 8.49, 74.4]` |

`rounded corners` sinh đoạn **8,49pt** hoàn toàn hợp lệ (dây cung của góc bo). TikZ
mặc định bo 4pt → dây cung 5,66pt, còn thấp hơn nữa. Ngưỡng độ dài đơn thuần báo oan
mọi sơ đồ bo góc.

### Vòng 2: "dấu góc rẽ trái nhau = bậc thang" — CŨNG SAI

Đo góc rẽ **có dấu**:

| Ca | Ý định | Góc rẽ |
|---|---|---|
| 1 | LỖI bậc thang | `[+90, -90]` |
| 6 | HỢP LỆ rẽ thường | `[+90, -90]` |

**Giống hệt nhau.** Hai ca chỉ khác độ dài đoạn giữa (2,0 vs 34,0). Nên dấu góc rẽ
một mình cũng không tách được.

### Vòng 2b: "lệch trục nhiều = toạ độ sai" — SAI, và sai ngược chiều

| Ca | Ý định | Lệch trục | Offset vuông góc |
|---|---|---|---|
| 2 | LỖI jitter | 1,209° | **0,5pt** |
| 3 | HỢP LỆ `bend left` | 0,931° | **2,7pt** |

Ca hợp lệ lệch **ít hơn** mà offset **lớn hơn** ca lỗi. Cả hai ngưỡng tuyệt đối đều
vô dụng, và ngưỡng offset còn báo oan đường cong *nặng hơn* là bắt lỗi thật.

## Tiêu chí đúng: GIAO của nhiều điều kiện, và suy Ý ĐỊNH từ chính route

Không có đại lượng đơn nào tách được. Phải giao:

**`G9/route-micro-step`** — cả ba điều kiện:
1. đoạn **giữa** ngắn hơn `ROUTE_MIN_INTERIOR_LEN`;
2. hai góc rẽ hai bên đủ sắc **và TRÁI DẤU** (góc bo luôn cùng dấu: 45+45 thay cho một góc 90);
3. hai đoạn kề dài hơn đoạn giữa ≥ `ROUTE_NEIGHBOR_RATIO` lần.

Điều kiện (3) chống Bézier bị làm phẳng: trên đường cong các đoạn liên tiếp dài xấp
xỉ nhau, không có tỉ lệ 40:1 như bậc thang thật. Số đo: ca 1 (lỗi) tỉ lệ 85/2 = 42
lần; ca 4 (bo góc, hợp lệ) 22/8,49 = 2,6 lần. Ngưỡng 4,0 nằm giữa, **không sát mép
bên nào** — đó là cách chọn ngưỡng đúng.

**`G9/route-axis-jitter`** — suy ý định thay vì đặt ngưỡng tuyệt đối:

> Chỉ báo khi route **đã tự chứng tỏ nó vuông góc** (có ≥1 đoạn trùng trục chính xác
> trong `ROUTE_AXIS_EXACT_DEG`) **và** đoạn lệch có đoạn kề trùng trục chính xác.

Đường cong tự động miễn nhiễm: **mọi** đoạn của nó đều lệch, nên tập `exact` rỗng và
check thoát sớm. Không cần danh sách miễn trừ, không cần nhận diện Bézier.

## Đo thế nào

Probe rời, in bảng, **không** gọi hàm check đang viết:

```python
import sys; sys.path.insert(0, 'scripts')
import tikz_gate as G
page, holder, close = G._open_page('fixtures/_build/route-rhythm.pdf', 0)
_, _, edges, _, _ = G.classify(page)
for ei, e in enumerate(edges):
    segs = G._segments(e.poly)
    lens = [G._seg_len(s) for s in segs]
    turns = [G._signed_turn_deg(e.poly[i], e.poly[i+1], e.poly[i+2])
             for i in range(len(e.poly) - 2)]
    devs = [G._axis_deviation_deg(*s) for s in segs]
    print(ei, [round(x, 2) for x in lens],
          [round(t, 2) for t in turns if t is not None],
          [round(d, 3) for d in devs if d is not None])
close()
```

In **mọi** đại lượng ứng viên cùng lúc (độ dài, góc rẽ có dấu, lệch trục, offset,
tỉ lệ với đoạn kề) rồi mới chọn. Đo một đại lượng một lần là cách bỏ sót chuyện
"ca hợp lệ lệch ít hơn ca lỗi".

## Fixture cho check dựa trên ngưỡng: 2 ca lỗi + 4 ca hợp lệ

Nhiều ca hợp lệ hơn ca lỗi, và mỗi ca hợp lệ nhắm một **cơ chế báo oan** khác nhau:

| Ca | Vai trò |
|---|---|
| 1 | LỖI bậc thang tí hon giữa hai đoạn dài |
| 2 | LỖI toạ độ lệch nhẹ (`(2,0) -- (2.02,-1)`) |
| 3 | HỢP LỆ `bend left` — chống báo oan Bézier |
| 4 | HỢP LỆ `rounded corners` — chống báo oan góc bo |
| 5 | HỢP LỆ đoạn ngắn ở **đầu/cuối** (nối vào viền node) |
| 6 | HỢP LỆ rẽ vuông thường — cùng góc rẽ như ca 1, khác độ dài |

Ca 6 là ca đắt giá nhất: nó **trùng góc rẽ với ca lỗi**, nên nó chính là ca chứng
minh tiêu chí không thể chỉ dựa vào góc.

## Số đo phụ đáng ghi

Bézier **không** bị làm phẳng thành hàng chục đoạn nhỏ. pdfplumber trả 4 điểm control,
nên `bend left` chỉ ra 1–3 đoạn dài (ca 3: **1 đoạn** 166,2pt). Rủi ro báo oan trên
đường cong thấp hơn dự đoán ban đầu — nhưng biết được điều đó là *nhờ đo*, không nhờ
suy luận.
