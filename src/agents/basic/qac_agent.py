# src/agents/basic/qac_agent.py
from typing import List, Tuple

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from src.core.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from src.agents.prompts.get_prompt_template import load_prompt_template


class QACAgent:
    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        self.llm = get_llm(provider)

    async def generate_qa(self, contexts: List[str]) -> List[Tuple[str, str]]:
        """
        Generate question-answer pairs based on the provided contexts.

        Args:
            contexts (List[str]): List of contexts to generate QA pairs from.

        Returns:
            List[Tuple[str, str]]: List of (question, answer) tuples.
        """
        try:
            language = "en"
            prompt_template = load_prompt_template(
                task_name="generate_qa",
                language_code=language,
            )
            prompt = PromptTemplate(template=prompt_template, input_variables=["input"])

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
