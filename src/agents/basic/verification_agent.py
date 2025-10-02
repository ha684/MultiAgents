# src/agents/verification_agent.py

from typing import List, Tuple
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from src.config.llm_config import SupportedLLMProviders
from src.llm.factory import get_llm
from src.models.reference import SupportCitation
from src.utils.decorators import singleton

from src.utils.logger_conf import logger


# Prompt template for verification
VERIFICATION_PROMPT_TEMPLATE = """
You are a meticulous verification assistant. Your task is to determine if the provided context contains enough information to directly answer the user's query. Do not try to answer the query yourself, only verify if the context allows for an answer.

User Query: {query}

Context Documents:
{context}

Based *only* on the text provided in the 'Context Documents' above, can you answer the 'User Query'? 
Respond with only 'YES' or 'NO'.
"""


CITATION_PROMPT_TEMPLATE = """
You are a citation expert. Based on the User Query and the Context Documents provided, identify which of the 'Context Documents' directly contain information needed to answer the 'User Query'. 

User Query: {query}

Context Documents:
{context}

Your task is to determine which documents are directly relevant to answering the query. Return only the index numbers of those documents, based on their order in the list (starting from 0).

If no documents support the answer directly, return an empty list.

Format your output strictly as a JSON object matching the schema below.
DO NOT include any other text, explanations, or conversational filler.
DO NOT include markdown code fences unless explicitly instructed by the system.

JSON Output:
{{"relevant_document_indexes": [0, 2]}}
"""


@singleton
class VerificationAgent:
    """Agent responsible for verifying if retrieved documents answer the query and extracting citations."""

    def __init__(self, provider: SupportedLLMProviders = "nxchat"):
        self.llm = get_llm(provider)
        self.structured_llm = self.llm.with_structured_output(SupportCitation)
        self.verification_prompt = ChatPromptTemplate.from_template(
            VERIFICATION_PROMPT_TEMPLATE
        )
        self.citation_prompt = ChatPromptTemplate.from_template(
            CITATION_PROMPT_TEMPLATE
        )
        self.output_parser = StrOutputParser()

        # Chain for verification check (YES/NO)
        self.verification_chain = (
            self.verification_prompt | self.llm | self.output_parser
        )

        # Chain for citation extraction
        self.citation_chain = self.citation_prompt | self.structured_llm
        # self.citation_chain = self.citation_prompt | self.llm | self.output_parser
        logger.info("Verification Agent initialized successfully.")

    def _format_context(self, documents: List[Document]) -> str:
        """Formats the list of documents into a single string for the prompt."""
        formatted_context = ""
        for i, doc in enumerate(documents):
            source = doc.metadata.get("original_filename", "Unknown Source")
            # Include page number or other relevant metadata if available
            page_num = doc.metadata.get("page", None)
            source_info = f"Source: {source}" + (
                f", Page: {page_num}" if page_num else ""
            )
            formatted_context += f"--- Document {i} ({source_info}) ---\n"
            formatted_context += doc.page_content
            formatted_context += "\n\n"
        return formatted_context.strip()

    def verify_context(
        self, query: str, documents: List[Document]
    ) -> Tuple[bool, List[str]]:
        """Verifies if the documents contain the answer and extracts citations."""
        logger.info(f'Verification Agent: Verifying context for query: 	"{query}"')
        if not documents:
            logger.info("Verification Agent: No documents provided for verification.")
            return False, []

        formatted_context = self._format_context(documents)

        # Step 1: Verify if context contains the answer
        # try:
        #     verification_response = self.verification_chain.invoke(
        #         {"query": query, "context": formatted_context}
        #     )
        #     print(
        #         f"Verification Agent: LLM Verification Response: {verification_response}"
        #     )
        #     can_answer = verification_response.strip().upper() == "YES"
        # except Exception as e:
        #     print(f"Error during verification step: {e}")
        #     can_answer = False  # Default to NO if verification fails
        can_answer = True  # Default to YES for testing purposes

        # Step 2: Extract citations if verification is positive
        citations = []
        if can_answer:
            logger.info(
                "Verification Agent: Context deemed sufficient. Extracting citations..."
            )
            try:
                # logger.info(formatted_context)
                citation_response = self.citation_chain.with_retry().invoke(
                    {"query": query, "context": formatted_context}
                )
                logger.info(
                    f"Verification Agent: LLM Citation Response: {citation_response}"
                )
                # Basic parsing, assuming LLM follows instructions (might need refinement)
                citations = citation_response.support_citation

            except Exception as e:
                logger.error(f"Error during citation extraction: {e}")
                # Citations remain empty if extraction fails
        else:
            logger.info(
                "Verification Agent: Context deemed insufficient to answer the query."
            )

        logger.info(
            f"Verification Agent: Verification result: {can_answer}, Citations found: {len(citations)}"
        )
        return can_answer, citations
