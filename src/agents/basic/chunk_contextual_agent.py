from typing import List
from src.llm.factory import get_llm
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.documents import Document
from src.utils.logger_conf import logger

CHUNK_CONTEXTUAL_PROMPT = """You are an expert at understanding document structure and meaning. Your task is to provide contextual information that will help this specific chunk be found when someone searches for its content.

<task>
You will receive surrounding chunks from a document and a target chunk. You must deeply understand what this target chunk means within the broader document context, then generate a concise contextual description that captures its essential meaning and purpose.
</task>

<input_format>
You will receive:
- Chunks that come BEFORE the target chunk (if any exist)
- Chunks that come AFTER the target chunk (if any exist)  
- The TARGET CHUNK that needs contextualization

The surrounding chunks give you the document's flow, topic, and structure so you can understand exactly what role the target chunk plays.
</input_format>

<core_principle>
The goal is to make someone reading just the contextualized chunk understand EXACTLY what it's about, even without seeing the rest of the document. Think: "If someone found only this chunk in a search, what context would they need to fully understand its meaning and significance?"
</core_principle>

<requirements>
- Provide 50-100 tokens of context (approximately 1-2 sentences)
- Capture the chunk's role, significance, and meaning within the document
- Include specific entities, dates, numbers, or concepts that make the chunk unique
- Use terminology that searchers would actually use in queries
- Make the chunk completely self-explanatory and discoverable
- Focus on MEANING and PURPOSE, not just topic description
</requirements>

<examples>
Example 1:
Context: SEC filing about ACME Corp's Q2 2023 performance, previous quarter revenue was $314 million
Target chunk: "The company's revenue grew by 3% over the previous quarter."
Good context: "This chunk is from ACME Corp's Q2 2023 SEC filing showing revenue growth from $314 million baseline; the previous quarter's revenue was $314 million."

Example 2:
Context: Research paper on neural networks, discussing training challenges, leads into optimization methods
Target chunk: "The backpropagation algorithm calculates gradients by applying the chain rule from output to input layers."
Good context: "Technical explanation of backpropagation gradient calculation mechanism in neural network training, part of optimization methodology discussion."

Example 3:
Context: Medical chart for diabetes patient John Smith, reviewing 3-day hospital stay for blood pressure monitoring
Target chunk: "Day 2 readings: Morning 142/89, Afternoon 138/85, Evening 145/92"
Good context: "Day 2 blood pressure monitoring data for diabetic patient John Smith during 3-day hypertension evaluation showing consistently elevated readings."

Example 4:
Context: Company strategic plan document, discussing market expansion after covering current performance
Target chunk: "We project 25% growth in the Asian markets within 18 months through strategic partnerships."
Good context: "Strategic growth projection for Asian market expansion timeline and methodology, part of company's broader international expansion planning."
</examples>

<instructions>
1. Read ALL surrounding chunks to deeply understand the document's purpose, structure, and flow
2. Identify exactly what role the target chunk plays - is it data, analysis, conclusion, background, methodology, etc.?
3. Determine what specific information makes this chunk unique and searchable
4. Consider what someone searching for this information would need to know to understand its context
5. Write context that makes the chunk completely self-contained and meaningful
6. Output ONLY the contextual description - no explanations or additional commentary
</instructions>

Your context should transform an isolated chunk into a piece of information that anyone can immediately understand and find relevant to their search"""


class ChunkContextualAgent:
    def __init__(self):
        self.llm = get_llm("nxchat")

    def _prepare_batch_messages(
        self,
        chunks: List[Document],
        total_context_chunks: int = 16,
    ) -> List[List[SystemMessage | HumanMessage]]:
        """
        Prepare all messages for batch processing.
        """
        batch_messages = []

        for i, chunk in enumerate(chunks):
            max_before = i
            max_after = len(chunks) - 1 - i

            ideal_before = total_context_chunks // 2
            ideal_after = total_context_chunks - ideal_before

            actual_before = min(ideal_before, max_before)
            actual_after = min(ideal_after, max_after)

            if actual_before < ideal_before and max_after > actual_after:
                compensation = min(
                    ideal_before - actual_before, max_after - actual_after
                )
                actual_after += compensation
            elif actual_after < ideal_after and max_before > actual_before:
                compensation = min(
                    ideal_after - actual_after, max_before - actual_before
                )
                actual_before += compensation

            chunks_before = []
            if actual_before > 0:
                start_before = i - actual_before
                chunks_before = chunks[start_before:i]

            chunks_after = []
            if actual_after > 0:
                end_after = i + actual_after + 1
                chunks_after = chunks[i + 1 : end_after]

            prompt_parts = []
            if chunks_before:
                prompt_parts.append("Chunks that come BEFORE the target chunk:")
                for j, before_chunk in enumerate(chunks_before):
                    prompt_parts.append(f"Before[{j + 1}]: {before_chunk.page_content}")
            else:
                prompt_parts.append(
                    "No chunks before this target chunk (this might be near the beginning of the document)."
                )

            if chunks_after:
                prompt_parts.append("Chunks that come AFTER the target chunk:")
                for j, after_chunk in enumerate(chunks_after):
                    prompt_parts.append(f"After[{j + 1}]: {after_chunk.page_content}")
            else:
                prompt_parts.append(
                    "No chunks after this target chunk (this might be near the end of the document)."
                )

            prompt_parts.append(f"TARGET CHUNK to contextualize:\n{chunk.page_content}")

            system_prompt = SystemMessage(content=CHUNK_CONTEXTUAL_PROMPT)
            user_content = HumanMessage(content="\n\n".join(prompt_parts))
            messages = [system_prompt, user_content]

            batch_messages.append(messages)

        return batch_messages

    async def contextualize_chunks(
        self,
        chunks: List[Document],
        total_context_chunks: int = 16,
        batch_size: int = 10,
    ) -> List[Document]:
        """
        Contextualizes all chunks in batches
        """
        batch_messages = self._prepare_batch_messages(chunks, total_context_chunks)
        logger.info(f"Prepared {len(batch_messages)} messages for batch processing")

        contextualized_chunks = []

        for i in range(0, len(batch_messages), batch_size):
            batch_slice = batch_messages[i : i + batch_size]
            chunk_slice = chunks[i : i + batch_size]

            try:
                batch_responses = await self.llm.abatch(batch_slice)
                logger.info(
                    f"Processed batch {i // batch_size + 1} for file {chunk_slice[0].metadata.get('original_filename', chunk_slice[0].metadata.get('sheet_name', 'unknown'))} with {len(batch_responses)} responses"
                )
            except Exception as e:
                logger.error(
                    f"Error during batch processing for batch {i // batch_size + 1}: {e}"
                )
                contextualized_chunks.extend(chunk_slice)
                continue

            for chunk, response in zip(chunk_slice, batch_responses):
                context = (
                    response.content.strip()
                    if hasattr(response, "content")
                    else str(response).strip()
                )

                if chunk.metadata:
                    page_info = chunk.metadata.get("page", "")
                    total_pages = chunk.metadata.get("total_pages", "")
                    title = chunk.metadata.get("title", "")
                    page_info = (
                        f"Page {page_info + 1} of {total_pages}"
                        if page_info and total_pages
                        else ""
                    )
                    title_info = f"Title: {title}" if title else ""
                else:
                    page_info = ""
                    title_info = ""

                page_content = (
                    f"{page_info}\n{title_info}\n- {context}\n- {chunk.page_content}"
                )

                contextualized_chunks.append(
                    Document(page_content=page_content, metadata=chunk.metadata)
                )

        logger.info(f"Successfully contextualized {len(contextualized_chunks)} chunks")
        return contextualized_chunks
