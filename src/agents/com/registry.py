# src/agents/com/registry.py
from typing import Dict, List, Optional, Callable, Type
from dataclasses import dataclass


@dataclass
class SubgraphConfig:
    """Configuration for registering a subgraph as a tool"""

    name: str
    description: str
    when_to_use: str
    examples: List[str]
    entry_state_type: Type
    executor: Callable
    fallback_chain: Optional[List[str]] = None
    requires_confirmation: bool = False


class SubgraphRegistry:
    """Central registry for all subgraphs"""

    def __init__(self):
        self._subgraphs: Dict[str, SubgraphConfig] = {}

    def register(self, config: SubgraphConfig):
        """Register a subgraph"""
        self._subgraphs[config.name] = config

    def get_definitions(self) -> List[Dict]:
        """Convert subgraphs to LLM tool definitions"""
        tools = []
        for name, config in self._subgraphs.items():
            tools.append(
                {
                    "name": f"execute_{name}",
                    "description": f"{config.description}\n\nWhen to use: {config.when_to_use}\n\nExamples:\n"
                    + "\n".join(f"- {ex}" for ex in config.examples[:3]),
                }
            )
        return tools

    def get_subgraph(self, name: str) -> Optional[SubgraphConfig]:
        """Get subgraph config"""
        return self._subgraphs.get(name)


registry = SubgraphRegistry()

registry.register(
    SubgraphConfig(
        name="simple_search",
        description="Retrieve documents using semantic and bm25 search and synthesize answer",
        when_to_use="When query has clear information need answerable from knowledge base",
        examples=[
            "What is our Q4 revenue?",
            "Explain the product features",
            "Compare pricing plans",
        ],
        entry_state_type=dict,
        executor=lambda state: ...,
        fallback_chain=["deep_research"],
        requires_confirmation=True,
    )
)

registry.register(
    SubgraphConfig(
        name="sql_query",
        description="Execute SQL queries against structured database",
        when_to_use="When query needs structured data from database tables",
        examples=[
            "Show users registered last week",
            "Count active subscriptions",
            "Top 10 customers by revenue",
        ],
        entry_state_type=dict,
        executor=lambda state: ...,
        fallback_chain=["simple_search"],
        requires_confirmation=True,
    )
)

# registry.register(SubgraphConfig(
#     name="dêp_research",
# ))
