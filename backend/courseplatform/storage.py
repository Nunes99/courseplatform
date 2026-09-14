import base64
import binascii
import hashlib
import io
import re
import unicodedata
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any
from urllib.parse import quote, urlsplit

from .config import get_settings


ASSIGNMENT_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "text/plain",
    "application/msword",
    "application/vnd.ms-excel",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}
RECEIPT_MIME_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/webp"}
MIME_EXTENSIONS = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "text/plain": "txt",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
    "application/vnd.ms-powerpoint": "ppt",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
}
LEGACY_DATA_URL = re.compile(r"^data:([^;,]+);base64,(.+)$", re.IGNORECASE | re.DOTALL)


class StorageError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ValidatedUpload:
    content: bytes
    file_name: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


def normalized_file_name(value: Any, fallback: str = "ficheiro") -> str:
    name = PurePath(str(value or "").replace("\\", "/")).name.strip().strip(".")
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    return (name or fallback)[:180]


def safe_download_name(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", normalized_file_name(value))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = re.sub(r"[^A-Za-z0-9._-]+", "-", ascii_name).strip("-.")
    return ascii_name[:160] or "ficheiro"


def _decode_base64(value: Any, max_bytes: int) -> bytes:
    encoded = re.sub(r"\s+", "", str(value or ""))
    if not encoded:
        raise StorageError("FILE_REQUIRED", "Selecione um ficheiro para carregar.")
    if len(encoded) > ((max_bytes + 2) // 3) * 4 + 8:
        raise StorageError("FILE_TOO_LARGE", "O ficheiro excede o tamanho máximo permitido.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise StorageError("INVALID_FILE_CONTENT", "O conteúdo do ficheiro não é Base64 válido.") from exc
    if not content:
        raise StorageError("EMPTY_FILE", "O ficheiro selecionado está vazio.")
    if len(content) > max_bytes:
        raise StorageError("FILE_TOO_LARGE", "O ficheiro excede o tamanho máximo permitido.")
    return content


def _zip_mime_type(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except (zipfile.BadZipFile, OSError):
        return ""
    if any(name.startswith("word/") for name in names):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if any(name.startswith("xl/") for name in names):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if any(name.startswith("ppt/") for name in names):
        return "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return ""


def detected_mime_type(content: bytes, claimed_mime_type: str) -> str:
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith(b"PK\x03\x04"):
        return _zip_mime_type(content)
    if content.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        legacy_mime = claimed_mime_type.lower()
        if legacy_mime in {"application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint"}:
            return legacy_mime
        return ""
    if claimed_mime_type.lower() == "text/plain" and b"\x00" not in content[:4096]:
        try:
            content.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            return ""
    return ""


def validate_upload(
    base64_data: Any,
    file_name: Any,
    claimed_mime_type: Any,
    *,
    purpose: str,
) -> ValidatedUpload:
    settings = get_settings()
    max_bytes = (
        settings.payment_receipt_max_bytes
        if purpose == "PAYMENT_RECEIPT"
        else settings.submission_file_max_bytes
    )
    content = _decode_base64(base64_data, max_bytes)
    claimed = str(claimed_mime_type or "application/octet-stream").split(";", 1)[0].strip().lower()
    detected = detected_mime_type(content, claimed)
    allowed = RECEIPT_MIME_TYPES if purpose == "PAYMENT_RECEIPT" else ASSIGNMENT_MIME_TYPES
    if not detected or detected not in allowed:
        raise StorageError("UNSUPPORTED_FILE_TYPE", "O formato real do ficheiro não é permitido.")
    if claimed not in {"", "application/octet-stream", detected}:
        raise StorageError("FILE_TYPE_MISMATCH", "O tipo declarado não corresponde ao conteúdo do ficheiro.")
    name = normalized_file_name(file_name)
    expected_extension = MIME_EXTENSIONS[detected]
    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    compatible_extensions = {expected_extension}
    if detected == "image/jpeg":
        compatible_extensions.add("jpeg")
    if suffix and suffix not in compatible_extensions:
        raise StorageError("FILE_EXTENSION_MISMATCH", "A extensão não corresponde ao conteúdo do ficheiro.")
    if not suffix:
        name = f"{name}.{expected_extension}"
    return ValidatedUpload(
        content=content,
        file_name=name,
        mime_type=detected,
        size_bytes=len(content),
        checksum_sha256=hashlib.sha256(content).hexdigest(),
    )


def storage_object_path(purpose: str, owner_id: Any, entity_id: Any, upload: ValidatedUpload) -> str:
    segments = [purpose.lower(), str(owner_id or "unknown"), str(entity_id or "unknown"), upload.checksum_sha256]
    safe_segments = [re.sub(r"[^A-Za-z0-9_-]+", "-", item).strip("-") or "unknown" for item in segments]
    return "/".join([*safe_segments, f"content.{MIME_EXTENSIONS[upload.mime_type]}"])


def storage_service_headers(settings: Any) -> dict[str, str]:
    key = str(
        getattr(settings, "supabase_secret_key", "")
        or getattr(settings, "supabase_service_role_key", "")
    ).strip()
    if not key:
        return {}
    headers = {"apikey": key}
    if not key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {key}"
    return headers


def _storage_request(bucket: str, object_path: str, *, data: bytes | None = None, mime_type: str = ""):
    settings = get_settings()
    service_headers = storage_service_headers(settings)
    if not settings.supabase_url or not service_headers:
        raise StorageError(
            "PRIVATE_STORAGE_NOT_CONFIGURED",
            "O armazenamento privado ainda não está configurado no servidor.",
        )
    encoded_path = quote(object_path.strip("/"), safe="/")
    request = urllib.request.Request(
        f"{settings.supabase_url}/storage/v1/object/{quote(bucket, safe='')}/{encoded_path}",
        data=data,
        method="POST" if data is not None else "GET",
        headers={
            **service_headers,
            **({"Content-Type": mime_type, "x-upsert": "true"} if data is not None else {}),
        },
    )
    try:
        return urllib.request.urlopen(request, timeout=settings.storage_timeout_seconds)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise StorageError("PRIVATE_STORAGE_UNAVAILABLE", "O armazenamento privado não está disponível.") from exc


def upload_private_object(bucket: str, object_path: str, upload: ValidatedUpload) -> None:
    with _storage_request(bucket, object_path, data=upload.content, mime_type=upload.mime_type) as response:
        if not 200 <= response.status < 300:
            raise StorageError("PRIVATE_STORAGE_UNAVAILABLE", "Não foi possível guardar o ficheiro.")


def download_private_object(bucket: str, object_path: str, max_bytes: int) -> bytes:
    with _storage_request(bucket, object_path) as response:
        if not 200 <= response.status < 300:
            raise StorageError("PRIVATE_STORAGE_UNAVAILABLE", "Não foi possível abrir o ficheiro.")
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise StorageError("FILE_TOO_LARGE", "O ficheiro armazenado excede o limite permitido.")
    return content


def decode_legacy_data_url(value: Any, max_bytes: int) -> tuple[bytes, str]:
    match = LEGACY_DATA_URL.match(str(value or ""))
    if not match:
        raise StorageError("FILE_CONTENT_UNAVAILABLE", "O conteúdo histórico do ficheiro não está disponível.")
    return _decode_base64(match.group(2), max_bytes), match.group(1).lower()


def validate_legacy_upload(value: Any, file_name: Any, claimed_mime_type: Any, *, purpose: str) -> ValidatedUpload:
    match = LEGACY_DATA_URL.match(str(value or ""))
    if not match:
        raise StorageError("FILE_CONTENT_UNAVAILABLE", "O conteúdo histórico do ficheiro não está disponível.")
    return validate_upload(
        match.group(2),
        file_name,
        claimed_mime_type or match.group(1),
        purpose=purpose,
    )


def legacy_external_url(value: Any) -> str:
    url = str(value or "").strip()
    if not url.lower().startswith("https://"):
        return ""
    parsed = urlsplit(url)
    return url if parsed.scheme.lower() == "https" and parsed.netloc else ""
