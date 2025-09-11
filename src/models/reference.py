from pydantic import BaseModel, Field
from typing import List


class Citation(BaseModel):
    source_id: int = Field(
        ...,
        description="The integer ID of a SPECIFIC source which justifies the answer.",
    )
    quote: str = Field(
        ...,
        description="The VERBATIM quote from the specified source that justifies the answer.",
    )


class SupportCitation(BaseModel):
    support_citation: List[Citation] = Field(
        ...,
        description="A list of citations that support the answer to the query.",
    )


class CitationIndexes(BaseModel):
    indexes: List[int]


class Reference(BaseModel):
    source_id: str = Field(
        ...,
        description="The integer ID of the source.",
    )
    source_index: int = Field(
        ...,
        description="The index of the source in the list of sources.",
    )
    source: str = Field(
        ...,
        description="The name of the source.",
    )
    quote: str = Field(
        ...,
        description="The verbatim quote from the source that supports the answer.",
    )
    page_content: str = Field(
        ...,
        description="The content of the source, which may include text, images, or other media.",
    )
