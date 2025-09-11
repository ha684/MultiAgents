import logging
import re
from typing import Dict, List, Optional, cast
from src.agents.reasoning.prompts import (
    BEGIN_FOLDER_PARAM,
    BEGIN_SEARCH_QUERY,
    BEGIN_SEARCH_RESULT,
    END_FOLDER_PARAM,
    END_SEARCH_RESULT,
    MAX_SEARCH_LIMIT,
    END_SEARCH_QUERY,
    REASON_PROMPT,
    RELEVANT_EXTRACTION_PROMPT,
)
from src.llm.factory import get_llm
from src.rag.vector import vector_retrieval
from langchain_core.documents import Document
from qdrant_client.models import Filter, models

from src.utils import extract_between

logging.basicConfig(level=logging.INFO)


class DeepResearcher:
    def __init__(
        self,
        kb_id: str,
    ):
        self.chat_mdl = get_llm("nxchat")
        self.retrieval = vector_retrieval
        self.kb_id = kb_id

    @classmethod
    def _remove_tags(cls, text: str, start_tag: str, end_tag: str) -> str:
        """General Tag Removal Method"""
        pattern = re.escape(start_tag) + r"(.*?)" + re.escape(end_tag)
        return re.sub(pattern, "", text)

    @staticmethod
    def _remove_query_tags(text: str) -> str:
        """Remove Query Tags"""
        return DeepResearcher._remove_tags(text, BEGIN_SEARCH_QUERY, END_SEARCH_QUERY)

    @staticmethod
    def _remove_result_tags(text: str) -> str:
        """Remove Result Tags"""
        return DeepResearcher._remove_tags(text, BEGIN_SEARCH_RESULT, END_SEARCH_RESULT)

    def _generate_reasoning(self, msg_history, folder_structure=None):
        """Generate reasoning steps"""
        print(f"Generating reasoning with message history: {msg_history}")
        query_think = ""
        if msg_history[-1]["role"] != "user":
            msg_history.append(
                {
                    "role": "user",
                    "content": "Continues reasoning with the new information.\n",
                }
            )
        else:
            msg_history[-1]["content"] += (
                "\n\nContinues reasoning with the new information.\n"
            )

        if folder_structure:
            folder_structure = "\n".join(
                f"{key}: {value}" for key, value in folder_structure.items()
            )
        else:
            folder_structure = "No folder structure provided."

        input = [
            {
                "role": "system",
                "content": REASON_PROMPT.format(folder_structure=folder_structure),
            },
        ] + msg_history

        for ans in self.chat_mdl.stream(input):
            ans = re.sub(r"^.*</think>", "", cast(str, ans.content), flags=re.DOTALL)
            if not ans:
                continue
            query_think += ans
            yield query_think
        return query_think

    def _extract_search_queries(self, query_think, question, step_index):
        """Extract search queries from thinking"""
        queries = extract_between(query_think, BEGIN_SEARCH_QUERY, END_SEARCH_QUERY)
        if not queries and step_index == 0:
            # If this is the first step and no queries are found, use the original question as the query
            queries = [question]
        return queries

    def _extract_folder_param(self, query_think):
        """Extract folder query from thinking"""
        folder_query = extract_between(
            query_think, BEGIN_FOLDER_PARAM, END_FOLDER_PARAM
        )
        if not folder_query:
            return None
        return folder_query[0] if isinstance(folder_query, list) else folder_query

    def _truncate_previous_reasoning(self, all_reasoning_steps):
        """Truncate previous reasoning steps to maintain a reasonable length"""
        truncated_prev_reasoning = ""
        for i, step in enumerate(all_reasoning_steps):
            truncated_prev_reasoning += f"Step {i + 1}: {step}\n\n"

        prev_steps = truncated_prev_reasoning.split("\n\n")
        if len(prev_steps) <= 5:
            truncated_prev_reasoning = "\n\n".join(prev_steps)
        else:
            truncated_prev_reasoning = ""
            for i, step in enumerate(prev_steps):
                if (
                    i == 0
                    or i >= len(prev_steps) - 4
                    or BEGIN_SEARCH_QUERY in step
                    or BEGIN_SEARCH_RESULT in step
                ):
                    truncated_prev_reasoning += step + "\n\n"
                else:
                    if truncated_prev_reasoning[-len("\n\n...\n\n") :] != "\n\n...\n\n":
                        truncated_prev_reasoning += "...\n\n"

        return truncated_prev_reasoning.strip("\n")

    def _retrieve_information(
        self, search_query: str, folder_param: Optional[str] = None
    ) -> List[Document]:
        """Retrieve information from different sources"""
        # 1. Knowledge base retrieval
        kbinfos: List[Document] = []
        try:
            filters: models.Filter = Filter(must=[])
            if folder_param:
                cast(List[models.Condition], filters.must).append(
                    models.FieldCondition(
                        key="metadata.folder_path",
                        match=models.MatchAny(any=[folder_param]),
                    )
                )
            docs = self.retrieval.retrieve(
                kb_id=self.kb_id, query=search_query, top_n=3, filters=filters
            )
            return docs
        except Exception as e:
            logging.error(f"Knowledge base retrieval error: {e}")

        return kbinfos

    def _extract_relevant_info(
        self, truncated_prev_reasoning, search_query, kbinfos: List[Document]
    ):
        """Extract and summarize relevant information"""
        summary_think = ""
        input = [
            {
                "role": "system",
                "content": RELEVANT_EXTRACTION_PROMPT.format(
                    prev_reasoning=truncated_prev_reasoning,
                    search_query=search_query,
                    document="\n======\n".join(
                        doc.page_content for doc in kbinfos if doc.page_content
                    ),
                ),
            },
            {
                "role": "user",
                "content": f'Now you should analyze each web page and find helpful information based on the current search query "{search_query}" and previous reasoning steps.',
            },
        ]
        for ans in self.chat_mdl.stream(
            input,
        ):
            ans = re.sub(r"^.*</think>", "", cast(str, ans.content), flags=re.DOTALL)
            if not ans:
                continue
            summary_think += ans
            yield summary_think

        return summary_think

    def thinking(
        self, question: str, folder_structure: Optional[Dict[str, str]] = None
    ):
        executed_search_queries = []
        msg_history = [{"role": "user", "content": f'Question:"{question}"\n'}]
        all_reasoning_steps = []
        think = "<think>"

        for step_index in range(MAX_SEARCH_LIMIT + 1):
            # Check if the maximum search limit has been reached
            if step_index == MAX_SEARCH_LIMIT - 1:
                summary_think = f"\n{BEGIN_SEARCH_RESULT}\nThe maximum search limit is exceeded. You are not allowed to search.\n{END_SEARCH_RESULT}\n"
                yield {
                    "answer": think + summary_think + "</think>",
                    "reference": {},
                }
                all_reasoning_steps.append(summary_think)
                msg_history.append({"role": "assistant", "content": summary_think})
                print(
                    f"Maximum search limit reached at step {step_index}. Ending search process."
                )
                break

            # Step 1: Generate reasoning
            query_think = ""
            for ans in self._generate_reasoning(msg_history, folder_structure):
                query_think = ans
                yield {
                    "answer": think + self._remove_query_tags(query_think) + "</think>",
                    "reference": {},
                }

            print(f"Generated reasoning for step {step_index}: {query_think}")

            think += self._remove_query_tags(query_think)
            all_reasoning_steps.append(query_think)

            # Step 2: Extract search queries
            queries = self._extract_search_queries(query_think, question, step_index)
            folder_query = self._extract_folder_param(query_think)
            if not queries and step_index > 0:
                print(
                    f"No search queries found for step {step_index}. Ending search process."
                )
                # If not the first step and no queries, end the search process
                break

            # Process each search query
            for search_query in queries:
                logging.info(f"[THINK]Query: {step_index}. {search_query}")
                msg_history.append(
                    {
                        "role": "assistant",
                        "content": f"{BEGIN_SEARCH_QUERY}{search_query}{END_SEARCH_QUERY}",
                    }
                )
                think += f"\n\n> {step_index + 1}. {search_query}\n\n"
                yield {
                    "answer": think + "</think>",
                    "reference": {},
                }

                # Check if the query has already been executed
                if search_query in executed_search_queries:
                    summary_think = f"\n{BEGIN_SEARCH_RESULT}\nYou have searched this query. Please refer to previous results.\n{END_SEARCH_RESULT}\n"
                    yield {
                        "answer": think + summary_think + "</think>",
                        "reference": {},
                    }
                    all_reasoning_steps.append(summary_think)
                    msg_history.append({"role": "user", "content": summary_think})
                    think += summary_think
                    continue

                executed_search_queries.append(search_query)

                # Step 3: Truncate previous reasoning steps
                truncated_prev_reasoning = self._truncate_previous_reasoning(
                    all_reasoning_steps
                )

                # Step 4: Retrieve information
                kbinfos = self._retrieve_information(search_query, folder_query)

                # Step 5: Update chunk information
                # self._update_chunk_info(chunk_info, kbinfos)

                # Step 6: Extract relevant information
                think += "\n\n"
                summary_think = ""
                for ans in self._extract_relevant_info(
                    truncated_prev_reasoning, search_query, kbinfos
                ):
                    summary_think = ans
                    yield {
                        "answer": think
                        + self._remove_result_tags(summary_think)
                        + "</think>",
                        "reference": {},
                    }

                all_reasoning_steps.append(summary_think)
                msg_history.append(
                    {
                        "role": "user",
                        "content": f"\n\n{BEGIN_SEARCH_RESULT}{summary_think}{END_SEARCH_RESULT}\n\n",
                    }
                )
                think += self._remove_result_tags(summary_think)
                logging.info(f"[THINK]Summary: {step_index}. {summary_think}")

        yield think + "</think>"


if __name__ == "__main__":
    # Example usage
    researcher = DeepResearcher(kb_id="4c482abc-a644-4e0e-a864-24289149c7d4")
    res = ""

    sample_folder_structure = {
        "API Reference": "Comprehensive technical documentation of all REST and GraphQL APIs.",
        "Authentication": "Guides and configs for user login, token handling, and OAuth flows.",
        "Deployment & CI": "Instructions and YAML pipelines for CI/CD, staging, and production environments.",
        "Testing Framework": "Details about automated tests, test environments, and QA processes.",
        "Release Process": "Checklists and steps for final release, sign-off, and change approvals.",
        "Monitoring & Alerts": "Describes logging setup, dashboards, error reporting, and system health alerts.",
        "Developer Onboarding": "Resources for new developers: repo setup, code style, environment config.",
        "Product Requirements": "User stories, feature specs, and acceptance criteria.",
        "Data Models": "Schema definitions, ERDs, and relationships between entities.",
        "Meeting Notes": "Weekly sync summaries, decisions made, and team blockers.",
        "User Documentation": "End-user help articles, UI walkthroughs, and troubleshooting tips.",
    }
    for response in researcher.thinking(
        "Tuấn Cùi là ai?", folder_structure=sample_folder_structure
    ):
        res = response

    print(f"RESULT:{res}")
