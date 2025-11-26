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
from src.rag.embeddings import ragas_embedding

API_BASE_URL = "http://localhost:8000"
API_KEY = "hapt68"
USER_ID = "hafizh"
APP_NAME = "evaluation_app"

# Knowledge Base ID
KB_ID = "06926eb4-af94-7355-8000-765cda3cfeec"

# Cấu hình Concurrency (Số luồng chạy song song)
CONCURRENCY_LIMIT = 2  # Tăng lên 10 hoặc 20 nếu server mạnh

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
        # Tìm file temp gần nhất nếu có để resume dễ hơn, hoặc dùng timestamp hiện tại
        self.temp_file = "ragas_evaluation_temp.json"
        self.timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        # Initialize custom LLM
        self.llm_provider = llm_provider
        self.llm = None

        # Flag to track if evaluation is cancelled
        self.is_cancelled = False

        # Semaphore for concurrency control
        self.semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle interrupt signals (Ctrl+C)"""
        print("\n\n⚠️  Interrupt received! Saving current progress...")
        self.is_cancelled = True
        # Không exit ngay lập tức mà để loop hiện tại finish việc save

    def save_temp_results(self):
        """Save temporary results to JSON file"""
        temp_data = {
            "last_updated": datetime.now().isoformat(),
            "normal_results": self.normal_results,
            "agent_results": self.agent_results,
        }

        # Save to a fixed filename so we can resume easily later
        with open(self.temp_file, "w", encoding="utf-8") as f:
            json.dump(temp_data, f, ensure_ascii=False, indent=2)

        print(
            f"💾 Saved {len(self.normal_results)} normal + {len(self.agent_results)} agent results to {self.temp_file}"
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
                        f"📂 RESUMING: Loaded {len(self.normal_results)} normal + {len(self.agent_results)} agent results"
                    )
                    return True
            except Exception as e:
                print(f"⚠️  Failed to load temp file: {e}")
                return False
        return False

    def _initialize_llm(self):
        """Initialize custom LLM for Ragas"""
        try:
            self.llm = get_llm(provider="nxchat")
            print(f"✅ Initialized custom LLM: {self.llm_provider}")
        except Exception as e:
            print(f"❌ Failed to initialize custom LLM: {e}")
            print("⚠️  Falling back to default Ragas LLM")
            self.llm = None

    def categorize_file_type(self, filename: str) -> str:
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

        print("\n🔍 Running Ragas evaluation (Metrics Calculation)...")

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
            # Ragas needs list of strings, handle empty
            if not contexts:
                contexts = ["No context retrieved"]
            dataset_dict["contexts"].append(contexts)

        dataset = Dataset.from_dict(dataset_dict)

        metrics = [
            answer_relevancy,
            answer_correctness,
            answer_similarity,
            faithfulness,
            context_precision,
            context_recall,
        ]

        try:
            eval_kwargs = {"dataset": dataset, "metrics": metrics}
            if self.llm is not None:
                eval_kwargs["llm"] = self.llm
            eval_kwargs["embeddings"] = ragas_embedding
            eval_kwargs["batch_size"] = 10
            # Run evaluation (Ragas supports async internal but we call it sync here)
            # You can also pass raise_exceptions=False to prevent crashing
            evaluation_result = evaluate(**eval_kwargs, raise_exceptions=False)
            results_df = evaluation_result.to_pandas()

            # Add original metadata back
            for i, result in enumerate(results_data):
                results_df.loc[i, "document_name"] = result.get(
                    "document_name", "unknown"
                )
                results_df.loc[i, "file_type"] = result.get("file_type", "unknown")
                results_df.loc[i, "response_time_seconds"] = result.get(
                    "response_time_seconds", 0
                )
                results_df.loc[i, "num_contexts"] = len(result.get("contexts", []))

            return results_df

        except Exception as e:
            print(f"❌ Ragas evaluation error: {e}")
            return pd.DataFrame(results_data)

    async def list_documents(
        self, session: aiohttp.ClientSession, limit: int = 100
    ) -> List[Dict]:
        url = f"{self.base_url}/documents"
        params = {"knowledge_base_id": KB_ID, "skip": 0, "limit": limit}
        async with session.get(url, params=params, headers=self.headers) as response:
            if response.status != 200:
                raise Exception(f"Failed to list documents: {response.status}")
            data = await response.json()
            items = data.get("data", data).get("items", [])
            return [doc for doc in items if doc.get("status") == "finished"]

    async def get_qa_pairs(
        self, session: aiohttp.ClientSession, document_id: str
    ) -> List[Dict]:
        url = f"{self.base_url}/documents/{document_id}/qa"
        try:
            async with session.get(url, headers=self.headers) as response:
                if response.status != 200:
                    return []
                data = await response.json()
                qa_data = data.get("data", data)
                return qa_data if isinstance(qa_data, list) else []
        except Exception:
            return []

    async def create_conversation(self, session: aiohttp.ClientSession) -> str:
        url = f"{self.base_url}/conversation/create"
        params = {"app_name": APP_NAME}
        async with session.post(url, params=params, headers=self.headers) as response:
            if response.status != 200:
                raise Exception(f"Failed to create conversation: {response.status}")
            data = await response.json()
            return data.get("data", data).get("conversation_id")

    async def _bounded_ask_question(
        self, session, conversation_id, question, use_agent, doc_info
    ):
        """Wrapper to limit concurrency using semaphore"""
        async with self.semaphore:
            if self.is_cancelled:
                return None

            print(f"  🚀 Sending: {question[:50]}...")
            answer, time_taken, success, contexts = await self.ask_question(
                session, conversation_id, question, use_agent
            )

            result = {
                "document_name": doc_info["filename"],
                "file_type": doc_info["file_type"],
                "query": question,
                "labeled_response": doc_info["expected_answer"],
                "endpoint_response": answer,
                "contexts": contexts,
                "response_time_seconds": round(time_taken, 2),
                "request_success": success,
            }

            status_icon = "✅" if success else "❌"
            print(f"  {status_icon} Finished: {question[:30]}... ({time_taken:.2f}s)")
            return result

    async def ask_question(
        self, session, conversation_id, question, use_agent
    ) -> tuple[str, float, bool, List[str]]:
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
                    duration = time.time() - start_time

                    if response.status != 200:
                        if attempt < MAX_RETRIES - 1:
                            await asyncio.sleep(1 * (attempt + 1))
                            continue
                        return f"Error: {response.status}", duration, False, []

                    data = await response.json()
                    actual_data = data.get("data", data)

                    # Parse Answer
                    answer_text = ""
                    for part in actual_data.get("parts", []):
                        if part.get("type") == "text":
                            answer_text += part.get("text", "")

                    # Parse Contexts
                    contexts = []
                    chunks = actual_data.get("retrieval_context", {}).get(
                        "cited_chunks", []
                    )
                    for chunk in chunks:
                        content = (
                            chunk.get("page_content", "")
                            if isinstance(chunk, dict)
                            else getattr(chunk, "page_content", "")
                        )
                        if content:
                            contexts.append(content)

                    return answer_text, duration, True, contexts

            except Exception as e:
                duration = time.time() - start_time
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(1)
                    continue
                return f"Error: {type(e).__name__}", duration, False, []

        return "Error: Unknown", 0.0, False, []

    async def evaluate_mode(
        self, session: aiohttp.ClientSession, use_agent: bool
    ) -> List[Dict]:
        mode_name = "Agent Mode" if use_agent else "Normal Mode"
        print(f"\n{'=' * 60}")
        print(f"Evaluating: {mode_name} | Concurrency: {CONCURRENCY_LIMIT}")
        print(f"{'=' * 60}")

        # Load existing results for this mode to skip them
        current_results = self.agent_results if use_agent else self.normal_results
        processed_queries = {r["query"] for r in current_results}
        print(
            f"ℹ️  Found {len(processed_queries)} previously processed queries. These will be skipped."
        )

        documents = await self.list_documents(session)
        conversation_id = await self.create_conversation(session)

        # 1. Collect all tasks first
        tasks_data = []
        print("\n📥 Fetching QA pairs from all documents...")

        # Note: Fetching QA pairs can also be parallelized if needed, but usually fast enough
        for doc in documents:
            if self.is_cancelled:
                break

            doc_id = doc.get("id")
            filename = doc.get("original_filename", "unknown")
            file_type = self.categorize_file_type(filename)

            qa_pairs = await self.get_qa_pairs(session, doc_id)

            for qa in qa_pairs:
                question = qa.get("question", "")
                expected_answer = qa.get("answer", "")

                if not question or not expected_answer:
                    continue

                # Skip if already processed
                if question in processed_queries:
                    continue

                tasks_data.append(
                    {
                        "question": question,
                        "expected_answer": expected_answer,
                        "filename": filename,
                        "file_type": file_type,
                    }
                )

        if not tasks_data:
            print("✅ All questions already processed or no questions found.")
            return current_results

        print(f"⚡ Queueing {len(tasks_data)} new questions to process in parallel...")

        # 2. Process tasks in parallel using Semaphore
        pending_tasks = []
        new_results_buffer = []

        for task_info in tasks_data:
            if self.is_cancelled:
                break

            # Create async task
            coro = self._bounded_ask_question(
                session, conversation_id, task_info["question"], use_agent, task_info
            )
            pending_tasks.append(coro)

        # Execute in chunks or gather all (Semaphore controls active load)
        # Using as_completed allows us to save progress incrementally
        total_tasks = len(pending_tasks)
        completed_count = 0

        if total_tasks > 0:
            for future in asyncio.as_completed(pending_tasks):
                if self.is_cancelled:
                    print("\n🛑 Creating checkpoint and stopping...")
                    break

                result = await future
                if result:
                    new_results_buffer.append(result)
                    current_results.append(result)
                    completed_count += 1

                    # Incremental Save every 5 items
                    if len(new_results_buffer) >= 5:
                        self.save_temp_results()
                        new_results_buffer = []  # Clear buffer
                        print(
                            f"💾 Checkpoint saved. Progress: {completed_count}/{total_tasks}"
                        )

        # Final save for the batch
        self.save_temp_results()
        return current_results

    def add_statistics_to_sheet(
        self, df: pd.DataFrame, sheet_name: str, writer, partial: bool = False
    ):
        if df.empty:
            return
        if partial:
            sheet_name += " (Partial)"

        # Write data
        df.to_excel(writer, sheet_name=sheet_name, index=False)

        # Write basic summary at the bottom (simplified for robustness)
        worksheet = writer.sheets[sheet_name]
        start_row = len(df) + 3

        stats = {"Total": len(df), "Avg Time (s)": df["response_time_seconds"].mean()}

        # Add ragas metrics if they exist
        ragas_cols = [
            "answer_relevancy",
            "answer_correctness",
            "context_precision",
            "context_recall",
            "faithfulness",
        ]
        for col in ragas_cols:
            if col in df.columns:
                stats[col] = df[col].mean()

        row = start_row
        worksheet.cell(row, 1, "STATISTICS")
        row += 1
        for k, v in stats.items():
            worksheet.cell(row, 1, k)
            worksheet.cell(row, 2, round(v, 3) if isinstance(v, float) else v)
            row += 1

    def generate_final_report(self, partial: bool = False):
        print(f"\n📊 Generating Final Report (Partial={partial})...")
        if not self.normal_results and not self.agent_results:
            print("No data to report.")
            return

        with pd.ExcelWriter(self.output_file, engine="openpyxl") as writer:
            if self.normal_results:
                print("  - Calculating metrics for Normal Mode...")
                df_normal = self.evaluate_with_ragas(self.normal_results)
                self.add_statistics_to_sheet(df_normal, "Normal Mode", writer, partial)

            if self.agent_results:
                print("  - Calculating metrics for Agent Mode...")
                df_agent = self.evaluate_with_ragas(self.agent_results)
                self.add_statistics_to_sheet(df_agent, "Agent Mode", writer, partial)

        print(f"✅ Report saved: {self.output_file}")

    async def run_evaluation(self):
        print("Starting Parallel Ragas Evaluation")
        print(f"Timestamp: {datetime.now().isoformat()}")

        # Load previous progress
        self.load_temp_results()

        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                if not self.is_cancelled:
                    self.normal_results = await self.evaluate_mode(
                        session, use_agent=False
                    )

                if not self.is_cancelled:
                    self.agent_results = await self.evaluate_mode(
                        session, use_agent=True
                    )

                # Only generate report if not explicitly cancelled, or if we want partial report
                if not self.is_cancelled:
                    self.generate_final_report()
                else:
                    self.generate_final_report(partial=True)

        except Exception as e:
            print(f"\n❌ Critical Error: {e}")
            self.save_temp_results()
            raise


async def main():
    llm_provider = "nxchat"
    evaluator = RagasLLMEvaluator(API_BASE_URL, API_KEY, llm_provider=llm_provider)
    await evaluator.run_evaluation()


if __name__ == "__main__":
    asyncio.run(main())
