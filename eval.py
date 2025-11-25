import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import pandas as pd
from openpyxl.styles import Font, PatternFill

from src.llm.factory import get_llm

API_BASE_URL = "https://smart-kind-macaque.ngrok-free.app"
API_KEY = "hapt68"
USER_ID = "hafizh"
APP_NAME = "evaluation_app"

# Knowledge Base ID
KB_ID = "069241ac-c3e1-7341-8000-837652ccb703"

# File extensions để phân loại
UNSTRUCTURED_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".md", ".ppt", ".pptx"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp"}
STRUCTURED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".tsv"}
CODE_EXTENSIONS = {
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
}

REQUEST_TIMEOUT = 300
MAX_RETRIES = 3


class LLMEvaluator:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.client = get_llm("nxchat")
        self.normal_results = []
        self.agent_results = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = f"llm_evaluation_report_{self.timestamp}.xlsx"
        self.timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    def categorize_file_type(self, filename: str) -> str:
        """Phân loại file theo extension"""
        ext = Path(filename).suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return "image"
        elif ext in STRUCTURED_EXTENSIONS:
            return "structured"
        elif ext in CODE_EXTENSIONS:
            return "code"
        elif ext in UNSTRUCTURED_EXTENSIONS:
            return "unstructured"
        else:
            return "other"

    async def evaluate_answer(
        self, question: str, expected: str, actual: str
    ) -> Tuple[bool, Optional[str]]:
        """Đánh giá câu trả lời"""
        prompt = f"""You are an expert answer evaluator. Determine if the LLM's answer is correct/relevant.

Question: {question}

Expected Answer:
{expected}

LLM's Answer:
{actual}

EVALUATION CRITERIA:

PASS if:
- Same topic and main idea as expected answer
- Provides equivalent or more detailed information
- May use different wording but same meaning
- Numbers/data match expected answer

FAIL if:
- Completely wrong topic
- Information contradicts expected answer
- Doesn't answer the question
- Numbers/data significantly wrong
- Says "I don't know" or similar

Respond in JSON format ONLY:
{{
  "result": "PASS" or "FAIL",
  "reasoning": "brief explanation of why it passed/failed"
}}"""

        try:
            response = await self.client.ainvoke(prompt)
            response_text = response.content

            json_str = response_text.strip()
            if json_str.startswith("```json"):
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif json_str.startswith("```"):
                json_str = json_str.split("```")[1].split("```")[0].strip()

            result = json.loads(json_str)
            is_pass = result.get("result", "FAIL").upper() == "PASS"
            reasoning = result.get("reasoning", "")

            return is_pass, reasoning if not is_pass else None

        except Exception as e:
            print(f"  ⚠ Evaluation error: {e}")
            return False, f"Evaluation error: {str(e)}"

    async def list_documents(
        self, session: aiohttp.ClientSession, limit: int = 100
    ) -> List[Dict]:
        """Lấy danh sách documents từ KB"""
        url = f"{self.base_url}/documents"
        params = {"knowledge_base_id": KB_ID, "skip": 0, "limit": limit}

        async with session.get(url, params=params, headers=self.headers) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(f"Failed to list documents: {response.status} - {text}")

            data = await response.json()
            actual_data = data.get("data", data)
            items = actual_data.get("items", [])
            finished_docs = [doc for doc in items if doc.get("status") == "finished"]

            print(f"Found {len(finished_docs)} finished documents")
            return finished_docs

    async def get_qa_pairs(
        self, session: aiohttp.ClientSession, document_id: str
    ) -> List[Dict]:
        """Lấy QA pairs từ document"""
        url = f"{self.base_url}/documents/{document_id}/qa"

        async with session.get(url, headers=self.headers) as response:
            if response.status != 200:
                return []

            data = await response.json()
            actual_data = data.get("data", data)

            if isinstance(actual_data, list):
                return actual_data
            return []

    async def create_conversation(self, session: aiohttp.ClientSession) -> str:
        """Tạo conversation mới"""
        url = f"{self.base_url}/conversation/create"
        params = {"app_name": APP_NAME}

        async with session.post(url, params=params, headers=self.headers) as response:
            if response.status != 200:
                text = await response.text()
                raise Exception(
                    f"Failed to create conversation: {response.status} - {text}"
                )

            data = await response.json()
            actual_data = data.get("data", data)
            conversation_id = actual_data.get("conversation_id")

            if not conversation_id:
                raise Exception(f"Conversation ID not found in response: {data}")

            return conversation_id

    async def ask_question(
        self,
        session: aiohttp.ClientSession,
        conversation_id: str,
        question: str,
        use_agent: bool = False,
    ) -> tuple[str, float, bool]:
        """Gửi câu hỏi và đo thời gian response"""
        url = f"{self.base_url}/chat/ask"

        payload = {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": question}],
                "metadata": {
                    "conversation_id": conversation_id,
                    "kb_id": KB_ID,
                    "user_id": USER_ID,
                },
            },
            "agentic": use_agent,
            "web_search": False,
        }

        for attempt in range(MAX_RETRIES):
            start_time = time.time()

            try:
                async with session.post(
                    url, json=payload, headers=self.headers, timeout=self.timeout
                ) as response:
                    response_time = time.time() - start_time

                    if response.status != 200:
                        if attempt < MAX_RETRIES - 1:
                            print(
                                f"  ⚠ API Error {response.status}, retrying ({attempt + 1}/{MAX_RETRIES})..."
                            )
                            await asyncio.sleep(2**attempt)
                            continue
                        else:
                            print(
                                f"  ❌ API Error {response.status} after {MAX_RETRIES} attempts"
                            )
                            return f"Error: {response.status}", response_time, False

                    data = await response.json()
                    actual_data = data.get("data", data)

                    parts = actual_data.get("parts", [])
                    answer_text = ""
                    for part in parts:
                        if part.get("type") == "text":
                            answer_text += part.get("text", "")

                    return answer_text, response_time, True

            except asyncio.TimeoutError:
                response_time = time.time() - start_time
                if attempt < MAX_RETRIES - 1:
                    print(f"  ⚠ Timeout, retrying ({attempt + 1}/{MAX_RETRIES})...")
                    await asyncio.sleep(2**attempt)
                    continue
                else:
                    print(f"  ❌ Timeout after {MAX_RETRIES} attempts")
                    return "Error: Timeout", response_time, False

            except Exception as e:
                response_time = time.time() - start_time
                if attempt < MAX_RETRIES - 1:
                    print(
                        f"  ⚠ Unexpected error, retrying ({attempt + 1}/{MAX_RETRIES})..."
                    )
                    await asyncio.sleep(2**attempt)
                    continue
                else:
                    print(f"  ❌ Unexpected error: {e}")
                    return f"Error: {type(e).__name__}", response_time, False

        return "Error: Unknown", 0.0, False

    async def evaluate_mode(
        self, session: aiohttp.ClientSession, use_agent: bool
    ) -> List[Dict]:
        """Đánh giá với một mode (agent=True hoặc False)"""
        mode_name = "Agent Mode" if use_agent else "Normal Mode"
        print(f"\n{'=' * 60}")
        print(f"Evaluating: {mode_name}")
        print(f"{'=' * 60}")

        documents = await self.list_documents(session)

        if not documents:
            print("No finished documents found")
            return []

        conversation_id = await self.create_conversation(session)
        print(f"Created conversation: {conversation_id}\n")

        results = []
        question_count = 0

        for doc in documents:
            doc_id = doc.get("id")
            filename = doc.get("original_filename", "unknown")
            file_type = self.categorize_file_type(filename)

            print(f"\n📄 Processing: {filename} ({file_type})")

            qa_pairs = await self.get_qa_pairs(session, doc_id)

            if not qa_pairs:
                print("  No QA pairs found")
                continue

            print(f"  Found {len(qa_pairs)} QA pairs")

            for idx, qa in enumerate(qa_pairs, 1):
                question = qa.get("question", "")
                expected_answer = qa.get("answer", "")

                if not question or not expected_answer:
                    continue

                question_count += 1
                print(f"  [{idx}/{len(qa_pairs)}] Asking question...")

                actual_answer, response_time, is_success = await self.ask_question(
                    session, conversation_id, question, use_agent
                )

                if is_success:
                    is_correct, fail_reason = await self.evaluate_answer(
                        question, expected_answer, actual_answer
                    )
                else:
                    is_correct = False
                    fail_reason = f"Request failed: {actual_answer}"

                result_icon = "✓" if is_correct else "✗"
                status = (
                    "PASS"
                    if is_correct
                    else ("REQUEST_FAILED" if not is_success else "FAIL")
                )
                print(f"    {result_icon} {response_time:.2f}s | {status}")

                if not is_correct and fail_reason:
                    print(f"      ↳ {fail_reason[:100]}")

                result = {
                    "document_name": filename,
                    "file_type": file_type,
                    "query": question,
                    "labeled_response": expected_answer,
                    "endpoint_response": actual_answer,
                    "response_time_seconds": round(response_time, 2),
                    "is_correct": is_correct,
                    "fail_reason": fail_reason if not is_correct else "",
                }

                results.append(result)

        print(f"\n✅ Completed {question_count} questions for {mode_name}")
        return results

    async def run_evaluation(self):
        """Chạy evaluation cho cả 2 modes"""
        print("Starting LLM Evaluation")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"KB ID: {KB_ID}\n")

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            # Evaluate Normal Mode (agent=False)
            self.normal_results = await self.evaluate_mode(session, use_agent=False)

            # Evaluate Agent Mode (agent=True)
            self.agent_results = await self.evaluate_mode(session, use_agent=True)

        self.generate_final_report()

    def add_statistics_to_sheet(self, df: pd.DataFrame, sheet_name: str, writer):
        """Thêm thống kê vào cuối sheet"""
        if df.empty:
            return

        # Tính toán statistics
        total = len(df)
        correct = df["is_correct"].sum()
        accuracy = (correct / total * 100) if total > 0 else 0
        avg_time = df["response_time_seconds"].mean()

        # Statistics by file type
        file_type_stats = []
        for file_type in df["file_type"].unique():
            type_df = df[df["file_type"] == file_type]
            type_total = len(type_df)
            type_correct = type_df["is_correct"].sum()
            type_accuracy = (type_correct / type_total * 100) if type_total > 0 else 0
            type_avg_time = type_df["response_time_seconds"].mean()

            file_type_stats.append(
                {
                    "File Type": file_type.upper(),
                    "Total": type_total,
                    "Correct": type_correct,
                    "Accuracy (%)": round(type_accuracy, 2),
                    "Avg Time (s)": round(type_avg_time, 2),
                }
            )

        # Ghi data vào sheet
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)

        worksheet = writer.sheets[sheet_name]

        # Vị trí bắt đầu statistics (sau data + 2 dòng trống)
        start_row = len(df) + 3

        # Overall Statistics
        worksheet.cell(start_row, 1, "OVERALL STATISTICS")
        worksheet.cell(start_row, 1).font = Font(bold=True, size=12)
        worksheet.cell(start_row, 1).fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        worksheet.cell(start_row, 1).font = Font(bold=True, size=12, color="FFFFFF")

        worksheet.cell(start_row + 1, 1, "Total Questions:")
        worksheet.cell(start_row + 1, 2, total)
        worksheet.cell(start_row + 2, 1, "Correct Answers:")
        worksheet.cell(start_row + 2, 2, correct)
        worksheet.cell(start_row + 3, 1, "Accuracy:")
        worksheet.cell(start_row + 3, 2, f"{accuracy:.2f}%")
        worksheet.cell(start_row + 4, 1, "Average Response Time:")
        worksheet.cell(start_row + 4, 2, f"{avg_time:.2f}s")

        # File Type Statistics
        stats_start_row = start_row + 7
        worksheet.cell(stats_start_row, 1, "STATISTICS BY FILE TYPE")
        worksheet.cell(stats_start_row, 1).font = Font(bold=True, size=12)
        worksheet.cell(stats_start_row, 1).fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        worksheet.cell(stats_start_row, 1).font = Font(
            bold=True, size=12, color="FFFFFF"
        )

        # Headers
        stats_df = pd.DataFrame(file_type_stats)
        for col_idx, col_name in enumerate(stats_df.columns, 1):
            cell = worksheet.cell(stats_start_row + 1, col_idx, col_name)
            cell.font = Font(bold=True)
            cell.fill = PatternFill(
                start_color="D9E1F2", end_color="D9E1F2", fill_type="solid"
            )

        # Data
        for row_idx, row_data in enumerate(stats_df.values, stats_start_row + 2):
            for col_idx, value in enumerate(row_data, 1):
                worksheet.cell(row_idx, col_idx, value)

        # Adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            worksheet.column_dimensions[column_letter].width = adjusted_width

    def generate_final_report(self):
        """Tạo final report với 2 sheets"""
        print(f"\n{'=' * 60}")
        print("GENERATING FINAL REPORT")
        print(f"{'=' * 60}")

        with pd.ExcelWriter(self.output_file, engine="openpyxl") as writer:
            # Sheet 1: Normal Mode
            if self.normal_results:
                df_normal = pd.DataFrame(self.normal_results)
                self.add_statistics_to_sheet(df_normal, "Normal Mode", writer)
                print(f"\n📊 Normal Mode: {len(self.normal_results)} questions")

            # Sheet 2: Agent Mode
            if self.agent_results:
                df_agent = pd.DataFrame(self.agent_results)
                self.add_statistics_to_sheet(df_agent, "Agent Mode", writer)
                print(f"📊 Agent Mode: {len(self.agent_results)} questions")

        print(f"\n✅ Report saved to: {self.output_file}")

        # Print summary
        if self.normal_results:
            df_normal = pd.DataFrame(self.normal_results)
            total = len(df_normal)
            correct = df_normal["is_correct"].sum()
            accuracy = (correct / total * 100) if total > 0 else 0
            print(f"\n📈 Normal Mode Accuracy: {accuracy:.2f}% ({correct}/{total})")

        if self.agent_results:
            df_agent = pd.DataFrame(self.agent_results)
            total = len(df_agent)
            correct = df_agent["is_correct"].sum()
            accuracy = (correct / total * 100) if total > 0 else 0
            print(f"📈 Agent Mode Accuracy: {accuracy:.2f}% ({correct}/{total})")


async def main():
    evaluator = LLMEvaluator(API_BASE_URL, API_KEY)
    await evaluator.run_evaluation()


if __name__ == "__main__":
    asyncio.run(main())
