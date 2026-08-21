# Tài nguyên AWS - Day 21

Đã provision thật bằng account `779047208133`, region `us-east-1`, ngày
21/08/2026. Không ghi secret access key hoặc nội dung private key vào repo.

## Tài nguyên đang dùng

| Loại | Tên / ID |
|---|---|
| S3 bucket | `income-lab-k4-day21-779047208133-20260821-856a783a` |
| S3 public access block | Đủ 4 cờ `true` |
| IAM user CI | `income-lab-ci-856a783a` |
| IAM policy CI | `IncomeLabS3Policy-856a783a` — chỉ bucket này, prefix `dvc/` và `artifacts/` |
| CI access key ID | `AKIA3KYWVATCXFBKS6WB` (secret không ghi) |
| EC2 instance | `i-0d56a7eaa98e140f2`, `t3.micro`, Ubuntu 22.04, `ami-06e78a71af43ef21a` |
| Public / private IP | `3.239.179.205` / `10.0.1.220` |
| Key pair | `income-lab-ec2-key-856a783a`; private key local `/home/hh/.ssh/income_lab.pem`, mode 400 |
| Security group | `income-lab-sg-856a783a` (`sg-08445fa21b1a8bff4`) |
| Security group ingress | TCP 8080 từ `0.0.0.0/0`; TCP 22 từ `58.186.69.190/32` và thêm `0.0.0.0/0` cho GitHub-hosted runner |
| EC2 role / profile | `income-lab-ec2-role-856a783a` / `income-lab-ec2-profile-856a783a` |
| EC2 inline policy | `IncomeLabArtifactsRead`, chỉ `s3:GetObject` trên `artifacts/*` |
| VPC / subnet | `vpc-049cf62ad1658bdce` / `subnet-06bab903f8b651157` |
| Internet gateway | `igw-0c0ca16c6854325f8` |
| Route table / association | `rtb-069f225c4f7b29936` / `rtbassoc-0a51a4c695a486476` |
| API service | systemd `income-api`, port 8080, model `artifacts/current/model.joblib` |
| DVC remote | `s3://income-lab-k4-day21-779047208133-20260821-856a783a/dvc` |

`ai-lab-user` thuộc group `AI-Lab-Group` và có inline policy
`IncomeLabS3Access` (được cấp trước/ngoài phần provision này); policy đó không
được dùng cho runtime EC2. Port 22 mở public là trade-off để GitHub Actions
hosted runner chạy `appleboy/ssh-action`; nên thu hẹp theo dải IP runner hoặc
đóng lại sau khi chấm bài.

## Teardown (chưa chạy)

Chạy lần lượt sau khi chấm bài; kiểm tra lại ID trước khi thực hiện. Lệnh xoá
bucket sẽ xoá các object DVC/artifact trong bucket.

```bash
REGION=us-east-1
BUCKET=income-lab-k4-day21-779047208133-20260821-856a783a
INSTANCE_ID=i-0d56a7eaa98e140f2
SG_ID=sg-08445fa21b1a8bff4
KEY_NAME=income-lab-ec2-key-856a783a
ROLE_NAME=income-lab-ec2-role-856a783a
PROFILE_NAME=income-lab-ec2-profile-856a783a
LAB_USER=income-lab-ci-856a783a
CI_KEY_ID=AKIA3KYWVATCXFBKS6WB
VPC_ID=vpc-049cf62ad1658bdce
SUBNET_ID=subnet-06bab903f8b651157
IGW_ID=igw-0c0ca16c6854325f8
RTB_ID=rtb-069f225c4f7b29936
ASSOC_ID=rtbassoc-0a51a4c695a486476

aws s3 rm "s3://$BUCKET" --recursive --region "$REGION"
aws s3api delete-bucket --bucket "$BUCKET" --region "$REGION"
aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
aws ec2 wait instance-terminated --instance-ids "$INSTANCE_ID" --region "$REGION"
aws ec2 delete-security-group --group-id "$SG_ID" --region "$REGION"
aws ec2 delete-key-pair --key-name "$KEY_NAME" --region "$REGION"
aws iam remove-role-from-instance-profile --instance-profile-name "$PROFILE_NAME" --role-name "$ROLE_NAME"
aws iam delete-instance-profile --instance-profile-name "$PROFILE_NAME"
aws iam delete-role-policy --role-name "$ROLE_NAME" --policy-name IncomeLabArtifactsRead
aws iam delete-role --role-name "$ROLE_NAME"
aws iam delete-access-key --user-name "$LAB_USER" --access-key-id "$CI_KEY_ID"
aws iam delete-user-policy --user-name "$LAB_USER" --policy-name IncomeLabS3Policy-856a783a
aws iam delete-user --user-name "$LAB_USER"
aws ec2 disassociate-route-table --association-id "$ASSOC_ID" --region "$REGION"
aws ec2 delete-route-table --route-table-id "$RTB_ID" --region "$REGION"
aws ec2 detach-internet-gateway --internet-gateway-id "$IGW_ID" --vpc-id "$VPC_ID" --region "$REGION"
aws ec2 delete-internet-gateway --internet-gateway-id "$IGW_ID" --region "$REGION"
aws ec2 delete-subnet --subnet-id "$SUBNET_ID" --region "$REGION"
aws ec2 delete-vpc --vpc-id "$VPC_ID" --region "$REGION"
```

Policy `IncomeLabS3Access` trên user `ai-lab-user` là quyền được cấp để gỡ
vật cản ban đầu, không phải tài nguyên CI tạo mới. Chỉ xoá khi đã được phép:

```bash
aws iam delete-user-policy --user-name ai-lab-user --policy-name IncomeLabS3Access
```

Có thể xoá 6 GitHub Secrets sau khi teardown bằng `gh secret delete` với đúng
tên trong workflow: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`ARTIFACT_BUCKET`, `SERVER_HOST`, `SERVER_USER`, `SERVER_SSH_KEY`.
