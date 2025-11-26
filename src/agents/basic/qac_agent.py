import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.core.config.llm_config import LLMModelConfigs, SupportedLLMProviders
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

QAC_SYSTEM_PROMPT = """You are an expert at creating high-quality question-answer pairs for evaluating Retrieval-Augmented Generation (RAG) systems using RAGAS metrics.

**OBJECTIVE:**
Generate 3-7 diverse, self-contained question-answer pairs that test different aspects of RAG performance: factual recall, reasoning, specificity, and comprehension.

**CRITICAL RULES FOR QUESTIONS:**

1. **Complete Self-Containment (MANDATORY)**
   - NEVER use: "the document", "the text", "above", "below", "mentioned", "described", "provided", "shown", "following", "preceding"
   - NEVER refer to: "the table", "the chart", "the figure", "the image", "the diagram", "the list"
   - Questions must be answerable without any reference to the source document
   - Include ALL necessary context: names, terms, domains, timeframes, quantities

2. **High Specificity**
   - Always include: specific entities (proper nouns), technical terms, numerical values, dates, locations
   - Be precise about what you're asking
   
   ❌ BAD: "What is the main advantage?"
   ✅ GOOD: "What is the main advantage of using ResNet's residual connections in deep neural networks?"
   
   ❌ BAD: "What are the key findings?"
   ✅ GOOD: "What accuracy improvements did BERT achieve over ELMo on the GLUE benchmark?"

3. **Question Diversity**
   Generate different types to test RAG capabilities:
   - **Factual**: Direct fact retrieval (numbers, dates, definitions)
   - **Conceptual**: Understanding of concepts, processes, relationships
   - **Comparative**: Comparing methods, approaches, results
   - **Analytical**: Why/how questions requiring reasoning
   - **Specific Detail**: Granular technical details

4. **Answer Quality**
   - Answers must be directly extractable from the content
   - Be precise and complete, including numbers, units, and qualifiers
   - Include relevant context that makes the answer meaningful
   - Length: 1-4 sentences (concise but comprehensive)

5. **Quality Filters**
   - Skip vague, generic, or trivial questions
   - Avoid yes/no questions unless they're meaningful
   - No redundant questions on the same fact
   - Focus on information that matters for understanding the content

**EXAMPLES OF EXCELLENT Q/A PAIRS:**

Content: "BERT (Bidirectional Encoder Representations from Transformers) achieved state-of-the-art results on 11 NLP tasks in 2018. On the SQuAD v1.1 question answering dataset, BERT-Large obtained an F1 score of 93.2, surpassing the previous best system by 1.5 points. The model uses masked language modeling to pre-train on unlabeled text."

✅ EXCELLENT Pairs:
1. {
   "question": "What F1 score did BERT-Large achieve on the SQuAD v1.1 question answering dataset?",
   "answer": "BERT-Large achieved an F1 score of 93.2 on the SQuAD v1.1 dataset."
}

2. {
   "question": "By how many points did BERT-Large surpass the previous best system on SQuAD v1.1?",
   "answer": "BERT-Large surpassed the previous best system by 1.5 points on SQuAD v1.1."
}

3. {
   "question": "What pre-training technique does BERT use to learn from unlabeled text?",
   "answer": "BERT uses masked language modeling to pre-train on unlabeled text."
}

4. {
   "question": "How many NLP tasks did BERT achieve state-of-the-art results on in 2018?",
   "answer": "BERT achieved state-of-the-art results on 11 NLP tasks in 2018."
}

❌ BAD Examples (DO NOT GENERATE):
- "What does the document say about BERT?" (refers to "document")
- "What is the model mentioned?" (vague, no context)
- "What are the results?" (too generic)
- "What is shown in the table above?" (refers to visual element)
- "What is the main finding?" (lacks specificity)

**OUTPUT FORMAT:**
Return ONLY a valid JSON array (no markdown, no explanations, no code blocks):
[
  {"question": "...", "answer": "..."},
  {"question": "...", "answer": "..."}
]

**TASK:**
Analyze the document content carefully and generate 1-5 high-quality, diverse question-answer pairs that would be ideal for evaluating a RAG system's retrieval and generation capabilities."""

QAC_USER_PROMPT_TEMPLATE = """Document content to analyze:

<CONTENT>
{content}
</CONTENT>

Generate 1-5 self-contained, specific question-answer pairs covering the most important information. Ensure diversity in question types (factual, conceptual, comparative, analytical).

Return ONLY valid JSON (no markdown, no code blocks):
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]"""


@singleton
class QACAgent(BaseAgent):
    """Agent for generating question-answer pairs for RAG evaluation using RAGAS."""

    def __init__(
        self,
        provider: SupportedLLMProviders = "nxchat",
        config: LLMModelConfigs | None = None,
    ):
        super().__init__(provider, config)
        logger.info("QAC Agent initialized for RAG evaluation.")

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
        Parse LLM response into list of Q/A pairs with validation.

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
                qa_list = parsed
            elif isinstance(parsed, dict):
                qa_list = [parsed]
            else:
                logger.warning(f"Unexpected JSON structure: {type(parsed)}")
                return []

            validated_pairs = []
            for qa in qa_list:
                q = qa.get("question", "").strip()
                a = qa.get("answer", "").strip()

                if q and a and len(q) > 10 and len(a) > 10:
                    validated_pairs.append({"question": q, "answer": a})

            return validated_pairs

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {repr(e)}")
            logger.debug(f"Response text: {response_text[:200]}...")
            return []
        except Exception as e:
            logger.error(f"Error parsing Q/A response: {repr(e)}")
            return []

    async def ainvoke(
        self, full_text: str, max_tokens: int = 8192
    ) -> list[tuple[str, str]]:
        """
        Generate question-answer pairs for RAG evaluation.

        Args:
            full_text: Full document content
            max_tokens: Maximum tokens to process (default: 5000)

        Returns:
            List of (question, answer) tuples suitable for RAGAS evaluation
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

                q_normalized = question.lower().strip("?!. ")

                if q_normalized not in seen_questions:
                    unique_qa_pairs.append((question, answer))
                    seen_questions.add(q_normalized)

            logger.info(
                f"Generated {len(unique_qa_pairs)} unique Q/A pairs for RAG evaluation"
            )
            return unique_qa_pairs

        except Exception as e:
            logger.exception(f"Error generating Q/A pairs: {repr(e)}")
            return []
