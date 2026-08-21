# Tài nguyên AWS - Day 21

Trạng thái: chưa tạo được tài nguyên. Lệnh đăng nhập hiện tại là
`arn:aws:iam::779047208133:user/ai-lab-user`, nhưng AWS trả về `AccessDenied` cho
`s3:CreateBucket` và `s3:ListAllMyBuckets`. Vì vậy chưa có bucket, IAM lab user,
access key, key pair, security group, instance profile hay EC2 instance nào được tạo.

Chẩn đoán đã xác nhận: `ec2:DescribeVpcs` và `ec2:DescribeImages` đọc được; điểm
chặn là quyền S3 trước khi có thể cấu hình DVC hoặc pipeline. Cần cấp tối thiểu
`s3:CreateBucket` (và các quyền S3 cần thiết) cho `ai-lab-user`, hoặc nhờ quản trị
viên tạo bucket rồi cấp quyền đúng bucket. Chưa đưa credential nào vào GitHub Secrets.

## Thông tin sẽ ghi lại sau khi được cấp quyền

```text
bucket:
lab IAM user:
instance id:
public IP:
security group id:
key pair path: ~/.ssh/income_lab.pem
```

## Lệnh teardown sau khi tạo tài nguyên

Thay các placeholder bằng ID thực tế trong file này rồi chạy từng lệnh, sau khi
đã kiểm tra đúng target:

```bash
aws ec2 terminate-instances --instance-ids <INSTANCE_ID>
aws ec2 wait instance-terminated --instance-ids <INSTANCE_ID>
aws ec2 delete-security-group --group-id <SG_ID>
aws ec2 delete-key-pair --key-name <KEY_NAME>
aws iam remove-role-from-instance-profile --instance-profile-name <PROFILE_NAME> --role-name <ROLE_NAME>
aws iam delete-instance-profile --instance-profile-name <PROFILE_NAME>
aws iam delete-role-policy --role-name <ROLE_NAME> --policy-name income-lab-artifacts-read
aws iam delete-role --role-name <ROLE_NAME>
aws iam delete-user-policy --user-name <LAB_IAM_USER> --policy-name income-lab-s3-policy
aws iam delete-access-key --user-name <LAB_IAM_USER> --access-key-id <ACCESS_KEY_ID>
aws iam delete-user --user-name <LAB_IAM_USER>
aws s3 rm s3://<BUCKET> --recursive
aws s3api delete-bucket --bucket <BUCKET>
```
