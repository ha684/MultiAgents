from pydantic import BaseModel, Field
from typing import Optional


class SearchFileName(BaseModel):
    """Call this tool to search for a file by name. This tool will search for files using ILIKE %{query}% inside a database."""

    key: str = Field(
        description="The keywords to search for in the file name.",
    )


class QueryChunks(BaseModel):
    """
    Call this tool to query chunks from a vector database.
    If file_name is provided, it will filter chunks from that file.
    So if you need content from a specific file, provide its name and call this tool.
    """

    file_name: Optional[str] = Field(
        description="(Optional) The name of the file to get chunks from. Should be a single file name",
    )

    query: str = Field(
        description="The query to search for in the vector database, which will be used to retrieve relevant chunks. The retrieval will be based on hybrid search, which combines semantic and keyword search.",
    )


class ResearchCompleted(BaseModel):
    """Call this tool to indicate that the research is complete."""


class ConductResearch(BaseModel):
    """Call this tool to conduct research on a specific topic."""

    research_topic: str = Field(
        description="The topic to research. Should be a single topic, and should be described in high detail.",
    )
