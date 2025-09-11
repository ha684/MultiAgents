from langchain_core.documents import Document
from .core import SemanticChunker

class SemanticChunkerSplitter:
    def __init__(
        self, 
        api_key: str, 
        model_name: str, 
        api_url: str, 
        cluster_threshold: float = 0.4, 
        max_tokens: int = 512,  
    ):
        self._chunker = SemanticChunker(
            api_key=api_key,
            model_name=model_name,
            api_url=api_url,
            cluster_threshold=cluster_threshold,
            max_tokens=max_tokens,
        )

    def split_documents(self, documents: list[Document]) -> list[Document]:
        texts = [{"text": doc.page_content, "metadata": doc.metadata} for doc in documents]
        chunks = self._chunker.chunk(texts)

        return [
            Document(
                page_content=chunk["text"],
                metadata={"source_chunks": chunk.get("metadata", [])}

            )
            for chunk in chunks
        ]
