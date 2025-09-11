import numpy as np
import torch
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any
from collections import defaultdict
from ...embeding.api_inference import InferenceAPIEmbeddings
from tiktoken import get_encoding

class SemanticChunker:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        api_url: str,
        max_tokens=2048,
        cluster_threshold=0.5,
    ):
        self.model = InferenceAPIEmbeddings(
            api_key=api_key,
            model_name=model_name,
            api_url=api_url,
        )
        self.max_tokens = max_tokens
        self.cluster_threshold = cluster_threshold
        self.tokenizer = get_encoding("cl100k_base")

    def get_embeddings(self, chunks: List[Dict[str, Any]]):
        if not chunks:
            return np.array([])
        texts = [chunk["text"] for chunk in chunks]
        return np.array(self.model.embed_documents(texts))

    def compute_similarity(self, embeddings):
        if embeddings.size == 0:
            return np.zeros((0, 0))
        return cosine_similarity(embeddings)

    def cluster_chunks(self, similarity_matrix, threshold=0.5):
        n = similarity_matrix.shape[0]
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x, y):
            parent[find(x)] = find(y)

        for i in range(n):
            for j in range(i + 1, n):
                if similarity_matrix[i, j] >= threshold:
                    union(i, j)

        clusters = [find(i) for i in range(n)]
        cluster_map = {cid: idx for idx, cid in enumerate(sorted(set(clusters)))}
        return [cluster_map[c] for c in clusters]

    def merge_chunks(self, chunks: List[Dict[str, Any]], clusters: List[int]) -> List[Dict[str, Any]]:
        if not chunks or not clusters:
            return []

        cluster_map = defaultdict(list)
        for idx, cluster_id in enumerate(clusters):
            cluster_map[cluster_id].append(chunks[idx])

        merged_chunks = []
        for chunk_list in cluster_map.values():
            current_text = ""
            current_meta = []

            for chunk in chunk_list:
                next_text = (current_text + " " + chunk["text"]).strip()
                if self.tokenizer:
                    num_tokens = len(self.tokenizer.encode(next_text))
                else:
                    num_tokens = len(next_text.split())

                if num_tokens > self.max_tokens and current_text:
                    merged_chunks.append({
                        "text": current_text,
                        "metadata": current_meta
                    })
                    current_text = chunk["text"]
                    current_meta = [chunk]
                else:
                    current_text = next_text
                    current_meta.append(chunk)

            if current_text:
                merged_chunks.append({
                    "text": current_text,
                    "metadata": current_meta
                })

        return merged_chunks

    def chunk(self, chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        embeddings = self.get_embeddings(chunks)
        similarity_matrix = self.compute_similarity(embeddings)
        clusters = self.cluster_chunks(similarity_matrix, threshold=self.cluster_threshold)
        return self.merge_chunks(chunks, clusters)
