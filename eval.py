import asyncio
import json
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import aiohttp
import pandas as pd
from datasets import Dataset
from openpyxl.styles import Font, PatternFill
from ragas import evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)

from src.core.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm

API_BASE_URL = "http://localhost:8000"
API_KEY = "hapt68"
USER_ID = "hafizh"
APP_NAME = "evaluation_app"

# Knowledge Base ID
KB_ID = "06926e2f-3437-7cc5-8000-2162ac635054"

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


class RagasLLMEvaluator:
    def __init__(
        self, base_url: str, api_key: str, llm_provider: SupportedLLMProviders
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.normal_results = []
        self.agent_results = []
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.output_file = f"ragas_evaluation_report_{self.timestamp}.xlsx"
        self.temp_file = f"ragas_evaluation_temp_{self.timestamp}.json"
        self.timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        # Initialize custom LLM
        self.llm_provider = llm_provider
        self.llm = None
        self.embeddings = None

        # Flag to track if evaluation is cancelled
        self.is_cancelled = False

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle interrupt signals (Ctrl+C)"""
        print("\n\n⚠️  Interrupt received! Saving current progress...")
        self.is_cancelled = True
        self.save_temp_results()
        print(f"✅ Progress saved to: {self.temp_file}")
        print("📊 Generating partial report...")
        self.generate_final_report(partial=True)
        print(f"✅ Partial report saved to: {self.output_file}")
        exit(0)

    def save_temp_results(self):
        """Save temporary results to JSON file"""
        temp_data = {
            "timestamp": self.timestamp,
            "normal_results": self.normal_results,
            "agent_results": self.agent_results,
        }

        with open(self.temp_file, "w", encoding="utf-8") as f:
            json.dump(temp_data, f, ensure_ascii=False, indent=2)

        print(
            f"💾 Saved {len(self.normal_results)} normal mode + {len(self.agent_results)} agent mode results"
        )

    def load_temp_results(self) -> bool:
        """Load temporary results if exists"""
        if Path(self.temp_file).exists():
            try:
                with open(self.temp_file, "r", encoding="utf-8") as f:
                    temp_data = json.load(f)
                    self.normal_results = temp_data.get("normal_results", [])
                    self.agent_results = temp_data.get("agent_results", [])
                    print(
                        f"📂 Loaded previous progress: {len(self.normal_results)} normal + {len(self.agent_results)} agent results"
                    )
                    return True
            except Exception as e:
                print(f"⚠️  Failed to load temp file: {e}")
                return False
        return False

    def _initialize_llm(self):
        """Initialize custom LLM for Ragas"""
        try:
            self.llm = get_llm(self.llm_provider)
            print(f"✅ Initialized custom LLM: {self.llm_provider}")
        except Exception as e:
            print(f"❌ Failed to initialize custom LLM: {e}")
            print("⚠️  Falling back to default Ragas LLM")
            self.llm = None

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

    def evaluate_with_ragas(self, results_data: List[Dict]) -> pd.DataFrame:
        """Đánh giá bằng Ragas metrics với custom LLM"""
        if not results_data:
            return pd.DataFrame()

        print("\n🔍 Running Ragas evaluation...")

        # Initialize LLM if not already done
        if self.llm is None:
            self._initialize_llm()

        # Prepare data for Ragas
        dataset_dict = {
            "question": [],
            "answer": [],
            "ground_truth": [],
            "contexts": [],
        }

        for result in results_data:
            dataset_dict["question"].append(result["query"])
            dataset_dict["answer"].append(result["endpoint_response"])
            dataset_dict["ground_truth"].append(result["labeled_response"])
            contexts = result.get("contexts", [])
            if not contexts:
                contexts = ["No context retrieved"]
            dataset_dict["contexts"].append(contexts)

        # Create Ragas dataset
        dataset = Dataset.from_dict(dataset_dict)

        # Evaluate với các metrics
        metrics = [
            answer_relevancy,
            answer_correctness,
            answer_similarity,
            faithfulness,
            context_precision,
            context_recall,
        ]

        try:
            # Use custom LLM if available
            eval_kwargs = {"dataset": dataset, "metrics": metrics}

            if self.llm is not None:
                eval_kwargs["llm"] = self.llm
                print(f"🤖 Using custom LLM: {self.llm_provider}")
            else:
                print("🤖 Using default Ragas LLM")

            evaluation_result = evaluate(**eval_kwargs)

            # Convert to DataFrame
            results_df = evaluation_result.to_pandas()

            # Add original data
            for i, result in enumerate(results_data):
                results_df.loc[i, "document_name"] = result["document_name"]
                results_df.loc[i, "file_type"] = result["file_type"]
                results_df.loc[i, "response_time_seconds"] = result[
                    "response_time_seconds"
                ]
                results_df.loc[i, "num_contexts"] = len(result.get("contexts", []))

            return results_df

        except Exception as e:
            print(f"❌ Ragas evaluation error: {e}")
            # Fallback to basic results
            return pd.DataFrame(results_data)

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
    ) -> tuple[str, float, bool, List[str]]:
        """Gửi câu hỏi và đo thời gian response, lấy contexts"""
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
            # Check if cancelled
            if self.is_cancelled:
                return "Error: Cancelled", 0.0, False, []

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
                            return f"Error: {response.status}", response_time, False, []

                    data = await response.json()
                    actual_data = data.get("data", data)

                    # Extract answer text
                    parts = actual_data.get("parts", [])
                    answer_text = ""
                    for part in parts:
                        if part.get("type") == "text":
                            answer_text += part.get("text", "")

                    # Extract contexts from retrieval_context
                    contexts = []
                    retrieval_context = actual_data.get("retrieval_context", {})
                    cited_chunks = retrieval_context.get("cited_chunks", [])

                    for chunk in cited_chunks:
                        if isinstance(chunk, dict):
                            page_content = chunk.get("page_content", "")
                        else:
                            page_content = getattr(chunk, "page_content", "")

                        if page_content:
                            contexts.append(page_content)

                    return answer_text, response_time, True, contexts

            except asyncio.TimeoutError:
                response_time = time.time() - start_time
                if attempt < MAX_RETRIES - 1:
                    print(f"  ⚠ Timeout, retrying ({attempt + 1}/{MAX_RETRIES})...")
                    await asyncio.sleep(2**attempt)
                    continue
                else:
                    print(f"  ❌ Timeout after {MAX_RETRIES} attempts")
                    return "Error: Timeout", response_time, False, []

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
                    return f"Error: {type(e).__name__}", response_time, False, []

        return "Error: Unknown", 0.0, False, []

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
            # Check if cancelled before processing each document
            if self.is_cancelled:
                print(
                    f"\n⚠️  Evaluation cancelled. Processed {question_count} questions."
                )
                break

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
                # Check if cancelled before each question
                if self.is_cancelled:
                    break

                question = qa.get("question", "")
                expected_answer = qa.get("answer", "")

                if not question or not expected_answer:
                    continue

                question_count += 1
                print(f"  [{idx}/{len(qa_pairs)}] Asking question...")

                (
                    actual_answer,
                    response_time,
                    is_success,
                    contexts,
                ) = await self.ask_question(
                    session, conversation_id, question, use_agent
                )

                if not is_success:
                    actual_answer = "Error: Request failed"
                    contexts = []

                print(
                    f"    ⏱ {response_time:.2f}s | {len(contexts)} contexts retrieved"
                )

                result = {
                    "document_name": filename,
                    "file_type": file_type,
                    "query": question,
                    "labeled_response": expected_answer,
                    "endpoint_response": actual_answer,
                    "contexts": contexts,
                    "response_time_seconds": round(response_time, 2),
                    "request_success": is_success,
                }

                results.append(result)

                # Auto-save progress every 10 questions
                if question_count % 10 == 0:
                    if use_agent:
                        self.agent_results = results
                    else:
                        self.normal_results = results
                    self.save_temp_results()

        print(f"\n✅ Completed {question_count} questions for {mode_name}")
        return results

    async def run_evaluation(self):
        """Chạy evaluation cho cả 2 modes"""
        print("Starting Ragas-based LLM Evaluation with Custom LLM")
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"KB ID: {KB_ID}")
        print(f"LLM Provider: {self.llm_provider}\n")

        # Try to load previous progress
        if self.load_temp_results():
            user_input = input("Continue from previous progress? (y/n): ")
            if user_input.lower() != "y":
                self.normal_results = []
                self.agent_results = []

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                # Evaluate Normal Mode (agent=False)
                if not self.normal_results or len(self.normal_results) == 0:
                    self.normal_results = await self.evaluate_mode(
                        session, use_agent=False
                    )
                    self.save_temp_results()
                else:
                    print(
                        f"⏭️  Skipping Normal Mode (already completed: {len(self.normal_results)} questions)"
                    )

                # Evaluate Agent Mode (agent=True)
                if not self.is_cancelled:
                    if not self.agent_results or len(self.agent_results) == 0:
                        self.agent_results = await self.evaluate_mode(
                            session, use_agent=True
                        )
                        self.save_temp_results()
                    else:
                        print(
                            f"⏭️  Skipping Agent Mode (already completed: {len(self.agent_results)} questions)"
                        )

            self.generate_final_report()

            # Clean up temp file after successful completion
            if Path(self.temp_file).exists():
                Path(self.temp_file).unlink()
                print(f"🗑️  Cleaned up temporary file: {self.temp_file}")

        except Exception as e:
            print(f"\n❌ Error during evaluation: {e}")
            self.save_temp_results()
            print(f"💾 Progress saved to: {self.temp_file}")
            raise

    def add_statistics_to_sheet(
        self, df: pd.DataFrame, sheet_name: str, writer, partial: bool = False
    ):
        """Thêm thống kê vào cuối sheet"""
        if df.empty:
            return

        # Add partial warning if needed
        if partial:
            sheet_name = f"{sheet_name} (Partial)"

        # Tính toán statistics
        total = len(df)

        # Ragas metrics statistics
        ragas_metrics = {
            "answer_relevancy": df.get("answer_relevancy", pd.Series()).mean(),
            "answer_correctness": df.get("answer_correctness", pd.Series()).mean(),
            "answer_similarity": df.get("answer_similarity", pd.Series()).mean(),
            "faithfulness": df.get("faithfulness", pd.Series()).mean(),
            "context_precision": df.get("context_precision", pd.Series()).mean(),
            "context_recall": df.get("context_recall", pd.Series()).mean(),
        }

        avg_time = df["response_time_seconds"].mean()
        avg_contexts = df.get("num_contexts", pd.Series()).mean()

        # Statistics by file type
        file_type_stats = []
        for file_type in df["file_type"].unique():
            type_df = df[df["file_type"] == file_type]
            type_total = len(type_df)
            type_avg_time = type_df["response_time_seconds"].mean()

            type_stats = {
                "File Type": file_type.upper(),
                "Total": type_total,
                "Avg Time (s)": round(type_avg_time, 2),
            }

            # Add Ragas metrics for this file type
            for metric_name in ragas_metrics.keys():
                if metric_name in type_df.columns:
                    type_stats[metric_name.replace("_", " ").title()] = round(
                        type_df[metric_name].mean(), 3
                    )

            file_type_stats.append(type_stats)

        # Ghi data vào sheet
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)

        worksheet = writer.sheets[sheet_name]

        # Vị trí bắt đầu statistics (sau data + 2 dòng trống)
        start_row = len(df) + 3

        # Overall Statistics
        status_text = (
            "OVERALL STATISTICS (PARTIAL)" if partial else "OVERALL STATISTICS"
        )
        worksheet.cell(start_row, 1, status_text)
        worksheet.cell(start_row, 1).font = Font(bold=True, size=12)
        worksheet.cell(start_row, 1).fill = PatternFill(
            start_color="4472C4", end_color="4472C4", fill_type="solid"
        )
        worksheet.cell(start_row, 1).font = Font(bold=True, size=12, color="FFFFFF")

        row = start_row + 1
        worksheet.cell(row, 1, "Total Questions:")
        worksheet.cell(row, 2, total)

        row += 1
        worksheet.cell(row, 1, "Average Response Time:")
        worksheet.cell(row, 2, f"{avg_time:.2f}s")

        row += 1
        worksheet.cell(row, 1, "Average Contexts Retrieved:")
        worksheet.cell(row, 2, f"{avg_contexts:.1f}")

        # Ragas metrics
        row += 2
        worksheet.cell(row, 1, "RAGAS METRICS (0-1 scale, higher is better)")
        worksheet.cell(row, 1).font = Font(bold=True)

        for metric_name, metric_value in ragas_metrics.items():
            if not pd.isna(metric_value):
                row += 1
                worksheet.cell(row, 1, f"{metric_name.replace('_', ' ').title()}:")
                worksheet.cell(row, 2, f"{metric_value:.3f}")

        # File Type Statistics
        stats_start_row = row + 3
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

    def generate_final_report(self, partial: bool = False):
        """Tạo final report với 2 sheets"""
        status = "PARTIAL " if partial else ""
        print(f"\n{'=' * 60}")
        print(f"GENERATING {status}REPORT WITH RAGAS METRICS")
        print(f"{'=' * 60}")

        with pd.ExcelWriter(self.output_file, engine="openpyxl") as writer:
            # Sheet 1: Normal Mode
            if self.normal_results:
                print("\n📊 Evaluating Normal Mode with Ragas...")
                df_normal = self.evaluate_with_ragas(self.normal_results)
                self.add_statistics_to_sheet(df_normal, "Normal Mode", writer, partial)
                print(f"✓ Normal Mode: {len(self.normal_results)} questions")

            # Sheet 2: Agent Mode
            if self.agent_results:
                print("\n📊 Evaluating Agent Mode with Ragas...")
                df_agent = self.evaluate_with_ragas(self.agent_results)
                self.add_statistics_to_sheet(df_agent, "Agent Mode", writer, partial)
                print(f"✓ Agent Mode: {len(self.agent_results)} questions")

        print(f"\n✅ {status}Report saved to: {self.output_file}")

        # Print summary with Ragas metrics
        if self.normal_results:
            df_normal = self.evaluate_with_ragas(self.normal_results)
            print("\n📈 Normal Mode Ragas Scores:")
            for metric in [
                "answer_relevancy",
                "answer_correctness",
                "answer_similarity",
                "faithfulness",
                "context_precision",
                "context_recall",
            ]:
                if metric in df_normal.columns:
                    score = df_normal[metric].mean()
                    print(f"   {metric.replace('_', ' ').title()}: {score:.3f}")

        if self.agent_results:
            df_agent = self.evaluate_with_ragas(self.agent_results)
            print("\n📈 Agent Mode Ragas Scores:")
            for metric in [
                "answer_relevancy",
                "answer_correctness",
                "answer_similarity",
                "faithfulness",
                "context_precision",
                "context_recall",
            ]:
                if metric in df_agent.columns:
                    score = df_agent[metric].mean()
                    print(f"   {metric.replace('_', ' ').title()}: {score:.3f}")


async def main():
    llm_provider = "nxchat"

    evaluator = RagasLLMEvaluator(API_BASE_URL, API_KEY, llm_provider=llm_provider)
    await evaluator.run_evaluation()


if __name__ == "__main__":
    asyncio.run(main())
