
import io
from minio_config import minio_client

from config import settings
MINIO_BUCKET = settings.MINIO_BUCKET
MINIO_BUSINESSES_FOLDER_JPEG = settings.MINIO_BUSINESSES_FOLDER_JPEG
MINIO_BUSINESSES_FOLDER_WEBP = settings.MINIO_BUSINESSES_FOLDER_WEBP
MINIO_PRODUCTS_FOLDER_JPEG = settings.MINIO_PRODUCTS_FOLDER_JPEG
MINIO_PRODUCTS_FOLDER_WEBP = settings.MINIO_PRODUCTS_FOLDER_WEBP


from logger_config import get_logger
logger = get_logger(__name__)


from PIL import Image, UnidentifiedImageError
import io
from fastapi import UploadFile
from minio.error import S3Error
from starlette.concurrency import run_in_threadpool


import httpx

from starlette.datastructures import UploadFile as StarletteUploadFile
import io


ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
}


async def save_uploaded_image(
    avatar: UploadFile | None,
    filename: str,
    jpeg_path: str,
    webp_path: str
) -> dict:

    if not avatar:
        return {"status": False, "message": "Image file not provided"}

    if not filename:
        return {"status": False, "message": "Filename not provided"}

    if avatar.content_type not in ALLOWED_IMAGE_TYPES:
        return {
            "status": False,
            "message": f"Unsupported image type: {avatar.content_type}"
        }

    try:
        file_bytes = await avatar.read()

        # ==================================================
        # JPEG
        # ==================================================
        if avatar.content_type in ("image/jpeg", "image/jpg"):
            # сохраняем как есть
            jpeg_stream = io.BytesIO(file_bytes)

        else:
            # перекодируем в JPEG
            image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
            jpeg_stream = io.BytesIO()
            image.save(jpeg_stream, format="JPEG", quality=90, optimize=True)
            jpeg_stream.seek(0)

        await run_in_threadpool(
            minio_client.put_object,
            MINIO_BUCKET,
            jpeg_path,
            jpeg_stream,
            length=jpeg_stream.getbuffer().nbytes,
            content_type="image/jpeg"
        )

    except S3Error as e:
        logger.error(f"save_uploaded_image - MinIO error while saving JPEG: {e}")
        return {"status": False, "message": "Storage error while saving JPEG"}

    except Exception as e:
        logger.exception(e)
        return {"status": False, "message": "Error processing image"}

    # ==================================================
    # WebP (всегда перекодируем)
    # ==================================================
    try:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        webp_stream = io.BytesIO()
        image.save(webp_stream, format="WEBP", quality=85, method=6)
        webp_stream.seek(0)

        await run_in_threadpool(
            minio_client.put_object,
            MINIO_BUCKET,
            webp_path,
            webp_stream,
            length=webp_stream.getbuffer().nbytes,
            content_type="image/webp"
        )

    except Exception as e:
        logger.warning(f"Failed to create WebP for {filename}: {e}")
        webp_path = None

    return {
        "status": True,
        "jpeg_path": jpeg_path,
        "webp_path": webp_path
    }



async def save_uploaded_jpeg_business(avatar: UploadFile | None, filename: str) -> dict:
    jpeg_path = f"{MINIO_BUSINESSES_FOLDER_JPEG}/{filename}.jpeg"
    webp_path = f"{MINIO_BUSINESSES_FOLDER_WEBP}/{filename}.webp"
    result = await save_uploaded_image(avatar=avatar, filename=filename, jpeg_path=jpeg_path, webp_path=webp_path)
    return result


async def save_uploaded_jpeg_product(avatar: UploadFile | None, filename: str) -> dict:
    jpeg_path = f"{MINIO_PRODUCTS_FOLDER_JPEG}/{filename}.jpeg"
    webp_path = f"{MINIO_PRODUCTS_FOLDER_WEBP}/{filename}.webp"
    result = await save_uploaded_image(avatar=avatar, filename=filename, jpeg_path=jpeg_path, webp_path=webp_path)
    return result


async def get_avatar_from_telegram(avatar_url: str) -> dict:
    try:
        logger.info(f"get_avatar_from_telegram - trying to download file: {avatar_url}", user_id=0)
        # ===============================
        # Скачиваем файл
        # ===============================
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            response = await client.get(avatar_url, headers={"User-Agent": "Mozilla/5.0"})

        if response.status_code != 200:
            logger.warning("get_avatar_from_telegram - bad status", user_id=0)
            return {"status": False}

        file_bytes = response.content

        # ===============================
        # Пробуем открыть через PIL
        # ===============================
        try:
            image = await run_in_threadpool(
                lambda: Image.open(io.BytesIO(file_bytes)).convert("RGB")
            )
        except UnidentifiedImageError:
            logger.warning("get_avatar_from_telegram - cannot identify image", user_id=0)
            return {"status": False}

        # ===============================
        # Масштабирование до 800x800
        # ===============================
        target_size = 800
        width, height = image.size

        scale = target_size / min(width, height)
        new_width = int(width * scale)
        new_height = int(height * scale)

        image = await run_in_threadpool(
            lambda: image.resize((new_width, new_height), Image.LANCZOS)
        )

        # Центрированная обрезка
        left = (new_width - target_size) // 2
        top = (new_height - target_size) // 2
        right = left + target_size
        bottom = top + target_size

        image = await run_in_threadpool(
            lambda: image.crop((left, top, right, bottom))
        )

        # ===============================
        # Сохраняем в JPEG
        # ===============================
        output_stream = io.BytesIO()
        await run_in_threadpool(
            lambda: image.save(output_stream, format="JPEG", quality=90, optimize=True)
        )
        output_stream.seek(0)

        upload_file = StarletteUploadFile(
            filename="telegram_avatar.jpeg",
            file=output_stream,
            headers={"content-type": "image/jpeg"}
        )

        return {"status": True, "avatar_file": upload_file}

    except Exception as e:
        logger.exception(f"get_avatar_from_telegram error: {e}")
        return {"status": False}


