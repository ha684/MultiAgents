import tiktoken

from src.agents.basic.citation_agent import CITATION_PROMPT_TEMPLATE
from src.agents.basic.compress_agent import COMPRESS_PROMPT_TEMPLATE
from src.agents.basic.response_agent import (
    HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE,
    NO_CONTEXT_GENERATION_PROMPT_TEMPLATE,
    REASONING_ONLY_PROMPT_TEMPLATE,
    SQL_RESPONSE_MODE_PROMPT,
)
from src.agents.prompts.agent_prompts import PromptTemplates

encoder = tiktoken.get_encoding("cl100k_base")

print(
    "SQL query generation system prompt: ",
    len(encoder.encode(PromptTemplates.SQL_GENERATION_SYSTEM_PROMPT)),
)
print(
    "SQL relevance validation system prompt: ",
    len(encoder.encode(PromptTemplates.RELEVANCE_VALIDATION_SYSTEM_PROMPT)),
)
print(
    "Vegalite Chart generation system prompt: ",
    len(encoder.encode(PromptTemplates.CHART_GENERATION_SYSTEM_PROMPT)),
)
print(
    "Phase agent prompt: ", len(encoder.encode(PromptTemplates.PHASE_PLANNING_PROMPT))
)
print(
    "Reasoning execution prompt: ",
    len(encoder.encode(PromptTemplates.REASONING_EXECUTION_PROMPT)),
)
print(
    "Action execution prompt: ",
    len(encoder.encode(PromptTemplates.TOOL_EXECUTION_PROMPT)),
)
print(
    "SQL analysis system prompt: ",
    len(encoder.encode(PromptTemplates.SQL_ANALYSIS_SYSTEM_PROMPT)),
)
print(
    "Direct response prompt: ",
    len(encoder.encode(PromptTemplates.DIRECT_RESPONSE_PROMPT)),
)
print("Citation agent prompt: ", len(encoder.encode(CITATION_PROMPT_TEMPLATE)))
print(
    "Response agent prompt, advance mode: ",
    len(encoder.encode(PromptTemplates.FINAL_SYNTHESIZER_PROMPT)),
)
print(
    "Response agent prompt, have context: ",
    len(encoder.encode(HAVE_CONTEXT_GENERATION_PROMPT_TEMPLATE)),
)
print(
    "Response agent prompt, no context: ",
    len(encoder.encode(NO_CONTEXT_GENERATION_PROMPT_TEMPLATE)),
)
print(
    "Response agent prompt, sql response mode: ",
    len(encoder.encode(SQL_RESPONSE_MODE_PROMPT)),
)
print(
    "Response agent prompt, reasoning only: ",
    len(encoder.encode(REASONING_ONLY_PROMPT_TEMPLATE)),
)
print("Compress agent prompt: ", len(encoder.encode(COMPRESS_PROMPT_TEMPLATE)))
