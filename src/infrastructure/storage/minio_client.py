# src/infrastructure/storage/minio_client.py
import asyncio
from datetime import timedelta
import os

from minio.error import S3Error
from miniopy_async import Minio

from src.utils.decorators import singleton
from src.utils.logger_conf import logger


@singleton
class MinioClient:
    """
    A client for interacting with the MinIO object storage service.
    """

    def __init__(
        self, endpoint: str, access_key: str, secret_key: str, secure: bool = True
    ):
        """
        Initialize MinioClient with connection parameters.

        Args:
            endpoint: MinIO service endpoint
            access_key: MinIO access key
            secret_key: MinIO secret key
            secure: Whether to use HTTPS (default: True)
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    async def file_exists(self, bucket_name: str, object_name: str) -> bool:
        """
        Check if a file exists in MinIO.

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object in the bucket

        Returns:
            True if the file exists, False otherwise
        """
        try:
            return await self.client.stat_object(bucket_name, object_name) is not None
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            logger.exception(f"Error checking file existence: {str(e)}")
            raise

    async def _retry_upload(
        self, upload_func, max_retries: int = 3, delay: float = 1.0
    ):
        """
        Retry upload with exponential backoff.

        Args:
            upload_func: The upload function to retry
            max_retries: Maximum number of retry attempts
            delay: Initial delay between retries in seconds
        """
        for attempt in range(max_retries + 1):
            try:
                return await upload_func()
            except S3Error as e:
                if e.code == "XAmzContentSHA256Mismatch" and attempt < max_retries:
                    wait_time = delay * (2**attempt)
                    logger.warning(
                        f"Upload attempt {attempt + 1} failed with SHA256 mismatch. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise
            except Exception as e:
                if attempt < max_retries and "SHA256" in str(e):
                    wait_time = delay * (2**attempt)
                    logger.warning(
                        f"Upload attempt {attempt + 1} failed. Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    raise

    async def get_file(self, bucket_name: str, object_name: str, file_path: str):
        """
        Download a file from MinIO.

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object in the bucket
            file_path: Path where to save the downloaded file
        """
        try:
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            await self.client.fget_object(
                bucket_name=bucket_name, object_name=object_name, file_path=file_path
            )
        except Exception as e:
            logger.exception(f"Error downloading file from MinIO: {str(e)}")
            raise

    async def delete_file(self, bucket_name: str, object_name: str):
        """
        Delete a file from MinIO.

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object in the bucket

        Returns:
            None
        """
        try:
            await self.client.remove_object(
                bucket_name=bucket_name, object_name=object_name
            )
        except Exception as e:
            logger.exception(f"Error deleting file from MinIO: {str(e)}")
            raise

    async def upload_file(
        self,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str = "application/octet-stream",
        max_retries: int = 3,
    ) -> None:
        """
        Upload a file to MinIO from a stream/BytesIO object.

        Args:
            bucket_name: Name of the bucket
            object_name: Name to assign to the object in the bucket
            data: File-like object or BytesIO stream
            length: Size of the data in bytes
            content_type: Content type of the file
            max_retries: Maximum number of retry attempts

        Returns:
            MinIO object information
        """
        try:
            if not await self.client.bucket_exists(bucket_name):
                await self.client.make_bucket(bucket_name)

            async def do_upload():
                if hasattr(data, "seek"):
                    data.seek(0)

                return await self.client.put_object(
                    bucket_name=bucket_name,
                    object_name=object_name,
                    data=data,
                    length=length,
                    content_type=content_type,
                )

            return await self._retry_upload(do_upload, max_retries)

        except Exception as e:
            logger.exception(
                f"Error uploading stream to MinIO after {max_retries} retries: {str(e)}"
            )
            raise

    async def get_presigned_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=10),
    ) -> str:
        """
        Create a presigned URL for accessing an object in MinIO.

        Args:
            bucket_name: Name of the bucket
            object_name: Name of the object in the bucket
            expires_in: Expiration time in seconds (default: 7200)

        Returns:
            Presigned URL as a string
        """
        try:
            return await self.client.presigned_get_object(
                bucket_name=bucket_name, object_name=object_name, expires=expires
            )
        except Exception as e:
            logger.exception(f"Error creating presigned URL: {str(e)}")
            raise
