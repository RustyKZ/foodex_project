from config import settings
MINIO_STORAGE_URL = settings.MINIO_STORAGE_URL
MINIO_USERNAME = settings.MINIO_USERNAME
MINIO_PASSWORD = settings.MINIO_PASSWORD
MINIO_SECURE = settings.MINIO_SECURE


from minio import Minio
import urllib3

minio_client = Minio(
    MINIO_STORAGE_URL,
    access_key=MINIO_USERNAME,
    secret_key=MINIO_PASSWORD,
    secure=MINIO_SECURE
    #http_client=urllib3.PoolManager(cert_reqs='CERT_NONE')
)