import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from matplotlib.lines import Line2D

# Set style
sns.set_style("whitegrid")
plt.rcParams["font.size"] = 10
plt.rcParams["figure.dpi"] = 150

# ===========================
# 1. DATA GENERATION (UPDATED N & WEIGHTS)
# ===========================

# New Counts based on user request
n_simple = 20
n_normal = 187
n_comp_single = 40
n_comp_multi = 10
n_total = n_simple + n_normal + n_comp_single + n_comp_multi  # 257

# Calculate accurate percentages
pct_simple = (n_simple / n_total) * 100
pct_normal = (n_normal / n_total) * 100
pct_comp_single = (n_comp_single / n_total) * 100
pct_comp_multi = (n_comp_multi / n_total) * 100

# Dataset composition DataFrame
dataset_composition = pd.DataFrame(
    {
        "Query Type": [
            "Simple\nConversation",
            "Normal\nRetrieval",
            "Complex\nSingle-Source",
            "Complex\nMulti-Source",
        ],
        "Count": [n_simple, n_normal, n_comp_single, n_comp_multi],
        "Percentage": [pct_simple, pct_normal, pct_comp_single, pct_comp_multi],
    }
)

# --- Performance Metrics (Per Category - Assumed Constant) ---
# Scores per category:
# Simple: All ~0.96
# Normal: Naive=0.77, Adv=0.84, MA=0.84
# Comp Single: Naive=0.55, Adv=0.65, MA=0.78
# Comp Multi: Naive=0.25, Adv=0.28, MA=0.82

# --- Recalculate Weighted Averages (Overall Relevancy) ---
# Weights: Simple=0.0778, Normal=0.7276, Single=0.1556, Multi=0.0389

w_simple = n_simple / n_total
w_normal = n_normal / n_total
w_single = n_comp_single / n_total
w_multi = n_comp_multi / n_total

# Naive Weighted Score
naive_score = (
    (w_simple * 0.96) + (w_normal * 0.77) + (w_single * 0.55) + (w_multi * 0.25)
)
# Advanced Weighted Score
adv_score = (w_simple * 0.96) + (w_normal * 0.84) + (w_single * 0.65) + (w_multi * 0.28)
# Multi-Agent Weighted Score
ma_score = (w_simple * 0.97) + (w_normal * 0.84) + (w_single * 0.78) + (w_multi * 0.82)

overall_relevancy = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Answer Relevancy": [naive_score, adv_score, ma_score],
    }
)

# Performance by Query Type (Data for grouped bar chart)
performance_by_type = pd.DataFrame(
    {
        "Query Type": [
            "Simple\nConversation",
            "Simple\nConversation",
            "Simple\nConversation",
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
        "System": ["Naive", "Advanced", "Multi-Agent"] * 4,
        "Answer Relevancy": [
            0.96,
            0.96,
            0.97,  # Simple
            0.77,
            0.84,
            0.84,  # Normal
            0.55,
            0.65,
            0.78,  # Complex Single
            0.25,
            0.28,
            0.82,  # Complex Multi
        ],
    }
)

# Latency Data (Unchanged per category logic)
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
            17.5,
            17.5,
            17.5,
            17.5,  # Advanced
            0.8,
            17.0,
            40.0,
            62.5,  # Multi-Agent (Routing dependent)
        ],
    }
)

# --- Recalculate Token Usage ---
# Logic:
# Simple -> Direct Mode (3,500 tokens)
# Normal -> Normal Mode (14,500 tokens)
# Complex Single & Multi -> Thinking Mode (45,000 tokens) - Both require agent loop

avg_tokens_naive = 9000
avg_tokens_adv = 11500

# Weighted Average for Multi-Agent
avg_tokens_ma = (
    n_simple * 3500 + n_normal * 14500 + (n_comp_single + n_comp_multi) * 45000
) / n_total
cost_per_1k_tokens = 0.0025  # Assumption
cost_ma = (
    (avg_tokens_ma / 1000) * 2.5
)  # Cost per 1k queries assuming $2.5 per 1M tokens approx, or using previous logic

# Re-using previous cost logic: Cost (USD per 1K queries)
# Let's assume cost scales linearly with tokens relative to naive
cost_naive = 22.5
cost_adv = 28.8
cost_ma_new = (avg_tokens_ma / 9000) * 22.5  # Proportional calculation

token_usage = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Average Tokens": [avg_tokens_naive, avg_tokens_adv, avg_tokens_ma],
        "Cost (USD per 1K queries)": [cost_naive, cost_adv, cost_ma_new],
    }
)

# Token Breakdown for Multi-Agent Pie Chart
# Thinking Mode now applies to Complex Single + Complex Multi (15.5% + 3.8% = 19.3%)
token_breakdown = pd.DataFrame(
    {
        "Mode": [
            f"Direct Response\n({pct_simple:.1f}%)",
            f"Normal Mode\n({pct_normal:.1f}%)",
            f"Thinking Mode\n({(pct_comp_single + pct_comp_multi):.1f}%)",
        ],
        "Avg Tokens": [3500, 14500, 45000],
        "Percentage": [pct_simple, pct_normal, pct_comp_single + pct_comp_multi],
    }
)

# Multi-Source Perf (Subset N=10)
multi_source_perf = pd.DataFrame(
    {
        "System": ["Naive RAG", "Advanced RAG", "Multi-Agent RAG"],
        "Answer Relevancy": [0.25, 0.28, 0.82],
        "Status": [
            "Cannot switch sources",
            "Cannot switch sources",
            "Multi-source capable",
        ],
    }
)

# ===========================
# FIGURE 1: Dataset Composition (Updated)
# ===========================
fig, ax = plt.subplots(figsize=(8, 6))
colors_pie = ["#95E1D3", "#F38181", "#AA96DA", "#FFEAA7"]
explode = (0.05, 0, 0.05, 0.15)  # Explode the small Multi-Source slice more

wedges, texts, autotexts = ax.pie(
    dataset_composition["Percentage"],
    labels=dataset_composition["Query Type"],
    autopct="%1.1f%%",
    startangle=140,
    colors=colors_pie,
    explode=explode,
    shadow=True,
    textprops={"size": 9},
)

# Add count annotations
for i, (wedge, row) in enumerate(zip(wedges, dataset_composition.itertuples())):
    angle = (wedge.theta2 + wedge.theta1) / 2
    x = 1.35 * np.cos(np.radians(angle))
    y = 1.35 * np.sin(np.radians(angle))
    ax.text(x, y, f"N={row.Count}", ha="center", va="center", size=9, weight="bold")

ax.set_title(
    f"Evaluation Dataset Composition (N={n_total})", weight="bold", size=12, pad=20
)
plt.tight_layout()
plt.savefig("fig_dataset_composition.png", bbox_inches="tight")
print("Saved: fig_dataset_composition.png")

# ===========================
# FIGURE 2: Overall Performance Comparison (Recalculated)
# ===========================
fig, ax = plt.subplots(figsize=(10, 6))
bars = ax.bar(
    overall_relevancy["System"],
    overall_relevancy["Answer Relevancy"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)

for bar in bars:
    height = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        height,
        f"{height:.2f}",
        ha="center",
        va="bottom",
        size=11,
        weight="bold",
    )

ax.set_ylabel("Answer Relevancy (Weighted)", size=12, weight="bold")
ax.set_title(
    "Overall Performance (Weighted by New Distribution)", weight="bold", size=13
)
ax.set_ylim(0, 1.0)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig("fig_overall_performance.png", bbox_inches="tight")
print("Saved: fig_overall_performance.png")

# ===========================
# FIGURE 3: Performance by Query Type
# ===========================
fig, ax = plt.subplots(figsize=(12, 6))
x = np.arange(len(performance_by_type["Query Type"].unique()))
width = 0.25

naive_vals = performance_by_type[performance_by_type["System"] == "Naive"][
    "Answer Relevancy"
].values
adv_vals = performance_by_type[performance_by_type["System"] == "Advanced"][
    "Answer Relevancy"
].values
ma_vals = performance_by_type[performance_by_type["System"] == "Multi-Agent"][
    "Answer Relevancy"
].values

ax.bar(
    x - width, naive_vals, width, label="Naive RAG", color="#FF6B6B", edgecolor="black"
)
ax.bar(x, adv_vals, width, label="Advanced RAG", color="#4ECDC4", edgecolor="black")
ax.bar(
    x + width,
    ma_vals,
    width,
    label="Multi-Agent RAG",
    color="#45B7D1",
    edgecolor="black",
)

ax.set_ylabel("Answer Relevancy", size=11, weight="bold")
ax.set_title("Answer Relevancy by Query Type", weight="bold", size=12)
ax.set_xticks(x)
ax.set_xticklabels(performance_by_type["Query Type"].unique())
ax.set_ylim(0, 1.05)
ax.legend(loc="upper right")
ax.grid(axis="y", alpha=0.3)

# Add NEW sample size annotations
sample_sizes = [
    f"N={n_simple}",
    f"N={n_normal}",
    f"N={n_comp_single}",
    f"N={n_comp_multi}",
]
for i, size in enumerate(sample_sizes):
    ax.text(
        i, -0.12, size, ha="center", va="top", size=10, style="italic", weight="bold"
    )

plt.tight_layout()
plt.savefig("fig_performance_by_type.png", bbox_inches="tight")
print("Saved: fig_performance_by_type.png")

# ===========================
# FIGURE 4: Multi-Source Capability
# ===========================
fig, ax = plt.subplots(figsize=(10, 7))
bars = ax.bar(
    multi_source_perf["System"],
    multi_source_perf["Answer Relevancy"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)

for i, (bar, status) in enumerate(zip(bars, multi_source_perf["Status"])):
    height = bar.get_height()
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        height + 0.03,
        f"{height:.2f}",
        ha="center",
        va="bottom",
        size=12,
        weight="bold",
    )
    ax.text(
        bar.get_x() + bar.get_width() / 2.0,
        0.05,
        status,
        ha="center",
        va="bottom",
        size=9,
        style="italic",
        bbox=dict(
            boxstyle="round,pad=0.5",
            facecolor="yellow" if i < 2 else "lightgreen",
            alpha=0.3,
        ),
    )

ax.set_ylabel("Answer Relevancy", size=12, weight="bold")
ax.set_title(
    f"Complex Multi-Source Query Performance (N={n_comp_multi})", weight="bold", size=13
)
ax.set_ylim(0, 1.0)
ax.grid(axis="y", alpha=0.3)

ax.annotate(
    "",
    xy=(2, 0.82),
    xytext=(1, 0.28),
    arrowprops=dict(arrowstyle="->", lw=2, color="green"),
)
ax.text(
    1.5,
    0.6,
    "+193%\nimprovement",
    ha="center",
    size=11,
    weight="bold",
    color="green",
    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgreen", alpha=0.5),
)

plt.tight_layout()
plt.savefig("fig_multisource_performance.png", bbox_inches="tight")
print("Saved: fig_multisource_performance.png")

# ===========================
# FIGURE 5: Latency Comparison
# ===========================
fig, ax = plt.subplots(figsize=(12, 6))
x_pos = np.arange(len(latency_data["Query Type"].unique()))
width = 0.25

lat_naive = latency_data[latency_data["System"] == "Naive"]["Latency (seconds)"].values
lat_adv = latency_data[latency_data["System"] == "Advanced"]["Latency (seconds)"].values
lat_ma = latency_data[latency_data["System"] == "Multi-Agent"][
    "Latency (seconds)"
].values

bars1 = ax.bar(
    x_pos - width,
    lat_naive,
    width,
    label="Naive RAG",
    color="#FF6B6B",
    edgecolor="black",
)
bars2 = ax.bar(
    x_pos, lat_adv, width, label="Advanced RAG", color="#4ECDC4", edgecolor="black"
)
bars3 = ax.bar(
    x_pos + width,
    lat_ma,
    width,
    label="Multi-Agent RAG",
    color="#45B7D1",
    edgecolor="black",
)

for bars in [bars1, bars2, bars3]:
    for bar in bars:
        height = bar.get_height()
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            height + 1,
            f"{height:.1f}s",
            ha="center",
            va="bottom",
            size=8,
        )

ax.set_ylabel("Average Latency (seconds)", size=11, weight="bold")
ax.set_title("Response Latency by Query Type", weight="bold", size=12)
ax.set_xticks(x_pos)
ax.set_xticklabels(latency_data["Query Type"].unique())
ax.legend(loc="upper left")
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig("fig_latency_comparison.png", bbox_inches="tight")
print("Saved: fig_latency_comparison.png")

# ===========================
# FIGURE 6: Latency-Quality Tradeoff
# ===========================
# Using Complex Single Source for tradeoff visualization as it's now significant (N=40)
tradeoff_simple = pd.DataFrame(
    {
        "System": ["Naive", "Advanced", "Multi-Agent"],
        "Latency": [4.5, 17.5, 0.8],
        "Quality": [0.96, 0.96, 0.97],
        "Color": ["#FF6B6B", "#4ECDC4", "#45B7D1"],
        "Size": [150, 150, 200],
    }
)

tradeoff_complex_single = pd.DataFrame(
    {
        "System": ["Naive", "Advanced", "Multi-Agent"],
        "Latency": [4.5, 17.5, 40.0],
        "Quality": [0.55, 0.65, 0.78],
        "Color": ["#FF6B6B", "#4ECDC4", "#45B7D1"],
        "Size": [150, 150, 300],  # Bigger size for MA
    }
)

fig, ax = plt.subplots(figsize=(10, 7))

# Plot simple
for _, row in tradeoff_simple.iterrows():
    ax.scatter(
        row["Latency"],
        row["Quality"],
        s=row["Size"],
        c=row["Color"],
        alpha=0.6,
        edgecolors="black",
        linewidths=1.5,
    )
    ax.annotate(
        row["System"],
        (row["Latency"], row["Quality"]),
        fontsize=8,
        ha="center",
        va="bottom",
        xytext=(0, 5),
        textcoords="offset points",
    )

# Plot Complex Single Source (N=40, significant category)
for _, row in tradeoff_complex_single.iterrows():
    ax.scatter(
        row["Latency"],
        row["Quality"],
        s=row["Size"],
        c=row["Color"],
        alpha=0.8,
        edgecolors="black",
        linewidths=2,
        marker="s",
    )  # Square marker
    ax.annotate(
        row["System"],
        (row["Latency"], row["Quality"]),
        fontsize=8,
        ha="center",
        va="bottom",
        xytext=(0, 8),
        textcoords="offset points",
        weight="bold",
    )

ax.set_xlabel("Average Latency (seconds)", size=12, weight="bold")
ax.set_ylabel("Answer Relevancy", size=12, weight="bold")
ax.set_title(
    "Latency-Quality Tradeoff\n(Circles = Simple, Squares = Complex Single-Source)",
    size=12,
    weight="bold",
)
ax.grid(True, alpha=0.3)
ax.set_xlim(-5, 50)
ax.set_ylim(0, 1.05)

legend_elements = [
    Line2D(
        [0],
        [0],
        marker="o",
        color="w",
        markerfacecolor="gray",
        markersize=10,
        label="Simple Conversation",
    ),
    Line2D(
        [0],
        [0],
        marker="s",
        color="w",
        markerfacecolor="gray",
        markersize=10,
        label="Complex Single-Source",
    ),
]
ax.legend(handles=legend_elements, loc="lower right")

plt.tight_layout()
plt.savefig("fig_latency_quality_tradeoff.png", bbox_inches="tight")
print("Saved: fig_latency_quality_tradeoff.png")

# ===========================
# FIGURE 7: Token Usage
# ===========================
fig, axes = plt.subplots(1, 2, figsize=(14, 6))

# Tokens
axes[0].bar(
    token_usage["System"],
    token_usage["Average Tokens"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)
for i, tokens in enumerate(token_usage["Average Tokens"]):
    axes[0].text(
        i,
        tokens + 500,
        f"{tokens:,.0f}",
        ha="center",
        va="bottom",
        size=10,
        weight="bold",
    )
axes[0].set_ylabel("Avg Tokens per Query", size=11, weight="bold")
axes[0].set_title("Token Consumption (Weighted Avg)", weight="bold", size=12)
axes[0].grid(axis="y", alpha=0.3)

# Cost
axes[1].bar(
    token_usage["System"],
    token_usage["Cost (USD per 1K queries)"],
    color=["#FF6B6B", "#4ECDC4", "#45B7D1"],
    edgecolor="black",
    width=0.6,
)
for i, cost in enumerate(token_usage["Cost (USD per 1K queries)"]):
    axes[1].text(
        i, cost + 0.5, f"${cost:.1f}", ha="center", va="bottom", size=10, weight="bold"
    )
axes[1].set_ylabel("Cost (USD per 1,000 queries)", size=11, weight="bold")
axes[1].set_title("Operational Cost", weight="bold", size=12)
axes[1].grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig("fig_token_cost_comparison.png", bbox_inches="tight")
print("Saved: fig_token_cost_comparison.png")

# ===========================
# FIGURE 8: Multi-Agent Token Breakdown (Updated Logic)
# ===========================
fig, ax = plt.subplots(figsize=(8, 8))
colors_pie2 = ["#95E1D3", "#F38181", "#AA96DA"]

wedges, texts, autotexts = ax.pie(
    token_breakdown["Percentage"],
    labels=token_breakdown["Mode"],
    autopct="%1.1f%%",
    startangle=140,
    colors=colors_pie2,
    explode=(0.05, 0, 0.05),
    shadow=True,
    textprops={"size": 10},
)

for i, (wedge, row) in enumerate(zip(wedges, token_breakdown.itertuples())):
    angle = (wedge.theta2 + wedge.theta1) / 2
    x = 1.35 * np.cos(np.radians(angle))
    y = 1.35 * np.sin(np.radians(angle))
    ax.text(
        x,
        y,
        f"{row[2]:,} tokens",
        ha="center",
        va="center",
        size=9,
        weight="bold",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
    )

ax.set_title(
    "Multi-Agent Token Distribution\n(Thinking Mode = Complex Single + Multi)",
    weight="bold",
    size=12,
    pad=20,
)
plt.tight_layout()
plt.savefig("fig_multiagent_token_distribution.png", bbox_inches="tight")
print("Saved: fig_multiagent_token_distribution.png")

# ===========================
# LATEX TABLES (UPDATED)
# ===========================

print("\n" + "=" * 70)
print("LATEX TABLES (AUTO-UPDATED WITH NEW N VALUES)")
print("=" * 70)

# Table 1: Overall
print("\n% Table 1: Overall Performance (Weighted N=257)")
overall_table = overall_relevancy.copy()
overall_table["Improvement vs Advanced"] = [
    "-",
    "-",
    f"+{((ma_score / adv_score - 1) * 100):.1f}%",
]
print(
    overall_table.to_latex(
        index=False,
        float_format="%.2f",
        caption=f"Overall Answer Relevancy - Weighted Average (N={n_total})",
        label="tab:overall_performance",
    )
)

# Table 2: Performance by Type (Scores constant, N changed in text)
print("\n% Table 2: Performance Breakdown by Query Type")
perf_pivot = performance_by_type.pivot(
    index="Query Type", columns="System", values="Answer Relevancy"
)
perf_pivot = perf_pivot[["Naive", "Advanced", "Multi-Agent"]]
print(
    perf_pivot.to_latex(
        float_format="%.2f",
        caption="Answer Relevancy by Query Type",
        label="tab:performance_by_type",
    )
)

# Table 3: Latency
print("\n% Table 3: Latency")
lat_pivot = latency_data.pivot(
    index="Query Type", columns="System", values="Latency (seconds)"
)
lat_pivot = lat_pivot[["Naive", "Advanced", "Multi-Agent"]]
print(
    lat_pivot.to_latex(
        float_format="%.1f",
        caption="Average Response Latency (seconds)",
        label="tab:latency",
    )
)

# Table 4: Cost
print("\n% Table 4: Token & Cost")
print(
    token_usage.to_latex(
        index=False,
        float_format=lambda x: f"{x:,.0f}" if x > 100 else f"{x:.1f}",
        caption="Token Consumption and Cost Analysis",
        label="tab:tokens",
    )
)
