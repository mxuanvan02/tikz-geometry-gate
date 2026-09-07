# Negative control: chứng minh check im lặng vì hình sạch, không vì mù

Một check mới báo `0 finding` trên hình thật có **hai** cách hiểu, và chúng
ngược nhau hoàn toàn:

1. hình sạch — check đúng khi im lặng;
2. check không nhận được dữ kiện, hoặc không tồn tại trong bản đang chạy — check
   mù, và `0 finding` là lời nói dối.

Không phân biệt được hai cái đó thì mọi kết luận "hình đạt" đều vô giá trị. Quy
trình dưới đây là cách phân biệt, đã chạy thật trên 6 hình TikZ.

## Bước 0 (bắt buộc): xác minh bản đang chạy có check đó

Đây là bước dễ bỏ nhất và là chỗ đã sai một lần: kết quả scan đầu tiên báo
`0 finding G8/G9` trong khi bản cài vẫn là gate **7 check** — file chưa được
đồng bộ, mtime cũ hơn một ngày. Toàn bộ lần scan đó phải bỏ đi.

```bash
CLONE=~/skill_repos/tikz-geometry-gate/scripts/tikz_gate.py
CAI=~/.hermes/skills/tikz-geometry-gate/scripts/tikz_gate.py
sha256sum "$CLONE" "$CAI"          # hai dòng PHẢI khớp
python "$CAI" --list-checks | python -c 'import json,sys; print(len(json.load(sys.stdin)["checks"]))'
```

`sha256` khớp là điều kiện cần. Đếm số check là điều kiện đủ để biết bản cài
thực sự có check mới. Suy ra từ mtime hoặc từ việc "vừa chạy `cp`" là không đủ:
`cp` có thể đã chạy trên đường dẫn khác, hoặc bị ghi đè bởi lần đồng bộ sau.

## Bước 1: đếm dữ kiện đầu vào của từng check

Mỗi check chỉ hoạt động khi hình có đúng loại dữ kiện nó cần. Đếm trước, rồi
mới đọc kết quả:

| Check | Dữ kiện cần | Cách đếm |
|---|---|---|
| G8 | cặp (edge, khung bao) mà bbox chạm nhau | `container_indices()` khác rỗng **và** có cặp giao bbox |
| `G9/route-micro-step` | edge có ≥3 đoạn | `len(_segments(e.poly)) >= 3` |
| `G9/route-axis-jitter` | đoạn lệch trục trong `(0.25°, 5°]` **và** có đoạn trùng trục chính xác | đếm `_axis_deviation_deg` theo hai khoảng |

Nếu cột dữ kiện bằng 0 thì `0 finding` **không nói gì** về chất lượng hình — nó
chỉ nói hình không thuộc phạm vi check. Ghi rõ như vậy, đừng ghi "đạt".

## Bước 2: với hình CÓ dữ kiện, in lý do bị lọc

Đây là phần cho kết luận. Số đo thật trên `fig1_backbone_torsions`:

```
edge #10: 6 đoạn, độ dài [4.47, 26.3, 4.38, 4.47, 26.3, 4.47]
          góc rẽ có dấu [-26.57, +27.15, -53.71, +26.57, -26.57]
```

Hình này **có** đoạn giữa 4.38pt, dưới ngưỡng 6pt, nên thoả điều kiện thứ nhất
của `route-micro-step`. Nó vẫn không bị báo, và lý do in ra được:

> `ke (26.3, 4.5) khong gap 4.0x doan giua`

Điều kiện tỉ lệ đoạn kề loại nó ra. Đúng thiết kế: đây là hình zigzag đối xứng
của cấu trúc hoá học, các đoạn dài xấp xỉ nhau — không phải bậc thang tí hon
giữa hai đoạn dài.

Tương tự với `route-axis-jitter`. Bốn edge lệch 2.645° (offset 2.0pt) nhưng:

> `doan ke [] khong co doan trung truc chinh xac`

Mỗi edge chỉ có **một** đoạn duy nhất, `exact=[]`. Đường chéo có ý trong hình
hoá học, không có cơ sở nào để gọi là toạ độ lệch. Nếu điều kiện "route đã tự
chứng tỏ nó vuông góc" bị bỏ, cả bốn edge này bị báo oan.

Với G8, lý do còn đơn giản hơn — in ra đoạn chạy dọc viền **dài nhất** tìm được:

> `KHONG co doan nao song song VA cham vanh khung`

Hình có 2 khung bao và 9 cặp (edge, khung) chạm bbox, nên G8 *đã* xét thật; nó
im lặng sau khi xét, không phải im lặng vì không có gì để xét.

## Bước 3: kết luận đúng mức

Ba mức khác nhau, đừng gộp:

- **ngoài phạm vi** — hình không có dữ kiện loại đó (ví dụ hình không có khung
  bao thì G8 không nói gì về nó);
- **đã xét, sạch** — có dữ kiện, mọi ứng viên bị điều kiện phụ loại, và lý do
  loại in ra được;
- **đã xét, có lỗi** — finding kèm `evidence`.

## Phụ lục: một phát hiện của lần scan này

Ba bản `arch_diagram.tex` trùng tên nhưng khác nội dung:

| Đường dẫn | Kết quả |
|---|---|
| `rabs_build/RABS_STAIS/figures/` | sạch |
| `rabs_build/RABS_STAIS_clean/figures/` | **2 lỗi G6** |
| `RABS_STAIS_work/RABS_STAIS/figures/` | **2 lỗi G6** |

Bản mang tên `_clean` lại là bản **chưa** sửa. Tên thư mục không phải bằng
chứng về trạng thái; chỉ kết quả gate mới là. Khi có nhiều bản sao của cùng một
hình, chạy gate lên **tất cả** và dedup theo hash nội dung, đừng theo tên.
