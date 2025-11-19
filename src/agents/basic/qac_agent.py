# src/agents/basic/qac_agent.py

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from src.core.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm

QAC_PROMPT_TEMPLATE = """Your task is to create exactly one question and one answer based on the provided input.

<GUIDELINES>:
1. The question must be clear, concise, and accurately reflect the content of the input.
2. The answer must be precise, detailed, and relevant to the question without adding information beyond the input.
3. If the input lacks sufficient information to create a meaningful question and answer, return a question and answer suitable for the remaining content.
4. The languague of the question and answer should only be English.
5. Return exactly one question and one answer only.
</GUIDELINES>

<EXAMPLE>:
Input: "Renewable energy provides an environmentally friendly alternative to fossil fuels."
Output: {{"question": "What are the advantages of renewable energy?", "answer": "Renewable energy provides an environmentally friendly alternative to fossil fuels."}}
</EXAMPLE>

### Input:
{input}

### Output:
The output must be in exact proper valid JSON format, with no extra spaces or line breaks, with special characters properly escaped, following this structure:
{{"question": "Generated question", "answer": "Generated answer: but with \"quotes\""}}

## Remember:
JSON only allows certain characters to be escaped, such as double quotes, backslashes, and control characters. Ensure that your output adheres to this format strictly.
DO NOT escape characters that do not require escaping in JSON, such as underscores or spaces. The output must be a valid JSON object with the keys "question" and "answer"."""


class QACAgent:
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        self.llm = get_llm(provider)

    async def generate_qa(self, contexts: list[str]) -> list[tuple[str, str]]:
        """
        Generate question-answer pairs based on the provided contexts.

        Args:
            contexts (List[str]): List of contexts to generate QA pairs from.

        Returns:
            List[Tuple[str, str]]: List of (question, answer) tuples.
        """
        try:
            prompt = PromptTemplate(
                template=QAC_PROMPT_TEMPLATE, input_variables=["input"]
            )

            chain = prompt | self.llm | JsonOutputParser()

            inputs = [{"input": context} for context in contexts]

            results = await chain.with_retry().abatch(inputs=inputs)

            if not results:
                raise ValueError("No content returned from LLM response")

            unique_qa_pairs = []
            seen_questions = set()

            for content in results:
                question = content.get("question", "").strip()
                answer = content.get("answer", "").strip()

                if not question or not answer:
                    continue

                if question not in seen_questions:
                    unique_qa_pairs.append((question, answer))
                    seen_questions.add(question)

            return unique_qa_pairs

        except Exception as e:
            raise RuntimeError(f"Error generating QA: {str(e)}")
