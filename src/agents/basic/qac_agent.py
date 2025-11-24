# src/agents/basic/qac_agent.py

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate

from src.core.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm

QAC_PROMPT_TEMPLATE = """You are a question-answer pair generator. Your task is to create ONE self-contained, specific question and its answer from the given input.

<CRITICAL_RULES>:
1. Questions MUST be self-contained and specific
   - Include necessary context IN the question itself
   - DO NOT use phrases like: "the provided", "the document", "the text", "above", "following"
   - DO NOT use vague references: "What is mentioned?", "What is described?", "What is the value?"
   - DO NOT refer to visual elements: "the table", "the chart", "the figure"

2. Questions MUST be answerable without seeing the original document
   - Bad: "What is the main task described in the provided guidelines?"
   - Good: "What is the main task for data preprocessing in machine learning pipelines?"
   - Bad: "What is the numerical value provided?"
   - Good: "What is the accuracy score of the ResNet-50 model on ImageNet dataset?"

3. Include specific entities, numbers, or concepts from the input
   - Use proper nouns, technical terms, dates, locations
   - Make the question specific enough to stand alone

4. The answer must be accurate and directly from the input
   - Do not add information beyond what's provided
   - Keep the answer concise but complete

5. Language: English only

6. If the input is too vague or lacks substance, skip it by returning empty question and answer

</CRITICAL_RULES>

<GOOD_EXAMPLES>:
Input: "Renewable energy provides an environmentally friendly alternative to fossil fuels."
Output: {{"question": "What environmental benefit does renewable energy provide compared to fossil fuels?", "answer": "Renewable energy provides an environmentally friendly alternative to fossil fuels."}}

Input: "The ResNet-50 model achieved 76.5% accuracy on the ImageNet dataset."
Output: {{"question": "What accuracy did the ResNet-50 model achieve on the ImageNet dataset?", "answer": "The ResNet-50 model achieved 76.5% accuracy on the ImageNet dataset."}}

Input: "In 2023, Tesla delivered 1.8 million electric vehicles worldwide."
Output: {{"question": "How many electric vehicles did Tesla deliver worldwide in 2023?", "answer": "Tesla delivered 1.8 million electric vehicles worldwide in 2023."}}
</GOOD_EXAMPLES>

<BAD_EXAMPLES>:
❌ "What is the main point discussed?" (too vague)
❌ "What does the document mention about climate?" (refers to "the document")
❌ "What is shown in the table?" (refers to visual element)
❌ "What is the value?" (no context)
❌ "What is described in the text above?" (refers to "above")
</BAD_EXAMPLES>

### Input:
{input}

### Task:
Generate ONE question-answer pair that follows all the rules above. If the input is too vague or insufficient, return empty strings for both question and answer.

### Output:
Return ONLY valid JSON with no markdown formatting, following this exact structure:
{{"question": "Your specific, self-contained question here", "answer": "Your accurate answer here"}}

Remember: The question must make sense on its own without any external context or document reference.
"""


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
