# src/agents/basic/qac_agent.py

import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.core.config.llm_config import LLMModelConfigs, SupportedLLMProviders
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

QAC_SYSTEM_PROMPT = """You are an expert question-answer pair generator for knowledge management systems. Your task is to analyze document content and generate high-quality, self-contained question-answer pairs.

**CRITICAL REQUIREMENTS:**

1. **Self-Contained Questions**
   - Questions MUST include all necessary context within themselves
   - DO NOT use references like: "the document", "the text", "above", "following", "mentioned", "described", "provided"
   - DO NOT refer to visual elements: "the table", "the chart", "the figure", "the image"
   - Each question should make complete sense without seeing the original document

2. **Specificity & Clarity**
   - Include specific entities: proper nouns, technical terms, dates, numbers, locations
   - Bad: "What is the main task described in the provided guidelines?"
   - Good: "What is the main task for data preprocessing in machine learning pipelines?"
   - Bad: "What is the numerical value?"
   - Good: "What is the accuracy score of the ResNet-50 model on ImageNet dataset?"

3. **Accuracy**
   - Answers must be directly supported by the content
   - Do not add information beyond what's provided
   - Keep answers concise but complete
   - Preserve important details, numbers, and context

4. **Quality Control**
   - Skip trivial or obvious questions
   - Avoid repetitive questions on the same topic
   - Focus on key facts, concepts, and insights
   - Generate diverse questions covering different aspects of the content

5. **Format**
   - Language: English only
   - Output: Valid JSON array of question-answer pairs
   - Each pair: {"question": "...", "answer": "..."}

**GOOD EXAMPLES:**

Content: "The ResNet-50 model achieved 76.5% accuracy on the ImageNet dataset in 2015, significantly outperforming previous architectures."

Good Q/A Pairs:
1. {"question": "What accuracy did the ResNet-50 model achieve on the ImageNet dataset?", "answer": "The ResNet-50 model achieved 76.5% accuracy on the ImageNet dataset."}
2. {"question": "When did ResNet-50 achieve 76.5% accuracy on ImageNet?", "answer": "ResNet-50 achieved this accuracy in 2015."}
3. {"question": "How did ResNet-50 perform compared to previous architectures on ImageNet?", "answer": "ResNet-50 significantly outperformed previous architectures on ImageNet."}

**BAD EXAMPLES:**
❌ "What is mentioned about accuracy?" (vague, has reference)
❌ "What does the document say about ResNet?" (refers to "document")
❌ "What is shown in the table?" (refers to visual element)
❌ "What is the value?" (no context)

**TASK:**
Analyze the provided document content and generate 5-10 high-quality question-answer pairs that follow all the rules above. Focus on the most important and useful information."""

QAC_USER_PROMPT_TEMPLATE = """Analyze the following document content and generate question-answer pairs:

<DOCUMENT_CONTENT>
{content}
</DOCUMENT_CONTENT>

Generate 5-10 self-contained question-answer pairs covering the key information, facts, and concepts from this content.

Return ONLY a valid JSON array (no markdown, no code blocks):
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]"""


@singleton
class QACAgent(BaseAgent):
    """Agent responsible for generating question-answer pairs from document content."""

    def __init__(
        self,
        provider: SupportedLLMProviders = "nxchat",
        config: LLMModelConfigs | None = None,
    ):
        super().__init__(provider, config)
        logger.info("QAC Agent initialized successfully.")

    def _truncate_text(self, text: str, max_tokens: int = 5000) -> str:
        """
        Truncate text to approximately max_tokens using tiktoken tokenizer.

        Args:
            text: Full text to truncate
            max_tokens: Maximum number of tokens to keep (default: 5000)

        Returns:
            Truncated text
        """
        try:
            tokens = self.tokenizer.encode(text)
            if len(tokens) <= max_tokens:
                return text

            truncated_tokens = tokens[:max_tokens]
            truncated_text = self.tokenizer.decode(truncated_tokens)
            logger.info(
                f"Truncated text from {len(tokens)} to {len(truncated_tokens)} tokens"
            )
            return truncated_text

        except Exception as e:
            logger.warning(
                f"Error truncating text: {repr(e)}. Using character-based truncation."
            )
            max_chars = max_tokens * 4
            return text[:max_chars]

    def _parse_qa_response(self, response_text: str) -> list[dict[str, str]]:
        """
        Parse LLM response into list of Q/A pairs.

        Args:
            response_text: Raw response from LLM

        Returns:
            List of {"question": "...", "answer": "..."} dicts
        """
        try:
            response_text = response_text.strip()

            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                )

            parsed = json.loads(response_text)

            if isinstance(parsed, list):
                return parsed
            elif isinstance(parsed, dict):
                return [parsed]
            else:
                logger.warning(f"Unexpected JSON structure: {type(parsed)}")
                return []

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {repr(e)}")
            return []
        except Exception as e:
            logger.error(f"Error parsing Q/A response: {repr(e)}")
            return []

    async def ainvoke(
        self, full_text: str, max_tokens: int = 5000
    ) -> list[tuple[str, str]]:
        """
        Generate question-answer pairs from document content.

        Args:
            full_text: Full document content
            max_tokens: Maximum tokens to process (default: 5000)

        Returns:
            List of (question, answer) tuples
        """
        try:
            truncated_text = self._truncate_text(full_text, max_tokens)

            if not truncated_text.strip():
                logger.warning("Empty text after truncation")
                return []

            system_message = SystemMessage(content=QAC_SYSTEM_PROMPT)
            user_message = HumanMessage(
                content=QAC_USER_PROMPT_TEMPLATE.format(content=truncated_text)
            )

            response = await self.simple_llm_call(
                [system_message, user_message], error_context="QACAgent"
            )

            if not response.content:
                logger.warning("Empty response from LLM")
                return []

            qa_list = self._parse_qa_response(response.content)

            unique_qa_pairs = []
            seen_questions = set()

            for qa_dict in qa_list:
                question = qa_dict.get("question", "").strip()
                answer = qa_dict.get("answer", "").strip()

                if not question or not answer:
                    continue

                if len(question) < 10 or len(answer) < 5:
                    continue

                if question.lower() not in seen_questions:
                    unique_qa_pairs.append((question, answer))
                    seen_questions.add(question.lower())

            logger.info(f"Generated {len(unique_qa_pairs)} unique Q/A pairs")
            return unique_qa_pairs

        except Exception as e:
            logger.exception(f"Error generating Q/A pairs: {repr(e)}")
            return []
