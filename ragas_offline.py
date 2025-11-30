import asyncio
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
from datasets import Dataset
from ragas import RunConfig, evaluate
from ragas.metrics import (
    answer_correctness,
    answer_relevancy,
    answer_similarity,
    context_precision,
    context_recall,
    faithfulness,
)

from src.llm.factory import get_llm
from src.rag.embeddings import ragas_embedding

# --- CẤU HÌNH ---
INPUT_FILE = "ragas_evaluation_temp.json"
OUTPUT_FILE = f"ragas_report_offline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
LLM_PROVIDER = "nxchat"

# Giảm batch size xuống 1 để tránh DDOS LLM của chính mình gây timeout
BATCH_SIZE = 1
TIMEOUT_SECONDS = 300  # Tăng timeout lên 5 phút cho mỗi câu


def load_json_data(filepath):
    """Đọc file JSON và kiểm tra dữ liệu"""
    path = Path(filepath)
    if not path.exists():
        print(f"❌ Không tìm thấy file: {filepath}")
        return None, None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        normal = data.get("normal_results", [])
        agent = data.get("agent_results", [])

        print(f"📂 Đã đọc file JSON: {filepath}")
        print(f"   - Normal results: {len(normal)} records")
        print(f"   - Agent results: {len(agent)} records")

        return normal, agent
    except Exception as e:
        print(f"❌ Lỗi đọc JSON: {e}")
        return None, None


def run_ragas_metrics(results_data, llm):
    """Chạy đánh giá Ragas với cấu hình an toàn"""
    if not results_data:
        return pd.DataFrame()

    print(f"\n🚀 Bắt đầu chấm điểm Ragas cho {len(results_data)} dòng dữ liệu...")
    print(f"   ⚡ Batch Size: {BATCH_SIZE} | Timeout: {TIMEOUT_SECONDS}s")

    # 1. Chuẩn bị dữ liệu
    dataset_dict = {
        "question": [],
        "answer": [],
        "ground_truth": [],
        "contexts": [],
    }

    metadata_list = []

    for item in results_data:
        q = item.get("query", "")
        a = item.get("endpoint_response", "")
        gt = item.get("labeled_response", "")
        ctx = item.get("contexts", [])

        # Validate data để tránh Ragas lỗi
        if not ctx:
            ctx = ["No context provided"]
        if isinstance(ctx, str):
            ctx = [ctx]
        if not q:
            q = "Empty question"
        if not a:
            a = "Empty answer"
        if not gt:
            gt = "Empty ground truth"

        dataset_dict["question"].append(q)
        dataset_dict["answer"].append(a)
        dataset_dict["ground_truth"].append(gt)
        dataset_dict["contexts"].append(ctx)

        metadata_list.append(
            {
                "document_name": item.get("document_name", "unknown"),
                "file_type": item.get("file_type", "unknown"),
                "response_time": item.get("response_time_seconds", 0),
                "original_query": q,
            }
        )

    try:
        dataset = Dataset.from_dict(dataset_dict)
    except Exception as e:
        print(f"❌ Lỗi tạo Dataset: {e}")
        return pd.DataFrame(results_data)

    metrics_list = [
        answer_relevancy,
        answer_correctness,
        answer_similarity,
        faithfulness,
        context_precision,
        context_recall,
    ]

    print("   🔧 Đang cấu hình LLM & Embeddings cho từng metric...")
    for m in metrics_list:
        # Gán LLM nếu metric hỗ trợ
        if hasattr(m, "llm"):
            m.llm = llm

        # Gán Embeddings (bắt buộc cho answer_similarity)
        if hasattr(m, "embeddings"):
            m.embeddings = ragas_embedding

    # Kiểm tra kỹ ragas_embedding
    if ragas_embedding is None:
        print(
            "❌ CRITICAL: ragas_embedding bị None! Kiểm tra lại import src.rag.embeddings"
        )
        return pd.DataFrame(results_data)

    # 3. Chạy Evaluate với RunConfig
    try:
        # RunConfig giúp quản lý timeout và retries ở mức độ task
        run_config = RunConfig(timeout=TIMEOUT_SECONDS, max_retries=3, max_wait=60)

        evaluation_result = evaluate(
            dataset=dataset,
            metrics=metrics_list,
            llm=llm,
            embeddings=ragas_embedding,
            run_config=run_config,
            batch_size=BATCH_SIZE,  # Giảm tải
            raise_exceptions=True,  # False để nếu 1 câu lỗi thì không crash cả chương trình
        )

        results_df = evaluation_result.to_pandas()

        # Ghép metadata
        meta_df = pd.DataFrame(metadata_list)
        # Reset index để concat đúng dòng
        final_df = pd.concat(
            [meta_df.reset_index(drop=True), results_df.reset_index(drop=True)], axis=1
        )

        print(f"✅ Đã chấm xong. Kết quả: {len(final_df)} dòng.")
        return final_df

    except Exception as e:
        print(f"❌ CRITICAL ERROR khi chạy evaluate: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame(results_data)


def save_to_excel(normal_df, agent_df, output_path):
    print(f"\n💾 Đang ghi file Excel: {output_path} ...")
    try:
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            if not normal_df.empty:
                normal_df.to_excel(writer, sheet_name="Normal Mode", index=False)
                _add_summary(writer, "Normal Mode", normal_df)

            if not agent_df.empty:
                agent_df.to_excel(writer, sheet_name="Agent Mode", index=False)
                _add_summary(writer, "Agent Mode", agent_df)

        print(f"🎉 SUCCESS! File saved: {output_path}")
    except Exception as e:
        print(f"❌ Lỗi ghi Excel: {e}")


def _add_summary(writer, sheet_name, df):
    try:
        worksheet = writer.sheets[sheet_name]
        start_row = len(df) + 3
        metrics_cols = [
            "answer_relevancy",
            "answer_correctness",
            "context_precision",
            "context_recall",
            "faithfulness",
            "answer_similarity",
        ]

        worksheet.cell(row=start_row, column=1, value="AVERAGE METRICS")
        current_row = start_row + 1
        for col in metrics_cols:
            if col in df.columns:
                # Convert to numeric, errors='coerce' biến text lỗi thành NaN để tính mean ko bị crash
                avg_val = pd.to_numeric(df[col], errors="coerce").mean()
                worksheet.cell(row=current_row, column=1, value=col)
                worksheet.cell(row=current_row, column=2, value=round(avg_val, 4))
                current_row += 1
    except Exception:
        pass


def main():
    print("⚙️  Khởi tạo LLM...")
    try:
        llm = get_llm(provider=LLM_PROVIDER)
        print(f"✅ LLM: {LLM_PROVIDER}")
    except Exception as e:
        print(f"❌ Lỗi init LLM: {e}")
        return

    normal_data, agent_data = load_json_data(INPUT_FILE)
    if not normal_data and not agent_data:
        return

    df_normal = pd.DataFrame()
    df_agent = pd.DataFrame()

    if normal_data:
        print("\n--- PROCESSING NORMAL MODE ---")
        df_normal = run_ragas_metrics(normal_data, llm)

    if agent_data:
        print("\n--- PROCESSING AGENT MODE ---")
        df_agent = run_ragas_metrics(agent_data, llm)

    save_to_excel(df_normal, df_agent, OUTPUT_FILE)


if __name__ == "__main__":
    # Fix cho Windows asyncio loop policy (đôi khi giúp tránh lỗi loop closed)
    import sys

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    main()
