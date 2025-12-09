import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Set modern style
sns.set_style("whitegrid")
plt.rcParams["font.size"] = 11
plt.rcParams["figure.dpi"] = 150
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.facecolor"] = "#f8f9fa"
plt.rcParams["figure.facecolor"] = "white"

# Modern color palette
colors_modern = {
    "naive": "#FF6B6B",
    "advanced": "#4ECDC4",
    "multiagent": "#45B7D1",
    "correct": "#2ECC71",
    "partial": "#F39C12",
    "wrong": "#E74C3C",
}

# ===========================
# DATA GENERATION
# ===========================

# RAGAS for Normal Retrieval (N=187)
ragas_results = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Answer Relevancy": [0.80, 0.84, 0.87],
    }
)

# Manual Evaluation - Complex Single-Source (N=40)
manual_single_source = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Correct (1.0)": [8, 18, 34],
        "Partial (0.5)": [28, 17, 6],
        "Wrong (0.0)": [4, 5, 0],
    }
)
manual_single_source["Success Rate"] = (
    manual_single_source["Correct (1.0)"] * 1.0
    + manual_single_source["Partial (0.5)"] * 0.5
) / 40

# Manual Evaluation - Complex Multi-Source (N=10)
manual_multi_source = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Correct (1.0)": [0, 0, 10],
        "Partial (0.5)": [6, 7, 0],
        "Wrong (0.0)": [4, 3, 0],
    }
)
manual_multi_source["Success Rate"] = (
    manual_multi_source["Correct (1.0)"] * 1.0
    + manual_multi_source["Partial (0.5)"] * 0.5
) / 10

# Latency Data
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
            4.5,  # Naive
            12.0,
            17.5,
            21.0,
            24.0,  # Advanced
            0.8,
            20.0,
            52.5,
            62.5,  # Multi-Agent
        ],
    }
)

# Token Usage
token_usage = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Average Tokens": [9000, 11500, 21500],
        "Cost (USD per 1K queries)": [22.5, 28.8, 53.75],
    }
)

# ===========================
# FIGURE GENERATION
# ===========================

print("=" * 60)
print("GENERATING REVISED FIGURES")
print("=" * 60)

# --- FIGURE 1: RAGAS Results (Previously Fig 2) ---
fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(
    ragas_results["System"],
    ragas_results["Answer Relevancy"],
    color=[
        colors_modern["naive"],
        colors_modern["advanced"],
        colors_modern["multiagent"],
    ],
    edgecolor="black",
    linewidth=1.5,
    width=0.6,
    alpha=0.9,
)

# Add values on top of bars
for bar in bars:
    height = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 0.015,
        f"{height:.2f}",
        ha="center",
        va="bottom",
        size=14,
        weight="bold",
        bbox=dict(
            boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.8
        ),
    )

ax.set_ylabel("Answer Relevancy Score", size=13, weight="bold")
ax.set_title(
    "Automated Evaluation - Normal Retrieval Queries (N=187)\n[RAGAS Framework]",
    weight="bold",
    size=13,
    pad=15,
)
ax.set_ylim(0, 1.0)
ax.grid(axis="y", alpha=0.3, linestyle="--")
plt.tight_layout()
plt.savefig("fig_1_ragas_results.png", bbox_inches="tight", dpi=150)
print("✓ Figure 1: RAGAS Results (Cleaned)")

# --- FIGURE 2: Manual Single-Source (Previously Fig 3) ---
fig, ax = plt.subplots(figsize=(13, 8))
x = np.arange(len(manual_single_source["System"]))
width = 0.27
bars1 = ax.bar(
    x - width,
    manual_single_source["Correct (1.0)"],
    width,
    label="Correct (1.0)",
    color=colors_modern["correct"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars2 = ax.bar(
    x,
    manual_single_source["Partial (0.5)"],
    width,
    label="Partial (0.5)",
    color=colors_modern["partial"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars3 = ax.bar(
    x + width,
    manual_single_source["Wrong (0.0)"],
    width,
    label="Wrong (0.0)",
    color=colors_modern["wrong"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)

for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + 0.5,
                f"{int(height)}",
                ha="center",
                va="bottom",
                size=11,
                weight="bold",
            )

# Success Rate Annotations
for i, rate in enumerate(manual_single_source["Success Rate"]):
    color = "lightcoral" if rate < 0.6 else "lightgreen" if rate < 0.9 else "#90EE90"
    ax.text(
        i,
        44,
        f"Success Rate:\n{rate:.1%}",
        ha="center",
        size=11,
        weight="bold",
        bbox=dict(
            boxstyle="round,pad=0.6",
            facecolor=color,
            edgecolor="black",
            linewidth=1.5,
            alpha=0.85,
        ),
    )

ax.set_title(
    "Manual Evaluation - Complex Single-Source Queries (N=40)",
    weight="bold",
    size=13,
    pad=15,
)
ax.set_xticks(x)
ax.set_xticklabels(manual_single_source["System"], size=12, weight="bold")
ax.legend(loc="upper left", fontsize=11, framealpha=0.9)
ax.set_ylim(0, 50)
ax.set_ylabel("Number of Queries", size=12, weight="bold")
ax.grid(axis="y", alpha=0.3, linestyle="--")
plt.tight_layout()
plt.savefig("fig_2_manual_single_source.png", bbox_inches="tight", dpi=150)
print("✓ Figure 2: Manual Single-Source")

# --- FIGURE 3: Manual Multi-Source (Previously Fig 4) ---
fig, ax = plt.subplots(figsize=(13, 8))
x = np.arange(len(manual_multi_source["System"]))
width = 0.27
bars1 = ax.bar(
    x - width,
    manual_multi_source["Correct (1.0)"],
    width,
    label="Correct (1.0)",
    color=colors_modern["correct"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars2 = ax.bar(
    x,
    manual_multi_source["Partial (0.5)"],
    width,
    label="Partial (0.5)",
    color=colors_modern["partial"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars3 = ax.bar(
    x + width,
    manual_multi_source["Wrong (0.0)"],
    width,
    label="Wrong (0.0)",
    color=colors_modern["wrong"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)

for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        if height > 0:
            ax.text(
                bar.get_x() + bar.get_width() / 2.0,
                height + 0.15,
                f"{int(height)}",
                ha="center",
                va="bottom",
                size=12,
                weight="bold",
            )

# Success Rate Annotations (Without Arrows)
for i, (system, rate) in enumerate(
    zip(manual_multi_source["System"], manual_multi_source["Success Rate"])
):
    color = "lightcoral" if rate < 0.5 else "lightgreen"
    if rate == 1.0:
        color = "#90EE90"
    ax.text(
        i,
        11.5,
        f"Success Rate:\n{rate:.0%}",
        ha="center",
        size=12,
        weight="bold",
        bbox=dict(
            boxstyle="round,pad=0.6",
            facecolor=color,
            edgecolor="black",
            linewidth=1.5,
            alpha=0.9,
        ),
    )

ax.set_title(
    "Manual Evaluation - Complex Multi-Source Queries (N=10)",
    weight="bold",
    size=13,
    color="#C0392B",
    pad=15,
)
ax.set_xticks(x)
ax.set_xticklabels(manual_multi_source["System"], size=12, weight="bold")
ax.legend(loc="upper left", fontsize=11, framealpha=0.9)
ax.set_ylim(0, 15)
ax.set_ylabel("Number of Queries", size=12, weight="bold")
ax.grid(axis="y", alpha=0.3, linestyle="--")
plt.tight_layout()
plt.savefig("fig_3_manual_multi_source.png", bbox_inches="tight", dpi=150)
print("✓ Figure 3: Manual Multi-Source (Cleaned)")

# --- FIGURE 4: Response Latency (Previously Fig 5) ---
fig, ax = plt.subplots(figsize=(13, 8))
query_types = latency_data["Query Type"].unique()
x = np.arange(len(query_types))
width = 0.27

naive_latency = latency_data[latency_data["System"] == "Naive"][
    "Latency (seconds)"
].values
advanced_latency = latency_data[latency_data["System"] == "Advanced"][
    "Latency (seconds)"
].values
multiagent_latency = latency_data[latency_data["System"] == "Multi-Agent"][
    "Latency (seconds)"
].values

bars1 = ax.bar(
    x - width,
    naive_latency,
    width,
    label="Naive RAG",
    color=colors_modern["naive"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars2 = ax.bar(
    x,
    advanced_latency,
    width,
    label="Advanced RAG",
    color=colors_modern["advanced"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)
bars3 = ax.bar(
    x + width,
    multiagent_latency,
    width,
    label="Multi-Agent RAG",
    color=colors_modern["multiagent"],
    edgecolor="black",
    linewidth=1.2,
    alpha=0.9,
)

for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 1.0,
            f"{height:.1f}s",
            ha="center",
            va="bottom",
            size=10,
            weight="bold",
        )

ax.set_ylabel("Response Latency (seconds)", size=13, weight="bold")
ax.set_title("Response Latency Analysis by Query Type", weight="bold", size=14, pad=15)
ax.set_xticks(x)
ax.set_xticklabels(query_types, size=11)
ax.legend(loc="upper left", fontsize=11, framealpha=0.9)
ax.set_ylim(0, 70)
ax.grid(axis="y", alpha=0.3, linestyle="--")

plt.tight_layout()
plt.savefig("fig_4_latency_analysis.png", bbox_inches="tight", dpi=150)
print("✓ Figure 4: Latency Analysis (Cleaned)")

# --- FIGURE 5: Token Usage and Cost (Previously Fig 6) ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Token usage
bars1 = ax1.bar(
    token_usage["System"],
    token_usage["Average Tokens"],
    color=[
        colors_modern["naive"],
        colors_modern["advanced"],
        colors_modern["multiagent"],
    ],
    edgecolor="black",
    linewidth=1.5,
    width=0.65,
    alpha=0.9,
)
for bar in bars1:
    height = bar.get_height()
    ax1.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 500,
        f"{int(height):,}",
        ha="center",
        va="bottom",
        size=12,
        weight="bold",
        bbox=dict(
            boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.8
        ),
    )
ax1.set_ylabel("Average Tokens per Query", size=12, weight="bold")
ax1.set_title("Token Consumption", weight="bold", size=13)
ax1.set_ylim(0, 25000)
ax1.grid(axis="y", alpha=0.3, linestyle="--")

# Cost
bars2 = ax2.bar(
    token_usage["System"],
    token_usage["Cost (USD per 1K queries)"],
    color=[
        colors_modern["naive"],
        colors_modern["advanced"],
        colors_modern["multiagent"],
    ],
    edgecolor="black",
    linewidth=1.5,
    width=0.65,
    alpha=0.9,
)
for bar in bars2:
    height = bar.get_height()
    ax2.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 1.5,
        f"${height:.2f}",
        ha="center",
        va="bottom",
        size=12,
        weight="bold",
        bbox=dict(
            boxstyle="round,pad=0.3", facecolor="white", edgecolor="gray", alpha=0.8
        ),
    )
ax2.set_ylabel("Cost (USD per 1,000 queries)", size=12, weight="bold")
ax2.set_title("Operational Cost", weight="bold", size=13)
ax2.set_ylim(0, 65)
ax2.grid(axis="y", alpha=0.3, linestyle="--")

plt.tight_layout()
plt.savefig("fig_5_token_cost.png", bbox_inches="tight", dpi=150)
print("✓ Figure 5: Token Usage & Cost")

print("\n" + "=" * 60)
print("✨ FIGURES GENERATED SUCCESSFULLY")
print("=" * 60)
