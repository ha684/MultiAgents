import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Set style
sns.set_style("whitegrid")
plt.rcParams["font.size"] = 10
plt.rcParams["figure.dpi"] = 150

# ===========================
# DATA GENERATION
# ===========================

# Dataset composition (for quality evaluation)
dataset_quality = pd.DataFrame(
    {
        "Query Type": [
            "Normal\nRetrieval",
            "Complex\nSingle-Source",
            "Complex\nMulti-Source",
        ],
        "Count": [187, 40, 10],
        "Percentage": [78.9, 16.9, 4.2],
    }
)

# Full dataset (including simple conversation for efficiency metrics)
dataset_full = pd.DataFrame(
    {
        "Query Type": [
            "Simple\nConversation",
            "Normal\nRetrieval",
            "Complex\nSingle-Source",
            "Complex\nMulti-Source",
        ],
        "Count": [20, 187, 40, 10],
        "Percentage": [7.8, 72.8, 15.6, 3.9],
    }
)

# RAGAS Automated Evaluation (N=187 normal retrieval)
ragas_results = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Answer Relevancy": [0.80, 0.84, 0.84],
    }
)

# Manual Evaluation - Complex Single-Source (N=40)
# Scoring: 1.0 = correct, 0.5 = partial, 0.0 = wrong
manual_single_source = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Correct (1.0)": [8, 14, 28],
        "Partial (0.5)": [28, 22, 10],
        "Wrong (0.0)": [4, 4, 2],
        "Success Rate": [0.55, 0.625, 0.825],  # Weighted: (correct + 0.5*partial) / 40
    }
)

# Manual Evaluation - Complex Multi-Source (N=10)
manual_multi_source = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Correct (1.0)": [0, 0, 7],
        "Partial (0.5)": [8, 9, 2],
        "Wrong (0.0)": [2, 1, 1],
        "Success Rate": [0.40, 0.45, 0.80],  # Weighted: (correct + 0.5*partial) / 10
    }
)

# Overall Weighted Performance
# Weights: Normal 78.9%, Single 16.9%, Multi 4.2%
overall_performance = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Overall Score": [
            0.789 * 0.80 + 0.169 * 0.55 + 0.042 * 0.40,  # 0.741
            0.789 * 0.84 + 0.169 * 0.625 + 0.042 * 0.45,  # 0.788
            0.789 * 0.84 + 0.169 * 0.825 + 0.042 * 0.80,  # 0.836
        ],
    }
)

# Performance Breakdown by Query Type
performance_breakdown = pd.DataFrame(
    {
        "Query Type": [
            "Normal\nRetrieval",
            "Normal\nRetrieval",
            "Normal\nRetrieval",
            "Complex\nSingle-Source",
            "Complex\nSingle-Source",
            "Complex\nSingle-Source",
            "Complex\nMulti-Source",
            "Complex\nMulti-Source",
            "Complex\nMulti-Source",
        ],
        "System": ["Naive", "Advanced", "Multi-Agent"] * 3,
        "Success Rate": [
            0.80,
            0.84,
            0.84,  # Normal (RAGAS)
            0.55,
            0.625,
            0.825,  # Single-source (Manual)
            0.40,
            0.45,
            0.80,  # Multi-source (Manual)
        ],
        "Evaluation": [
            "RAGAS",
            "RAGAS",
            "RAGAS",
            "Manual",
            "Manual",
            "Manual",
            "Manual",
            "Manual",
            "Manual",
        ],
    }
)

# Latency by System and Query Type (includes simple conversation)
# Naive: 4.5s, Advanced: 17.5s
# Multi-Agent: Direct=0.8s, Normal=17s, Thinking single=52.5s, Thinking multi=62.5s
latency_data = pd.DataFrame(
    {
        "System": [
            "Naive",
            "Naive",
            "Naive",
            "Naive",
            "Advanced",
            "Advanced",
            "Advanced",
            "Advanced",
            "Multi-Agent",
            "Multi-Agent",
            "Multi-Agent",
            "Multi-Agent",
        ],
        "Query Type": ["Simple", "Normal", "Complex\nSingle", "Complex\nMulti"] * 3,
        "Latency (seconds)": [
            4.5,
            4.5,
            4.5,
            4.5,  # Naive: constant
            17.5,
            17.5,
            17.5,
            17.5,  # Advanced: constant
            0.8,
            17.0,
            52.5,
            62.5,  # Multi-Agent: varies by routing
        ],
    }
)

# Token Usage by System
# Naive: 9,000, Advanced: 11,500
# Multi-Agent: 0.078×3,500 + 0.728×14,500 + 0.156×45,000 + 0.039×45,000 = 19,604
token_usage = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Average Tokens": [9000, 11500, 19604],
        "Cost (USD per 1K queries)": [22.5, 28.8, 49.0],  # $0.0025/1K tokens
    }
)

# Token Breakdown by Mode (Multi-Agent only)
token_breakdown = pd.DataFrame(
    {
        "Mode": [
            "Direct Response\n(7.8%)",
            "Normal Mode\n(72.8%)",
            "Thinking Single\n(15.6%)",
            "Thinking Multi\n(3.9%)",
        ],
        "Avg Tokens": [3500, 14500, 45000, 45000],
        "Percentage": [7.8, 72.8, 15.6, 3.9],
    }
)

# ===========================
# FIGURE 1: Dataset Composition (Quality Evaluation)
# ===========================
fig, ax = plt.subplots(figsize=(8, 6))
colors_pie = ["#4ECDC4", "#F38181", "#AA96DA"]
explode = (0, 0.05, 0.15)

wedges, texts, autotexts = ax.pie(
    dataset_quality["Percentage"],
    labels=dataset_quality["Query Type"],
    autopct="%1.1f%%",
    startangle=90,
    colors=colors_pie,
    explode=explode,
    shadow=True,
    textprops={"size": 11, "weight": "bold"},
)

# Add count annotations
for i, (wedge, row) in enumerate(zip(wedges, dataset_quality.itertuples())):
    angle = (wedge.theta2 + wedge.theta1) / 2
    x = 1.3 * np.cos(np.radians(angle))
    y = 1.3 * np.sin(np.radians(angle))
    ax.text(
        x,
        y,
        f"N={row.Count}",
        ha="center",
        va="center",
        size=10,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.8),
    )

ax.set_title("Quality Evaluation Dataset (N=237)", weight="bold", size=13, pad=20)
plt.tight_layout()
plt.savefig("fig_dataset_composition.png", bbox_inches="tight", dpi=150)
print("Saved: fig_dataset_composition.png")

# ===========================
# FIGURE 2: RAGAS Results (Normal Retrieval)
# ===========================
fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(
    ragas_results["System"],
    ragas_results["Answer Relevancy"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)

for bar in bars:
    height = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 0.01,
        f"{height:.2f}",
        ha="center",
        va="bottom",
        size=12,
        weight="bold",
    )

ax.set_ylabel("Answer Relevancy (RAGAS)", size=12, weight="bold")
ax.set_title(
    "Automated Evaluation - Normal Retrieval Queries (N=187)", weight="bold", size=13
)
ax.set_ylim(0, 1.0)
ax.axhline(y=0.84, color="gray", linestyle="--", alpha=0.5, linewidth=1)
ax.text(2.5, 0.85, "Empirical baseline", size=9, style="italic", color="gray")
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("fig_ragas_results.png", bbox_inches="tight", dpi=150)
print("Saved: fig_ragas_results.png")

# ===========================
# FIGURE 3: Manual Evaluation - Complex Single-Source
# ===========================
fig, ax = plt.subplots(figsize=(12, 7))
x = np.arange(len(manual_single_source["System"]))
width = 0.25

bars1 = ax.bar(
    x - width,
    manual_single_source["Correct (1.0)"],
    width,
    label="Correct (1.0)",
    color="#2ECC71",
    edgecolor="black",
)
bars2 = ax.bar(
    x,
    manual_single_source["Partial (0.5)"],
    width,
    label="Partial (0.5)",
    color="#F39C12",
    edgecolor="black",
)
bars3 = ax.bar(
    x + width,
    manual_single_source["Wrong (0.0)"],
    width,
    label="Wrong (0.0)",
    color="#E74C3C",
    edgecolor="black",
)

# Add value labels
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
                size=9,
            )

# Add success rate annotations
for i, rate in enumerate(manual_single_source["Success Rate"]):
    ax.text(
        i,
        42,
        f"Success Rate:\n{rate:.1%}",
        ha="center",
        size=10,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="lightblue", alpha=0.7),
    )

ax.set_ylabel("Number of Queries", size=11, weight="bold")
ax.set_title(
    "Manual Evaluation - Complex Single-Source Queries (N=40)\n"
    + "Multi-aspect queries requiring synthesis from multiple documents",
    weight="bold",
    size=12,
)
ax.set_xticks(x)
ax.set_xticklabels(manual_single_source["System"])
ax.legend(loc="upper left", fontsize=10)
ax.set_ylim(0, 48)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("fig_manual_single_source.png", bbox_inches="tight", dpi=150)
print("Saved: fig_manual_single_source.png")

# ===========================
# FIGURE 4: Manual Evaluation - Complex Multi-Source (KEY)
# ===========================
fig, ax = plt.subplots(figsize=(12, 7))
x = np.arange(len(manual_multi_source["System"]))
width = 0.25

bars1 = ax.bar(
    x - width,
    manual_multi_source["Correct (1.0)"],
    width,
    label="Correct (1.0)",
    color="#2ECC71",
    edgecolor="black",
)
bars2 = ax.bar(
    x,
    manual_multi_source["Partial (0.5)"],
    width,
    label="Partial (0.5)",
    color="#F39C12",
    edgecolor="black",
)
bars3 = ax.bar(
    x + width,
    manual_multi_source["Wrong (0.0)"],
    width,
    label="Wrong (0.0)",
    color="#E74C3C",
    edgecolor="black",
)

# Add value labels
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height,
                f"{int(height)}",
                ha="center",
                va="bottom",
                size=9,
                weight="bold",
            )

# Add success rate with special emphasis
for i, (system, rate) in enumerate(
    zip(manual_multi_source["System"], manual_multi_source["Success Rate"])
):
    color = "lightcoral" if i < 2 else "lightgreen"
    ax.text(
        i,
        11,
        f"Success Rate:\n{rate:.0%}",
        ha="center",
        size=11,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.5", facecolor=color, alpha=0.8),
    )

# Add capability annotation
ax.text(
    0.5,
    13.5,
    "❌ Cannot switch sources",
    ha="center",
    size=10,
    style="italic",
    color="red",
    weight="bold",
)
ax.text(
    2,
    13.5,
    "✓ Multi-source orchestration",
    ha="center",
    size=10,
    style="italic",
    color="green",
    weight="bold",
)

# Add improvement arrow
ax.annotate(
    "",
    xy=(2, 9.5),
    xytext=(1, 9.5),
    arrowprops=dict(arrowstyle="->", lw=3, color="green"),
)
ax.text(
    1.5,
    10,
    "+78%",
    ha="center",
    size=12,
    weight="bold",
    color="green",
    bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen", alpha=0.7),
)

ax.set_ylabel("Number of Queries", size=11, weight="bold")
ax.set_title(
    "Manual Evaluation - Complex Multi-Source Queries (N=10)\n"
    + "Queries requiring synthesis from SQL + RAG or Web + RAG",
    weight="bold",
    size=12,
    color="#C0392B",
)
ax.set_xticks(x)
ax.set_xticklabels(manual_multi_source["System"])
ax.legend(loc="upper left", fontsize=10)
ax.set_ylim(0, 15)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("fig_manual_multi_source.png", bbox_inches="tight", dpi=150)
print("Saved: fig_manual_multi_source.png")

# ===========================
# FIGURE 5: Overall Performance (Weighted Average)
# ===========================
fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(
    overall_performance["System"],
    overall_performance["Overall Score"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)

for bar in bars:
    height = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 0.01,
        f"{height:.3f}",
        ha="center",
        va="bottom",
        size=12,
        weight="bold",
    )

# Add improvement annotation
improvement = (0.836 - 0.788) / 0.788 * 100
ax.annotate(
    "",
    xy=(2, 0.836),
    xytext=(1, 0.788),
    arrowprops=dict(arrowstyle="->", lw=2, color="green"),
)
ax.text(
    1.5,
    0.815,
    f"+{improvement:.1f}%",
    ha="center",
    size=11,
    weight="bold",
    color="green",
    bbox=dict(boxstyle="round,pad=0.4", facecolor="lightgreen", alpha=0.6),
)

ax.set_ylabel("Overall Success Rate (Weighted)", size=12, weight="bold")
ax.set_title(
    "Overall Performance - Weighted Average Across All Query Types\n"
    + "(Normal: 78.9%, Single: 16.9%, Multi: 4.2%)",
    weight="bold",
    size=12,
)
ax.set_ylim(0, 1.0)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("fig_overall_performance.png", bbox_inches="tight", dpi=150)
print("Saved: fig_overall_performance.png")

# ===========================
# FIGURE 6: Performance Breakdown by Type
# ===========================
fig, ax = plt.subplots(figsize=(12, 7))
x_pos = np.arange(len(performance_breakdown["Query Type"].unique()))
width = 0.25

naive_data = performance_breakdown[performance_breakdown["System"] == "Naive"][
    "Success Rate"
].values
advanced_data = performance_breakdown[performance_breakdown["System"] == "Advanced"][
    "Success Rate"
].values
multiagent_data = performance_breakdown[
    performance_breakdown["System"] == "Multi-Agent"
]["Success Rate"].values

bars1 = ax.bar(
    x_pos - width,
    naive_data,
    width,
    label="Naive RAG",
    color="#FF6B6B",
    edgecolor="black",
)
bars2 = ax.bar(
    x_pos,
    advanced_data,
    width,
    label="Advanced RAG",
    color="#4ECDC4",
    edgecolor="black",
)
bars3 = ax.bar(
    x_pos + width,
    multiagent_data,
    width,
    label="Multi-Agent RAG",
    color="#45B7D1",
    edgecolor="black",
)

# Add value labels
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 0.01,
            f"{height:.2f}",
            ha="center",
            va="bottom",
            size=9,
        )

ax.set_ylabel("Success Rate", size=11, weight="bold")
ax.set_title("Performance Breakdown by Query Type", weight="bold", size=12)
ax.set_xticks(x_pos)
ax.set_xticklabels(performance_breakdown["Query Type"].unique())
ax.set_ylim(0, 1.0)
ax.legend(loc="lower right", fontsize=10)
ax.grid(axis="y", alpha=0.3)

# Add evaluation method annotations
eval_methods = ["RAGAS\nN=187", "Manual\nN=40", "Manual\nN=10"]
for i, method in enumerate(eval_methods):
    ax.text(
        i, -0.15, method, ha="center", va="top", size=9, style="italic", color="gray"
    )

plt.tight_layout()
plt.savefig("fig_performance_breakdown.png", bbox_inches="tight", dpi=150)
print("Saved: fig_performance_breakdown.png")

# ===========================
# FIGURE 7: Latency Comparison
# ===========================
fig, ax = plt.subplots(figsize=(12, 7))
x_pos = np.arange(len(latency_data["Query Type"].unique()))
width = 0.25

naive_lat = latency_data[latency_data["System"] == "Naive"]["Latency (seconds)"].values
advanced_lat = latency_data[latency_data["System"] == "Advanced"][
    "Latency (seconds)"
].values
multiagent_lat = latency_data[latency_data["System"] == "Multi-Agent"][
    "Latency (seconds)"
].values

bars1 = ax.bar(
    x_pos - width,
    naive_lat,
    width,
    label="Naive RAG",
    color="#FF6B6B",
    edgecolor="black",
)
bars2 = ax.bar(
    x_pos, advanced_lat, width, label="Advanced RAG", color="#4ECDC4", edgecolor="black"
)
bars3 = ax.bar(
    x_pos + width,
    multiagent_lat,
    width,
    label="Multi-Agent RAG",
    color="#45B7D1",
    edgecolor="black",
)

# Add value labels
for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 1,
            f"{height:.1f}s",
            ha="center",
            va="bottom",
            size=9,
        )

ax.set_ylabel("Average Latency (seconds)", size=11, weight="bold")
ax.set_title("Response Latency by Query Type", weight="bold", size=12)
ax.set_xticks(x_pos)
ax.set_xticklabels(latency_data["Query Type"].unique())
ax.legend(loc="upper left", fontsize=10)
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, 70)

plt.tight_layout()
plt.savefig("fig_latency_comparison.png", bbox_inches="tight", dpi=150)
print("Saved: fig_latency_comparison.png")

# ===========================
# FIGURE 8: Token Usage & Cost
# ===========================
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Token usage
axes[0].bar(
    token_usage["System"],
    token_usage["Average Tokens"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)
for i, (system, tokens) in enumerate(
    zip(token_usage["System"], token_usage["Average Tokens"])
):
    axes[0].text(
        i, tokens + 600, f"{tokens:,}", ha="center", va="bottom", size=11, weight="bold"
    )
axes[0].set_ylabel("Average Tokens per Query", size=11, weight="bold")
axes[0].set_title("Token Consumption", weight="bold", size=12)
axes[0].grid(axis="y", alpha=0.3)
axes[0].set_ylim(0, 22000)

# Cost
axes[1].bar(
    token_usage["System"],
    token_usage["Cost (USD per 1K queries)"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)
for i, (system, cost) in enumerate(
    zip(token_usage["System"], token_usage["Cost (USD per 1K queries)"])
):
    axes[1].text(
        i, cost + 1.5, f"${cost:.1f}", ha="center", va="bottom", size=11, weight="bold"
    )
axes[1].set_ylabel("Cost (USD per 1,000 queries)", size=11, weight="bold")
axes[1].set_title("Operational Cost", weight="bold", size=12)
axes[1].grid(axis="y", alpha=0.3)
axes[1].set_ylim(0, 55)

plt.tight_layout()
plt.savefig("fig_token_cost.png", bbox_inches="tight", dpi=150)
print("Saved: fig_token_cost.png")

# ===========================
# TABLE GENERATION (LaTeX format)
# ===========================

print("\n" + "=" * 70)
print("LATEX TABLES")
print("=" * 70)

# Table 1: RAGAS Results
print("\n% Table 1: RAGAS Automated Evaluation")
print(
    ragas_results.to_latex(
        index=False,
        float_format="%.2f",
        caption="RAGAS Automated Evaluation - Normal Retrieval (N=187)",
        label="tab:ragas_results",
    )
)

# Table 2: Manual Single-Source
print("\n% Table 2: Manual Evaluation - Complex Single-Source")
print(
    manual_single_source.to_latex(
        index=False,
        float_format="%.0f",
        caption="Manual Evaluation Results - Complex Single-Source (N=40)",
        label="tab:manual_single",
    )
)

# Table 3: Manual Multi-Source
print("\n% Table 3: Manual Evaluation - Complex Multi-Source")
print(
    manual_multi_source.to_latex(
        index=False,
        float_format="%.0f",
        caption="Manual Evaluation Results - Complex Multi-Source (N=10)",
        label="tab:manual_multi",
    )
)

# Table 4: Overall Performance
print("\n% Table 4: Overall Weighted Performance")
overall_table = overall_performance.copy()
overall_table["Improvement vs Advanced"] = ["-", "-", "+6.1%"]
print(
    overall_table.to_latex(
        index=False,
        float_format="%.3f",
        caption="Overall Performance - Weighted Average",
        label="tab:overall",
    )
)

# Table 5: Latency Summary
print("\n% Table 5: Latency by Query Type")
latency_pivot = latency_data.pivot(
    index="Query Type", columns="System", values="Latency (seconds)"
)
latency_pivot = latency_pivot[["Naive", "Advanced", "Multi-Agent"]]
print(
    latency_pivot.to_latex(
        float_format="%.1f",
        caption="Average Response Latency (seconds)",
        label="tab:latency",
    )
)

# Table 6: Token & Cost
print("\n% Table 6: Token Usage and Cost")
print(
    token_usage.to_latex(
        index=False,
        caption="Token Consumption and Operational Cost",
        label="tab:tokens",
    )
)

print("\n" + "=" * 70)
print("All figures and tables generated successfully!")
print("=" * 70)
print("\nGenerated Files:")
print("  1. fig_dataset_composition.png")
print("  2. fig_ragas_results.png")
print("  3. fig_manual_single_source.png")
print("  4. fig_manual_multi_source.png (KEY DIFFERENTIATOR)")
print("  5. fig_overall_performance.png")
print("  6. fig_performance_breakdown.png")
print("  7. fig_latency_comparison.png")
print("  8. fig_token_cost.png")
