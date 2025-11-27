import argparse
from pathlib import Path
from typing import Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ============================================================
# CONFIG
# ============================================================

METRICS = [
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
    "faithfulness",
    "answer_similarity",
]

# Nếu không có sheet "Agent Mode" trong Excel thì dùng số manual này
USE_MANUAL_AGENT_SUMMARY = True
MANUAL_AGENT_SUMMARY: Dict[str, float] = {
    # đại khái agent kém hơn fixed RAG flow trên bộ offline
    "answer_relevancy": 0.75,
    "answer_correctness": 0.40,
    "context_precision": 0.20,
    "context_recall": 0.55,
    "faithfulness": 0.78,
    "answer_similarity": 0.70,
    # avg response time (giây) – ví dụ agent chậm hơn
    "avg_response_time": 1.60,
}

# Chọn metric dùng cho các chart theo file_type
# => ĐÃ ĐỔI sang answer_relevancy
FILE_TYPE_MAIN_METRIC = "answer_relevancy"
FILE_TYPES_INTEREST = ["structured", "unstructured", "image"]


# ============================================================
# LOADING & PREP
# ============================================================


def load_mode_df(xlsx_path: Path, sheet_name: str) -> Optional[pd.DataFrame]:
    """Đọc 1 sheet từ Excel (Normal Mode / Agent Mode)."""
    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)
    except Exception:
        return None

    if df is None or df.empty:
        return None

    # Chuẩn hóa numeric cho các metric & response_time
    numeric_cols = METRICS + ["response_time"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # has_context: có context nếu precision > 0 hoặc recall > 0 (logic cũ, dùng cho report)
    if "context_precision" in df.columns and "context_recall" in df.columns:
        df["has_context"] = (df["context_precision"] > 1e-9) | (
            df["context_recall"] > 1e-9
        )
    else:
        df["has_context"] = False

    # file_type fallback
    if "file_type" not in df.columns:
        df["file_type"] = "unknown"
    df["file_type"] = df["file_type"].fillna("unknown").astype(str)

    df["mode"] = sheet_name
    return df


def compute_overall_metrics(df: pd.DataFrame) -> Dict[str, float]:
    """Mean cho tất cả METRICS trong df."""
    result = {}
    for m in METRICS:
        if m in df.columns:
            val = pd.to_numeric(df[m], errors="coerce").mean()
            if not pd.isna(val):
                result[m] = float(val)
    return result


def compute_overall_metrics_filtered(
    df: pd.DataFrame, mask: pd.Series
) -> Dict[str, float]:
    """Mean METRICS sau khi filter bằng mask."""
    return compute_overall_metrics(df[mask])


def compute_avg_response_time(
    df: pd.DataFrame, mask: Optional[pd.Series] = None
) -> Optional[float]:
    if "response_time" not in df.columns:
        return None
    sub = df[mask] if mask is not None else df
    val = pd.to_numeric(sub["response_time"], errors="coerce").mean()
    if pd.isna(val):
        return None
    return float(val)


# ============================================================
# PLOTTING HELPERS
# ============================================================


def _auto_zoom_y_axis(ax, values):
    """Zoom trục Y quanh khoảng giá trị để nhìn rõ chênh lệch nhỏ."""
    if not values:
        return
    min_v = min(values)
    max_v = max(values)
    if np.isnan(min_v) or np.isnan(max_v):
        return

    margin = max(0.02, (max_v - min_v) * 0.2)
    lower = max(0.0, min_v - margin)
    upper = min(1.0, max_v + margin)

    if upper > lower:
        ax.set_ylim(lower, upper)


def _add_value_labels(ax, bars):
    """Gắn nhãn giá trị trên đầu mỗi bar."""
    for bar in bars:
        height = bar.get_height()
        if np.isnan(height):
            continue
        ax.annotate(
            f"{height:.3f}",
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
        )


def save_bar_modes(
    normal_metrics: Dict[str, float],
    agent_metrics: Optional[Dict[str, float]],
    out_path: Path,
    title: str,
    agent_label: str = "Agent Mode",
):
    """
    Vẽ bar chart Normal vs Agent cho tất cả METRICS.
    Nếu agent_metrics = None thì chỉ vẽ Normal.
    """
    metrics = [m for m in METRICS if m in normal_metrics]
    if agent_metrics is not None:
        metrics = [m for m in metrics if m in agent_metrics]

    if not metrics:
        return

    x = np.arange(len(metrics))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 5))

    normal_vals = [normal_metrics[m] for m in metrics]
    bars_normal = ax.bar(x - width / 2, normal_vals, width, label="Normal Mode")

    all_vals = list(normal_vals)

    if agent_metrics is not None:
        agent_vals = [agent_metrics[m] for m in metrics]
        bars_agent = ax.bar(x + width / 2, agent_vals, width, label=agent_label)
        all_vals.extend(agent_vals)
    else:
        bars_agent = []

    _auto_zoom_y_axis(ax, all_vals)
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, rotation=30, ha="right")
    ax.set_ylabel("Mean score")
    ax.set_title(title)
    ax.legend()

    _add_value_labels(ax, bars_normal)
    if bars_agent:
        _add_value_labels(ax, bars_agent)

    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def save_bar_filetype(
    df: pd.DataFrame,
    out_path: Path,
    metric_name: str,
    title: str,
    only_no_context: bool = False,
):
    """
    Vẽ bar chart theo file_type cho 1 metric (single mode).
    Giữ lại để dùng fallback nếu không có Agent.
    """
    if metric_name not in df.columns:
        return

    sub = df.copy()
    if only_no_context:
        sub = sub[sub["has_context"] == False]

    sub = sub[sub["file_type"].isin(FILE_TYPES_INTEREST)]
    if sub.empty:
        return

    grouped = (
        sub.groupby("file_type")[metric_name]
        .mean()
        .reindex(FILE_TYPES_INTEREST)
        .dropna()
    )
    if grouped.empty:
        return

    x_labels = list(grouped.index)
    values = list(grouped.values)
    x = np.arange(len(x_labels))

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(x, values)

    _auto_zoom_y_axis(ax, values)
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax.set_xticks(x)
    ax.set_xticklabels(x_labels, rotation=0)
    ax.set_ylabel(metric_name)
    ax.set_title(title)

    _add_value_labels(ax, bars)

    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


def save_bar_filetype_modes(
    normal_df: pd.DataFrame,
    agent_df: Optional[pd.DataFrame],
    out_path: Path,
    metric_name: str,
    title: str,
    agent_label: str = "Agent Mode",
):
    """
    Vẽ bar chart theo file_type cho 1 metric:
    - So sánh Normal vs Agent (2 cột / file_type).
    - Nếu không có Agent thì fallback: vẽ 1 mode (Normal) như cũ.
    """
    if metric_name not in normal_df.columns:
        return

    sub_n = normal_df[normal_df["file_type"].isin(FILE_TYPES_INTEREST)].copy()

    # Nếu có agent và có metric tương ứng
    if agent_df is not None and metric_name in agent_df.columns:
        sub_a = agent_df[agent_df["file_type"].isin(FILE_TYPES_INTEREST)].copy()
    else:
        sub_a = None

    if sub_n.empty and (sub_a is None or sub_a.empty):
        return

    grouped_n = (
        (sub_n.groupby("file_type")[metric_name].mean().reindex(FILE_TYPES_INTEREST))
        if not sub_n.empty
        else pd.Series(dtype=float)
    )

    if sub_a is not None and not sub_a.empty:
        grouped_a = (
            sub_a.groupby("file_type")[metric_name].mean().reindex(FILE_TYPES_INTEREST)
        )
    else:
        grouped_a = None

    file_types = []
    normal_vals = []
    agent_vals = []

    for ft in FILE_TYPES_INTEREST:
        vn = grouped_n[ft] if ft in grouped_n.index else np.nan
        va = (
            grouped_a[ft]
            if (grouped_a is not None and ft in grouped_a.index)
            else np.nan
        )
        if (not np.isnan(vn)) or (not np.isnan(va)):
            file_types.append(ft)
            normal_vals.append(float(vn) if not np.isnan(vn) else np.nan)
            agent_vals.append(float(va) if not np.isnan(va) else np.nan)

    if not file_types:
        return

    x = np.arange(len(file_types))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    bars_n = ax.bar(x - width / 2, normal_vals, width, label="Normal Mode")
    all_vals = [v for v in normal_vals if not np.isnan(v)]

    if agent_df is not None and agent_vals and not all(np.isnan(agent_vals)):
        bars_a = ax.bar(x + width / 2, agent_vals, width, label=agent_label)
        all_vals.extend([v for v in agent_vals if not np.isnan(v)])
    else:
        bars_a = []

    _auto_zoom_y_axis(ax, all_vals)
    ax.grid(axis="y", linestyle="--", alpha=0.3)

    ax.set_xticks(x)
    ax.set_xticklabels(file_types)
    ax.set_ylabel(metric_name)
    ax.set_title(title)
    ax.legend()

    _add_value_labels(ax, bars_n)
    if bars_a:
        _add_value_labels(ax, bars_a)

    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    plt.close(fig)


# ============================================================
# TXT REPORT
# ============================================================


def write_txt_report(
    report_path: Path,
    normal_df: Optional[pd.DataFrame],
    agent_df: Optional[pd.DataFrame],
    manual_agent_used: bool,
    manual_agent_name: Optional[str],
):
    lines = []
    lines.append("RAGAS EVALUATION BAR-CHART REPORT")
    lines.append("=" * 80)
    lines.append("")

    # ------------ NORMAL MODE ------------
    if normal_df is not None:
        lines.append("MODE: Normal Mode")
        lines.append("-" * 80)
        lines.append(f"Number of rows: {len(normal_df)}")
        lines.append("")

        # Overall
        lines.append("1. Overall metrics (all rows)")
        overall = compute_overall_metrics(normal_df)
        for m, v in overall.items():
            lines.append(f"   - {m}: {v:.4f}")
        avg_rt = compute_avg_response_time(normal_df)
        if avg_rt is not None:
            lines.append(f"   - avg_response_time: {avg_rt:.4f} seconds")
        lines.append("")

        # Overall chỉ rows có context (dựa trên has_context cũ: OR)
        lines.append("2. Overall metrics (has_context=True)")
        mask_ctx = normal_df["has_context"] == True
        overall_ctx = compute_overall_metrics_filtered(normal_df, mask_ctx)
        for m, v in overall_ctx.items():
            lines.append(f"   - {m}: {v:.4f}")
        avg_rt_ctx = compute_avg_response_time(normal_df, mask_ctx)
        if avg_rt_ctx is not None:
            lines.append(f"   - avg_response_time: {avg_rt_ctx:.4f} seconds")
        lines.append("")

        # File type all rows (metric = FILE_TYPE_MAIN_METRIC => answer_relevancy)
        lines.append(f"3. {FILE_TYPE_MAIN_METRIC} by file_type (all rows, Normal Mode)")
        sub_all = normal_df[normal_df["file_type"].isin(FILE_TYPES_INTEREST)]
        if not sub_all.empty and FILE_TYPE_MAIN_METRIC in sub_all.columns:
            grouped = (
                sub_all.groupby("file_type")[FILE_TYPE_MAIN_METRIC]
                .mean()
                .reindex(FILE_TYPES_INTEREST)
            )
            for ft, v in grouped.items():
                if not pd.isna(v):
                    lines.append(f"   - {ft}: {v:.4f}")
        else:
            lines.append("   (no rows for structured/unstructured/image)")
        lines.append("")

        # File type only no-context (giữ logic cũ cho report)
        lines.append(
            f"4. {FILE_TYPE_MAIN_METRIC} by file_type (has_context=False, Normal Mode)"
        )
        sub_nc = normal_df[
            (normal_df["has_context"] == False)
            & (normal_df["file_type"].isin(FILE_TYPES_INTEREST))
        ]
        if not sub_nc.empty and FILE_TYPE_MAIN_METRIC in sub_nc.columns:
            grouped = (
                sub_nc.groupby("file_type")[FILE_TYPE_MAIN_METRIC]
                .mean()
                .reindex(FILE_TYPES_INTEREST)
            )
            for ft, v in grouped.items():
                if not pd.isna(v):
                    lines.append(f"   - {ft}: {v:.4f}")
        else:
            lines.append("   (no rows without context for these file types)")
        lines.append("")
        lines.append("")

    # ------------ AGENT MODE ------------
    if agent_df is not None:
        lines.append("MODE: Agent Mode")
        lines.append("-" * 80)
        lines.append(f"Number of rows: {len(agent_df)}")
        lines.append("")
        overall = compute_overall_metrics(agent_df)
        lines.append("1. Overall metrics (all rows)")
        for m, v in overall.items():
            lines.append(f"   - {m}: {v:.4f}")
        avg_rt = compute_avg_response_time(agent_df)
        if avg_rt is not None:
            lines.append(f"   - avg_response_time: {avg_rt:.4f} seconds")
        lines.append("")
    elif manual_agent_used and manual_agent_name is not None:
        lines.append(f"MODE: {manual_agent_name}")
        lines.append("-" * 80)
        lines.append(
            "NOTE: This mode uses manually specified placeholder metrics, "
            "NOT computed from the Excel dataset."
        )
        lines.append("")
        lines.append("1. Overall metrics (manual)")
        for m in METRICS:
            if m in MANUAL_AGENT_SUMMARY:
                v = MANUAL_AGENT_SUMMARY[m]
                lines.append(f"   - {m}: {v:.4f}")
        if "avg_response_time" in MANUAL_AGENT_SUMMARY:
            lines.append(
                f"   - avg_response_time: "
                f"{MANUAL_AGENT_SUMMARY['avg_response_time']:.4f} seconds"
            )
        lines.append("")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] TXT report written to: {report_path}")


# ============================================================
# MAIN
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Generate bar charts + txt report from RAGAS Excel output."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="ragas_report_offline.xlsx",
        help="Path to the RAGAS Excel file (with Normal Mode / Agent Mode sheets).",
    )
    parser.add_argument(
        "--out_dir",
        type=str,
        default="ragas_outputs",
        help="Output directory for plots and txt report.",
    )
    parser.add_argument(
        "--report_name",
        type=str,
        default="ragas_bar_report.txt",
        help="Text report filename (inside out_dir).",
    )

    args = parser.parse_args()

    xlsx_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    plots_dir = out_dir / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    if not xlsx_path.exists():
        raise FileNotFoundError(f"Input Excel not found: {xlsx_path}")

    # Load data
    normal_df = load_mode_df(xlsx_path, "Normal Mode")
    agent_df = load_mode_df(xlsx_path, "Agent Mode")

    manual_agent_used = False
    manual_agent_name: Optional[str] = None

    # Agent manual fallback
    agent_overall_manual: Optional[Dict[str, float]] = None
    if agent_df is None and USE_MANUAL_AGENT_SUMMARY:
        agent_overall_manual = {
            m: MANUAL_AGENT_SUMMARY[m] for m in METRICS if m in MANUAL_AGENT_SUMMARY
        }
        manual_agent_used = True
        manual_agent_name = "Agent Mode (manual)"

    # --------------------------------------------------------
    # 1) Bar chart overall Normal vs Agent (all rows)
    # --------------------------------------------------------
    if normal_df is not None:
        normal_overall = compute_overall_metrics(normal_df)
        if agent_df is not None:
            agent_overall = compute_overall_metrics(agent_df)
        else:
            agent_overall = agent_overall_manual

        out_path1 = plots_dir / "01_overall_normal_vs_agent.png"
        save_bar_modes(
            normal_overall,
            agent_overall,
            out_path1,
            title="Overall RAGAS metrics - Normal vs Agent (all rows)",
            agent_label="Agent Mode"
            if agent_df is not None
            else manual_agent_name or "Agent Mode (manual)",
        )

    # --------------------------------------------------------
    # 2) Bar chart Normal vs Agent, chỉ rows có context (dựa trên has_context)
    # --------------------------------------------------------
    if normal_df is not None:
        mask_ctx = normal_df["has_context"] == True
        normal_overall_ctx = compute_overall_metrics_filtered(normal_df, mask_ctx)

        if agent_df is not None:
            mask_ctx_agent = agent_df["has_context"] == True
            agent_overall_ctx = compute_overall_metrics_filtered(
                agent_df, mask_ctx_agent
            )
        else:
            agent_overall_ctx = agent_overall_manual

        out_path2 = plots_dir / "02_overall_normal_vs_agent_has_context.png"
        save_bar_modes(
            normal_overall_ctx,
            agent_overall_ctx,
            out_path2,
            title="Overall RAGAS metrics - Normal vs Agent (has_context=True)",
            agent_label="Agent Mode"
            if agent_df is not None
            else manual_agent_name or "Agent Mode (manual)",
        )

    # --------------------------------------------------------
    # 3) Bar chart: file_type (structured / unstructured / image)
    #    => metric = answer_relevancy, ALL ROWS, Normal vs Agent
    # --------------------------------------------------------
    if normal_df is not None:
        out_path3 = plots_dir / "03_filetype_answer_relevancy_all_rows.png"
        title3 = f"{FILE_TYPE_MAIN_METRIC} by file_type - Normal vs Agent (all rows)"

        normal_all = normal_df.copy()
        agent_all = agent_df.copy() if agent_df is not None else None

        save_bar_filetype_modes(
            normal_all,
            agent_all,
            out_path3,
            metric_name=FILE_TYPE_MAIN_METRIC,
            title=title3,
            agent_label="Agent Mode",
        )

    # --------------------------------------------------------
    # 4) Bar chart: file_type (structured / unstructured / image)
    #    => metric = answer_relevancy, CHỈ rows CÓ CONTEXT:
    #       context_precision > 0 và context_recall > 0
    #       So sánh Normal vs Agent
    # --------------------------------------------------------
    if normal_df is not None:
        out_path4 = plots_dir / "04_filetype_answer_relevancy_with_context.png"
        title4 = (
            f"{FILE_TYPE_MAIN_METRIC} by file_type - Normal vs Agent "
            "(context_precision>0 & context_recall>0)"
        )

        # Lọc Normal: strict context
        if (
            "context_precision" in normal_df.columns
            and "context_recall" in normal_df.columns
        ):
            mask_ctx_strict_n = (normal_df["context_precision"] > 0) & (
                normal_df["context_recall"] > 0
            )
            normal_with_ctx = normal_df[mask_ctx_strict_n].copy()
        else:
            normal_with_ctx = normal_df.iloc[0:0].copy()  # rỗng nếu thiếu cột

        # Lọc Agent: strict context
        if (
            agent_df is not None
            and "context_precision" in agent_df.columns
            and "context_recall" in agent_df.columns
        ):
            mask_ctx_strict_a = (agent_df["context_precision"] > 0) & (
                agent_df["context_recall"] > 0
            )
            agent_with_ctx = agent_df[mask_ctx_strict_a].copy()
        else:
            agent_with_ctx = None

        save_bar_filetype_modes(
            normal_with_ctx,
            agent_with_ctx,
            out_path4,
            metric_name=FILE_TYPE_MAIN_METRIC,
            title=title4,
            agent_label="Agent Mode",
        )

    # --------------------------------------------------------
    # TXT report
    # --------------------------------------------------------
    report_path = out_dir / args.report_name
    write_txt_report(
        report_path,
        normal_df=normal_df,
        agent_df=agent_df,
        manual_agent_used=manual_agent_used,
        manual_agent_name=manual_agent_name,
    )

    print(f"[OK] Plots saved to: {plots_dir}")


if __name__ == "__main__":
    main()
