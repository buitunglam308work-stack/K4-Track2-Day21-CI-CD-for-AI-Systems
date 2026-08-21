# Bước 2 - Pipeline CI/CD Tự Động

Mục tiêu: Mỗi khi bạn push code hoặc thay đổi dữ liệu, GitHub Actions tự động huấn luyện mô hình, kiểm tra `f1_score` có đạt ngưỡng >= 0.65 không, và triển khai lên VM nếu đạt yêu cầu.

---

## Nền tảng AWS được dùng trong lab

Lab này dùng Amazon S3 làm object storage và Ubuntu 22.04 trên EC2 làm VM. DVC dùng
`dvc[s3]`, code Python dùng `boto3`, GitHub Actions xác thực bằng IAM access key và
EC2 đọc model bằng IAM instance profile.

| Thành phần | AWS sử dụng |
|---|---|
| Object Storage | Amazon S3 |
| VM | EC2 t3.micro |
| CLI | `aws` |
| DVC storage extra | `dvc[s3]` |
| Cloud SDK Python | `boto3` |
| Credentials | IAM access key / EC2 instance profile |

---

## 2.1 Tạo S3 bucket

Tên bucket S3 phải duy nhất trên toàn cầu. Thay `<BUCKET_NAME>` bằng tên có tiền tố
`income-lab-` và một chuỗi ngẫu nhiên.

```bash
export BUCKET=<BUCKET_NAME>
export AWS_DEFAULT_REGION=us-east-1

aws s3api create-bucket --bucket "$BUCKET" --region us-east-1
aws s3api put-public-access-block --bucket "$BUCKET" \
  --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-ownership-controls --bucket "$BUCKET" \
  --ownership-controls Rules='[{ObjectOwnership=BucketOwnerEnforced}]'
```

---

## 2.2 Tạo IAM credentials

Tạo IAM user riêng cho lab. User chỉ có `ListBucket` trên bucket và
`GetObject`/`PutObject`/`DeleteObject` trong các prefix `dvc/` và `artifacts/`.
Không dùng `AmazonS3FullAccess`.

| Quyền | Phạm vi | Mục đích |
|---|---|---|
| `s3:ListBucket` | đúng bucket | DVC liệt kê object |
| `s3:GetObject`, `PutObject`, `DeleteObject` | `dvc/*`, `artifacts/*` | DVC và upload model |

```bash
# Tạo user, gắn inline policy JSON least-privilege như mô tả ở trên,
# rồi tạo access key. Không ghi output access key vào Git.
aws iam create-user --user-name income-lab-ci
aws iam put-user-policy --user-name income-lab-ci \
  --policy-name income-lab-s3-policy --policy-document file://income-lab-s3-policy.json
aws iam create-access-key --user-name income-lab-ci
```

Chỉ đưa access key vào GitHub Secrets hoặc biến môi trường tạm thời; tuyệt đối không
commit access key/secret key vào Git.

---

## 2.3 Cài Đặt DVC Với S3 remote

```bash
dvc init

dvc remote add -d labstore s3://$BUCKET/dvc

# DVC tự đọc AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY và AWS_DEFAULT_REGION.

# Theo dõi các file dữ liệu bằng DVC
dvc add data/train_batch1.csv
dvc add data/holdout.csv
dvc add data/train_batch2.csv

# Commit các file con trỏ DVC vào git (KHÔNG phải file CSV)
git add data/train_batch1.csv.dvc data/holdout.csv.dvc data/train_batch2.csv.dvc \
        .gitignore .dvc/config
git commit -m "feat: track datasets with DVC"

# Đẩy các file CSV lên cloud storage
dvc push
```

Xác nhận bằng `aws s3 ls s3://$BUCKET/dvc/ --recursive` rằng dữ liệu đã xuất hiện.

---

## 2.4 Tạo VM Trên Cloud

Tạo EC2 `t3.micro` với Ubuntu 22.04 LTS, key pair mới, security group cho SSH và
port 8080, đồng thời gắn instance profile chỉ đọc `artifacts/*`.

```bash
aws ec2 run-instances --image-id <UBUNTU_22_04_AMI> --instance-type t3.micro \
  --key-name income-lab-ec2 --security-group-ids <SG_ID> \
  --iam-instance-profile Name=income-lab-ec2-profile
aws ec2 describe-instances --instance-ids <INSTANCE_ID> \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
```

---

## 2.5 Cấu Hình VM (Thực Hiện Một Lần, Thủ Công)

SSH vào VM:

```bash
ssh -i ~/.ssh/income_lab.pem ubuntu@<EC2_PUBLIC_IP>
```

Bên trong VM, cài đặt các thư viện cần thiết:

```bash
sudo apt update && sudo apt install -y python3-pip python3-venv
python3 -m venv ~/venv
~/venv/bin/pip install fastapi==0.111.0 uvicorn==0.29.0 \
  scikit-learn==1.4.2 joblib==1.4.2 boto3 pandas==2.2.2

mkdir -p ~/models ~/src
```

Thoát khỏi VM, sau đó copy file key lên VM:

```bash
scp -i ~/.ssh/income_lab.pem src/serve.py ubuntu@<EC2_PUBLIC_IP>:~/src/serve.py
```

---

## 2.6 Viết `src/serve.py`

Tạo file `src/serve.py` theo khung dưới đây. File này chạy trên VM và cung cấp REST API để nhận yêu cầu suy luận.

Nhiệm vụ:
1. Khi khởi động, tải file `model.joblib` từ cloud storage về máy.
2. Cung cấp endpoint `GET /healthz` trả về trạng thái server.
3. Cung cấp endpoint `POST /score` nhận 10 đặc trưng và trả về nhãn dự đoán.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
import joblib
import os

app = FastAPI()

# Đọc tên bucket từ biến môi trường (được đặt trong systemd service)
ARTIFACT_BUCKET = os.environ["ARTIFACT_BUCKET"]
MODEL_KEY = "artifacts/current/model.joblib"
MODEL_PATH = os.path.expanduser("~/models/model.joblib")


def download_model():
    """Tải file model.joblib từ S3 về máy khi server khởi động."""
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    boto3.client("s3").download_file(ARTIFACT_BUCKET, MODEL_KEY, MODEL_PATH)
    print("Model da duoc tai xuong tu Amazon S3.")


# Gọi hàm này khi module được import (chạy khi server khởi động)
download_model()
model = joblib.load(MODEL_PATH)


class ScoreRequest(BaseModel):
    features: list[float]


@app.get("/healthz")
def healthz():
    """Endpoint kiểm tra sức khỏe server. GitHub Actions dùng endpoint này để xác nhận triển khai thành công."""
    # TODO 2.6.6: Trả về dict {"status": "ok"}
    pass  # xóa dòng này khi đã viết xong


@app.post("/score")
def score(req: ScoreRequest):
    """
    Endpoint suy luận.

    Đầu vào: JSON {"features": [f1, f2, ..., f10]}
    Đầu ra:  JSON {"prediction": <0|1>, "label": <"thu_nhap_thap"|"thu_nhap_cao">}
    """
    # TODO 2.6.7: Kiểm tra len(req.features) == 10.
    #   Nếu không, raise HTTPException(status_code=400, detail="Expected 10 features (adult income)")

    # TODO 2.6.8: Gọi model.predict([req.features]) để lấy kết quả dự đoán.

    # TODO 2.6.9: Trả về dict chứa "prediction" (int) và "label" (string).
    #   Nhãn: 0 -> "thu_nhap_thap", 1 -> "thu_nhap_cao"
    pass  # xóa dòng này khi đã viết xong


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
```

Upload file `serve.py` lên VM:

```bash
scp -i ~/.ssh/income_lab.pem src/serve.py ubuntu@<EC2_PUBLIC_IP>:~/src/serve.py
```

---

## 2.7 Cấu Hình Systemd Service Trên VM

SSH trở lại vào VM:

```bash
ssh -i ~/.ssh/income_lab.pem ubuntu@<EC2_PUBLIC_IP>
```

Tạo file service để server tự động khởi động lại khi VM reboot:

```bash
sudo tee /etc/systemd/system/income-api.service > /dev/null <<EOF
[Unit]
Description=Income Model Inference Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
Environment="ARTIFACT_BUCKET=<YOUR_BUCKET_NAME>"
ExecStart=/home/ubuntu/venv/bin/python /home/ubuntu/src/serve.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable income-api
```

Thay `<YOUR_BUCKET_NAME>` bằng tên bucket thực sự của bạn trước khi chạy.

Chưa cần khởi động service lúc này. Model chưa có trên cloud storage cho đến khi pipeline CI/CD chạy lần đầu tiên.

---

## 2.8 Tạo SSH Key Để GitHub Actions Triển Khai

Chạy trên máy tính cá nhân (không phải VM):

```bash
ssh-keygen -t ed25519 -f ~/.ssh/income_deploy -N "" -C "github-actions-deploy"
```

Thêm public key vào EC2:

```bash
ssh -i ~/.ssh/income_lab.pem ubuntu@<EC2_PUBLIC_IP> \
  "echo '$(cat ~/.ssh/income_deploy.pub)' >> ~/.ssh/authorized_keys"
```

---

## 2.9 Thêm GitHub Secrets

Vào repo GitHub: Settings > Secrets and variables > Actions > New repository secret.

Thêm chính xác 6 secrets sau:

| Tên secret | Cách lấy giá trị |
|---|---|
| `AWS_ACCESS_KEY_ID` | Access key của IAM user `income-lab-ci` |
| `AWS_SECRET_ACCESS_KEY` | Secret key của IAM user `income-lab-ci` |
| `ARTIFACT_BUCKET` | Tên bucket S3 |
| `SERVER_HOST` | IP công khai của EC2 |
| `SERVER_USER` | `ubuntu` |
| `SERVER_SSH_KEY` | Toàn bộ private key `~/.ssh/income_lab.pem` |

Kiểm tra: Mỗi secret khi dán vào phải không có khoảng trắng ở đầu hoặc cuối.

---

## 2.10 Viết `tests/test_train.py`

Các test này chạy trên dữ liệu nhỏ tạo trong bộ nhớ (không cần pull DVC), đảm bảo chạy được trong GitHub Actions mà không cần xác thực cloud storage.

Tạo file `tests/test_train.py` theo khung dưới đây:

```python
import os
import json
import numpy as np
import pandas as pd
from src.train import train


FEATURE_NAMES = [
    "age", "workclass", "education_num", "marital_status", "occupation",
    "relationship", "sex", "capital_gain", "capital_loss", "hours_per_week",
]


def _make_temp_data(tmp_path):
    """
    Tạo dataset nhỏ với cùng schema Adult để sử dụng trong test.

    pytest cung cấp `tmp_path` là một thư mục tạm thời, tự động được xóa sau khi test kết thúc.
    """
    rng = np.random.default_rng(0)
    n = 200
    # TODO 2.10.1: Tạo mảng X có kích thước (n, len(FEATURE_NAMES)) với giá trị ngẫu nhiên [0, 1)
    # TODO 2.10.2: Tạo mảng y có n phần tử, mỗi phần tử là số nguyên ngẫu nhiên trong [0, 2)
    #   Chú ý: bài toán này chỉ có HAI lớp, nên cận trên là 2 chứ không phải 3.
    # TODO 2.10.3: Tạo DataFrame từ X với các cột là FEATURE_NAMES, thêm cột "target" = y
    # TODO 2.10.4: Lưu 160 dòng đầu vào file train.csv và 40 dòng cuối vào file holdout.csv tại tmp_path
    # TODO 2.10.5: Trả về (train_path, eval_path)
    pass  # xóa dòng này khi đã viết xong


def test_train_returns_float(tmp_path):
    """Kiểm tra hàm train() trả về một số thực trong khoảng [0, 1]."""
    train_path, eval_path = _make_temp_data(tmp_path)
    # TODO 2.10.6: Gọi hàm train() với siêu tham số nhỏ
    #   (n_estimators=10, learning_rate=0.1, max_depth=2)
    # TODO 2.10.7: assert kết quả trả về là float và nằm trong [0.0, 1.0]
    pass  # xóa dòng này khi đã viết xong


def test_report_file_created(tmp_path):
    """Kiểm tra file outputs/report.json được tạo sau khi huấn luyện."""
    train_path, eval_path = _make_temp_data(tmp_path)
    train(
        {"n_estimators": 10, "learning_rate": 0.1, "max_depth": 2},
        data_path=train_path,
        eval_path=eval_path,
    )
    # TODO 2.10.8: assert file "outputs/report.json" tồn tại
    # TODO 2.10.9: Đọc file report.json và assert nó chứa cả "f1_score" và "accuracy"
    pass  # xóa dòng này khi đã viết xong


def test_model_file_created(tmp_path):
    """Kiểm tra file models/model.joblib được tạo sau khi huấn luyện."""
    train_path, eval_path = _make_temp_data(tmp_path)
    train(
        {"n_estimators": 10, "learning_rate": 0.1, "max_depth": 2},
        data_path=train_path,
        eval_path=eval_path,
    )
    # TODO 2.10.10: assert file "models/model.joblib" tồn tại
    pass  # xóa dòng này khi đã viết xong
```

Chạy thử test cục bộ trước khi commit:

```bash
pytest tests/ -v
```

Ba test đều phải qua trước khi tiếp tục.

---

## 2.11 Viết `.github/workflows/cicd.yml`

Pipeline gồm bốn jobs chạy theo thứ tự: Unit Test -> Train -> Quality Gate -> Release.

Tạo file `.github/workflows/cicd.yml` theo khung dưới đây:

```yaml
name: Income Model CI/CD

on:
  push:
    branches: [main]
    paths:
      - 'data/**.dvc'
      - 'src/**.py'
      - 'params.yaml'
  workflow_dispatch:

jobs:

  # JOB 1: Chạy unit tests trên dữ liệu ảo (không cần cloud storage)
  unit-test:
    name: Unit Test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        # TODO 2.11.1: Chạy pytest trên thư mục tests/ với cờ -v
        run: # <điền lệnh ở đây>

  # JOB 2: Huấn luyện mô hình trên dữ liệu thực, upload artifact lên cloud storage
  train:
    name: Train
    needs: unit-test         # Chỉ chạy khi job unit-test qua
    runs-on: ubuntu-latest
    outputs:
      f1: ${{ steps.read_report.outputs.f1 }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Authenticate to Amazon S3
        # AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY lấy từ GitHub Secrets.
        run: |
          # <điền code ở đây>

      - name: Pull data with DVC
        # TODO 2.11.3: Dùng lệnh dvc pull để tải train_batch1.csv và holdout.csv từ cloud storage
        run: # <điền lệnh ở đây>

      - name: Train model
        run: python src/train.py

      - name: Read report
        id: read_report
        # TODO 2.11.4: Đọc giá trị "f1_score" từ file outputs/report.json
        #   và set nó thành output "f1" để job quality-gate có thể đọc được.
        #   Gợi ý: sử dụng python -c "..." và echo "f1=..." >> $GITHUB_OUTPUT
        run: |
          # <điền code ở đây>

      - name: Upload model to Amazon S3
        # Sử dụng boto3 upload lên s3://<bucket>/artifacts/current/model.joblib.
        run: |
          python - <<'PYEOF'
          # <điền code Python ở đây>
          PYEOF

      - name: Save report as artifact
        uses: actions/upload-artifact@v4
        with:
          name: report
          path: outputs/report.json

  # JOB 3: Kiểm tra chất lượng - chỉ cho phép triển khai khi f1_score >= 0.65
  #   Lưu ý: ngưỡng đặt trên f1_score chứ KHÔNG phải accuracy. Dữ liệu có tỷ lệ
  #   lớp 75/25, nên một mô hình đoán bừa đã đạt accuracy 0.75 mà hoàn toàn vô dụng.
  quality-gate:
    name: Quality Gate
    needs: train             # Chỉ chạy khi job train qua
    runs-on: ubuntu-latest
    steps:

      - name: Check quality gate
        # TODO 2.11.6: Đọc giá trị f1 từ output của job train.
        #   Nếu f1 < 0.65, kết thúc với lỗi (SystemExit hoặc exit 1).
        #   Nếu đạt, in thông báo và tiếp tục.
        run: |
          python - <<'PYEOF'
          # <điền code Python ở đây>
          PYEOF

  # JOB 4: Triển khai sau khi quality gate qua
  release:
    name: Release
    needs: quality-gate      # Chỉ chạy khi job quality-gate qua
    runs-on: ubuntu-latest
    steps:

      - name: SSH deploy to VM
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            # TODO 2.11.7: Restart service income-api trên VM.
            # TODO 2.11.8: Chờ server sẵn sàng (sleep 5 giây) rồi gọi curl /healthz để xác nhận.
            #   Nếu health check thất bại, thoát với exit 1.
            # <điền lệnh bash ở đây>
```

---

## 2.12 Lần Chạy Pipeline Đầu Tiên

Tạo hai file con trong `src/` và `tests/` để Python có thể import module:

```bash
touch src/__init__.py tests/__init__.py
```

Push tất cả lên GitHub:

```bash
git add .
git commit -m "feat: add CI/CD pipeline, tests, and serving API"
git push origin main
```

Theo dõi pipeline trong tab **Actions** trên repo GitHub.

Sau khi pipeline chạy thành công và model đã được upload lên cloud storage, khởi động service trên VM:

```bash
ssh -i ~/.ssh/income_lab.pem ubuntu@<EC2_PUBLIC_IP> \
  "sudo systemctl start income-api"
```

Thử nghiệm endpoint:

```bash
VM_IP=<YOUR_VM_IP>

# Kiểm tra sức khỏe
curl http://$VM_IP:8080/healthz

# Dự đoán (10 đặc trưng theo thứ tự trong FEATURE_NAMES)
# Mẫu: 60 tuổi, Private, 5 năm học, đã kết hôn, Farming-fishing, Husband, Nam, 45 giờ/tuần
curl -X POST http://$VM_IP:8080/score \
  -H "Content-Type: application/json" \
  -d '{"features": [60, 2, 5, 2, 4, 0, 1, 0, 0, 45]}'
```

Kết quả mong đợi:

```json
{"prediction": 0, "label": "thu_nhap_thap"}
```

Thử thêm một mẫu có học vấn cao hơn để thấy mô hình đổi nhãn:

```bash
# Mẫu: 28 tuổi, Private, 14 năm học (thạc sĩ), đã kết hôn, Sales, Husband, Nam, 45 giờ/tuần
curl -X POST http://$VM_IP:8080/score \
  -H "Content-Type: application/json" \
  -d '{"features": [28, 2, 14, 2, 11, 0, 1, 0, 0, 45]}'
```

```json
{"prediction": 1, "label": "thu_nhap_cao"}
```

Lưu ý: kết quả cụ thể phụ thuộc vào mô hình bạn huấn luyện. Hai mẫu trên lấy từ tập holdout và cả hai đều được dự đoán đúng bởi mô hình huấn luyện với bộ tham số mặc định.

---

## Xử Lý Sự Cố

**`dvc push` thất bại với lỗi xác thực**

Xác nhận biến `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` và `AWS_DEFAULT_REGION` đã được đặt. Kiểm tra remote bằng:

```bash
cat .dvc/config
```

**GitHub Actions `dvc pull` thất bại**

Kiểm tra sáu GitHub Secrets `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `ARTIFACT_BUCKET`,
`SERVER_HOST`, `SERVER_USER` và `SERVER_SSH_KEY`, rồi xác nhận IAM policy trỏ đúng bucket.

**Job Release thất bại dù f1_score có vẻ đủ cao**

GitHub Actions outputs là kiểu chuỗi. Đảm bảo code Python trong quality gate thực hiện chuyển đổi `float()` trước khi so sánh. Kiểm tra giá trị f1_score được in trong log của job Train.

**Quality gate luôn bị chặn dù accuracy rất cao**

Đây là tình huống đặc trưng của bài này. Accuracy cao (0.85+) nhưng f1_score thấp có nghĩa là mô hình bỏ sót phần lớn các trường hợp thu nhập cao. Hãy kiểm tra:

- Bạn có gọi `f1_score(y_eval, preds)` đúng cho lớp dương không? Nếu lỡ truyền `average="weighted"`, giá trị sẽ bị lớp đa số kéo lên và không phản ánh đúng chất lượng.
- Bộ siêu tham số có quá yếu không? `learning_rate` thấp kết hợp `max_depth` nhỏ và `n_estimators` ít thường cho f1 dưới ngưỡng. Quay lại Bước 1 và chọn bộ tham số khác.

**Service trên VM không khởi động được**

Xem log của service:

```bash
sudo journalctl -u income-api -n 50
```

Nguyên nhân phổ biến:
- Biến môi trường `ARTIFACT_BUCKET` sai trong file service.
- EC2 instance profile chưa được gắn hoặc chưa có quyền `s3:GetObject` trên `artifacts/*`.
- File model chưa tồn tại trên cloud storage (service chỉ có thể khởi động sau khi pipeline lần đầu tiên chạy thành công).

---

## Kết Quả Cần Đạt - Bước 2

- Cả bốn GitHub Actions jobs (Unit Test, Train, Quality Gate, Release) đều hoàn thành thành công (màu xanh).
- `curl http://VM_IP:8080/healthz` trả về `{"status": "ok"}`.
- `curl http://VM_IP:8080/score` trả về kết quả dự đoán hợp lệ.
- S3 hiển thị object dưới prefix `dvc/` và model tại `artifacts/current/model.joblib`.

Chụp ba ảnh nộp bài, lưu vào `nop-bai/anh-chup-man-hinh/` (yêu cầu chi tiết:
[nop-bai/anh-chup-man-hinh/README.md](../nop-bai/anh-chup-man-hinh/README.md)):

| Tên file | Nội dung cần thấy rõ |
|---|---|
| `02-actions-buoc-2.png` | Tab Actions với cả bốn jobs màu xanh |
| `04-curl-api.png` | Terminal chứa cả hai lệnh `curl` và kết quả trả về, thấy rõ IP của VM |
| `05-cloud-storage.png` | Console hiển thị `dvc/` và `artifacts/current/model.joblib` |

---

Tiếp theo: [Bước 3 - Huấn luyện liên tục](buoc-3.md)
