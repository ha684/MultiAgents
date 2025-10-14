# src/rag/vector/migrations.py
from qdrant_client import AsyncQdrantClient, models
from src.config.settings import settings
from src.utils.logger_conf import logger


class VectorStorageMigration:
    def __init__(self, client: AsyncQdrantClient):
        self.client = client

    async def run_migrations(self):
        """Run all necessary migrations/setup"""
        await self._ensure_collection_exists()
        await self._create_payload_indexes()

    async def _ensure_collection_exists(self):
        if not await self.client.collection_exists(settings.vector_collection_name):
            logger.info(f"Creating collection '{settings.vector_collection_name}'")
            await self.client.create_collection(
                collection_name=settings.vector_collection_name,
                vectors_config={
                    "dense": models.VectorParams(
                        size=settings.embedding_dimensions,
                        distance=models.Distance.COSINE,
                    )
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams(
                        index=models.SparseIndexParams(on_disk=False)
                    )
                },
            )

    async def _create_payload_indexes(self):
        await self.client.create_payload_index(
            collection_name=settings.vector_collection_name,
            field_name="metadata.document_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
        await self.client.create_payload_index(
            collection_name=settings.vector_collection_name,
            field_name="metadata.kb_id",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

        await self.client.create_payload_index(
            collection_name=settings.vector_collection_name,
            field_name="metadata.original_filename",
            field_schema=models.TextIndexParams(
                type=models.TextIndexType.TEXT,
                tokenizer=models.TokenizerType.PREFIX,
                min_token_len=1,
                max_token_len=256,
            ),
        )

        await self.client.create_payload_index(
            collection_name=settings.vector_collection_name,
            field_name="metadata.folder_path",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
