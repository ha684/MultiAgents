"""
Script để upload tất cả files từ một folder lên endpoint /documents/upload_and_process
"""

import uuid
from pathlib import Path
from typing import Optional

import requests

# Cấu hình
BASE_URL = "http://localhost:8000"
ENDPOINT = "/documents/upload_and_process"
AUTHORIZATION_TOKEN = "hapt68"
KNOWLEDGE_BASE_ID = (
    "0694b628-14b6-7665-8000-23469f812da1"  # Thay bằng UUID thực tế của bạn
)
FOLDER_PATH = (
    r"C:\Users\ha.phan\Downloads\data"  # Thay bằng đường dẫn folder chứa files
)


def upload_file(file_path: Path, kb_id: str, token: str) -> Optional[dict]:
    """
    Upload một file lên endpoint.

    Args:
        file_path: Đường dẫn đến file cần upload
        kb_id: Knowledge base ID (UUID)
        token: Bearer token để authentication

    Returns:
        Response JSON nếu thành công, None nếu thất bại
    """
    url = f"{BASE_URL}{ENDPOINT}"

    # Kiểm tra file có tồn tại không
    if not file_path.exists():
        print(f"❌ File không tồn tại: {file_path}")
        return None

    # Kiểm tra file size (max 100MB)
    file_size = file_path.stat().st_size
    max_size = 100 * 1024 * 1024  # 100MB
    if file_size > max_size:
        print(f"❌ File quá lớn ({file_size / (1024 * 1024):.2f}MB): {file_path.name}")
        return None

    try:
        # Mở file và upload
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            params = {"knowledge_base_id": kb_id}
            headers = {"Authorization": f"Bearer {token}"}

            print(f"📤 Đang upload: {file_path.name} ({file_size / 1024:.2f}KB)...")

            response = requests.post(
                url,
                files=files,
                params=params,
                headers=headers,
                timeout=300,  # 5 phút timeout
            )

            if response.status_code == 200:
                result = response.json()
                print(f"✅ Upload thành công: {file_path.name}")
                print(f"   Document ID: {result.get('id')}")
                print(f"   Task ID: {result.get('task_id')}")
                return result
            else:
                print(f"❌ Upload thất bại: {file_path.name}")
                print(f"   Status code: {response.status_code}")
                print(f"   Error: {response.text}")
                return None

    except Exception as e:
        print(f"❌ Lỗi khi upload {file_path.name}: {str(e)}")
        return None


def upload_all_files_from_folder(
    folder_path: str, kb_id: str, token: str, extensions: Optional[list[str]] = None
) -> dict:
    """
    Upload tất cả files từ một folder.

    Args:
        folder_path: Đường dẫn đến folder chứa files
        kb_id: Knowledge base ID (UUID)
        token: Bearer token để authentication
        extensions: Danh sách extensions cho phép (None = tất cả files)

    Returns:
        Dictionary với thống kê kết quả
    """
    folder = Path(folder_path)

    if not folder.exists():
        print(f"❌ Folder không tồn tại: {folder_path}")
        return {"success": 0, "failed": 0, "total": 0}

    if not folder.is_dir():
        print(f"❌ Đường dẫn không phải là folder: {folder_path}")
        return {"success": 0, "failed": 0, "total": 0}

    # Validate KB ID format
    try:
        uuid.UUID(kb_id)
    except ValueError:
        print(f"❌ Knowledge Base ID không hợp lệ (phải là UUID): {kb_id}")
        return {"success": 0, "failed": 0, "total": 0}

    # Lấy danh sách files
    if extensions:
        files = []
        for ext in extensions:
            files.extend(folder.glob(f"*{ext}"))
            files.extend(folder.glob(f"*{ext.upper()}"))
    else:
        files = [f for f in folder.iterdir() if f.is_file()]

    if not files:
        print(f"⚠️  Không tìm thấy file nào trong folder: {folder_path}")
        return {"success": 0, "failed": 0, "total": 0}

    print(f"\n📁 Tìm thấy {len(files)} file(s) trong folder: {folder_path}\n")

    # Upload từng file
    results = {"success": 0, "failed": 0, "total": len(files), "details": []}

    for file_path in files:
        result = upload_file(file_path, kb_id, token)
        if result:
            results["success"] += 1
            results["details"].append(
                {"file": file_path.name, "status": "success", "data": result}
            )
        else:
            results["failed"] += 1
            results["details"].append({"file": file_path.name, "status": "failed"})
        print()  # Dòng trống giữa các file

    # In thống kê
    print("=" * 60)
    print("📊 Thống kê:")
    print(f"   Tổng số file: {results['total']}")
    print(f"   ✅ Thành công: {results['success']}")
    print(f"   ❌ Thất bại: {results['failed']}")
    print("=" * 60)

    return results


if __name__ == "__main__":
    # Kiểm tra cấu hình
    if KNOWLEDGE_BASE_ID == "YOUR_KNOWLEDGE_BASE_ID_HERE":
        print("⚠️  Vui lòng thay đổi KNOWLEDGE_BASE_ID trong file test.py")
        print("   Ví dụ: KNOWLEDGE_BASE_ID = '123e4567-e89b-12d3-a456-426614174000'")
        exit(1)

    if FOLDER_PATH == "path/to/your/folder":
        print("⚠️  Vui lòng thay đổi FOLDER_PATH trong file test.py")
        print(
            "   Ví dụ: FOLDER_PATH = './documents' hoặc FOLDER_PATH = 'C:/Users/YourName/Documents'"
        )
        exit(1)

    # Upload tất cả files
    # Có thể chỉ định extensions nếu muốn (ví dụ: ['.pdf', '.docx', '.txt'])
    # Để None nếu muốn upload tất cả files
    upload_all_files_from_folder(
        folder_path=FOLDER_PATH,
        kb_id=KNOWLEDGE_BASE_ID,
        token=AUTHORIZATION_TOKEN,
        extensions=None,  # None = upload tất cả files, hoặc ['.pdf', '.docx'] để chỉ upload các file này
    )
