import os

import boto3
from dotenv import load_dotenv

load_dotenv("docker/.env")

# Khởi tạo S3 Client
# Nếu đã có biến môi trường AWS_... chuẩn như trên, boto3 tự đọc, không cần truyền tham số
s3 = boto3.client("s3")

bucket_name = os.getenv("S3_BUCKET_NAME")

# 1. Test Upload file
print("Dang upload file...")
with open("test.txt", "w") as f:
    f.write("Hello from Local Computer!")

s3.upload_file("test.txt", bucket_name, "hello_s3.txt")
print("Upload thanh cong!")

# 2. Test List file
print("Danh sach file trong bucket:")
response = s3.list_objects_v2(Bucket=bucket_name)
if "Contents" in response:
    for obj in response["Contents"]:
        print(f"- {obj['Key']} (Size: {obj['Size']} bytes)")

        # Nếu bạn muốn lấy URL công khai (nhưng bucket private thì link này sẽ 403 Forbidden)
        url = f"https://{bucket_name}.s3.{os.getenv('AWS_REGION')}.amazonaws.com/{obj['Key']}"
        print(f"  Link (Private): {url}")
