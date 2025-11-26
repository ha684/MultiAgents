import asyncio
from pathlib import Path
from typing import Dict

import aiohttp

# Configuration
API_BASE_URL = "http://localhost:8000"  # Thay bằng URL API của bạn
API_KEY = "hapt68"
FOLDER_PATH = r"C:\workspace\data"  # Thay bằng đường dẫn folder của bạn

EXISTING_KB_ID = None

# Supported file extensions
SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".md",
    ".ppt",
    ".pptx",
    ".rtf",
    ".odt",
    # Images
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".bmp",
    ".svg",
    ".webp",
    ".tiff",
    # Code files
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".cpp",
    ".c",
    ".h",
    ".cs",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".swift",
    ".kt",
    ".scala",
    ".r",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".vue",
    ".sh",
    ".bash",
    ".yaml",
    ".yml",
    ".json",
    ".xml",
    ".toml",
    ".ini",
    ".env",
    # Structured data
    ".xlsx",
    ".xls",
    ".csv",
    ".tsv",
}


class KnowledgeBaseUploader:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    async def create_knowledge_base(
        self, session: aiohttp.ClientSession, name: str, description: str
    ) -> str:
        """Create a knowledge base and return its ID"""
        url = f"{self.base_url}/kb/create"
        payload = {"name": name, "description": description}

        async with session.post(url, json=payload, headers=self.headers) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(
                    f"Failed to create KB '{name}': {response.status} - {text}"
                )

            data = await response.json()
            print(f"Response data: {data}")  # Debug

            # Response được wrap trong envelope với "data" field
            actual_data = data.get("data", data)

            # Thử các field có thể có trong actual_data
            kb_id = (
                actual_data.get("id")
                or actual_data.get("knowledge_base_id")
                or actual_data.get("kb_id")
            )

            if not kb_id:
                raise Exception(f"KB ID not found in response. Full response: {data}")

            print(f"✓ Created knowledge base: {name} (ID: {kb_id})")
            return str(kb_id)

    async def upload_file(
        self, session: aiohttp.ClientSession, kb_id: str, file_path: Path
    ) -> Dict:
        """Upload a single file to a knowledge base"""
        url = f"{self.base_url}/documents/upload_and_process"

        # Tạo FormData để upload file
        data = aiohttp.FormData()

        # Đọc file và thêm vào form
        with open(file_path, "rb") as f:
            file_content = f.read()
            data.add_field(
                "file",
                file_content,
                filename=file_path.name,
                content_type="application/octet-stream",
            )

        # knowledge_base_id phải là query parameter
        params = {"knowledge_base_id": kb_id}

        # Headers cho upload file (không có Content-Type vì FormData tự set)
        upload_headers = {"Authorization": f"Bearer {self.api_key}"}

        async with session.post(
            url, data=data, params=params, headers=upload_headers
        ) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"Status {response.status}: {text}")

            result = await response.json()

            # Response được wrap, lấy data thực từ envelope
            actual_result = result.get("data", result)
            task_id = actual_result.get("task_id", "N/A")

            print(f"  ✓ Uploaded: {file_path.name} (Task: {task_id})")
            return actual_result

    async def process_folder(self, folder_path: str):
        """Main function to process all files in folder"""
        folder = Path(folder_path)

        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Folder not found: {folder_path}")

        # Collect all supported files
        all_files = []
        for file_path in folder.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix.lower()
                if ext in SUPPORTED_EXTENSIONS:
                    all_files.append(file_path)

        print(f"\nFound {len(all_files)} files to upload\n")

        async with aiohttp.ClientSession() as session:
            # Get or create knowledge base
            print("Setting up knowledge base...")

            if EXISTING_KB_ID:
                kb_id = EXISTING_KB_ID
                print(f"✓ Using existing KB: {kb_id}")
            else:
                kb_id = await self.create_knowledge_base(
                    session,
                    "All Documents",
                    "Knowledge base for all document types including PDFs, Office docs, images, code files, and structured data",
                )

            # Upload all files
            if all_files:
                print(f"\nUploading {len(all_files)} files...")
                success_count = 0
                failed_files = []

                for file_path in all_files:
                    try:
                        await self.upload_file(session, kb_id, file_path)
                        success_count += 1
                    except Exception as e:
                        print(f"  ✗ Error uploading {file_path.name}: {str(e)}")
                        failed_files.append((file_path.name, str(e)))

                print(
                    f"\n  → Successfully uploaded {success_count}/{len(all_files)} files"
                )

                if failed_files:
                    print(f"\n  Failed files ({len(failed_files)}):")
                    for filename, error in failed_files:
                        print(f"    - {filename}: {error}")

        print("\n" + "=" * 60)
        print("✓ All done!")
        print("=" * 60)
        print(f"\nKnowledge Base ID: {kb_id}")
        print("\nTo skip KB creation next time, update the script:")
        print(f"  EXISTING_KB_ID = '{kb_id}'")


async def main():
    uploader = KnowledgeBaseUploader(API_BASE_URL, API_KEY)
    await uploader.process_folder(FOLDER_PATH)


if __name__ == "__main__":
    asyncio.run(main())
