import json

from langchain_core.messages import HumanMessage, SystemMessage

from src.agents.basic.base import BaseAgent
from src.core.config.llm_config import LLMModelConfigs, SupportedLLMProviders
from src.utils.decorators import singleton
from src.utils.logger_conf import logger

QAC_SYSTEM_PROMPT = """You are an expert at creating high-quality question-answer pairs for evaluating RAG (Retrieval-Augmented Generation) systems.

**CORE PRINCIPLE:** Quality over quantity. Generate ONLY meaningful Q/A pairs from content with substantial information. If the content is trivial, blank, or lacks meaningful information, return an empty array.

**CONTENT FILTERING (CRITICAL):**
Skip generation entirely if the content is:
- Blank, empty, or placeholder text
- Generic metadata without substance (e.g., "This is a mixed content type")
- Navigation elements, headers, footers only
- Repetitive or meaningless information
- Image descriptions that say "no visible content" or "blank image"

**QUESTION REQUIREMENTS:**

1. **Self-Contained & Specific**
   - NEVER use references: "the document", "the text", "the image", "above", "mentioned", "described", "shown"
   - Include ALL context: specific names, terms, technologies, numbers, dates, domains
   - Question must be answerable independently without seeing the source

2. **Meaningful & Testable**
   - Ask about substantive information: facts, concepts, processes, relationships, technical details
   - Avoid meta-questions about the document itself
   - Should test real knowledge retrieval and understanding

**ANSWER REQUIREMENTS (CRITICAL FOR EVALUATION):**

1. **Comprehensive & Complete**
   - Provide FULL context and supporting details
   - Include relevant numbers, dates, names, qualifications
   - Explain WHY and HOW, not just WHAT
   - Length: 2-5 sentences typically (enough for judge to evaluate accurately)

2. **Self-Sufficient**
   - Answer should contain enough information that a judge can verify correctness
   - Include background context that makes the answer meaningful
   - Don't assume the judge has seen the original content

**COMPARISON:**

❌ SHORT, INADEQUATE ANSWER:
Q: "What accuracy did ResNet-50 achieve on ImageNet?"
A: "76.5% accuracy."
→ Judge cannot verify if this is complete or contextualized correctly

✅ FULL, COMPREHENSIVE ANSWER:
Q: "What accuracy did ResNet-50 achieve on ImageNet in 2015?"
A: "ResNet-50 achieved 76.5% top-5 accuracy on the ImageNet classification dataset when it was introduced in 2015. This performance significantly outperformed previous state-of-the-art architectures at the time, marking a breakthrough in deep learning by demonstrating that residual connections could enable training of much deeper networks."
→ Judge has full context to evaluate

**EXAMPLES:**

Content: "Transformer architecture introduced in 'Attention Is All You Need' (2017) uses self-attention mechanisms instead of recurrence. The base model has 65M parameters with 6 encoder and 6 decoder layers. It achieved 28.4 BLEU on WMT English-to-German translation, training in 3.5 days on 8 P100 GPUs."

✅ EXCELLENT PAIR:
{
  "question": "What BLEU score did the base Transformer model achieve on WMT English-to-German translation, and how long did training take?",
  "answer": "The base Transformer model achieved 28.4 BLEU score on the WMT English-to-German translation task. The model was trained for 3.5 days using 8 P100 GPUs. This was introduced in the 'Attention Is All You Need' paper (2017), where the Transformer architecture demonstrated that self-attention mechanisms alone, without recurrence, could achieve state-of-the-art translation performance. The base model contained 65 million parameters with 6 encoder layers and 6 decoder layers."
}

❌ INADEQUATE PAIR (TOO SHORT):
{
  "question": "What is the BLEU score?",
  "answer": "28.4 BLEU"
}

❌ MEANINGLESS CONTENT - RETURN EMPTY:
Content: "This image appears blank with no visible content. Content type: Mixed."
→ Return: []

**OUTPUT FORMAT:**
Return ONLY valid JSON array (no markdown, no code blocks, no explanations):
- If content is meaningful: [{"question": "...", "answer": "..."}, ...]
- If content lacks substance: []

Generate 1-3 pairs maximum. Focus on the most important, testable information."""

QAC_USER_PROMPT_TEMPLATE = """Analyze this content and decide if it contains substantial, meaningful information worth testing:

<CONTENT>
{content}
</CONTENT>

**INSTRUCTIONS:**
1. First, assess if this content has meaningful information (not blank, not just metadata, not trivial)
2. If NO meaningful content → return empty array: []
3. If YES → generate 1-3 high-quality Q/A pairs with comprehensive answers

Generate questions that are self-contained and specific. Write answers that are detailed (2-5 sentences) with full context so a judge can accurately evaluate responses.

Return ONLY valid JSON (no markdown, no explanations):
[
  {{"question": "...", "answer": "..."}},
  {{"question": "...", "answer": "..."}}
]

Or if no meaningful content:
[]"""


@singleton
class QACAgent(BaseAgent):
    """Agent for generating high-quality question-answer pairs for RAG evaluation."""

    def __init__(
        self,
        provider: SupportedLLMProviders = "nxchat",
        config: LLMModelConfigs | None = None,
    ):
        super().__init__(provider, config)
        logger.info("QAC Agent initialized for RAG evaluation (quality-focused).")

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

    def _validate_qa_quality(self, question: str, answer: str) -> bool:
        """
        Validate Q/A pair quality based on length and content.

        Args:
            question: Question text
            answer: Answer text

        Returns:
            True if pair meets quality standards
        """
        # Minimum length requirements
        if len(question) < 20 or len(answer) < 50:
            return False

        # Check for meta-references (questions about "the document" itself)
        forbidden_phrases = [
            "the document",
            "the text",
            "the image",
            "the table",
            "the content",
            "mentioned above",
            "shown above",
            "described in",
            "provided in",
            "this document",
        ]

        q_lower = question.lower()
        for phrase in forbidden_phrases:
            if phrase in q_lower:
                logger.debug(
                    f"Question contains forbidden phrase '{phrase}': {question[:50]}..."
                )
                return False

        # Answer should be substantial (multiple words, ideally multiple sentences)
        word_count = len(answer.split())
        if word_count < 15:  # Answers should be at least 15 words for good evaluation
            logger.debug(f"Answer too short ({word_count} words): {answer[:50]}...")
            return False

        return True

    def _parse_qa_response(self, response_text: str) -> list[dict[str, str]]:
        """
        Parse LLM response into list of Q/A pairs with strict validation.

        Args:
            response_text: Raw response from LLM

        Returns:
            List of {"question": "...", "answer": "..."} dicts
        """
        try:
            response_text = response_text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(
                    line for line in lines if not line.strip().startswith("```")
                )

            parsed = json.loads(response_text)

            # Handle empty array (no meaningful content)
            if isinstance(parsed, list) and len(parsed) == 0:
                logger.info("LLM returned empty array - no meaningful content detected")
                return []

            if isinstance(parsed, list):
                qa_list = parsed
            elif isinstance(parsed, dict):
                qa_list = [parsed]
            else:
                logger.warning(f"Unexpected JSON structure: {type(parsed)}")
                return []

            # Strict validation for each Q/A pair
            validated_pairs = []
            for idx, qa in enumerate(qa_list):
                q = qa.get("question", "").strip()
                a = qa.get("answer", "").strip()

                if not q or not a:
                    logger.debug(f"Pair {idx}: Empty question or answer")
                    continue

                if not self._validate_qa_quality(q, a):
                    logger.debug(f"Pair {idx}: Failed quality validation")
                    continue

                validated_pairs.append({"question": q, "answer": a})
                logger.debug(
                    f"Pair {idx}: Validated ✓ (Q: {len(q)} chars, A: {len(a)} chars)"
                )

            return validated_pairs

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse JSON response: {repr(e)}")
            logger.debug(f"Response text: {response_text[:200]}...")
            return []
        except Exception as e:
            logger.error(f"Error parsing Q/A response: {repr(e)}")
            return []

    async def ainvoke(
        self, full_text: str, max_tokens: int = 5000
    ) -> list[tuple[str, str]]:
        """
        Generate high-quality question-answer pairs for RAG evaluation.
        Returns empty list if content is not substantial enough.

        Args:
            full_text: Full document content
            max_tokens: Maximum tokens to process (default: 5000)

        Returns:
            List of (question, answer) tuples. Empty list if no meaningful content.
        """
        try:
            truncated_text = self._truncate_text(full_text, max_tokens)

            if not truncated_text.strip():
                logger.warning("Empty text after truncation")
                return []

            if len(truncated_text) < 50:
                logger.info("Text too short to generate meaningful Q/A pairs")
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

            if not qa_list:
                logger.info(
                    "No Q/A pairs generated - content may lack substance or failed validation"
                )
                return []

            unique_qa_pairs = []
            seen_questions = set()

            for qa_dict in qa_list:
                question = qa_dict["question"]
                answer = qa_dict["answer"]

                q_normalized = question.lower().strip("?!. ")

                if q_normalized not in seen_questions:
                    unique_qa_pairs.append((question, answer))
                    seen_questions.add(q_normalized)
                    logger.info(
                        f"✓ Generated Q/A pair: Q={len(question)} chars, A={len(answer)} chars"
                    )

            logger.info(
                f"Successfully generated {len(unique_qa_pairs)} high-quality Q/A pairs"
            )
            return unique_qa_pairs

        except Exception as e:
            logger.exception(f"Error generating Q/A pairs: {repr(e)}")
            return []
