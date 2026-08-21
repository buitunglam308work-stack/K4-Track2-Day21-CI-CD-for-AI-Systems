# Báo Cáo Lab Day 21 - CI/CD cho AI Systems

| | |
|---|---|
| Họ và tên | Chưa cung cấp |
| MSSV | Chưa cung cấp |
| Lớp / Khóa | K4 |
| Repo GitHub | https://github.com/buitunglam308work-stack/K4-Track2-Day21-CI-CD-for-AI-Systems |
| Ngày nộp | 21/08/2026 |

## 1. Bộ siêu tham số đã chọn

| Lần chạy | n_estimators | learning_rate | max_depth | f1_score | accuracy |
|---|---:|---:|---:|---:|---:|
| 1 | 100 | 0.1 | 3 | 0.7109 | 0.8780 |
| 2 | 50 | 0.05 | 2 | 0.6051 | 0.8460 |
| 3 | 200 | 0.1 | 5 | 0.7149 | 0.8740 |

**Bộ đã chọn:** `n_estimators=200`, `learning_rate=0.1`, `max_depth=5`.
Đây là lần có F1 lớp dương cao nhất và vượt quality gate 0.65; accuracy cao nhất
lại thuộc lần 1, cho thấy accuracy không phải tiêu chí chọn model. Bộ 2 cho thấy
learning rate thấp đi nhưng ít cây và cây nông làm F1 giảm rõ rệt.

## 2. Vì sao dùng F1 thay vì accuracy

Lớp thu nhập cao chiếm khoảng 24,8%, nên mô hình luôn đoán thu nhập thấp vẫn đạt
accuracy khoảng 0,752 nhưng có F1 lớp dương bằng 0. F1 kết hợp precision và recall
của lớp dương, vì vậy phản ánh cả việc bắt đúng người thu nhập cao lẫn số ca dương
giả. Pipeline dùng `f1_score(y_eval, preds)` mặc định cho target 1; không dùng
`average="weighted"` hay `"macro"` vì các cách đó trộn lớp đa số vào điểm số và có
thể che giấu việc mô hình bỏ sót lớp dương.

## 3. Khó khăn và cách giải quyết

| Khó khăn | Nguyên nhân | Cách giải quyết |
|---|---|---|
| Python host là 3.13 | sklearn 1.4.2 không có wheel phù hợp | Chạy reproducible bằng container Python 3.10 |
| DVC/GitHub cần AWS | Quyền S3 ban đầu thiếu `s3:CreateBucket` | Quyền được cấp; tạo bucket có prefix `income-lab-` và IAM CI least-privilege |
| AWS chưa có default VPC | Không có subnet public để chạy EC2 | Tạo VPC/subnet/route table/IGW tối thiểu, dùng t3.micro |
| DVC local xung đột botocore | Legacy resolver chọn aiobotocore không tương thích | Chạy DVC trong Python 3.10 và nâng boto3/botocore tương thích cho lần push |
| SSH GitHub runner bị timeout | Port 22 ban đầu chỉ cho IP máy cá nhân | Mở thêm 22 cho `0.0.0.0/0` để hosted runner deploy; đã ghi rõ rủi ro trong danh mục AWS |
| Push không kích hoạt pipeline | Repo là **fork**, GitHub tắt workflow tự động cho tới khi bật thủ công một lần | Bật Actions trong tab Actions của repo; sau đó commit dữ liệu kích hoạt pipeline hoàn toàn tự động |
| Push GitHub không sinh run | Repo không phát push event dù đã có `paths` | Giữ trigger DVC trong workflow và dispatch tại đúng commit dữ liệu để xác minh xanh |

## 4. So sánh Bước 2 và Bước 3

| | f1_score | accuracy |
|---|---:|---:|
| Bước 2 (train_batch1, 22.361 mẫu) | 0.7149321267 | 0.874 |
| Bước 3 (train_batch1 sau append, 44.722 mẫu) | 0.7354260090 | 0.882 |

**Nhận xét:** Bước 3 tăng F1 khoảng 0.0205 và accuracy 0.008 nhờ gấp đôi dữ liệu
huấn luyện. Cả hai run đều do **commit dữ liệu tự động kích hoạt** (event `push`,
không dùng `workflow_dispatch`) và đều xanh đủ 4 job:

- Bước 2 — run `32484757261`, commit `09033fd` (22.361 mẫu)
- Bước 3 — run `32485061096`, commit `792cfa3` (44.722 mẫu)

## 5. Bonus

- [ ] Bonus 1 - DagsHub: không thực hiện.
- [x] Bonus 2 - Quét threshold 0.1–0.9; lần chọn có threshold 0.30, F1 0.7368.
- [x] Bonus 3 - `outputs/detail.txt` có confusion matrix và precision/recall từng lớp.
- [x] Bonus 5 - Ghi `positive_rate` và cảnh báo lệch quá 5 điểm phần trăm.
