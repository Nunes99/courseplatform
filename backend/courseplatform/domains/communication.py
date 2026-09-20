import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import re
import secrets
import smtplib
import ssl
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from html import escape as html_escape
from typing import Any
from urllib.parse import urlencode, urlsplit

from ..contracts import ApiError

logger = logging.getLogger(__name__)

_NOTIFICATION_SCHEMA_READY = False
_CHAT_SCHEMA_READY = False
_CHAT_REALTIME_SCHEMA_READY = False


ACTION_BINDINGS = (
    ("studentStartTelegramLink", "student_start_telegram_link"),
    ("studentConfirmTelegramLink", "student_confirm_telegram_link"),
    ("studentUnlinkTelegram", "student_unlink_telegram"),
    ("getPushConfiguration", "student_push_configuration"),
    ("subscribePush", "student_subscribe_push"),
    ("unsubscribePush", "student_unsubscribe_push"),
    ("getMyNotifications", "my_notifications"),
    ("markNotificationRead", "mark_notification_read"),
    ("getChatRealtimeConfiguration", "chat_realtime_configuration"),
    ("getChatRooms", "chat_list_rooms"),
    ("getChatContacts", "chat_list_contacts"),
    ("startDirectChat", "chat_start_direct"),
    ("updatePresence", "chat_presence_heartbeat"),
    ("getChatMessages", "chat_list_messages"),
    ("sendChatMessage", "chat_send_message"),
    ("editChatMessage", "chat_edit_message"),
    ("deleteChatMessage", "chat_delete_message"),
    ("markChatRoomRead", "chat_mark_read"),
    ("reportChatMessage", "chat_report_message"),
    ("adminListNotifications", "admin_list_notifications"),
    ("adminListChatRooms", "chat_list_rooms"),
    ("adminGetChatRealtimeConfiguration", "chat_realtime_configuration"),
    ("adminUpdatePresence", "chat_presence_heartbeat"),
    ("adminGetChatMessages", "chat_list_messages"),
    ("adminSendChatMessage", "chat_send_message"),
    ("adminEditChatMessage", "chat_edit_message"),
    ("adminDeleteChatMessage", "chat_delete_message"),
    ("adminMarkChatRoomRead", "chat_mark_read"),
    ("adminCreateNotification", "admin_create_notification"),
    ("adminSaveNotificationTemplate", "admin_save_notification_template"),
    ("adminResetNotificationTemplate", "admin_reset_notification_template"),
    ("adminSaveWhatsAppConfiguration", "admin_save_whatsapp_configuration"),
    ("adminSaveEmailConfiguration", "admin_save_email_configuration"),
    ("adminSaveTelegramConfiguration", "admin_save_telegram_configuration"),
    ("adminRetryNotificationDeliveries", "admin_retry_notification_deliveries"),
)


@dataclass(frozen=True)
class CommunicationRuntime:
    DEFAULT_NOTIFICATION_PREFERENCES: Any
    NOTIFICATION_STATUS_LABELS: Any
    NOTIFICATION_TEMPLATE_DEFINITIONS: Any
    NOTIFICATION_TEMPLATE_VARIABLES: Any
    _NOTIFICATION_TEMPLATE_COLUMNS: Any
    _jwt_segment: Any
    _notification_plain_text: Any
    _render_notification_template: Any
    _telegram_markdown_v2: Any
    _template_tokens: Any
    accessible_chat_room: Any
    admin_context: Any
    as_bool: Any
    audit: Any
    chat_actor_with_conn: Any
    chat_direct_pair: Any
    chat_message_body: Any
    chat_message_row: Any
    chat_message_rows: Any
    chat_realtime_token: Any
    chat_room_participant_count: Any
    chat_room_summary_context: Any
    claim_notification_deliveries: Any
    connection: Any
    create_student_notification: Any
    cursor_page_limit: Any
    cursor_pagination_result: Any
    cursor_scope: Any
    decode_list_cursor: Any
    decrypt_notification_secret: Any
    deliver_pending_channel: Any
    deliver_pending_email: Any
    deliver_pending_push: Any
    deliver_pending_telegram: Any
    deliver_pending_whatsapp: Any
    dispatch_notification_deliveries: Any
    email_configuration: Any
    email_runtime_configuration: Any
    ensure_chat_feature_schema: Any
    ensure_chat_realtime_schema: Any
    ensure_notification_feature_schema: Any
    fetch_all: Any
    fetch_one: Any
    generate_id: Any
    get_settings: Any
    hash_secret: Any
    int_value: Any
    iso: Any
    mark_chat_room_read_with_conn: Any
    normalize_email: Any
    normalize_email_recipient: Any
    normalize_telegram_parse_mode: Any
    normalize_telegram_recipient: Any
    normalize_whatsapp_recipient: Any
    notification_encryption_key: Any
    notification_preferences: Any
    notification_template_payload: Any
    notification_templates_payload: Any
    pagination: Any
    parse_datetime: Any
    prepare_chat_feature_schema: Any
    prepare_notification_feature_schema: Any
    process_telegram_link_updates: Any
    public_chat_message: Any
    public_chat_room: Any
    public_notification: Any
    public_student: Any
    push_subscriptions_for_student: Any
    record_chat_message_receipts: Any
    redact_notification_error: Any
    require_fields: Any
    require_schema_capabilities: Any
    resolve_notification_content: Any
    resolved_notification_action_url: Any
    safe_notification_action_url: Any
    send_email_notification: Any
    send_telegram_notification: Any
    send_web_push_notification: Any
    send_whatsapp_template: Any
    str_value: Any
    student_can_access_chat_room: Any
    student_context: Any
    student_context_with_conn: Any
    student_unread_badge_count: Any
    success: Any
    sync_chat_rooms: Any
    telegram_configuration: Any
    telegram_get_updates: Any
    telegram_runtime_configuration: Any
    touch_chat_presence: Any
    update_push_subscription_delivery: Any
    upsert_chat_room: Any
    upsert_chat_room_read_cursor: Any
    utc_now: Any
    valid_notification_host: Any
    valid_push_endpoint: Any
    valid_push_key: Any
    valid_telegram_bot_token: Any
    valid_vapid_key: Any
    valid_vapid_subject: Any
    valid_whatsapp_platform_url: Any
    validate_session_with_conn: Any
    web_push_configuration: Any
    web_push_runtime_configuration: Any
    webpush: Any
    whatsapp_configuration: Any
    whatsapp_runtime_configuration: Any


def notification_status_label_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    NOTIFICATION_STATUS_LABELS = runtime.NOTIFICATION_STATUS_LABELS
    str_value = runtime.str_value
    normalized = str_value(value).upper()
    return NOTIFICATION_STATUS_LABELS.get(normalized, normalized.replace("_", " ").title())


def notification_preferences_action(row: dict[str, Any] | None, *, runtime: CommunicationRuntime) -> dict[str, bool]:
    DEFAULT_NOTIFICATION_PREFERENCES = runtime.DEFAULT_NOTIFICATION_PREFERENCES
    as_bool = runtime.as_bool
    source = (row or {}).get("notification_preferences_json") or {}
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except json.JSONDecodeError:
            source = {}
    if not isinstance(source, dict):
        source = {}
    return {
        key: as_bool(source.get(key, default_value))
        for key, default_value in DEFAULT_NOTIFICATION_PREFERENCES.items()
    }


def ensure_notification_feature_schema_action(conn, *, runtime: CommunicationRuntime) -> None:
    require_schema_capabilities = runtime.require_schema_capabilities
    global _NOTIFICATION_SCHEMA_READY
    if _NOTIFICATION_SCHEMA_READY:
        return
    require_schema_capabilities(
        conn,
        "notificações",
        (
            "courseplatform.notifications",
            "courseplatform.notification_deliveries",
            "courseplatform.notification_channel_settings",
            "courseplatform.notification_templates",
            "courseplatform.push_subscriptions",
            "courseplatform.telegram_link_tokens",
            "courseplatform.notification_channel_state",
        ),
        (
            "courseplatform.students.whatsapp_opt_in",
            "courseplatform.students.email_opt_in",
            "courseplatform.students.telegram_chat_id",
            "courseplatform.students.notification_preferences_json",
            "courseplatform.notifications.template_key",
            "courseplatform.notifications.template_variables_json",
        ),
    )
    _NOTIFICATION_SCHEMA_READY = True


def prepare_notification_feature_schema_action(*, runtime: CommunicationRuntime) -> None:
    connection = runtime.connection
    ensure_notification_feature_schema = runtime.ensure_notification_feature_schema
    if _NOTIFICATION_SCHEMA_READY:
        return
    with connection() as conn:
        ensure_notification_feature_schema(conn)


def _template_tokens_action(value: Any, *, runtime: CommunicationRuntime) -> set[str]:
    return set(re.findall(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", str(value or ""), flags=re.IGNORECASE))


def _render_notification_template_action(value: Any, variables: dict[str, Any], fallback: str, limit: int, *, runtime: CommunicationRuntime) -> str:
    NOTIFICATION_TEMPLATE_VARIABLES = runtime.NOTIFICATION_TEMPLATE_VARIABLES
    str_value = runtime.str_value
    source = str(value or fallback)
    normalized = {key: str_value(item) for key, item in variables.items() if key in NOTIFICATION_TEMPLATE_VARIABLES}

    def replace(match: re.Match) -> str:
        return normalized.get(match.group(1).lower(), "")

    return re.sub(r"{{\s*([a-z_][a-z0-9_]*)\s*}}", replace, source, flags=re.IGNORECASE).strip()[:limit]


def notification_template_payload_action(template_key: str, row: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> dict[str, Any]:
    NOTIFICATION_TEMPLATE_DEFINITIONS = runtime.NOTIFICATION_TEMPLATE_DEFINITIONS
    NOTIFICATION_TEMPLATE_VARIABLES = runtime.NOTIFICATION_TEMPLATE_VARIABLES
    _NOTIFICATION_TEMPLATE_COLUMNS = runtime._NOTIFICATION_TEMPLATE_COLUMNS
    iso = runtime.iso
    definition = NOTIFICATION_TEMPLATE_DEFINITIONS[template_key]
    row = row or {}
    payload = {
        "templateKey": template_key,
        "label": definition["label"],
        "category": definition["category"],
        "customized": bool(row),
        "updatedAt": iso(row.get("updated_at")),
        "allowedVariables": sorted(NOTIFICATION_TEMPLATE_VARIABLES),
    }
    for public_name, column_name in _NOTIFICATION_TEMPLATE_COLUMNS.items():
        payload[public_name] = row.get(column_name) if row.get(column_name) is not None else definition[public_name]
        payload[f"default{public_name[0].upper()}{public_name[1:]}"] = definition[public_name]
    return payload


def notification_templates_payload_action(*, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    NOTIFICATION_TEMPLATE_DEFINITIONS = runtime.NOTIFICATION_TEMPLATE_DEFINITIONS
    fetch_all = runtime.fetch_all
    notification_template_payload = runtime.notification_template_payload
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    prepare_notification_feature_schema()
    rows = {
        row["template_key"]: row
        for row in fetch_all("select * from courseplatform.notification_templates")
        if row.get("template_key") in NOTIFICATION_TEMPLATE_DEFINITIONS
    }
    return [
        notification_template_payload(template_key, rows.get(template_key))
        for template_key in NOTIFICATION_TEMPLATE_DEFINITIONS
    ]


def resolve_notification_content_action(
    conn,
    template_key: str,
    variables: dict[str, Any] | None,
    title: str,
    message: str,
    *,
    email_subject: str = "",
    email_message: str = "",
    push_title: str = "",
    push_message: str = "",
    runtime: CommunicationRuntime,
) -> dict[str, Any]:
    NOTIFICATION_TEMPLATE_DEFINITIONS = runtime.NOTIFICATION_TEMPLATE_DEFINITIONS
    NOTIFICATION_TEMPLATE_VARIABLES = runtime.NOTIFICATION_TEMPLATE_VARIABLES
    _render_notification_template = runtime._render_notification_template
    notification_template_payload = runtime.notification_template_payload
    str_value = runtime.str_value
    normalized_key = str_value(template_key).upper()
    context = {
        key: str_value(value)[:1800]
        for key, value in (variables or {}).items()
        if key in NOTIFICATION_TEMPLATE_VARIABLES
    }
    if normalized_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        return {
            "templateKey": "",
            "variables": context,
            "title": str_value(title)[:180],
            "message": str_value(message)[:1800],
            "emailSubject": str_value(email_subject or title)[:180],
            "emailMessage": str_value(email_message or message)[:5000],
            "pushTitle": str_value(push_title or title)[:120],
            "pushMessage": str_value(push_message or message)[:300],
        }
    row = conn.execute(
        "select * from courseplatform.notification_templates where template_key = %s",
        (normalized_key,),
    ).fetchone() or {}
    template = notification_template_payload(normalized_key, row)
    return {
        "templateKey": normalized_key,
        "variables": context,
        "title": _render_notification_template(template["internalTitleTemplate"], context, title, 180),
        "message": _render_notification_template(template["internalMessageTemplate"], context, message, 1800),
        "emailSubject": _render_notification_template(template["emailSubjectTemplate"], context, email_subject or title, 180),
        "emailMessage": _render_notification_template(template["emailMessageTemplate"], context, email_message or message, 5000),
        "pushTitle": _render_notification_template(template["pushTitleTemplate"], context, push_title or title, 120),
        "pushMessage": _render_notification_template(template["pushMessageTemplate"], context, push_message or message, 300),
    }


def public_notification_action(row: dict[str, Any] | None, *, runtime: CommunicationRuntime):
    iso = runtime.iso
    if not row:
        return None
    def delivery(channel: str) -> dict[str, Any]:
        prefix = channel.lower()
        # Legacy WhatsApp-only selects expose unprefixed delivery columns.
        fallback = channel == "WHATSAPP"
        status = row.get(f"{prefix}_status") or (row.get("delivery_status") if fallback else None) or "NOT_REQUESTED"
        if status == "PROCESSING":
            status = "PENDING"
        recipient = row.get(f"{prefix}_recipient") or (row.get("delivery_recipient") if fallback else None)
        return {
            "status": status,
            # Telegram chat IDs are private provider identifiers and are never
            # part of an API response, including administrative history.
            "recipient": None if channel in {"TELEGRAM", "PUSH"} else recipient,
            "providerMessageId": row.get(f"{prefix}_provider_message_id") or (row.get("provider_message_id") if fallback else None),
            "attemptCount": int(row.get(f"{prefix}_attempt_count") or (row.get("attempt_count") if fallback else 0) or 0),
            "lastError": row.get(f"{prefix}_last_error") or (row.get("last_error") if fallback else None),
            "sentAt": iso(row.get(f"{prefix}_sent_at") or (row.get("sent_at") if fallback else None)),
        }
    return {
        "notificationId": row.get("notification_id"),
        "studentId": row.get("student_id"),
        "studentName": row.get("student_name") or row.get("full_name"),
        "category": row.get("category") or "GENERAL",
        "title": row.get("title"),
        "message": row.get("message"),
        "actionUrl": row.get("action_url"),
        "entityType": row.get("entity_type"),
        "entityId": row.get("entity_id"),
        "priority": row.get("priority") or "NORMAL",
        "readAt": iso(row.get("read_at")),
        "createdAt": iso(row.get("created_at")),
        "templateKey": row.get("template_key") or "",
        "whatsapp": delivery("WHATSAPP"),
        "email": delivery("EMAIL"),
        "telegram": delivery("TELEGRAM"),
        "push": delivery("PUSH"),
    }


def normalize_whatsapp_recipient_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    text = re.sub(r"[^0-9+]", "", str_value(value))
    if text.startswith("00"):
        text = f"+{text[2:]}"
    digits = re.sub(r"\D", "", text)
    return digits if 8 <= len(digits) <= 15 else ""


def normalize_email_recipient_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    normalize_email = runtime.normalize_email
    str_value = runtime.str_value
    text = normalize_email(str_value(value))
    if len(text) > 254 or "\r" in text or "\n" in text:
        return ""
    local, separator, domain = text.rpartition("@")
    if not separator or not local or not domain or "." not in domain:
        return ""
    if len(local) > 64 or not re.fullmatch(r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+", local, re.IGNORECASE):
        return ""
    if not re.fullmatch(r"[a-z0-9.-]+", domain, re.IGNORECASE) or domain.startswith((".", "-")):
        return ""
    return text


def normalize_telegram_recipient_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    text = str_value(value)
    # Student accounts are linked only to private chats. Negative IDs identify
    # groups/channels and must never become a personal notification endpoint.
    return text if re.fullmatch(r"\d{5,20}", text) else ""


def redact_notification_error_action(value: Any, *secrets_to_hide: Any, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    text = str(value)
    for secret in secrets_to_hide:
        secret_text = str_value(secret)
        if secret_text:
            text = text.replace(secret_text, "[redacted]")
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+\-/=]+", "Bearer [redacted]", text)
    text = re.sub(r"(?i)(?:bot)?\d{5,20}:[A-Za-z0-9_-]{20,}", "[redacted]", text)
    return text[:700]


def notification_encryption_key_action(settings: Any | None = None, *, runtime: CommunicationRuntime) -> str:
    get_settings = runtime.get_settings
    str_value = runtime.str_value
    settings = settings or get_settings()
    return str_value(
        getattr(settings, "notification_config_encryption_key", "")
        or getattr(settings, "whatsapp_config_encryption_key", "")
    )


def decrypt_notification_secret_action(channel: str, column: str, encryption_key: str, *, runtime: CommunicationRuntime) -> str:
    fetch_one = runtime.fetch_one
    str_value = runtime.str_value
    if channel not in {"WHATSAPP", "EMAIL", "TELEGRAM"} or column not in {
        "access_token_encrypted", "smtp_password_encrypted"
    }:
        raise ValueError("Canal ou coluna de segredo inválidos.")
    row = fetch_one(
        f"""
        select pgp_sym_decrypt({column}, %s)::text as secret
        from courseplatform.notification_channel_settings
        where channel = %s
        """,
        (encryption_key, channel),
    ) or {}
    return str_value(row.get("secret"))


def valid_whatsapp_platform_url_action(value: Any, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    text = str_value(value)
    if not text or len(text) > 1000:
        return False
    try:
        parsed = urlsplit(text)
        return bool(
            parsed.scheme in {"https", "http"}
            and parsed.hostname
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        return False


def valid_notification_host_action(value: Any, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    text = str_value(value)
    if not text or len(text) > 253 or "\r" in text or "\n" in text:
        return False
    # SMTP accepts DNS names and literal IPv4/IPv6 addresses. It must not
    # contain a scheme, path, credentials or an embedded port.
    if "://" in text or any(character in text for character in "/@?#"):
        return False
    candidate = text[1:-1] if text.startswith("[") and text.endswith("]") else text
    try:
        # Prevent the administration form from being used to probe local or
        # private network services through the SMTP client.
        return ipaddress.ip_address(candidate).is_global
    except ValueError:
        normalized = candidate.lower().rstrip(".")
        if normalized == "localhost" or normalized.endswith(".localhost"):
            return False
        return bool(re.fullmatch(r"[a-zA-Z0-9.-]+", candidate) and not candidate.startswith((".", "-")))


def valid_telegram_bot_token_action(value: Any, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    return bool(re.fullmatch(r"\d{5,20}:[A-Za-z0-9_-]{20,}", str_value(value)))


def normalize_telegram_parse_mode_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    normalized = str_value(value).upper()
    if normalized in {"", "NONE", "PLAIN"}:
        return ""
    if normalized == "HTML":
        return "HTML"
    if normalized in {"MARKDOWNV2", "MARKDOWN_V2"}:
        return "MarkdownV2"
    return "HTML"


def safe_notification_action_url_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    text = str_value(value)
    if text.startswith("#/") or text.startswith("https://") or text.startswith("http://"):
        return text[:1000]
    return "#/notifications"


def whatsapp_runtime_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    as_bool = runtime.as_bool
    decrypt_notification_secret = runtime.decrypt_notification_secret
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    iso = runtime.iso
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    valid_whatsapp_platform_url = runtime.valid_whatsapp_platform_url
    """Resolve the admin-managed WhatsApp configuration without exposing its token."""
    prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, phone_number_id, graph_api_version, template_name,
               template_language, platform_url,
               access_token_encrypted is not null as stored_token_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'WHATSAPP'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.whatsapp_enabled
    phone_number_id = str_value(source.get("phone_number_id")) if managed_by_admin else settings.whatsapp_phone_number_id
    graph_api_version = str_value(source.get("graph_api_version")) if managed_by_admin else settings.whatsapp_graph_api_version
    template_name = str_value(source.get("template_name")) if managed_by_admin else settings.whatsapp_template_name
    template_language = str_value(source.get("template_language")) if managed_by_admin else settings.whatsapp_template_language
    platform_url = str_value(source.get("platform_url")) if managed_by_admin else settings.whatsapp_platform_url
    stored_token_configured = as_bool(source.get("stored_token_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    access_token = settings.whatsapp_access_token
    token_source = "ENV" if access_token else "NONE"
    token_error = ""

    if stored_token_configured:
        if encryption_key_configured:
            try:
                decrypted_token = decrypt_notification_secret(
                    "WHATSAPP", "access_token_encrypted", encryption_key
                )
                if decrypted_token:
                    access_token = decrypted_token
                    token_source = "ADMIN"
            except Exception:
                token_error = "O token guardado não pôde ser desencriptado. Confirme a chave do servidor."
        elif not access_token:
            token_error = "Defina WHATSAPP_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes para utilizar o token guardado."

    configured = bool(
        enabled
        and access_token
        and phone_number_id
        and template_name
        and valid_whatsapp_platform_url(platform_url)
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "phoneNumberId": phone_number_id,
        "phoneNumberConfigured": bool(phone_number_id),
        "graphApiVersion": graph_api_version or "v23.0",
        "templateConfigured": bool(template_name),
        "templateName": template_name,
        "templateLanguage": template_language or "pt_PT",
        "platformUrl": platform_url,
        "accessToken": access_token,
        "tokenConfigured": bool(access_token),
        "storedTokenConfigured": stored_token_configured,
        "tokenSource": token_source,
        "tokenError": token_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.whatsapp_timeout_seconds,
    }


def whatsapp_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    whatsapp_runtime_configuration = runtime.whatsapp_runtime_configuration
    configuration = whatsapp_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"accessToken", "timeoutSeconds"}
    }


def email_runtime_configuration_action(*, prepare_schema: bool = True, runtime: CommunicationRuntime) -> dict[str, Any]:
    as_bool = runtime.as_bool
    decrypt_notification_secret = runtime.decrypt_notification_secret
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    int_value = runtime.int_value
    iso = runtime.iso
    normalize_email_recipient = runtime.normalize_email_recipient
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    valid_notification_host = runtime.valid_notification_host
    """Resolve SMTP settings while keeping the password server-side."""
    if prepare_schema:
        prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, smtp_host, smtp_port, smtp_username,
               from_email, from_name, use_tls,
               smtp_password_encrypted is not null as stored_password_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'EMAIL'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.email_enabled
    smtp_host = str_value(source.get("smtp_host")) if managed_by_admin else settings.smtp_host
    smtp_port = int_value(source.get("smtp_port"), 587) if managed_by_admin else settings.smtp_port
    smtp_username = str_value(source.get("smtp_username")) if managed_by_admin else settings.smtp_username
    from_email = normalize_email_recipient(source.get("from_email")) if managed_by_admin else normalize_email_recipient(settings.smtp_from_email)
    from_name = str_value(source.get("from_name")) if managed_by_admin else settings.smtp_from_name
    use_tls = as_bool(source.get("use_tls")) if managed_by_admin else settings.smtp_use_tls
    stored_password_configured = as_bool(source.get("stored_password_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    smtp_password = settings.smtp_password
    password_source = "ENV" if smtp_password else "NONE"
    password_error = ""
    if stored_password_configured:
        if encryption_key_configured:
            try:
                decrypted = decrypt_notification_secret("EMAIL", "smtp_password_encrypted", encryption_key)
                if decrypted:
                    smtp_password = decrypted
                    password_source = "ADMIN"
            except Exception:
                password_error = "A palavra-passe SMTP guardada não pôde ser desencriptada. Confirme a chave do servidor."
        elif not smtp_password:
            password_error = "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes."
    authentication_ready = not smtp_username or bool(smtp_password)
    configured = bool(
        enabled
        and valid_notification_host(smtp_host)
        and 1 <= smtp_port <= 65535
        and (smtp_port == 465 or use_tls)
        and from_email
        and authentication_ready
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "smtpHost": smtp_host,
        "smtpPort": smtp_port,
        "smtpUsername": smtp_username,
        "smtpPassword": smtp_password,
        "fromEmail": from_email,
        "fromName": from_name,
        "useTls": use_tls,
        "platformUrl": settings.platform_url,
        "passwordConfigured": bool(smtp_password),
        "storedPasswordConfigured": stored_password_configured,
        "passwordSource": password_source,
        "passwordError": password_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.smtp_timeout_seconds,
    }


def email_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    email_runtime_configuration = runtime.email_runtime_configuration
    configuration = email_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"smtpPassword", "timeoutSeconds"}
    }


def telegram_runtime_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    as_bool = runtime.as_bool
    decrypt_notification_secret = runtime.decrypt_notification_secret
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    iso = runtime.iso
    normalize_telegram_parse_mode = runtime.normalize_telegram_parse_mode
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    valid_telegram_bot_token = runtime.valid_telegram_bot_token
    """Resolve Telegram Bot API settings without exposing the bot token."""
    prepare_notification_feature_schema()
    settings = get_settings()
    row = fetch_one(
        """
        select channel, enabled, bot_username, parse_mode,
               access_token_encrypted is not null as stored_token_configured,
               updated_at
        from courseplatform.notification_channel_settings
        where channel = 'TELEGRAM'
        """
    )
    managed_by_admin = bool(row)
    source = row or {}
    enabled = as_bool(source.get("enabled")) if managed_by_admin else settings.telegram_enabled
    bot_username = str_value(source.get("bot_username")) if managed_by_admin else settings.telegram_bot_username
    parse_mode = normalize_telegram_parse_mode(source.get("parse_mode") if managed_by_admin else settings.telegram_parse_mode)
    stored_token_configured = as_bool(source.get("stored_token_configured"))
    encryption_key = notification_encryption_key(settings)
    encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
    bot_token = settings.telegram_bot_token
    token_source = "ENV" if bot_token else "NONE"
    token_error = ""
    if stored_token_configured:
        if encryption_key_configured:
            try:
                decrypted = decrypt_notification_secret("TELEGRAM", "access_token_encrypted", encryption_key)
                if decrypted:
                    bot_token = decrypted
                    token_source = "ADMIN"
            except Exception:
                token_error = "O token do bot guardado não pôde ser desencriptado. Confirme a chave do servidor."
        elif not bot_token:
            token_error = "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY com pelo menos 32 bytes."
    configured = bool(enabled and valid_telegram_bot_token(bot_token))
    return {
        "enabled": enabled,
        "configured": configured,
        "botToken": bot_token,
        "botUsername": bot_username,
        "parseMode": parse_mode,
        "platformUrl": settings.platform_url,
        "tokenConfigured": bool(bot_token),
        "storedTokenConfigured": stored_token_configured,
        "tokenSource": token_source,
        "tokenError": token_error,
        "encryptionKeyConfigured": encryption_key_configured,
        "source": "ADMIN" if managed_by_admin else "ENV",
        "updatedAt": iso(source.get("updated_at")),
        "timeoutSeconds": settings.telegram_timeout_seconds,
    }


def telegram_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    telegram_runtime_configuration = runtime.telegram_runtime_configuration
    configuration = telegram_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"botToken", "timeoutSeconds"}
    }


def valid_vapid_subject_action(value: Any, *, runtime: CommunicationRuntime) -> bool:
    normalize_email_recipient = runtime.normalize_email_recipient
    str_value = runtime.str_value
    text = str_value(value)
    if text.startswith("mailto:"):
        return bool(normalize_email_recipient(text[7:]))
    try:
        parsed = urlsplit(text)
        return parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
    except ValueError:
        return False


def valid_push_endpoint_action(value: Any, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    text = str_value(value)
    if not text or len(text) > 4096:
        return False
    try:
        parsed = urlsplit(text)
        return bool(parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password)
    except ValueError:
        return False


def valid_push_key_action(value: Any, minimum: int, maximum: int, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    text = str_value(value)
    return minimum <= len(text) <= maximum and bool(re.fullmatch(r"[A-Za-z0-9_-]+", text))


def valid_vapid_key_action(value: Any, expected_bytes: int, require_uncompressed_point: bool = False, *, runtime: CommunicationRuntime) -> bool:
    str_value = runtime.str_value
    valid_push_key = runtime.valid_push_key
    text = str_value(value)
    if not valid_push_key(text, 40, 100):
        return False
    try:
        padding = "=" * ((4 - len(text) % 4) % 4)
        decoded = base64.urlsafe_b64decode(f"{text}{padding}")
    except (ValueError, TypeError):
        return False
    if len(decoded) != expected_bytes:
        return False
    return not require_uncompressed_point or decoded[0] == 4


def web_push_runtime_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    as_bool = runtime.as_bool
    get_settings = runtime.get_settings
    int_value = runtime.int_value
    notification_encryption_key = runtime.notification_encryption_key
    str_value = runtime.str_value
    valid_vapid_key = runtime.valid_vapid_key
    valid_vapid_subject = runtime.valid_vapid_subject
    webpush = runtime.webpush
    settings = get_settings()
    encryption_key = notification_encryption_key(settings)
    encryption_ready = len(encryption_key.encode("utf-8")) >= 32
    dependency_ready = webpush is not None
    enabled = as_bool(getattr(settings, "web_push_enabled", False))
    public_key = str_value(getattr(settings, "vapid_public_key", ""))
    private_key = str_value(getattr(settings, "vapid_private_key", ""))
    subject = str_value(getattr(settings, "vapid_subject", ""))
    configured = bool(
        enabled
        and valid_vapid_key(public_key, 65, require_uncompressed_point=True)
        and valid_vapid_key(private_key, 32)
        and valid_vapid_subject(subject)
        and encryption_ready
        and dependency_ready
    )
    return {
        "enabled": enabled,
        "configured": configured,
        "publicKey": public_key,
        "privateKey": private_key,
        "subject": subject,
        "platformUrl": str_value(getattr(settings, "platform_url", "")),
        "ttlSeconds": max(60, min(int_value(getattr(settings, "web_push_ttl_seconds", 86400), 86400), 2419200)),
        "timeoutSeconds": max(3, min(int_value(getattr(settings, "web_push_timeout_seconds", 12), 12), 60)),
        "encryptionKey": encryption_key,
        "encryptionKeyConfigured": encryption_ready,
        "dependencyConfigured": dependency_ready,
    }


def web_push_configuration_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    web_push_runtime_configuration = runtime.web_push_runtime_configuration
    configuration = web_push_runtime_configuration()
    return {
        key: value
        for key, value in configuration.items()
        if key not in {"privateKey", "encryptionKey", "ttlSeconds", "timeoutSeconds"}
    }


def student_notification_channel_info_action(*, runtime: CommunicationRuntime) -> dict[str, Any]:
    email_configuration = runtime.email_configuration
    telegram_configuration = runtime.telegram_configuration
    web_push_configuration = runtime.web_push_configuration
    whatsapp_configuration = runtime.whatsapp_configuration
    """Student-safe provider discovery; credentials and SMTP topology stay private."""
    email = email_configuration()
    telegram = telegram_configuration()
    whatsapp = whatsapp_configuration()
    push = web_push_configuration()
    return {
        "whatsapp": {"enabled": bool(whatsapp.get("enabled")), "configured": bool(whatsapp.get("configured"))},
        "email": {"enabled": bool(email.get("enabled")), "configured": bool(email.get("configured"))},
        "telegram": {
            "enabled": bool(telegram.get("enabled")),
            "configured": bool(telegram.get("configured")),
            "botUsername": telegram.get("botUsername") or "",
            "linkingAvailable": bool(
                telegram.get("enabled") and telegram.get("configured") and telegram.get("botUsername")
            ),
        },
        "push": {
            "enabled": bool(push.get("enabled")),
            "configured": bool(push.get("configured")),
            "publicKey": push.get("publicKey") or "",
        },
    }


def create_student_notification_action(
    conn,
    student_id: str,
    category: str,
    title: str,
    message: str,
    *,
    admin_id: str | None = None,
    action_url: str = "#/notifications",
    entity_type: str = "",
    entity_id: str = "",
    priority: str = "NORMAL",
    template_key: str = "",
    template_variables: dict[str, Any] | None = None,
    email_subject: str = "",
    email_message: str = "",
    push_title: str = "",
    push_message: str = "",
    send_whatsapp: bool = True,
    send_email: bool = True,
    send_telegram: bool = True,
    send_push: bool = True,
    runtime: CommunicationRuntime,
) -> str | None:
    as_bool = runtime.as_bool
    generate_id = runtime.generate_id
    normalize_email_recipient = runtime.normalize_email_recipient
    normalize_telegram_recipient = runtime.normalize_telegram_recipient
    normalize_whatsapp_recipient = runtime.normalize_whatsapp_recipient
    notification_preferences = runtime.notification_preferences
    resolve_notification_content = runtime.resolve_notification_content
    safe_notification_action_url = runtime.safe_notification_action_url
    str_value = runtime.str_value
    student = conn.execute(
        "select * from courseplatform.students where student_id = %s",
        (student_id,),
    ).fetchone()
    if not student:
        return None
    normalized_category = str_value(category).upper() or "GENERAL"
    normalized_action_url = safe_notification_action_url(action_url)
    variables = dict(template_variables or {})
    variables["student_name"] = str_value(student.get("full_name")) or "Estudante"
    variables["action_url"] = normalized_action_url
    content = resolve_notification_content(
        conn,
        template_key,
        variables,
        title,
        message,
        email_subject=email_subject,
        email_message=email_message,
        push_title=push_title,
        push_message=push_message,
    )
    notification_id = generate_id("NTF")
    conn.execute(
        """
        insert into courseplatform.notifications
          (notification_id, student_id, created_by_admin_id, category, title, message,
           action_url, entity_type, entity_id, priority, template_key,
           template_variables_json, email_subject, email_message, push_title,
           push_message, created_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s::jsonb, %s, %s, %s, %s, now())
        """,
        (
            notification_id,
            student_id,
            admin_id,
            normalized_category,
            content["title"],
            content["message"],
            normalized_action_url,
            str_value(entity_type)[:80],
            str_value(entity_id)[:160],
            str_value(priority).upper() or "NORMAL",
            content["templateKey"] or None,
            json.dumps(content["variables"]),
            content["emailSubject"],
            content["emailMessage"],
            content["pushTitle"],
            content["pushMessage"],
        ),
    )
    preferences = notification_preferences(student)

    def queue_delivery(
        channel: str,
        recipient: str,
        opted_in: bool,
        provider: str,
        missing_contact_message: str,
    ) -> None:
        consented = opted_in and preferences.get(normalized_category, True)
        delivery_status = "PENDING" if consented and recipient else "SKIPPED"
        skip_reason = "" if delivery_status == "PENDING" else (
            f"Consentimento de {channel.title()} não concedido para este tipo de atualização."
            if not consented else missing_contact_message
        )
        conn.execute(
            """
            insert into courseplatform.notification_deliveries
              (delivery_id, notification_id, channel, recipient, status, provider,
               attempt_count, last_error, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, 0, %s, now(), now())
            on conflict (notification_id, channel) do nothing
            """,
            (
                generate_id("NDL"), notification_id, channel, recipient or None,
                delivery_status, provider, skip_reason or None,
            ),
        )

    if send_whatsapp:
        queue_delivery(
            "WHATSAPP", normalize_whatsapp_recipient(student.get("phone")),
            as_bool(student.get("whatsapp_opt_in")), "META_CLOUD_API",
            "Telefone inválido ou sem indicativo internacional.",
        )
    if send_email:
        queue_delivery(
            "EMAIL", normalize_email_recipient(student.get("email")),
            as_bool(student.get("email_opt_in")), "SMTP",
            "Endereço de email inválido ou em falta.",
        )
    if send_telegram:
        queue_delivery(
            "TELEGRAM", normalize_telegram_recipient(student.get("telegram_chat_id")),
            as_bool(student.get("telegram_opt_in")), "TELEGRAM_BOT_API",
            "Chat ID do Telegram inválido ou em falta.",
        )
    if send_push:
        active_push = conn.execute(
            "select count(*) as count from courseplatform.push_subscriptions where student_id = %s and enabled",
            (student_id,),
        ).fetchone() or {}
        queue_delivery(
            "PUSH",
            student_id,
            int(active_push.get("count") or 0) > 0,
            "WEB_PUSH",
            "Nenhum dispositivo possui notificações Push ativas.",
        )
    return notification_id


def send_whatsapp_template_action(delivery: dict[str, Any], configuration: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> str:
    redact_notification_error = runtime.redact_notification_error
    str_value = runtime.str_value
    whatsapp_runtime_configuration = runtime.whatsapp_runtime_configuration
    configuration = configuration or whatsapp_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração WhatsApp ainda não configurada no servidor.")
    endpoint = (
        f"https://graph.facebook.com/{configuration['graphApiVersion']}/"
        f"{configuration['phoneNumberId']}/messages"
    )
    action_url = str_value(delivery.get("action_url"))
    if not action_url.startswith(("https://", "http://")):
        base = str_value(configuration.get("platformUrl")).rstrip("/")
        action_url = f"{base}/{action_url}" if action_url.startswith("#/") else base
    body = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": delivery["recipient"],
        "type": "template",
        "template": {
            "name": configuration["templateName"],
            "language": {"code": configuration["templateLanguage"]},
            "components": [{
                "type": "body",
                "parameters": [
                    {"type": "text", "text": str_value(delivery.get("student_name"))[:120] or "Estudante"},
                    {"type": "text", "text": str_value(delivery.get("title"))[:180]},
                    {"type": "text", "text": str_value(delivery.get("message"))[:900]},
                    {"type": "text", "text": action_url[:1000]},
                ],
            }],
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {configuration['accessToken']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(3, int(configuration.get("timeoutSeconds") or 12))) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("accessToken"))
        raise RuntimeError(f"WhatsApp Cloud API HTTP {error.code}: {safe_error}") from error
    messages = result.get("messages") if isinstance(result, dict) else []
    provider_message_id = str_value(messages[0].get("id")) if messages else ""
    if not provider_message_id:
        raise RuntimeError("A API do WhatsApp não devolveu o identificador da mensagem.")
    return provider_message_id


def resolved_notification_action_url_action(delivery: dict[str, Any], configuration: dict[str, Any], *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    action_url = str_value(delivery.get("action_url"))
    if action_url.startswith(("https://", "http://")):
        return action_url
    base = str_value(configuration.get("platformUrl")).rstrip("/")
    if base and action_url.startswith("#/"):
        return f"{base}/{action_url}"
    return ""


def _notification_plain_text_action(delivery: dict[str, Any], action_url: str = "", *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    parts = [
        str_value(delivery.get("student_name")) or "Estudante",
        "",
        str_value(delivery.get("email_subject") or delivery.get("title")) or "Atualização académica",
        "",
        str_value(delivery.get("email_message") or delivery.get("message")),
    ]
    if action_url:
        parts.extend(["", f"Abrir na plataforma: {action_url}"])
    return "\n".join(parts).strip()


def send_email_notification_action(delivery: dict[str, Any], configuration: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> str:
    _notification_plain_text = runtime._notification_plain_text
    email_runtime_configuration = runtime.email_runtime_configuration
    normalize_email_recipient = runtime.normalize_email_recipient
    redact_notification_error = runtime.redact_notification_error
    resolved_notification_action_url = runtime.resolved_notification_action_url
    str_value = runtime.str_value
    configuration = configuration or email_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração de email ainda não configurada no servidor.")
    recipient = normalize_email_recipient(delivery.get("recipient"))
    if not recipient:
        raise RuntimeError("Endereço de email do destinatário inválido.")

    title = re.sub(r"[\r\n]+", " ", str_value(delivery.get("email_subject") or delivery.get("title")))[:180] or "Atualização académica"
    body_message = str_value(delivery.get("email_message") or delivery.get("message"))[:5000]
    action_url = resolved_notification_action_url(delivery, configuration)
    message = EmailMessage()
    message_id = make_msgid(domain=configuration["fromEmail"].partition("@")[2] or None)
    message["Message-ID"] = message_id
    message["Subject"] = title
    message["From"] = formataddr((configuration.get("fromName") or "", configuration["fromEmail"]))
    message["To"] = recipient
    message.set_content(_notification_plain_text(delivery, action_url))
    student_name = html_escape(str_value(delivery.get("student_name")) or "Estudante")
    brand_name = html_escape(configuration.get("fromName") or "Plataforma de ensino")
    safe_body = html_escape(body_message).replace(chr(10), "<br>")
    action_html = (
        '<p style="margin:28px 0 8px">'
        f'<a href="{html_escape(action_url, quote=True)}" style="display:inline-block;background:#00365B;color:#FFFFFF;text-decoration:none;padding:11px 18px;border-radius:6px;font:600 14px Inter,Arial,sans-serif">Abrir na plataforma</a>'
        "</p>"
        if action_url.startswith(("https://", "http://")) else ""
    )
    message.add_alternative(
        "<!doctype html><html lang=\"pt\"><body style=\"margin:0;background:#FFF8E4;padding:24px\">"
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="center">'
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;background:#FFFFFF;border:1px solid rgba(201,165,91,.35);border-radius:12px;overflow:hidden">'
        f'<tr><td style="background:#00365B;padding:20px 24px;color:#FFF8E4;font:600 16px Manrope,Arial,sans-serif">{brand_name}</td></tr>'
        '<tr><td style="padding:28px 24px;color:#00365B;font:15px/1.6 Inter,Arial,sans-serif">'
        f'<p style="margin:0 0 12px">Olá, {student_name}.</p>'
        f'<h1 style="margin:0 0 16px;font:600 24px/1.25 Manrope,Arial,sans-serif;color:#00365B">{html_escape(title)}</h1>'
        f'<p style="margin:0">{safe_body}</p>{action_html}'
        '</td></tr><tr><td style="border-top:1px solid rgba(201,165,91,.25);padding:16px 24px;color:rgba(0,54,91,.68);font:12px/1.5 Inter,Arial,sans-serif">Mensagem académica automática. Pode gerir os canais e categorias no seu perfil.</td></tr>'
        "</table></td></tr></table></body></html>",
        subtype="html",
    )

    try:
        port = int(configuration["smtpPort"])
        smtp_class = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        smtp_options: dict[str, Any] = {
            "host": configuration["smtpHost"],
            "port": port,
            "timeout": max(3, int(configuration.get("timeoutSeconds") or 12)),
        }
        if port == 465:
            smtp_options["context"] = ssl.create_default_context()
        with smtp_class(**smtp_options) as smtp:
            smtp.ehlo()
            if port != 465 and configuration.get("useTls"):
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if configuration.get("smtpUsername"):
                smtp.login(configuration["smtpUsername"], configuration.get("smtpPassword") or "")
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError, TimeoutError) as error:
        safe_error = redact_notification_error(error, configuration.get("smtpPassword"))
        raise RuntimeError(f"Falha no envio SMTP: {safe_error}") from error
    return message_id.strip("<>")


def dispatch_student_password_reset_action(reset_id: str, token: str, request_base_url: str = "", *, runtime: CommunicationRuntime) -> None:
    connection = runtime.connection
    email_runtime_configuration = runtime.email_runtime_configuration
    fetch_one = runtime.fetch_one
    hash_secret = runtime.hash_secret
    send_email_notification = runtime.send_email_notification
    str_value = runtime.str_value
    """Deliver one reset link without persisting or returning its plaintext token."""
    if not reset_id or not token:
        return
    token_hash = hash_secret(token)
    try:
        row = fetch_one(
            """
            select r.reset_id, r.student_id, r.status, r.expires_at,
                   s.full_name, s.email, s.status as student_status
            from courseplatform.student_password_resets r
            join courseplatform.students s on s.student_id = r.student_id
            where r.reset_id = %s and r.token_hash = %s
              and r.consumed_at is null and r.invalidated_at is null
              and r.expires_at > now()
            """,
            (reset_id, token_hash),
        )
        if not row or row.get("status") not in {"PENDING", "DELIVERED"} or row.get("student_status") != "ACTIVE":
            return
        configuration = email_runtime_configuration(prepare_schema=False)
        base_url = str_value(configuration.get("platformUrl") or request_base_url).rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise RuntimeError("PLATFORM_URL is not configured for password recovery.")
        action_url = f"{base_url}/#/reset-access?{urlencode({'token': token})}"
        send_email_notification(
            {
                "recipient": row.get("email"),
                "student_name": row.get("full_name"),
                "email_subject": "Definir uma nova palavra-passe",
                "email_message": (
                    "Recebemos um pedido para recuperar o acesso à sua conta. "
                    "Use o botão abaixo para definir uma nova palavra-passe. "
                    "O link é de utilização única e expira em breve. Se não fez este pedido, ignore esta mensagem."
                ),
                "action_url": action_url,
            },
            configuration,
        )
        with connection() as conn:
            conn.execute(
                """
                update courseplatform.student_password_resets
                set status = 'DELIVERED', delivery_attempted_at = now(),
                    delivered_at = now(), delivery_error_code = null
                where reset_id = %s and token_hash = %s
                  and consumed_at is null and invalidated_at is null
                """,
                (reset_id, token_hash),
            )
            conn.commit()
    except Exception as error:
        logger.error(
            "Student password reset delivery failed.",
            extra={"reset_id": reset_id, "error_type": error.__class__.__name__},
            exc_info=True,
        )
        try:
            with connection() as conn:
                conn.execute(
                    """
                    update courseplatform.student_password_resets
                    set status = 'DELIVERY_FAILED', delivery_attempted_at = now(),
                        invalidated_at = coalesce(invalidated_at, now()),
                        delivery_error_code = %s
                    where reset_id = %s and token_hash = %s and consumed_at is null
                    """,
                    (error.__class__.__name__[:80], reset_id, token_hash),
                )
                conn.commit()
        except Exception:
            pass


def _telegram_markdown_v2_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    str_value = runtime.str_value
    return re.sub(r"([_\*\[\]\(\)~`>#+\-=|{}.!])", r"\\\1", str_value(value))


def send_telegram_notification_action(delivery: dict[str, Any], configuration: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> str:
    _telegram_markdown_v2 = runtime._telegram_markdown_v2
    normalize_telegram_parse_mode = runtime.normalize_telegram_parse_mode
    normalize_telegram_recipient = runtime.normalize_telegram_recipient
    redact_notification_error = runtime.redact_notification_error
    resolved_notification_action_url = runtime.resolved_notification_action_url
    str_value = runtime.str_value
    telegram_runtime_configuration = runtime.telegram_runtime_configuration
    configuration = configuration or telegram_runtime_configuration()
    if not configuration["configured"]:
        raise RuntimeError("Integração Telegram ainda não configurada no servidor.")
    recipient = normalize_telegram_recipient(delivery.get("recipient"))
    if not recipient:
        raise RuntimeError("Chat ID do Telegram inválido.")

    name = str_value(delivery.get("student_name")) or "Estudante"
    title = str_value(delivery.get("title"))[:180]
    body_message = str_value(delivery.get("message"))[:3000]
    action_url = resolved_notification_action_url(delivery, configuration)
    parse_mode = normalize_telegram_parse_mode(configuration.get("parseMode"))
    if parse_mode == "HTML":
        text = f"<b>{html_escape(title)}</b>\n\n{html_escape(name)},\n{html_escape(body_message)}"
        if action_url:
            text += f"\n\n{html_escape(action_url)}"
    elif parse_mode == "MarkdownV2":
        text = f"*{_telegram_markdown_v2(title)}*\n\n{_telegram_markdown_v2(name)},\n{_telegram_markdown_v2(body_message)}"
        if action_url:
            text += f"\n\n{_telegram_markdown_v2(action_url)}"
    else:
        text = f"{title}\n\n{name},\n{body_message}"
        if action_url:
            text += f"\n\n{action_url}"
    if len(text) > 4096:
        # Avoid cutting an HTML entity or a Markdown escape sequence. Oversized
        # formatted content is safely downgraded to plain text.
        parse_mode = ""
        text = f"{title}\n\n{name},\n{body_message}"
        if action_url:
            text += f"\n\n{action_url}"
    request_body: dict[str, Any] = {
        "chat_id": recipient,
        "text": text[:4096],
        "disable_web_page_preview": True,
    }
    if parse_mode:
        request_body["parse_mode"] = parse_mode
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{configuration['botToken']}/sendMessage",
        data=json.dumps(request_body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(3, int(configuration.get("timeoutSeconds") or 12)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("botToken"))
        raise RuntimeError(f"Telegram Bot API HTTP {error.code}: {safe_error}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        safe_error = redact_notification_error(error, configuration.get("botToken"))
        raise RuntimeError(f"Falha no envio pelo Telegram: {safe_error}") from error
    message_id = str_value((result.get("result") or {}).get("message_id")) if isinstance(result, dict) else ""
    if not isinstance(result, dict) or not result.get("ok") or not message_id:
        description = str_value(result.get("description")) if isinstance(result, dict) else "Resposta inválida"
        safe_error = redact_notification_error(description, configuration.get("botToken"))
        raise RuntimeError(f"A API do Telegram rejeitou a mensagem: {safe_error}")
    return message_id


def push_subscriptions_for_student_action(student_id: str, encryption_key: str, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    fetch_all = runtime.fetch_all
    return fetch_all(
        """
        select subscription_id,
               pgp_sym_decrypt(endpoint_encrypted, %s)::text as endpoint,
               pgp_sym_decrypt(p256dh_encrypted, %s)::text as p256dh,
               pgp_sym_decrypt(auth_encrypted, %s)::text as auth
        from courseplatform.push_subscriptions
        where student_id = %s and enabled
        order by updated_at desc
        """,
        (encryption_key, encryption_key, encryption_key, student_id),
    )


def update_push_subscription_delivery_action(subscription_id: str, success_result: bool, expired: bool = False, *, runtime: CommunicationRuntime) -> None:
    connection = runtime.connection
    with connection() as conn:
        if success_result:
            conn.execute(
                """
                update courseplatform.push_subscriptions
                set last_success_at = now(), failure_count = 0, updated_at = now()
                where subscription_id = %s
                """,
                (subscription_id,),
            )
        else:
            conn.execute(
                """
                update courseplatform.push_subscriptions
                set failure_count = failure_count + 1,
                    enabled = case when %s or failure_count >= 4 then false else enabled end,
                    updated_at = now()
                where subscription_id = %s
                """,
                (expired, subscription_id),
            )
        conn.commit()


def send_web_push_notification_action(delivery: dict[str, Any], configuration: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> str:
    push_subscriptions_for_student = runtime.push_subscriptions_for_student
    redact_notification_error = runtime.redact_notification_error
    resolved_notification_action_url = runtime.resolved_notification_action_url
    str_value = runtime.str_value
    student_unread_badge_count = runtime.student_unread_badge_count
    update_push_subscription_delivery = runtime.update_push_subscription_delivery
    web_push_runtime_configuration = runtime.web_push_runtime_configuration
    webpush = runtime.webpush
    configuration = configuration or web_push_runtime_configuration()
    if not configuration.get("configured") or webpush is None:
        raise RuntimeError("Integração Web Push ainda não configurada no servidor.")
    student_id = str_value(delivery.get("student_id") or delivery.get("recipient"))
    if not student_id:
        raise RuntimeError("Destinatário Push inválido.")
    subscriptions = push_subscriptions_for_student(student_id, configuration["encryptionKey"])
    if not subscriptions:
        raise RuntimeError("Nenhum dispositivo possui notificações Push ativas.")
    action_url = resolved_notification_action_url(delivery, configuration) or str_value(delivery.get("action_url")) or "#/notifications"
    payload = json.dumps({
        "title": str_value(delivery.get("push_title") or delivery.get("title"))[:120],
        "body": str_value(delivery.get("push_message") or delivery.get("message"))[:300],
        "url": action_url,
        "icon": "/assets/app-icon-192.png",
        "badge": "/assets/app-icon-192.png",
        "tag": f"courseplatform-{str_value(delivery.get('notification_id'))[:80]}",
        "notificationId": str_value(delivery.get("notification_id")),
        "priority": str_value(delivery.get("priority") or "NORMAL"),
        "badgeCount": student_unread_badge_count(student_id),
    }, ensure_ascii=False)
    delivered = 0
    failures: list[str] = []
    for subscription in subscriptions:
        try:
            response = webpush(
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {"p256dh": subscription["p256dh"], "auth": subscription["auth"]},
                },
                data=payload,
                vapid_private_key=configuration["privateKey"],
                vapid_claims={"sub": configuration["subject"]},
                ttl=configuration["ttlSeconds"],
                timeout=configuration["timeoutSeconds"],
            )
            status_code = int(getattr(response, "status_code", 201) or 201)
            if status_code >= 400:
                raise RuntimeError(f"Serviço Push HTTP {status_code}.")
            delivered += 1
            update_push_subscription_delivery(subscription["subscription_id"], True)
        except Exception as error:
            response = getattr(error, "response", None)
            status_code = int(getattr(response, "status_code", 0) or 0)
            expired = status_code in {404, 410}
            update_push_subscription_delivery(subscription["subscription_id"], False, expired)
            failures.append(redact_notification_error(error, subscription.get("endpoint")))
    if not delivered:
        raise RuntimeError(failures[-1] if failures else "A notificação Push não foi entregue.")
    return f"{delivered} dispositivo(s)"


def student_unread_badge_count_action(student_id: str, *, runtime: CommunicationRuntime) -> int:
    connection = runtime.connection
    """Return the exact application badge without exposing private content."""
    try:
        with connection() as conn:
            notifications = conn.execute(
                """
                select count(*) as count
                from courseplatform.notifications
                where student_id = %s and read_at is null
                """,
                (student_id,),
            ).fetchone() or {}
            messages = conn.execute(
                """
                select count(*) as count
                from courseplatform.chat_messages message
                join courseplatform.chat_rooms room on room.room_id = message.room_id
                left join courseplatform.chat_reads room_read
                  on room_read.room_id = room.room_id and room_read.student_id = %s
                where message.status = 'ACTIVE'
                  and room.status = 'ACTIVE'
                  and message.sender_student_id is distinct from %s
                  and message.created_at > coalesce(room_read.last_read_at, 'epoch'::timestamptz)
                  and (
                    room.room_type = 'COMMUNITY'
                    or (room.room_type = 'SUPPORT' and room.owner_student_id = %s)
                    or (
                      room.room_type = 'DIRECT'
                      and (room.direct_student_one_id = %s or room.direct_student_two_id = %s)
                    )
                    or (
                      room.room_type = 'COURSE'
                      and exists (
                        select 1 from courseplatform.enrollments enrollment
                        where enrollment.student_id = %s
                          and enrollment.course_id = room.course_id
                          and enrollment.status in ('ACTIVE', 'COMPLETED')
                      )
                    )
                    or (
                      room.room_type = 'GROUP'
                      and (
                        exists (
                          select 1 from courseplatform.group_members member
                          where member.student_id = %s
                            and member.group_id = room.group_id
                            and member.status = 'ACTIVE'
                        )
                        or exists (
                          select 1 from courseplatform.enrollments enrollment
                          where enrollment.student_id = %s
                            and enrollment.group_id = room.group_id
                            and enrollment.status in ('ACTIVE', 'COMPLETED')
                        )
                      )
                    )
                  )
                """,
                (
                    student_id, student_id, student_id, student_id,
                    student_id, student_id, student_id, student_id,
                ),
            ).fetchone() or {}
        return max(0, int(notifications.get("count") or 0) + int(messages.get("count") or 0))
    except Exception:
        # An older schema must not prevent delivery while the application is
        # being upgraded. The open client reconciles the exact value.
        return 0


def telegram_get_updates_action(configuration: dict[str, Any], offset: int = 0, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    redact_notification_error = runtime.redact_notification_error
    str_value = runtime.str_value
    """Read pending bot updates without long polling (used by account linking)."""
    if not configuration.get("configured"):
        raise RuntimeError("Integração Telegram ainda não configurada no servidor.")
    query = urlencode({
        "offset": max(0, int(offset)),
        "limit": 100,
        "timeout": 0,
        "allowed_updates": json.dumps(["message"]),
    })
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{configuration['botToken']}/getUpdates?{query}",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=max(3, int(configuration.get("timeoutSeconds") or 12)),
        ) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")[:700]
        safe_error = redact_notification_error(response_text, configuration.get("botToken"))
        raise RuntimeError(f"Telegram Bot API HTTP {error.code}: {safe_error}") from error
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        safe_error = redact_notification_error(error, configuration.get("botToken"))
        raise RuntimeError(f"Falha ao confirmar a ligação ao Telegram: {safe_error}") from error
    updates = result.get("result") if isinstance(result, dict) else None
    if not isinstance(result, dict) or not result.get("ok") or not isinstance(updates, list):
        description = str_value(result.get("description")) if isinstance(result, dict) else "Resposta inválida"
        safe_error = redact_notification_error(description, configuration.get("botToken"))
        raise RuntimeError(f"A API do Telegram rejeitou a consulta: {safe_error}")
    return [item for item in updates if isinstance(item, dict)]


def process_telegram_link_updates_action(configuration: dict[str, Any] | None = None, *, runtime: CommunicationRuntime) -> int:
    audit = runtime.audit
    connection = runtime.connection
    fetch_one = runtime.fetch_one
    hash_secret = runtime.hash_secret
    int_value = runtime.int_value
    normalize_telegram_recipient = runtime.normalize_telegram_recipient
    str_value = runtime.str_value
    telegram_get_updates = runtime.telegram_get_updates
    telegram_runtime_configuration = runtime.telegram_runtime_configuration
    """Associate every valid /start token in the queue before advancing its offset."""
    configuration = configuration or telegram_runtime_configuration()
    state = fetch_one(
        "select cursor_value from courseplatform.notification_channel_state where channel = 'TELEGRAM'"
    ) or {}
    offset = int_value(state.get("cursor_value"))
    updates = telegram_get_updates(configuration, offset)
    if not updates:
        return 0
    linked = 0
    highest_update_id = offset - 1
    with connection() as conn:
        for update in updates:
            update_id = int_value(update.get("update_id"), -1)
            highest_update_id = max(highest_update_id, update_id)
            message = update.get("message") if isinstance(update.get("message"), dict) else {}
            chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
            match = re.fullmatch(
                r"/start(?:@[A-Za-z0-9_]+)?\s+([A-Za-z0-9_-]{20,64})",
                str_value(message.get("text")),
            )
            chat_id = normalize_telegram_recipient(chat.get("id"))
            if not match or not chat_id or str_value(chat.get("type")) != "private":
                continue
            token_hash = hash_secret(match.group(1))
            link = conn.execute(
                """
                select * from courseplatform.telegram_link_tokens
                where token_hash = %s and consumed_at is null and expires_at > now()
                for update
                """,
                (token_hash,),
            ).fetchone()
            if not link:
                continue
            conn.execute(
                """
                update courseplatform.students
                set telegram_chat_id = %s, telegram_opt_in = true,
                    telegram_opt_in_at = coalesce(telegram_opt_in_at, now()), updated_at = now()
                where student_id = %s
                """,
                (chat_id, link["student_id"]),
            )
            conn.execute(
                """
                update courseplatform.telegram_link_tokens
                set consumed_at = now(), telegram_update_id = %s
                where token_hash = %s
                """,
                (update_id, token_hash),
            )
            audit(
                conn,
                "STUDENT",
                link["student_id"],
                "TELEGRAM_LINKED",
                "STUDENT",
                link["student_id"],
                {"channel": "TELEGRAM"},
            )
            linked += 1
        if highest_update_id >= offset:
            conn.execute(
                """
                insert into courseplatform.notification_channel_state(channel, cursor_value, updated_at)
                values ('TELEGRAM', %s, now())
                on conflict (channel) do update set
                  cursor_value = greatest(courseplatform.notification_channel_state.cursor_value, excluded.cursor_value),
                  updated_at = now()
                """,
                (highest_update_id + 1,),
            )
        conn.commit()
    return linked


def claim_notification_deliveries_action(
    channel: str,
    notification_ids: list[str] | None,
    limit: int,
    *,
    runtime: CommunicationRuntime,
) -> list[dict[str, Any]]:
    connection = runtime.connection
    str_value = runtime.str_value
    """Atomically lease one channel's queue so workers cannot send duplicates."""
    normalized_channel = str_value(channel).upper()
    if normalized_channel not in {"WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"}:
        raise ValueError("Canal de notificação inválido.")
    notification_filter = ""
    params: list[Any] = [normalized_channel]
    if notification_ids:
        notification_filter = " and d.notification_id = any(%s)"
        params.append(notification_ids)
    params.append(max(1, min(int(limit), 200)))
    query = f"""
        with candidates as (
          select d.delivery_id
          from courseplatform.notification_deliveries d
          where d.channel = %s
            and (
              d.status in ('PENDING', 'FAILED')
              or (
                d.status = 'PROCESSING'
                and coalesce(d.updated_at, d.created_at) < now() - interval '5 minutes'
              )
            )
            and d.attempt_count < 3
            {notification_filter}
          order by d.created_at
          limit %s
          for update of d skip locked
        ), claimed as (
          update courseplatform.notification_deliveries d
          set status = 'PROCESSING',
              attempt_count = d.attempt_count + 1,
              last_error = null,
              updated_at = now()
          from candidates c
          where d.delivery_id = c.delivery_id
          returning d.*
        )
        select claimed.*, n.student_id, n.notification_id, n.title, n.message,
               n.email_subject, n.email_message, n.push_title, n.push_message,
               n.action_url, n.priority, s.full_name as student_name
        from claimed
        join courseplatform.notifications n on n.notification_id = claimed.notification_id
        join courseplatform.students s on s.student_id = n.student_id
        order by claimed.created_at
    """
    with connection() as conn:
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.commit()
    return rows


def claim_whatsapp_deliveries_action(notification_ids: list[str] | None, limit: int, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    claim_notification_deliveries = runtime.claim_notification_deliveries
    return claim_notification_deliveries("WHATSAPP", notification_ids, limit)


def claim_email_deliveries_action(notification_ids: list[str] | None, limit: int, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    claim_notification_deliveries = runtime.claim_notification_deliveries
    return claim_notification_deliveries("EMAIL", notification_ids, limit)


def claim_telegram_deliveries_action(notification_ids: list[str] | None, limit: int, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    claim_notification_deliveries = runtime.claim_notification_deliveries
    return claim_notification_deliveries("TELEGRAM", notification_ids, limit)


def claim_push_deliveries_action(notification_ids: list[str] | None, limit: int, *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    claim_notification_deliveries = runtime.claim_notification_deliveries
    return claim_notification_deliveries("PUSH", notification_ids, limit)


def deliver_pending_channel_action(
    channel: str,
    configuration_loader,
    sender,
    notification_ids: list[str] | None = None,
    limit: int = 50,
    *,
    runtime: CommunicationRuntime,
) -> dict[str, int]:
    claim_notification_deliveries = runtime.claim_notification_deliveries
    connection = runtime.connection
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    redact_notification_error = runtime.redact_notification_error
    configuration = configuration_loader()
    if not configuration["configured"]:
        return {"sent": 0, "failed": 0, "pending": 0}
    prepare_notification_feature_schema()
    rows = claim_notification_deliveries(channel, notification_ids, limit)
    delivery_results: list[tuple[dict[str, Any], str, str]] = []
    if rows:
        worker_count = min(5, len(rows))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            futures = {executor.submit(sender, delivery, configuration): delivery for delivery in rows}
            for future in as_completed(futures):
                delivery = futures[future]
                try:
                    delivery_results.append((delivery, "SENT", future.result()))
                except Exception as error:
                    delivery_results.append((
                        delivery,
                        "FAILED",
                        redact_notification_error(
                            error,
                            configuration.get("accessToken"),
                            configuration.get("smtpPassword"),
                            configuration.get("botToken"),
                            configuration.get("privateKey"),
                            configuration.get("encryptionKey"),
                        ),
                    ))

    sent = 0
    failed = 0
    with connection() as conn:
        for delivery, result_status, result_value in delivery_results:
            if result_status == "SENT":
                conn.execute(
                    """
                    update courseplatform.notification_deliveries
                    set status = 'SENT', provider_message_id = %s,
                        last_error = null, sent_at = now(), updated_at = now()
                    where delivery_id = %s and status = 'PROCESSING'
                    """,
                    (result_value or None, delivery["delivery_id"]),
                )
                sent += 1
            else:
                conn.execute(
                    """
                    update courseplatform.notification_deliveries
                    set status = 'FAILED', last_error = %s, updated_at = now()
                    where delivery_id = %s and status = 'PROCESSING'
                    """,
                    (result_value, delivery["delivery_id"]),
                )
                failed += 1
        conn.commit()
    return {"sent": sent, "failed": failed, "pending": max(0, len(rows) - sent - failed)}


def deliver_pending_whatsapp_action(notification_ids: list[str] | None = None, limit: int = 50, *, runtime: CommunicationRuntime) -> dict[str, int]:
    deliver_pending_channel = runtime.deliver_pending_channel
    send_whatsapp_template = runtime.send_whatsapp_template
    whatsapp_runtime_configuration = runtime.whatsapp_runtime_configuration
    return deliver_pending_channel(
        "WHATSAPP", whatsapp_runtime_configuration, send_whatsapp_template,
        notification_ids, limit,
    )


def deliver_pending_email_action(notification_ids: list[str] | None = None, limit: int = 50, *, runtime: CommunicationRuntime) -> dict[str, int]:
    deliver_pending_channel = runtime.deliver_pending_channel
    email_runtime_configuration = runtime.email_runtime_configuration
    send_email_notification = runtime.send_email_notification
    return deliver_pending_channel(
        "EMAIL", email_runtime_configuration, send_email_notification,
        notification_ids, limit,
    )


def deliver_pending_telegram_action(notification_ids: list[str] | None = None, limit: int = 50, *, runtime: CommunicationRuntime) -> dict[str, int]:
    deliver_pending_channel = runtime.deliver_pending_channel
    send_telegram_notification = runtime.send_telegram_notification
    telegram_runtime_configuration = runtime.telegram_runtime_configuration
    return deliver_pending_channel(
        "TELEGRAM", telegram_runtime_configuration, send_telegram_notification,
        notification_ids, limit,
    )


def deliver_pending_push_action(notification_ids: list[str] | None = None, limit: int = 50, *, runtime: CommunicationRuntime) -> dict[str, int]:
    deliver_pending_channel = runtime.deliver_pending_channel
    send_web_push_notification = runtime.send_web_push_notification
    web_push_runtime_configuration = runtime.web_push_runtime_configuration
    return deliver_pending_channel(
        "PUSH", web_push_runtime_configuration, send_web_push_notification,
        notification_ids, limit,
    )


def dispatch_notification_deliveries_action(notification_ids: list[str], *, runtime: CommunicationRuntime) -> None:
    deliver_pending_email = runtime.deliver_pending_email
    deliver_pending_push = runtime.deliver_pending_push
    deliver_pending_telegram = runtime.deliver_pending_telegram
    deliver_pending_whatsapp = runtime.deliver_pending_whatsapp
    if not notification_ids:
        return
    for delivery_function in (
        deliver_pending_whatsapp,
        deliver_pending_email,
        deliver_pending_telegram,
        deliver_pending_push,
    ):
        try:
            # Keep the request bounded while covering a typical class in one
            # operation. Larger campaigns remain safely queued and are exposed
            # through the administrative retry control.
            delivery_function(notification_ids, limit=20)
        except Exception:
            # Internal notifications are the source of truth; a provider outage
            # must never roll back the administrative transaction.
            continue


def ensure_chat_feature_schema_action(conn, *, runtime: CommunicationRuntime) -> None:
    require_schema_capabilities = runtime.require_schema_capabilities
    global _CHAT_SCHEMA_READY
    if _CHAT_SCHEMA_READY:
        return
    require_schema_capabilities(
        conn,
        "chat",
        (
            "courseplatform.chat_rooms",
            "courseplatform.chat_messages",
            "courseplatform.chat_reads",
            "courseplatform.chat_message_receipts",
            "courseplatform.chat_presence",
            "courseplatform.chat_message_reports",
        ),
        (
            "courseplatform.chat_rooms.direct_student_one_id",
            "courseplatform.chat_rooms.direct_student_two_id",
        ),
    )
    _CHAT_SCHEMA_READY = True


def prepare_chat_feature_schema_action(*, runtime: CommunicationRuntime) -> None:
    connection = runtime.connection
    ensure_chat_feature_schema = runtime.ensure_chat_feature_schema
    if _CHAT_SCHEMA_READY:
        return
    with connection() as conn:
        ensure_chat_feature_schema(conn)


def ensure_chat_realtime_schema_action(conn, *, runtime: CommunicationRuntime) -> bool:
    if _CHAT_REALTIME_SCHEMA_READY:
        return True
    capabilities = conn.execute(
        """
        select
          to_regclass('realtime.messages') is not null as messages_ready,
          exists (
            select 1 from pg_proc procedure
            join pg_namespace namespace on namespace.oid = procedure.pronamespace
            where namespace.nspname = 'realtime' and procedure.proname = 'send'
          ) as broadcast_ready,
          exists (
            select 1 from pg_proc procedure
            join pg_namespace namespace on namespace.oid = procedure.pronamespace
            where namespace.nspname = 'realtime' and procedure.proname = 'topic'
          ) as topic_ready,
          exists (
            select 1 from pg_proc procedure
            join pg_namespace namespace on namespace.oid = procedure.pronamespace
            where namespace.nspname = 'courseplatform'
              and procedure.proname = 'chat_realtime_topic_allowed'
              and pg_get_functiondef(procedure.oid) like '%chat:actor:%'
              and pg_get_functiondef(procedure.oid) like '%active_group.status%'
          ) as access_policy_function_ready,
          exists (
            select 1 from pg_proc procedure
            join pg_namespace namespace on namespace.oid = procedure.pronamespace
            where namespace.nspname = 'courseplatform'
              and procedure.proname = 'broadcast_chat_message_change'
              and pg_get_functiondef(procedure.oid) like '%ROOMS_CHANGED%'
              and pg_get_functiondef(procedure.oid) like '%realtime.send%'
          ) as broadcast_function_ready,
          exists (
            select 1 from pg_trigger trigger_row
            where trigger_row.tgrelid = 'courseplatform.chat_messages'::regclass
              and trigger_row.tgname = 'chat_messages_realtime_broadcast'
              and not trigger_row.tgisinternal
          ) as trigger_ready,
          exists (
            select 1 from pg_policies
            where schemaname = 'realtime'
              and tablename = 'messages'
              and policyname = 'courseplatform_chat_broadcast_select'
          ) as rls_policy_ready
        """
    ).fetchone() or {}
    return all(capabilities.get(key) for key in (
        "messages_ready",
        "broadcast_ready",
        "topic_ready",
        "access_policy_function_ready",
        "broadcast_function_ready",
        "trigger_ready",
        "rls_policy_ready",
    ))


def _jwt_segment_action(value: dict[str, Any], *, runtime: CommunicationRuntime) -> str:
    encoded = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def chat_realtime_token_action(actor: dict[str, Any], secret: str, lifetime_minutes: int, *, runtime: CommunicationRuntime) -> tuple[str, datetime]:
    _jwt_segment = runtime._jwt_segment
    utc_now = runtime.utc_now
    issued_at = utc_now()
    expires_at = issued_at + timedelta(minutes=max(5, min(int(lifetime_minutes or 30), 120)))
    header = _jwt_segment({"alg": "HS256", "typ": "JWT"})
    claims = _jwt_segment({
        "sub": f"{actor['type'].lower()}:{actor['id']}",
        "role": "authenticated",
        "aud": "authenticated",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "actor_type": actor["type"],
        "actor_id": actor["id"],
    })
    signing_input = f"{header}.{claims}".encode("ascii")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    return f"{header}.{claims}.{signature}", expires_at


def student_push_configuration_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    fetch_one = runtime.fetch_one
    iso = runtime.iso
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    student_context = runtime.student_context
    success = runtime.success
    web_push_configuration = runtime.web_push_configuration
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = web_push_configuration()
    subscription = fetch_one(
        """
        select count(*) as count, max(updated_at) as updated_at
        from courseplatform.push_subscriptions
        where student_id = %s and enabled
        """,
        (student["student_id"],),
    ) or {}
    return success({
        "pushConfiguration": configuration,
        "subscriptionCount": int(subscription.get("count") or 0),
        "updatedAt": iso(subscription.get("updated_at")),
    })


def student_subscribe_push_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    generate_id = runtime.generate_id
    hash_secret = runtime.hash_secret
    iso = runtime.iso
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    valid_push_endpoint = runtime.valid_push_endpoint
    valid_push_key = runtime.valid_push_key
    web_push_runtime_configuration = runtime.web_push_runtime_configuration
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = web_push_runtime_configuration()
    if not configuration.get("configured"):
        raise ApiError(
            "WEB_PUSH_NOT_CONFIGURED",
            "As notificações Push ainda não estão configuradas no servidor.",
        )
    subscription = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload
    endpoint = str_value(subscription.get("endpoint"))
    keys = subscription.get("keys") if isinstance(subscription.get("keys"), dict) else {}
    p256dh = str_value(keys.get("p256dh") or subscription.get("p256dh"))
    auth_key = str_value(keys.get("auth") or subscription.get("auth"))
    if not valid_push_endpoint(endpoint):
        raise ApiError("INVALID_PUSH_ENDPOINT", "A subscrição Push possui um endereço inválido.")
    if not valid_push_key(p256dh, 60, 200) or not valid_push_key(auth_key, 10, 100):
        raise ApiError("INVALID_PUSH_KEYS", "As chaves da subscrição Push são inválidas.")
    encryption_key = str_value(configuration.get("encryptionKey"))
    if len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    endpoint_hash = hash_secret(endpoint)
    device_label = str_value(payload.get("deviceLabel"))[:120]
    user_agent = str_value(payload.get("userAgent"))[:500]
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.push_subscriptions
              (subscription_id, student_id, endpoint_hash, endpoint_encrypted,
               p256dh_encrypted, auth_encrypted, user_agent, device_label,
               enabled, failure_count, created_at, updated_at)
            values (
              %s, %s, %s,
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256'),
              %s, %s, true, 0, now(), now()
            )
            on conflict (endpoint_hash) do update set
              student_id = excluded.student_id,
              endpoint_encrypted = excluded.endpoint_encrypted,
              p256dh_encrypted = excluded.p256dh_encrypted,
              auth_encrypted = excluded.auth_encrypted,
              user_agent = excluded.user_agent,
              device_label = excluded.device_label,
              enabled = true,
              failure_count = 0,
              updated_at = now()
            returning subscription_id, device_label, enabled, created_at, updated_at
            """,
            (
                generate_id("PSH"), student["student_id"], endpoint_hash,
                endpoint, encryption_key, p256dh, encryption_key, auth_key, encryption_key,
                user_agent or None, device_label or None,
            ),
        ).fetchone()
        audit(
            conn, "STUDENT", student["student_id"], "PUSH_SUBSCRIBED",
            "PUSH_SUBSCRIPTION", row["subscription_id"],
            {"deviceLabel": device_label, "endpointHash": endpoint_hash[:16]},
        )
        conn.commit()
    return success({
        "subscribed": True,
        "subscription": {
            "subscriptionId": row["subscription_id"],
            "deviceLabel": row.get("device_label") or "",
            "enabled": as_bool(row.get("enabled")),
            "updatedAt": iso(row.get("updated_at")),
        },
    })


def student_unsubscribe_push_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    hash_secret = runtime.hash_secret
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    endpoint = str_value(payload.get("endpoint"))
    all_devices = as_bool(payload.get("allDevices"))
    if not endpoint and not all_devices:
        raise ApiError("PUSH_SUBSCRIPTION_REQUIRED", "Informe a subscrição Push deste dispositivo.")
    with connection() as conn:
        if all_devices:
            result = conn.execute(
                """
                update courseplatform.push_subscriptions
                set enabled = false, updated_at = now()
                where student_id = %s and enabled
                """,
                (student["student_id"],),
            )
        else:
            result = conn.execute(
                """
                update courseplatform.push_subscriptions
                set enabled = false, updated_at = now()
                where student_id = %s and endpoint_hash = %s and enabled
                """,
                (student["student_id"], hash_secret(endpoint)),
            )
        audit(
            conn, "STUDENT", student["student_id"], "PUSH_UNSUBSCRIBED",
            "PUSH_SUBSCRIPTION", "ALL" if all_devices else hash_secret(endpoint)[:16],
            {"allDevices": all_devices, "updatedCount": result.rowcount},
        )
        conn.commit()
    return success({"unsubscribed": True, "updatedCount": result.rowcount})


def student_start_telegram_link_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    connection = runtime.connection
    hash_secret = runtime.hash_secret
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    telegram_runtime_configuration = runtime.telegram_runtime_configuration
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    configuration = telegram_runtime_configuration()
    bot_username = str_value(configuration.get("botUsername")).lstrip("@")
    if not configuration.get("configured") or not bot_username:
        raise ApiError(
            "TELEGRAM_LINK_UNAVAILABLE",
            "A ligação ao Telegram ainda não está disponível. Contacte a administração.",
        )
    token = secrets.token_urlsafe(24)
    with connection() as conn:
        conn.execute(
            """
            update courseplatform.telegram_link_tokens
            set consumed_at = coalesce(consumed_at, now())
            where student_id = %s and consumed_at is null
            """,
            (student["student_id"],),
        )
        conn.execute(
            """
            insert into courseplatform.telegram_link_tokens
              (token_hash, student_id, expires_at, created_at)
            values (%s, %s, now() + interval '15 minutes', now())
            """,
            (hash_secret(token), student["student_id"]),
        )
        conn.commit()
    return success({
        "linkUrl": f"https://t.me/{bot_username}?start={token}",
        "linkToken": token,
        "botUsername": bot_username,
        "expiresInSeconds": 900,
    })


def student_confirm_telegram_link_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    fetch_one = runtime.fetch_one
    hash_secret = runtime.hash_secret
    normalize_telegram_recipient = runtime.normalize_telegram_recipient
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    process_telegram_link_updates = runtime.process_telegram_link_updates
    public_student = runtime.public_student
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    link_token = str_value(payload.get("linkToken"))
    if not re.fullmatch(r"[A-Za-z0-9_-]{20,64}", link_token):
        raise ApiError("INVALID_TELEGRAM_LINK_TOKEN", "A ligação ao Telegram é inválida ou expirou.")
    pending = fetch_one(
        """
        select token_hash from courseplatform.telegram_link_tokens
        where token_hash = %s and student_id = %s and consumed_at is null and expires_at > now()
        """,
        (hash_secret(link_token), student["student_id"]),
    )
    if not pending:
        raise ApiError("TELEGRAM_LINK_EXPIRED", "A ligação ao Telegram é inválida ou expirou. Gere uma nova ligação.")
    try:
        process_telegram_link_updates()
    except RuntimeError as error:
        raise ApiError("TELEGRAM_LINK_CHECK_FAILED", str(error)) from error
    linked_student = fetch_one(
        "select * from courseplatform.students where student_id = %s",
        (student["student_id"],),
    ) or student
    consumed = fetch_one(
        "select consumed_at from courseplatform.telegram_link_tokens where token_hash = %s and student_id = %s",
        (hash_secret(link_token), student["student_id"]),
    ) or {}
    if not consumed.get("consumed_at") or not normalize_telegram_recipient(linked_student.get("telegram_chat_id")):
        return success({
            "linked": False,
            "student": public_student(linked_student),
            "message": "Abra o bot, toque em Iniciar e volte a confirmar.",
        })
    return success({"linked": True, "student": public_student(linked_student)})


def student_unlink_telegram_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    audit = runtime.audit
    connection = runtime.connection
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_student = runtime.public_student
    student_context = runtime.student_context
    success = runtime.success
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    with connection() as conn:
        row = conn.execute(
            """
            update courseplatform.students
            set telegram_chat_id = null, telegram_opt_in = false,
                telegram_opt_in_at = null, updated_at = now()
            where student_id = %s
            returning *
            """,
            (student["student_id"],),
        ).fetchone()
        conn.execute(
            """
            update courseplatform.telegram_link_tokens
            set consumed_at = coalesce(consumed_at, now())
            where student_id = %s and consumed_at is null
            """,
            (student["student_id"],),
        )
        audit(
            conn,
            "STUDENT",
            student["student_id"],
            "TELEGRAM_UNLINKED",
            "STUDENT",
            student["student_id"],
            {"channel": "TELEGRAM"},
        )
        conn.commit()
    return success({"unlinked": True, "student": public_student(row)})


def my_notifications_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    as_bool = runtime.as_bool
    fetch_all = runtime.fetch_all
    fetch_one = runtime.fetch_one
    pagination = runtime.pagination
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_notification = runtime.public_notification
    student_context = runtime.student_context
    success = runtime.success
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    limit, offset, page = pagination(payload, default_limit=40, max_limit=100)
    unread_only = as_bool(payload.get("unreadOnly"))
    where_unread = "and n.read_at is null" if unread_only else ""
    rows = fetch_all(
        f"""
        select n.*,
               w.status as whatsapp_status, w.recipient as whatsapp_recipient,
               w.provider_message_id as whatsapp_provider_message_id,
               w.attempt_count as whatsapp_attempt_count, w.last_error as whatsapp_last_error,
               w.sent_at as whatsapp_sent_at,
               e.status as email_status, e.recipient as email_recipient,
               e.provider_message_id as email_provider_message_id,
               e.attempt_count as email_attempt_count, e.last_error as email_last_error,
               e.sent_at as email_sent_at,
               t.status as telegram_status, t.recipient as telegram_recipient,
               t.provider_message_id as telegram_provider_message_id,
               t.attempt_count as telegram_attempt_count, t.last_error as telegram_last_error,
               t.sent_at as telegram_sent_at,
               p.status as push_status,
               p.provider_message_id as push_provider_message_id,
               p.attempt_count as push_attempt_count, p.last_error as push_last_error,
               p.sent_at as push_sent_at
        from courseplatform.notifications n
        left join courseplatform.notification_deliveries w
          on w.notification_id = n.notification_id and w.channel = 'WHATSAPP'
        left join courseplatform.notification_deliveries e
          on e.notification_id = n.notification_id and e.channel = 'EMAIL'
        left join courseplatform.notification_deliveries t
          on t.notification_id = n.notification_id and t.channel = 'TELEGRAM'
        left join courseplatform.notification_deliveries p
          on p.notification_id = n.notification_id and p.channel = 'PUSH'
        where n.student_id = %s {where_unread}
        order by n.created_at desc
        limit %s offset %s
        """,
        (student["student_id"], limit, offset),
    )
    unread = fetch_one(
        "select count(*) as count from courseplatform.notifications where student_id = %s and read_at is null",
        (student["student_id"],),
    )
    total = fetch_one(
        "select count(*) as count from courseplatform.notifications where student_id = %s",
        (student["student_id"],),
    )
    return success({
        "notifications": [public_notification(row) for row in rows],
        "unreadCount": int((unread or {}).get("count") or 0),
        "total": int((total or {}).get("count") or 0),
        "page": page,
        "limit": limit,
    })


def mark_notification_read_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    as_bool = runtime.as_bool
    connection = runtime.connection
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    student_context = runtime.student_context
    success = runtime.success
    prepare_notification_feature_schema()
    _, student = student_context(payload)
    notification_id = str_value(payload.get("notificationId"))
    mark_all = as_bool(payload.get("markAll"))
    if not notification_id and not mark_all:
        raise ApiError("NOTIFICATION_REQUIRED", "Selecione uma notificação.")
    with connection() as conn:
        if mark_all:
            result = conn.execute(
                "update courseplatform.notifications set read_at = coalesce(read_at, now()) where student_id = %s",
                (student["student_id"],),
            )
        else:
            result = conn.execute(
                """
                update courseplatform.notifications
                set read_at = coalesce(read_at, now())
                where notification_id = %s and student_id = %s
                """,
                (notification_id, student["student_id"]),
            )
        updated_count = result.rowcount
        conn.commit()
    return success({"updatedCount": updated_count})


def admin_list_notifications_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    email_configuration = runtime.email_configuration
    fetch_all = runtime.fetch_all
    fetch_one = runtime.fetch_one
    notification_templates_payload = runtime.notification_templates_payload
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_notification = runtime.public_notification
    str_value = runtime.str_value
    success = runtime.success
    telegram_configuration = runtime.telegram_configuration
    web_push_configuration = runtime.web_push_configuration
    whatsapp_configuration = runtime.whatsapp_configuration
    _, _admin = admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"})
    prepare_notification_feature_schema()
    limit = cursor_page_limit(payload, default_limit=80, max_limit=200)
    query = str_value(payload.get("query")).lower()
    category = str_value(payload.get("category") or "ALL").upper()
    scope = cursor_scope("admin-notifications", category, query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-notifications", scope)
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_at, cursor_id = cursor
        cursor_sql = "and (n.created_at < %s or (n.created_at = %s and n.notification_id < %s))"
        cursor_params.extend((cursor_at, cursor_at, cursor_id))
    rows = fetch_all(
        f"""
        select n.*, s.full_name as student_name,
               n.created_at as pagination_sort_at,
               w.status as whatsapp_status, w.recipient as whatsapp_recipient,
               w.provider_message_id as whatsapp_provider_message_id,
               w.attempt_count as whatsapp_attempt_count, w.last_error as whatsapp_last_error,
               w.sent_at as whatsapp_sent_at,
               e.status as email_status, e.recipient as email_recipient,
               e.provider_message_id as email_provider_message_id,
               e.attempt_count as email_attempt_count, e.last_error as email_last_error,
               e.sent_at as email_sent_at,
               t.status as telegram_status, t.recipient as telegram_recipient,
               t.provider_message_id as telegram_provider_message_id,
               t.attempt_count as telegram_attempt_count, t.last_error as telegram_last_error,
               t.sent_at as telegram_sent_at,
               p.status as push_status,
               p.provider_message_id as push_provider_message_id,
               p.attempt_count as push_attempt_count, p.last_error as push_last_error,
               p.sent_at as push_sent_at
        from courseplatform.notifications n
        join courseplatform.students s on s.student_id = n.student_id
        left join courseplatform.notification_deliveries w
          on w.notification_id = n.notification_id and w.channel = 'WHATSAPP'
        left join courseplatform.notification_deliveries e
          on e.notification_id = n.notification_id and e.channel = 'EMAIL'
        left join courseplatform.notification_deliveries t
          on t.notification_id = n.notification_id and t.channel = 'TELEGRAM'
        left join courseplatform.notification_deliveries p
          on p.notification_id = n.notification_id and p.channel = 'PUSH'
        where (%s = 'ALL' or n.category = %s)
          and (%s = '' or lower(coalesce(s.full_name, '') || ' ' || coalesce(n.title, '') || ' ' || coalesce(n.message, '')) like %s)
          {cursor_sql}
        order by n.created_at desc, n.notification_id desc
        limit %s
        """,
        (category, category, query, f"%{query}%", *cursor_params, limit + 1),
    )
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-notifications", scope, "pagination_sort_at", "notification_id"
    )
    totals = fetch_one(
        """
        select
          (select count(*) from courseplatform.notifications) as internal_total,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'SENT') as whatsapp_sent,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status in ('PENDING', 'PROCESSING')) as whatsapp_pending,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'FAILED') as whatsapp_failed,
          count(*) filter (where d.channel = 'WHATSAPP' and d.status = 'SKIPPED') as whatsapp_skipped,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'SENT') as email_sent,
          count(*) filter (where d.channel = 'EMAIL' and d.status in ('PENDING', 'PROCESSING')) as email_pending,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'FAILED') as email_failed,
          count(*) filter (where d.channel = 'EMAIL' and d.status = 'SKIPPED') as email_skipped,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'SENT') as telegram_sent,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status in ('PENDING', 'PROCESSING')) as telegram_pending,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'FAILED') as telegram_failed,
          count(*) filter (where d.channel = 'TELEGRAM' and d.status = 'SKIPPED') as telegram_skipped,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'SENT') as push_sent,
          count(*) filter (where d.channel = 'PUSH' and d.status in ('PENDING', 'PROCESSING')) as push_pending,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'FAILED') as push_failed,
          count(*) filter (where d.channel = 'PUSH' and d.status = 'SKIPPED') as push_skipped
        from courseplatform.notification_deliveries d
        """
    ) or {}
    return success({
        "notifications": [public_notification(row) for row in rows],
        "summary": {
            "internalTotal": int(totals.get("internal_total") or 0),
            "whatsappSent": int(totals.get("whatsapp_sent") or 0),
            "whatsappPending": int(totals.get("whatsapp_pending") or 0),
            "whatsappFailed": int(totals.get("whatsapp_failed") or 0),
            "whatsappSkipped": int(totals.get("whatsapp_skipped") or 0),
            "emailSent": int(totals.get("email_sent") or 0),
            "emailPending": int(totals.get("email_pending") or 0),
            "emailFailed": int(totals.get("email_failed") or 0),
            "emailSkipped": int(totals.get("email_skipped") or 0),
            "telegramSent": int(totals.get("telegram_sent") or 0),
            "telegramPending": int(totals.get("telegram_pending") or 0),
            "telegramFailed": int(totals.get("telegram_failed") or 0),
            "telegramSkipped": int(totals.get("telegram_skipped") or 0),
            "pushSent": int(totals.get("push_sent") or 0),
            "pushPending": int(totals.get("push_pending") or 0),
            "pushFailed": int(totals.get("push_failed") or 0),
            "pushSkipped": int(totals.get("push_skipped") or 0),
        },
        "whatsappConfiguration": whatsapp_configuration(),
        "emailConfiguration": email_configuration(),
        "telegramConfiguration": telegram_configuration(),
        "pushConfiguration": web_push_configuration(),
        "notificationTemplates": notification_templates_payload(),
        "limit": limit,
        "pagination": page_info,
    })


def admin_create_notification_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    create_student_notification = runtime.create_student_notification
    dispatch_notification_deliveries = runtime.dispatch_notification_deliveries
    fetch_all = runtime.fetch_all
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    require_fields = runtime.require_fields
    safe_notification_action_url = runtime.safe_notification_action_url
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    require_fields(payload, ["title", "message"])
    notify_all = as_bool(payload.get("notifyAll"))
    student_ids = payload.get("studentIds") if isinstance(payload.get("studentIds"), list) else []
    student_ids = [str_value(student_id) for student_id in student_ids if str_value(student_id)]
    if notify_all:
        student_ids = [
            row["student_id"]
            for row in fetch_all("select student_id from courseplatform.students where status = 'ACTIVE' order by full_name")
        ]
    if not student_ids:
        raise ApiError("NOTIFICATION_RECIPIENT_REQUIRED", "Selecione pelo menos um estudante.")
    notification_ids: list[str] = []
    with connection() as conn:
        for student_id in dict.fromkeys(student_ids):
            notification_id = create_student_notification(
                conn,
                student_id,
                str_value(payload.get("category") or "GENERAL"),
                str_value(payload.get("title")),
                str_value(payload.get("message")),
                admin_id=admin["admin_id"],
                action_url=safe_notification_action_url(payload.get("actionUrl")),
                entity_type="MANUAL_UPDATE",
                entity_id="",
                priority=str_value(payload.get("priority") or "NORMAL"),
                email_subject=str_value(payload.get("emailSubject")),
                email_message=str_value(payload.get("emailMessage")),
                push_title=str_value(payload.get("pushTitle")),
                push_message=str_value(payload.get("pushMessage")),
                send_whatsapp=as_bool(payload.get("sendWhatsApp")),
                send_email=as_bool(payload.get("sendEmail")),
                send_telegram=as_bool(payload.get("sendTelegram")),
                send_push=as_bool(payload.get("sendPush")),
            )
            if notification_id:
                notification_ids.append(notification_id)
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "NOTIFICATION_SENT",
            "NOTIFICATION",
            "",
            {
                "studentCount": len(notification_ids),
                "sendWhatsApp": as_bool(payload.get("sendWhatsApp")),
                "sendEmail": as_bool(payload.get("sendEmail")),
                "sendTelegram": as_bool(payload.get("sendTelegram")),
                "sendPush": as_bool(payload.get("sendPush")),
            },
        )
        conn.commit()
    dispatch_notification_deliveries(notification_ids)
    return success({"notificationCount": len(notification_ids), "notificationIds": notification_ids})


def admin_save_notification_template_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    NOTIFICATION_TEMPLATE_DEFINITIONS = runtime.NOTIFICATION_TEMPLATE_DEFINITIONS
    NOTIFICATION_TEMPLATE_VARIABLES = runtime.NOTIFICATION_TEMPLATE_VARIABLES
    _template_tokens = runtime._template_tokens
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    notification_template_payload = runtime.notification_template_payload
    notification_templates_payload = runtime.notification_templates_payload
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    source = payload.get("notificationTemplate") if isinstance(payload.get("notificationTemplate"), dict) else payload
    template_key = str_value(source.get("templateKey")).upper()
    if template_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        raise ApiError("INVALID_NOTIFICATION_TEMPLATE", "Selecione um modelo de notificação válido.")
    limits = {
        "internalTitleTemplate": 180,
        "internalMessageTemplate": 1800,
        "emailSubjectTemplate": 180,
        "emailMessageTemplate": 5000,
        "pushTitleTemplate": 120,
        "pushMessageTemplate": 300,
    }
    values: dict[str, str] = {}
    for field, limit in limits.items():
        value = str_value(source.get(field))
        if not value:
            raise ApiError("NOTIFICATION_TEMPLATE_FIELD_REQUIRED", "Todos os textos do modelo são obrigatórios.", {"field": field})
        if len(value) > limit:
            raise ApiError("NOTIFICATION_TEMPLATE_TOO_LONG", "Um dos textos excede o tamanho permitido.", {"field": field, "limit": limit})
        unknown_tokens = _template_tokens(value) - NOTIFICATION_TEMPLATE_VARIABLES
        if unknown_tokens:
            raise ApiError(
                "INVALID_NOTIFICATION_TEMPLATE_VARIABLE",
                "O modelo contém variáveis não suportadas.",
                {"field": field, "variables": sorted(unknown_tokens)},
            )
        values[field] = value
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.notification_templates
              (template_key, internal_title_template, internal_message_template,
               email_subject_template, email_message_template,
               push_title_template, push_message_template, updated_by, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (template_key) do update set
              internal_title_template = excluded.internal_title_template,
              internal_message_template = excluded.internal_message_template,
              email_subject_template = excluded.email_subject_template,
              email_message_template = excluded.email_message_template,
              push_title_template = excluded.push_title_template,
              push_message_template = excluded.push_message_template,
              updated_by = excluded.updated_by,
              updated_at = now()
            returning *
            """,
            (
                template_key,
                values["internalTitleTemplate"], values["internalMessageTemplate"],
                values["emailSubjectTemplate"], values["emailMessageTemplate"],
                values["pushTitleTemplate"], values["pushMessageTemplate"],
                admin["admin_id"],
            ),
        ).fetchone()
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_TEMPLATE_UPDATED",
            "NOTIFICATION_TEMPLATE", template_key,
        )
        conn.commit()
    return success({
        "notificationTemplate": notification_template_payload(template_key, row),
        "notificationTemplates": notification_templates_payload(),
    })


def admin_reset_notification_template_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    NOTIFICATION_TEMPLATE_DEFINITIONS = runtime.NOTIFICATION_TEMPLATE_DEFINITIONS
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    notification_template_payload = runtime.notification_template_payload
    notification_templates_payload = runtime.notification_templates_payload
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    template_key = str_value(payload.get("templateKey")).upper()
    if template_key not in NOTIFICATION_TEMPLATE_DEFINITIONS:
        raise ApiError("INVALID_NOTIFICATION_TEMPLATE", "Selecione um modelo de notificação válido.")
    with connection() as conn:
        conn.execute("delete from courseplatform.notification_templates where template_key = %s", (template_key,))
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_TEMPLATE_RESET",
            "NOTIFICATION_TEMPLATE", template_key,
        )
        conn.commit()
    return success({
        "notificationTemplate": notification_template_payload(template_key),
        "notificationTemplates": notification_templates_payload(),
    })


def admin_save_whatsapp_configuration_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    get_settings = runtime.get_settings
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    success = runtime.success
    valid_whatsapp_platform_url = runtime.valid_whatsapp_platform_url
    whatsapp_configuration = runtime.whatsapp_configuration
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("whatsappConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload

    enabled = as_bool(configuration.get("enabled"))
    phone_number_id = str_value(configuration.get("phoneNumberId"))
    graph_api_version = str_value(configuration.get("graphApiVersion")) or "v23.0"
    template_name = str_value(configuration.get("templateName"))
    template_language = str_value(configuration.get("templateLanguage")) or "pt_PT"
    platform_url = str_value(configuration.get("platformUrl")).rstrip("/")
    access_token = str_value(configuration.get("accessToken"))
    remove_access_token = as_bool(configuration.get("removeAccessToken"))

    if access_token and remove_access_token:
        raise ApiError(
            "AMBIGUOUS_WHATSAPP_TOKEN_UPDATE",
            "Escolha entre substituir ou remover o token de acesso.",
        )
    if len(access_token) > 8192:
        raise ApiError("INVALID_WHATSAPP_ACCESS_TOKEN", "O token de acesso excede o tamanho permitido.")
    if phone_number_id and not re.fullmatch(r"\d{6,30}", phone_number_id):
        raise ApiError("INVALID_WHATSAPP_PHONE_ID", "O Phone Number ID deve conter apenas números.")
    if not re.fullmatch(r"v\d+\.\d+", graph_api_version):
        raise ApiError("INVALID_WHATSAPP_API_VERSION", "Utilize uma versão da Graph API no formato v23.0.")
    if template_name and not re.fullmatch(r"[a-z0-9_]{1,512}", template_name):
        raise ApiError("INVALID_WHATSAPP_TEMPLATE", "O nome do modelo deve usar letras minúsculas, números e underscores.")
    if not re.fullmatch(r"[a-z]{2,3}(?:_[A-Z]{2})?", template_language):
        raise ApiError("INVALID_WHATSAPP_LANGUAGE", "Utilize um idioma no formato pt_PT.")
    if platform_url and not valid_whatsapp_platform_url(platform_url):
        raise ApiError("INVALID_WHATSAPP_PLATFORM_URL", "Informe um endereço http:// ou https:// completo e válido.")
    encryption_key = notification_encryption_key(settings)
    if access_token and not encryption_key:
        raise ApiError(
            "WHATSAPP_ENCRYPTION_KEY_REQUIRED",
            "Defina NOTIFICATION_CONFIG_ENCRYPTION_KEY no servidor antes de guardar o token pelo painel.",
        )
    if access_token and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_WHATSAPP_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )

    with connection() as conn:
        existing = conn.execute(
            """
            select access_token_encrypted,
                   access_token_encrypted is not null as token_configured
            from courseplatform.notification_channel_settings
            where channel = 'WHATSAPP'
            """
        ).fetchone() or {}
        encrypted_token = None if remove_access_token else existing.get("access_token_encrypted")
        if access_token:
            encrypted_token = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_token",
                (access_token, encryption_key),
            ).fetchone()["encrypted_token"]

        encryption_key_configured = len(encryption_key.encode("utf-8")) >= 32
        token_available = bool(
            access_token
            or (encrypted_token is not None and encryption_key_configured)
            or settings.whatsapp_access_token
        )
        if enabled and not (phone_number_id and template_name and platform_url and token_available):
            raise ApiError(
                "INCOMPLETE_WHATSAPP_CONFIGURATION",
                "Preencha o Phone Number ID, o modelo, o endereço da plataforma e um token antes de ativar o WhatsApp.",
            )

        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, phone_number_id, graph_api_version, template_name,
               template_language, platform_url, access_token_encrypted, updated_by, updated_at)
            values ('WHATSAPP', %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled,
              phone_number_id = excluded.phone_number_id,
              graph_api_version = excluded.graph_api_version,
              template_name = excluded.template_name,
              template_language = excluded.template_language,
              platform_url = excluded.platform_url,
              access_token_encrypted = excluded.access_token_encrypted,
              updated_by = excluded.updated_by,
              updated_at = now()
            """,
            (
                enabled,
                phone_number_id or None,
                graph_api_version,
                template_name or None,
                template_language,
                platform_url or None,
                encrypted_token,
                admin["admin_id"],
            ),
        )
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "WHATSAPP_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL",
            "WHATSAPP",
            {
                "enabled": enabled,
                "phoneNumberConfigured": bool(phone_number_id),
                "templateName": template_name,
                "tokenChanged": bool(access_token or remove_access_token),
            },
        )
        conn.commit()
    return success({"whatsappConfiguration": whatsapp_configuration()})


def admin_save_email_configuration_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    email_configuration = runtime.email_configuration
    get_settings = runtime.get_settings
    int_value = runtime.int_value
    normalize_email_recipient = runtime.normalize_email_recipient
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    success = runtime.success
    valid_notification_host = runtime.valid_notification_host
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("emailConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload
    enabled = as_bool(configuration.get("enabled"))
    smtp_host = str_value(configuration.get("smtpHost"))
    smtp_port = int_value(configuration.get("smtpPort"), 587)
    smtp_username = str_value(configuration.get("smtpUsername"))
    smtp_password = str_value(configuration.get("smtpPassword"))
    from_email = normalize_email_recipient(configuration.get("fromEmail"))
    raw_from_email = str_value(configuration.get("fromEmail"))
    from_name = str_value(configuration.get("fromName"))
    use_tls = as_bool(configuration.get("useTls"))
    remove_password = as_bool(configuration.get("removeSmtpPassword"))
    encryption_key = notification_encryption_key(settings)
    if smtp_password and remove_password:
        raise ApiError("AMBIGUOUS_SMTP_PASSWORD_UPDATE", "Escolha entre substituir ou remover a palavra-passe SMTP.")
    if smtp_host and not valid_notification_host(smtp_host):
        raise ApiError("INVALID_SMTP_HOST", "Informe apenas um hostname SMTP válido, sem protocolo ou caminho.")
    if not 1 <= smtp_port <= 65535:
        raise ApiError("INVALID_SMTP_PORT", "A porta SMTP deve estar entre 1 e 65535.")
    if enabled and smtp_port != 465 and not use_tls:
        raise ApiError(
            "INSECURE_SMTP_TRANSPORT",
            "Ative TLS para proteger as credenciais e o conteúdo do email. A porta 465 utiliza TLS implícito.",
        )
    if len(smtp_username) > 320:
        raise ApiError("INVALID_SMTP_USERNAME", "O utilizador SMTP excede o tamanho permitido.")
    if len(smtp_password) > 8192:
        raise ApiError("INVALID_SMTP_PASSWORD", "A palavra-passe SMTP excede o tamanho permitido.")
    if raw_from_email and not from_email:
        raise ApiError("INVALID_SMTP_FROM_EMAIL", "Informe um endereço de remetente válido.")
    if len(from_name) > 120 or "\r" in from_name or "\n" in from_name:
        raise ApiError("INVALID_SMTP_FROM_NAME", "O nome do remetente é inválido.")
    if smtp_password and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    with connection() as conn:
        existing = conn.execute(
            """
            select smtp_password_encrypted
            from courseplatform.notification_channel_settings where channel = 'EMAIL'
            """
        ).fetchone() or {}
        encrypted_password = None if remove_password else existing.get("smtp_password_encrypted")
        if smtp_password:
            encrypted_password = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_secret",
                (smtp_password, encryption_key),
            ).fetchone()["encrypted_secret"]
        stored_password_available = bool(
            smtp_password
            or (encrypted_password is not None and len(encryption_key.encode("utf-8")) >= 32)
            or settings.smtp_password
        )
        if enabled and not (
            smtp_host and from_email and (not smtp_username or stored_password_available)
        ):
            raise ApiError(
                "INCOMPLETE_EMAIL_CONFIGURATION",
                "Preencha o servidor, o remetente e, quando houver autenticação, a palavra-passe SMTP.",
            )
        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, smtp_host, smtp_port, smtp_username,
               smtp_password_encrypted, from_email, from_name, use_tls, updated_by, updated_at)
            values ('EMAIL', %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled, smtp_host = excluded.smtp_host,
              smtp_port = excluded.smtp_port, smtp_username = excluded.smtp_username,
              smtp_password_encrypted = excluded.smtp_password_encrypted,
              from_email = excluded.from_email, from_name = excluded.from_name,
              use_tls = excluded.use_tls, updated_by = excluded.updated_by, updated_at = now()
            """,
            (
                enabled, smtp_host or None, smtp_port, smtp_username or None,
                encrypted_password, from_email or None, from_name or None,
                use_tls, admin["admin_id"],
            ),
        )
        audit(
            conn, "ADMIN", admin["admin_id"], "EMAIL_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL", "EMAIL",
            {
                "enabled": enabled, "smtpHostConfigured": bool(smtp_host),
                "fromEmailConfigured": bool(from_email),
                "passwordChanged": bool(smtp_password or remove_password),
            },
        )
        conn.commit()
    return success({"emailConfiguration": email_configuration()})


def admin_save_telegram_configuration_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    get_settings = runtime.get_settings
    normalize_telegram_parse_mode = runtime.normalize_telegram_parse_mode
    notification_encryption_key = runtime.notification_encryption_key
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    str_value = runtime.str_value
    success = runtime.success
    telegram_configuration = runtime.telegram_configuration
    valid_telegram_bot_token = runtime.valid_telegram_bot_token
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    settings = get_settings()
    configuration = payload.get("telegramConfiguration")
    if not isinstance(configuration, dict):
        configuration = payload
    enabled = as_bool(configuration.get("enabled"))
    bot_token = str_value(configuration.get("botToken"))
    bot_username = str_value(configuration.get("botUsername")).lstrip("@")
    raw_parse_mode = str_value(configuration.get("parseMode")) or "HTML"
    parse_mode = normalize_telegram_parse_mode(raw_parse_mode)
    remove_token = as_bool(configuration.get("removeBotToken"))
    encryption_key = notification_encryption_key(settings)
    if bot_token and remove_token:
        raise ApiError("AMBIGUOUS_TELEGRAM_TOKEN_UPDATE", "Escolha entre substituir ou remover o token do bot.")
    if bot_token and not valid_telegram_bot_token(bot_token):
        raise ApiError("INVALID_TELEGRAM_BOT_TOKEN", "O token do bot Telegram possui um formato inválido.")
    if bot_username and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", bot_username):
        raise ApiError("INVALID_TELEGRAM_BOT_USERNAME", "Informe o username do bot sem @, com 5 a 32 caracteres.")
    if raw_parse_mode.upper() not in {"HTML", "MARKDOWNV2", "MARKDOWN_V2", "NONE", "PLAIN"}:
        raise ApiError("INVALID_TELEGRAM_PARSE_MODE", "Utilize HTML, MarkdownV2 ou sem formatação.")
    if len(bot_token) > 256:
        raise ApiError("INVALID_TELEGRAM_BOT_TOKEN", "O token do bot excede o tamanho permitido.")
    if bot_token and len(encryption_key.encode("utf-8")) < 32:
        raise ApiError(
            "WEAK_NOTIFICATION_ENCRYPTION_KEY",
            "NOTIFICATION_CONFIG_ENCRYPTION_KEY deve possuir pelo menos 32 bytes.",
        )
    with connection() as conn:
        existing = conn.execute(
            """
            select access_token_encrypted
            from courseplatform.notification_channel_settings where channel = 'TELEGRAM'
            """
        ).fetchone() or {}
        encrypted_token = None if remove_token else existing.get("access_token_encrypted")
        if bot_token:
            encrypted_token = conn.execute(
                "select pgp_sym_encrypt(%s, %s, 'cipher-algo=aes256') as encrypted_secret",
                (bot_token, encryption_key),
            ).fetchone()["encrypted_secret"]
        token_available = bool(
            bot_token
            or (encrypted_token is not None and len(encryption_key.encode("utf-8")) >= 32)
            or settings.telegram_bot_token
        )
        if enabled and not (bot_username and token_available):
            raise ApiError(
                "INCOMPLETE_TELEGRAM_CONFIGURATION",
                "Preencha o username e o token do bot antes de ativar o Telegram.",
            )
        conn.execute(
            """
            insert into courseplatform.notification_channel_settings
              (channel, enabled, bot_username, parse_mode, access_token_encrypted, updated_by, updated_at)
            values ('TELEGRAM', %s, %s, %s, %s, %s, now())
            on conflict (channel) do update set
              enabled = excluded.enabled, bot_username = excluded.bot_username,
              parse_mode = excluded.parse_mode,
              access_token_encrypted = excluded.access_token_encrypted,
              updated_by = excluded.updated_by, updated_at = now()
            """,
            (enabled, bot_username or None, parse_mode or None, encrypted_token, admin["admin_id"]),
        )
        audit(
            conn, "ADMIN", admin["admin_id"], "TELEGRAM_CONFIGURATION_UPDATED",
            "NOTIFICATION_CHANNEL", "TELEGRAM",
            {
                "enabled": enabled, "botUsernameConfigured": bool(bot_username),
                "parseMode": parse_mode, "tokenChanged": bool(bot_token or remove_token),
            },
        )
        conn.commit()
    return success({"telegramConfiguration": telegram_configuration()})


def admin_retry_notification_deliveries_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    deliver_pending_email = runtime.deliver_pending_email
    deliver_pending_push = runtime.deliver_pending_push
    deliver_pending_telegram = runtime.deliver_pending_telegram
    deliver_pending_whatsapp = runtime.deliver_pending_whatsapp
    email_configuration = runtime.email_configuration
    int_value = runtime.int_value
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    redact_notification_error = runtime.redact_notification_error
    str_value = runtime.str_value
    success = runtime.success
    telegram_configuration = runtime.telegram_configuration
    web_push_configuration = runtime.web_push_configuration
    whatsapp_configuration = runtime.whatsapp_configuration
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    prepare_notification_feature_schema()
    limit = max(1, min(int_value(payload.get("limit"), 20), 20))
    requested = payload.get("channels") if isinstance(payload.get("channels"), list) else []
    channels = [str_value(channel).upper() for channel in requested]
    channels = [channel for channel in dict.fromkeys(channels) if channel in {"WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"}]
    if not channels:
        channels = ["WHATSAPP", "EMAIL", "TELEGRAM", "PUSH"]
    delivery_functions = {
        "WHATSAPP": deliver_pending_whatsapp,
        "EMAIL": deliver_pending_email,
        "TELEGRAM": deliver_pending_telegram,
        "PUSH": deliver_pending_push,
    }
    deliveries: dict[str, dict[str, int]] = {}
    for channel in channels:
        try:
            deliveries[channel.lower()] = delivery_functions[channel](limit=limit)
        except Exception as error:
            deliveries[channel.lower()] = {
                "sent": 0, "failed": 1, "pending": 0,
                "error": redact_notification_error(error),
            }
    result = {
        key: sum(int(channel_result.get(key) or 0) for channel_result in deliveries.values())
        for key in ("sent", "failed", "pending")
    }
    with connection() as conn:
        audit(
            conn, "ADMIN", admin["admin_id"], "NOTIFICATION_DELIVERIES_RETRIED",
            "NOTIFICATION", "", {"total": result, "channels": channels},
        )
        conn.commit()
    return success({
        "delivery": result,
        "deliveries": deliveries,
        "whatsappConfiguration": whatsapp_configuration(),
        "emailConfiguration": email_configuration(),
        "telegramConfiguration": telegram_configuration(),
        "pushConfiguration": web_push_configuration(),
    })


def chat_message_body_action(value: Any, *, runtime: CommunicationRuntime) -> str:
    body = str(value or "").replace("\x00", "").strip()
    if not body:
        raise ApiError("CHAT_MESSAGE_REQUIRED", "Escreva uma mensagem antes de enviar.")
    if len(body) > 2000:
        raise ApiError("CHAT_MESSAGE_TOO_LONG", "A mensagem não pode exceder 2 000 caracteres.")
    return body


def touch_chat_presence_action(conn, actor: dict[str, Any], room_id: str = "", *, runtime: CommunicationRuntime) -> None:
    generate_id = runtime.generate_id
    str_value = runtime.str_value
    conn.execute(
        """
        insert into courseplatform.chat_presence
          (presence_id, actor_type, actor_id, current_room_id, last_seen_at, updated_at)
        values (%s, %s, %s, %s, now(), now())
        on conflict (actor_type, actor_id) do update set
          current_room_id = excluded.current_room_id,
          last_seen_at = now(),
          updated_at = now()
        """,
        (
            generate_id("CPR"),
            actor["type"],
            actor["id"],
            str_value(room_id)[:160] or None,
        ),
    )


def chat_actor_with_conn_action(conn, payload: dict[str, Any], *, runtime: CommunicationRuntime) -> dict[str, Any]:
    str_value = runtime.str_value
    student_context_with_conn = runtime.student_context_with_conn
    touch_chat_presence = runtime.touch_chat_presence
    validate_session_with_conn = runtime.validate_session_with_conn
    if payload.get("adminToken"):
        session = validate_session_with_conn(conn, str_value(payload.get("adminToken")), "ADMIN")
        admin_id = str(session["subject_id"]).replace("ADMIN:", "", 1)
        admin = conn.execute(
            """
            select a.*, s.status as identity_status
            from courseplatform.admins a
            left join courseplatform.students s on s.student_id = a.student_id
            where a.admin_id = %s
            """,
            (admin_id,),
        ).fetchone()
        if (
            not admin
            or admin.get("status") != "ACTIVE"
            or (admin.get("student_id") and admin.get("identity_status") != "ACTIVE")
        ):
            raise ApiError("ADMIN_NOT_ACTIVE", "A conta administrativa não está ativa.")
        if admin.get("role") not in {"OWNER", "ADMIN", "REVIEWER"}:
            raise ApiError("FORBIDDEN", "O seu perfil não possui acesso às conversas.")
        actor = {"type": "ADMIN", "id": admin_id, "record": admin}
        touch_chat_presence(conn, actor, payload.get("roomId") or payload.get("currentRoomId") or "")
        return actor
    _, student = student_context_with_conn(conn, payload)
    actor = {"type": "STUDENT", "id": student["student_id"], "record": student}
    touch_chat_presence(conn, actor, payload.get("roomId") or payload.get("currentRoomId") or "")
    return actor


def upsert_chat_room_action(
    conn,
    room_key: str,
    room_type: str,
    name: str,
    description: str,
    *,
    course_id: str | None = None,
    group_id: str | None = None,
    owner_student_id: str | None = None,
    direct_student_one_id: str | None = None,
    direct_student_two_id: str | None = None,
    runtime: CommunicationRuntime,
) -> dict[str, Any] | None:
    generate_id = runtime.generate_id
    return conn.execute(
        """
        insert into courseplatform.chat_rooms
          (room_id, room_key, room_type, name, description, course_id, group_id,
           owner_student_id, direct_student_one_id, direct_student_two_id,
           status, created_at, updated_at)
        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'ACTIVE', now(), now())
        on conflict (room_key) do update set
          name = excluded.name,
          description = excluded.description,
          course_id = excluded.course_id,
          group_id = excluded.group_id,
          owner_student_id = excluded.owner_student_id,
          direct_student_one_id = excluded.direct_student_one_id,
          direct_student_two_id = excluded.direct_student_two_id,
          updated_at = now()
        where (
          courseplatform.chat_rooms.name,
          courseplatform.chat_rooms.description,
          courseplatform.chat_rooms.course_id,
          courseplatform.chat_rooms.group_id,
          courseplatform.chat_rooms.owner_student_id,
          courseplatform.chat_rooms.direct_student_one_id,
          courseplatform.chat_rooms.direct_student_two_id
        ) is distinct from (
          excluded.name,
          excluded.description,
          excluded.course_id,
          excluded.group_id,
          excluded.owner_student_id,
          excluded.direct_student_one_id,
          excluded.direct_student_two_id
        )
        returning *
        """,
        (
            generate_id("CRM"), room_key, room_type, name[:160], description[:500],
            course_id, group_id, owner_student_id,
            direct_student_one_id, direct_student_two_id,
        ),
    ).fetchone()


def chat_direct_pair_action(student_a: str, student_b: str, *, runtime: CommunicationRuntime) -> tuple[str, str]:
    first, second = sorted((str(student_a), str(student_b)))
    if not first or first == second:
        raise ApiError("INVALID_CHAT_CONTACT", "Selecione outro estudante para iniciar a conversa.")
    return first, second


def sync_chat_rooms_action(conn, actor: dict[str, Any], *, runtime: CommunicationRuntime) -> None:
    if actor["type"] == "STUDENT":
        desired_rooms_sql = """
          select 'COMMUNITY'::text as room_key, 'COMMUNITY'::text as room_type,
                 'Comunidade geral'::text as name,
                 'Espaço comum para estudantes e formadores da plataforma.'::text as description,
                 null::text as course_id, null::text as group_id, null::text as owner_student_id
          union all
          select distinct 'COURSE:' || c.course_id, 'COURSE', c.title,
                 'Conversa do curso com estudantes e formadores matriculados.',
                 c.course_id, null::text, null::text
          from courseplatform.enrollments e
          join courseplatform.courses c on c.course_id = e.course_id
          where e.student_id = %s and e.status in ('ACTIVE', 'COMPLETED') and c.status = 'ACTIVE'
          union all
          select distinct 'GROUP:' || g.group_id, 'GROUP', g.name,
                 'Canal reservado aos membros deste grupo.',
                 g.course_id, g.group_id, null::text
          from courseplatform.groups g
          left join courseplatform.group_members gm
            on gm.group_id = g.group_id and gm.student_id = %s and gm.status = 'ACTIVE'
          left join courseplatform.enrollments e
            on e.group_id = g.group_id and e.student_id = %s and e.status in ('ACTIVE', 'COMPLETED')
          where g.status = 'ACTIVE' and (gm.group_member_id is not null or e.enrollment_id is not null)
          union all
          select 'SUPPORT:' || %s, 'SUPPORT', 'Apoio com formadores',
                 'Conversa privada entre o estudante e a equipa de formação.',
                 null::text, null::text, %s
        """
        params = (actor["id"], actor["id"], actor["id"], actor["id"], actor["id"])
    else:
        desired_rooms_sql = """
          select 'COMMUNITY'::text as room_key, 'COMMUNITY'::text as room_type,
                 'Comunidade geral'::text as name,
                 'Espaço comum para estudantes e formadores da plataforma.'::text as description,
                 null::text as course_id, null::text as group_id, null::text as owner_student_id
          union all
          select 'COURSE:' || c.course_id, 'COURSE', c.title,
                 'Conversa do curso com estudantes e formadores matriculados.',
                 c.course_id, null::text, null::text
          from courseplatform.courses c where c.status = 'ACTIVE'
          union all
          select 'GROUP:' || g.group_id, 'GROUP', g.name,
                 'Canal reservado aos membros deste grupo.',
                 g.course_id, g.group_id, null::text
          from courseplatform.groups g where g.status = 'ACTIVE'
          union all
          select 'SUPPORT:' || s.student_id, 'SUPPORT', 'Apoio com formadores',
                 'Conversa privada entre o estudante e a equipa de formação.',
                 null::text, null::text, s.student_id
          from courseplatform.students s where s.status = 'ACTIVE'
        """
        params = ()

    conn.execute(
        f"""
        with desired_rooms as ({desired_rooms_sql})
        insert into courseplatform.chat_rooms
          (room_id, room_key, room_type, name, description, course_id, group_id,
           owner_student_id, status, created_at, updated_at)
        select
          'CRM-' || upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 12)),
          room_key, room_type, left(name, 160), left(description, 500),
          course_id, group_id, owner_student_id, 'ACTIVE', now(), now()
        from desired_rooms
        on conflict (room_key) do update set
          name = excluded.name,
          description = excluded.description,
          course_id = excluded.course_id,
          group_id = excluded.group_id,
          owner_student_id = excluded.owner_student_id,
          updated_at = now()
        where (
          courseplatform.chat_rooms.name,
          courseplatform.chat_rooms.description,
          courseplatform.chat_rooms.course_id,
          courseplatform.chat_rooms.group_id,
          courseplatform.chat_rooms.owner_student_id
        ) is distinct from (
          excluded.name,
          excluded.description,
          excluded.course_id,
          excluded.group_id,
          excluded.owner_student_id
        )
        """,
        params,
    )


def student_can_access_chat_room_action(conn, student_id: str, room: dict[str, Any], *, runtime: CommunicationRuntime) -> bool:
    room_type = room.get("room_type")
    if room_type == "COMMUNITY":
        return True
    if room_type == "SUPPORT":
        return room.get("owner_student_id") == student_id
    if room_type == "DIRECT":
        return student_id in {
            room.get("direct_student_one_id"),
            room.get("direct_student_two_id"),
        }
    if room_type == "COURSE":
        row = conn.execute(
            """
            select 1 from courseplatform.enrollments
            where student_id = %s and course_id = %s and status in ('ACTIVE', 'COMPLETED')
            limit 1
            """,
            (student_id, room.get("course_id")),
        ).fetchone()
        return bool(row)
    if room_type == "GROUP":
        row = conn.execute(
            """
            select 1
            from courseplatform.groups g
            left join courseplatform.group_members gm
              on gm.group_id = g.group_id and gm.student_id = %s and gm.status = 'ACTIVE'
            left join courseplatform.enrollments e
              on e.group_id = g.group_id and e.student_id = %s and e.status in ('ACTIVE', 'COMPLETED')
            where g.group_id = %s and g.status = 'ACTIVE'
              and (gm.group_member_id is not null or e.enrollment_id is not null)
            limit 1
            """,
            (student_id, student_id, room.get("group_id")),
        ).fetchone()
        return bool(row)
    return False


def accessible_chat_room_action(conn, room_id: str, actor: dict[str, Any], *, runtime: CommunicationRuntime) -> dict[str, Any]:
    student_can_access_chat_room = runtime.student_can_access_chat_room
    room = conn.execute(
        "select * from courseplatform.chat_rooms where room_id = %s and status = 'ACTIVE'",
        (room_id,),
    ).fetchone()
    if not room:
        raise ApiError("CHAT_ROOM_NOT_FOUND", "A conversa não foi encontrada.")
    if actor["type"] == "ADMIN" and room.get("room_type") == "DIRECT":
        raise ApiError("CHAT_ROOM_FORBIDDEN", "As conversas privadas entre estudantes são reservadas aos participantes.")
    if actor["type"] == "STUDENT" and not student_can_access_chat_room(conn, actor["id"], room):
        raise ApiError("CHAT_ROOM_FORBIDDEN", "Não possui acesso a esta conversa.")
    return room


def chat_realtime_configuration_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_realtime_token = runtime.chat_realtime_token
    connection = runtime.connection
    ensure_chat_realtime_schema = runtime.ensure_chat_realtime_schema
    get_settings = runtime.get_settings
    iso = runtime.iso
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    success = runtime.success
    global _CHAT_REALTIME_SCHEMA_READY
    prepare_chat_feature_schema()
    settings = get_settings()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        conn.commit()
        environment_ready = bool(
            settings.chat_realtime_enabled
            and settings.supabase_url.startswith("https://")
            and settings.supabase_publishable_key
            and len(settings.supabase_realtime_jwt_secret) >= 32
        )
        schema_ready = False
        if environment_ready:
            try:
                schema_ready = ensure_chat_realtime_schema(conn)
                conn.commit()
                _CHAT_REALTIME_SCHEMA_READY = schema_ready
            except Exception:
                conn.rollback()
                schema_ready = False
    configured = environment_ready and schema_ready
    result: dict[str, Any] = {
        "enabled": configured,
        "transport": "SUPABASE_BROADCAST" if configured else "POLLING",
        "pollIntervalMs": 15000 if configured else 4000,
    }
    if configured:
        token, expires_at = chat_realtime_token(
            actor,
            settings.supabase_realtime_jwt_secret,
            settings.chat_realtime_token_minutes,
        )
        result.update({
            "url": settings.supabase_url,
            "publishableKey": settings.supabase_publishable_key,
            "accessToken": token,
            "expiresAt": iso(expires_at),
            "inboxTopic": f"chat:actor:{actor['type'].lower()}:{actor['id']}:inbox",
        })
    return success({"realtime": result})


def chat_message_rows_action(conn, message_ids: list[str], *, runtime: CommunicationRuntime) -> list[dict[str, Any]]:
    if not message_ids:
        return []
    return conn.execute(
        """
        select m.*,
               s.full_name as student_name, s.public_student_id, s.profile_photo_url,
               a.full_name as admin_name, a.role as admin_role,
               reply.body as reply_body, reply.status as reply_status,
               rs.full_name as reply_student_name, ra.full_name as reply_admin_name,
               (select count(*) from courseplatform.chat_message_reports r
                where r.message_id = m.message_id and r.status = 'OPEN') as report_count,
               (select count(*) from courseplatform.chat_message_receipts receipt
                where receipt.message_id = m.message_id and receipt.delivered_at is not null) as delivered_count,
               (select count(*) from courseplatform.chat_message_receipts receipt
                where receipt.message_id = m.message_id and receipt.read_at is not null) as read_count,
               (select max(receipt.read_at) from courseplatform.chat_message_receipts receipt
                where receipt.message_id = m.message_id) as last_read_at
        from courseplatform.chat_messages m
        left join courseplatform.students s on s.student_id = m.sender_student_id
        left join courseplatform.admins a on a.admin_id = m.sender_admin_id
        left join courseplatform.chat_messages reply on reply.message_id = m.reply_to_message_id
        left join courseplatform.students rs on rs.student_id = reply.sender_student_id
        left join courseplatform.admins ra on ra.admin_id = reply.sender_admin_id
        where m.message_id = any(%s)
        """,
        (message_ids,),
    ).fetchall()


def chat_message_row_action(conn, message_id: str, *, runtime: CommunicationRuntime) -> dict[str, Any] | None:
    chat_message_rows = runtime.chat_message_rows
    rows = chat_message_rows(conn, [message_id])
    return rows[0] if rows else None


def public_chat_message_action(row: dict[str, Any] | None, actor: dict[str, Any], *, runtime: CommunicationRuntime) -> dict[str, Any] | None:
    iso = runtime.iso
    if not row:
        return None
    sender_type = row.get("sender_type") or "STUDENT"
    sender_id = row.get("sender_admin_id") if sender_type == "ADMIN" else row.get("sender_student_id")
    sender_name = row.get("admin_name") if sender_type == "ADMIN" else row.get("student_name")
    reply_name = row.get("reply_admin_name") or row.get("reply_student_name") or "Participante"
    deleted = row.get("status") in {"DELETED", "MODERATED"}
    delivered_count = int(row.get("delivered_count") or 0)
    read_count = int(row.get("read_count") or 0)
    delivery_status = "READ" if read_count else "DELIVERED" if delivered_count else "SENT"
    return {
        "messageId": row.get("message_id"),
        "roomId": row.get("room_id"),
        "body": "" if deleted else row.get("body") or "",
        "status": row.get("status") or "ACTIVE",
        "isDeleted": deleted,
        "isMine": sender_type == actor["type"] and sender_id == actor["id"],
        "sender": {
            "type": sender_type,
            "id": row.get("public_student_id") if sender_type == "STUDENT" else "",
            "name": sender_name or ("Formador" if sender_type == "ADMIN" else "Estudante"),
            "publicId": row.get("public_student_id") or "",
            "role": row.get("admin_role") or "STUDENT",
            "profilePhotoUrl": row.get("profile_photo_url") or "",
        },
        "replyTo": {
            "messageId": row.get("reply_to_message_id"),
            "senderName": reply_name,
            "body": "Mensagem removida" if row.get("reply_status") in {"DELETED", "MODERATED"} else row.get("reply_body") or "",
        } if row.get("reply_to_message_id") else None,
        "reportCount": int(row.get("report_count") or 0),
        "deliveryStatus": delivery_status,
        "deliveredCount": delivered_count,
        "readCount": read_count,
        "lastReadAt": iso(row.get("last_read_at")),
        "createdAt": iso(row.get("created_at")),
        "editedAt": iso(row.get("edited_at")),
        "updatedAt": iso(row.get("updated_at")),
    }


def record_chat_message_receipts_action(
    conn,
    message_ids: list[str],
    actor: dict[str, Any],
    *,
    mark_read: bool = False,
    runtime: CommunicationRuntime,
) -> None:
    generate_id = runtime.generate_id
    utc_now = runtime.utc_now
    if not message_ids:
        return
    rows = conn.execute(
        """
        select message_id, sender_type, sender_student_id, sender_admin_id
        from courseplatform.chat_messages
        where message_id = any(%s)
        """,
        (message_ids,),
    ).fetchall()
    for row in rows:
        sender_id = row.get("sender_student_id") if row.get("sender_type") == "STUDENT" else row.get("sender_admin_id")
        if row.get("sender_type") == actor["type"] and sender_id == actor["id"]:
            continue
        if actor["type"] == "STUDENT":
            changed = conn.execute(
                """
                insert into courseplatform.chat_message_receipts
                  (receipt_id, message_id, actor_type, student_id, delivered_at, read_at, updated_at)
                values (%s, %s, 'STUDENT', %s, now(), %s, now())
                on conflict (message_id, student_id) where student_id is not null do update set
                  delivered_at = coalesce(courseplatform.chat_message_receipts.delivered_at, now()),
                  read_at = case when %s then coalesce(courseplatform.chat_message_receipts.read_at, now())
                                 else courseplatform.chat_message_receipts.read_at end,
                  updated_at = now()
                where %s and courseplatform.chat_message_receipts.read_at is null
                returning message_id
                """,
                (
                    generate_id("CRC"), row["message_id"], actor["id"],
                    bool(mark_read) and utc_now() or None, bool(mark_read), bool(mark_read),
                ),
            ).fetchone()
        else:
            changed = conn.execute(
                """
                insert into courseplatform.chat_message_receipts
                  (receipt_id, message_id, actor_type, admin_id, delivered_at, read_at, updated_at)
                values (%s, %s, 'ADMIN', %s, now(), %s, now())
                on conflict (message_id, admin_id) where admin_id is not null do update set
                  delivered_at = coalesce(courseplatform.chat_message_receipts.delivered_at, now()),
                  read_at = case when %s then coalesce(courseplatform.chat_message_receipts.read_at, now())
                                 else courseplatform.chat_message_receipts.read_at end,
                  updated_at = now()
                where %s and courseplatform.chat_message_receipts.read_at is null
                returning message_id
                """,
                (
                    generate_id("CRC"), row["message_id"], actor["id"],
                    bool(mark_read) and utc_now() or None, bool(mark_read), bool(mark_read),
                ),
            ).fetchone()
        if changed:
            conn.execute(
                "update courseplatform.chat_messages set updated_at = now() where message_id = %s",
                (row["message_id"],),
            )


def mark_chat_room_read_with_conn_action(conn, room_id: str, actor: dict[str, Any], *, runtime: CommunicationRuntime) -> None:
    record_chat_message_receipts = runtime.record_chat_message_receipts
    upsert_chat_room_read_cursor = runtime.upsert_chat_room_read_cursor
    message_rows = conn.execute(
        """
        select message_id from courseplatform.chat_messages
        where room_id = %s and status = 'ACTIVE'
        order by created_at desc limit 200
        """,
        (room_id,),
    ).fetchall()
    record_chat_message_receipts(
        conn,
        [row["message_id"] for row in message_rows],
        actor,
        mark_read=True,
    )
    upsert_chat_room_read_cursor(conn, room_id, actor)


def upsert_chat_room_read_cursor_action(conn, room_id: str, actor: dict[str, Any], *, runtime: CommunicationRuntime) -> None:
    generate_id = runtime.generate_id
    if actor["type"] == "STUDENT":
        conn.execute(
            """
            insert into courseplatform.chat_reads
              (read_id, room_id, actor_type, student_id, last_read_at, updated_at)
            values (%s, %s, 'STUDENT', %s, now(), now())
            on conflict (room_id, student_id) where student_id is not null
            do update set last_read_at = now(), updated_at = now()
            """,
            (generate_id("CRD"), room_id, actor["id"]),
        )
    else:
        conn.execute(
            """
            insert into courseplatform.chat_reads
              (read_id, room_id, actor_type, admin_id, last_read_at, updated_at)
            values (%s, %s, 'ADMIN', %s, now(), now())
            on conflict (room_id, admin_id) where admin_id is not null
            do update set last_read_at = now(), updated_at = now()
            """,
            (generate_id("CRD"), room_id, actor["id"]),
        )


def chat_room_summary_context_action(
    conn,
    rooms: list[dict[str, Any]],
    actor: dict[str, Any],
    active_admin_count: int,
    *,
    runtime: CommunicationRuntime,
) -> dict[str, dict[str, Any]]:
    chat_message_rows = runtime.chat_message_rows
    str_value = runtime.str_value
    room_ids = [str_value(room.get("room_id")) for room in rooms if room.get("room_id")]
    if not room_ids:
        return {}

    latest_refs = conn.execute(
        """
        select distinct on (room_id) room_id, message_id
        from courseplatform.chat_messages
        where room_id = any(%s)
        order by room_id, created_at desc, message_id desc
        """,
        (room_ids,),
    ).fetchall()
    latest_rows = chat_message_rows(conn, [row["message_id"] for row in latest_refs])
    latest_by_room = {row["room_id"]: row for row in latest_rows}

    actor_column = "student_id" if actor["type"] == "STUDENT" else "admin_id"
    sender_column = "sender_student_id" if actor["type"] == "STUDENT" else "sender_admin_id"
    unread_rows = conn.execute(
        f"""
        with read_cursors as (
          select room_id, max(last_read_at) as last_read_at
          from courseplatform.chat_reads
          where {actor_column} = %s and room_id = any(%s)
          group by room_id
        )
        select m.room_id, count(*) as count
        from courseplatform.chat_messages m
        left join read_cursors r on r.room_id = m.room_id
        where m.room_id = any(%s)
          and m.status = 'ACTIVE'
          and m.{sender_column} is distinct from %s
          and m.created_at > coalesce(r.last_read_at, 'epoch'::timestamptz)
        group by m.room_id
        """,
        (actor["id"], room_ids, room_ids, actor["id"]),
    ).fetchall()
    unread_by_room = {row["room_id"]: int(row.get("count") or 0) for row in unread_rows}

    online_rows = conn.execute(
        """
        select current_room_id as room_id, count(*) as count
        from courseplatform.chat_presence
        where current_room_id = any(%s)
          and last_seen_at > now() - interval '75 seconds'
        group by current_room_id
        """,
        (room_ids,),
    ).fetchall()
    online_by_room = {row["room_id"]: int(row.get("count") or 0) for row in online_rows}

    course_ids = sorted({room.get("course_id") for room in rooms if room.get("room_type") == "COURSE" and room.get("course_id")})
    course_counts = {}
    if course_ids:
        rows = conn.execute(
            """
            select course_id, count(distinct student_id) as count
            from courseplatform.enrollments
            where course_id = any(%s) and status in ('ACTIVE', 'COMPLETED')
            group by course_id
            """,
            (course_ids,),
        ).fetchall()
        course_counts = {row["course_id"]: int(row.get("count") or 0) for row in rows}

    group_ids = sorted({room.get("group_id") for room in rooms if room.get("room_type") == "GROUP" and room.get("group_id")})
    group_counts = {}
    if group_ids:
        rows = conn.execute(
            """
            select group_id, count(distinct student_id) as count
            from (
              select group_id, student_id from courseplatform.group_members
              where group_id = any(%s) and status = 'ACTIVE'
              union
              select group_id, student_id from courseplatform.enrollments
              where group_id = any(%s) and status in ('ACTIVE', 'COMPLETED')
            ) members
            group by group_id
            """,
            (group_ids, group_ids),
        ).fetchall()
        group_counts = {row["group_id"]: int(row.get("count") or 0) for row in rows}

    active_student_count = 0
    if any(room.get("room_type") == "COMMUNITY" for room in rooms):
        row = conn.execute(
            "select count(*) as count from courseplatform.students where status = 'ACTIVE'"
        ).fetchone() or {}
        active_student_count = int(row.get("count") or 0)

    peer_ids: set[str] = set()
    for room in rooms:
        if room.get("room_type") == "DIRECT" and actor["type"] == "STUDENT":
            peer_ids.add(
                room.get("direct_student_two_id")
                if room.get("direct_student_one_id") == actor["id"]
                else room.get("direct_student_one_id")
            )
        elif room.get("room_type") == "SUPPORT" and actor["type"] == "ADMIN":
            peer_ids.add(room.get("owner_student_id"))
    peer_ids.discard(None)
    peer_ids.discard("")
    peers_by_id = {}
    if peer_ids:
        rows = conn.execute(
            """
            select s.student_id, s.public_student_id, s.full_name, s.profile_photo_url, s.organization,
                   presence.last_seen_at,
                   coalesce(presence.last_seen_at > now() - interval '75 seconds', false) as is_online
            from courseplatform.students s
            left join courseplatform.chat_presence presence
              on presence.actor_type = 'STUDENT' and presence.actor_id = s.student_id
            where s.student_id = any(%s)
            """,
            (sorted(peer_ids),),
        ).fetchall()
        peers_by_id = {row["student_id"]: row for row in rows}

    context: dict[str, dict[str, Any]] = {}
    for room in rooms:
        room_type = room.get("room_type")
        if room_type == "DIRECT":
            participant_count = 2
        elif room_type == "SUPPORT":
            participant_count = 1 + active_admin_count
        elif room_type == "COURSE":
            participant_count = course_counts.get(room.get("course_id"), 0) + active_admin_count
        elif room_type == "GROUP":
            participant_count = group_counts.get(room.get("group_id"), 0) + active_admin_count
        else:
            participant_count = active_student_count + active_admin_count
        context[room["room_id"]] = {
            "lastMessage": latest_by_room.get(room["room_id"]),
            "unreadCount": unread_by_room.get(room["room_id"], 0),
            "onlineCount": online_by_room.get(room["room_id"], 0),
            "participantCount": participant_count,
            "peersById": peers_by_id,
        }
    return context


def chat_room_participant_count_action(conn, room: dict[str, Any], active_admin_count: int | None = None, *, runtime: CommunicationRuntime) -> int:
    if room.get("room_type") == "DIRECT":
        return 2
    if active_admin_count is None:
        active_admins = conn.execute(
            """
            select count(*) as count
            from courseplatform.admins a
            left join courseplatform.students s on s.student_id = a.student_id
            where a.status = 'ACTIVE'
              and (a.student_id is null or s.status = 'ACTIVE')
            """
        ).fetchone() or {}
        admin_count = int(active_admins.get("count") or 0)
    else:
        admin_count = active_admin_count
    if room.get("room_type") == "SUPPORT":
        return 1 + admin_count
    if room.get("room_type") == "COURSE":
        row = conn.execute(
            """
            select count(distinct student_id) as count from courseplatform.enrollments
            where course_id = %s and status in ('ACTIVE', 'COMPLETED')
            """,
            (room.get("course_id"),),
        ).fetchone() or {}
        return int(row.get("count") or 0) + admin_count
    if room.get("room_type") == "GROUP":
        row = conn.execute(
            """
            select count(distinct student_id) as count
            from (
              select student_id from courseplatform.group_members
              where group_id = %s and status = 'ACTIVE'
              union
              select student_id from courseplatform.enrollments
              where group_id = %s and status in ('ACTIVE', 'COMPLETED')
            ) members
            """,
            (room.get("group_id"), room.get("group_id")),
        ).fetchone() or {}
        return int(row.get("count") or 0) + admin_count
    row = conn.execute(
        "select count(*) as count from courseplatform.students where status = 'ACTIVE'"
    ).fetchone() or {}
    return int(row.get("count") or 0) + admin_count


def public_chat_room_action(
    conn,
    room: dict[str, Any],
    actor: dict[str, Any],
    active_admin_count: int | None = None,
    summary: dict[str, Any] | None = None,
    *,
    runtime: CommunicationRuntime,
) -> dict[str, Any]:
    chat_message_row = runtime.chat_message_row
    chat_room_participant_count = runtime.chat_room_participant_count
    iso = runtime.iso
    public_chat_message = runtime.public_chat_message
    actor_column = "student_id" if actor["type"] == "STUDENT" else "admin_id"
    sender_column = "sender_student_id" if actor["type"] == "STUDENT" else "sender_admin_id"
    if summary is None:
        last_message_ref = conn.execute(
            """
            select message_id from courseplatform.chat_messages
            where room_id = %s order by created_at desc, message_id desc limit 1
            """,
            (room["room_id"],),
        ).fetchone()
        last_message = chat_message_row(conn, last_message_ref["message_id"]) if last_message_ref else None
        unread = conn.execute(
            f"""
            select count(*) as count
            from courseplatform.chat_messages m
            where m.room_id = %s
              and m.status = 'ACTIVE'
              and m.{sender_column} is distinct from %s
              and m.created_at > coalesce((
                select last_read_at from courseplatform.chat_reads
                where room_id = %s and {actor_column} = %s
                order by last_read_at desc limit 1
              ), 'epoch'::timestamptz)
            """,
            (room["room_id"], actor["id"], room["room_id"], actor["id"]),
        ).fetchone() or {}
    else:
        last_message = summary.get("lastMessage")
        unread = {"count": summary.get("unreadCount", 0)}
    display_name = room.get("name") or "Conversa"
    peer_payload = None
    if room.get("room_type") == "DIRECT" and actor["type"] == "STUDENT":
        peer_id = (
            room.get("direct_student_two_id")
            if room.get("direct_student_one_id") == actor["id"]
            else room.get("direct_student_one_id")
        )
        peer = (summary or {}).get("peersById", {}).get(peer_id)
        if peer is None:
            peer = conn.execute(
                """
                select s.public_student_id, s.full_name, s.profile_photo_url, s.organization,
                       presence.last_seen_at,
                       coalesce(presence.last_seen_at > now() - interval '75 seconds', false) as is_online
                from courseplatform.students s
                left join courseplatform.chat_presence presence
                  on presence.actor_type = 'STUDENT' and presence.actor_id = s.student_id
                where s.student_id = %s and s.status = 'ACTIVE'
                """,
                (peer_id,),
            ).fetchone() or {}
        display_name = peer.get("full_name") or "Colega de curso"
        peer_payload = {
            "publicStudentId": peer.get("public_student_id") or "",
            "fullName": peer.get("full_name") or "Colega de curso",
            "profilePhotoUrl": peer.get("profile_photo_url") or "",
            "organization": peer.get("organization") or "",
            "isOnline": bool(peer.get("is_online")),
            "lastSeenAt": iso(peer.get("last_seen_at")),
        }
    if room.get("room_type") == "SUPPORT" and actor["type"] == "ADMIN":
        owner = (summary or {}).get("peersById", {}).get(room.get("owner_student_id"))
        if owner is None:
            owner = conn.execute(
                """
                select s.public_student_id, s.full_name, s.profile_photo_url, s.organization,
                       presence.last_seen_at,
                       coalesce(presence.last_seen_at > now() - interval '75 seconds', false) as is_online
                from courseplatform.students s
                left join courseplatform.chat_presence presence
                  on presence.actor_type = 'STUDENT' and presence.actor_id = s.student_id
                where s.student_id = %s
                """,
                (room.get("owner_student_id"),),
            ).fetchone() or {}
        display_name = owner.get("full_name") or "Apoio ao estudante"
        peer_payload = {
            "publicStudentId": owner.get("public_student_id") or "",
            "fullName": owner.get("full_name") or "Estudante",
            "profilePhotoUrl": owner.get("profile_photo_url") or "",
            "organization": owner.get("organization") or "",
            "isOnline": bool(owner.get("is_online")),
            "lastSeenAt": iso(owner.get("last_seen_at")),
        }
    if summary is None:
        online = conn.execute(
            """
            select count(*) as count from courseplatform.chat_presence
            where current_room_id = %s and last_seen_at > now() - interval '75 seconds'
            """,
            (room["room_id"],),
        ).fetchone() or {}
        participant_count = chat_room_participant_count(conn, room, active_admin_count)
    else:
        online = {"count": summary.get("onlineCount", 0)}
        participant_count = int(summary.get("participantCount") or 0)
    return {
        "roomId": room.get("room_id"),
        "roomType": room.get("room_type"),
        "name": display_name,
        "description": room.get("description") or "",
        "courseId": room.get("course_id") or "",
        "groupId": room.get("group_id") or "",
        "peer": peer_payload,
        "onlineCount": int(online.get("count") or 0),
        "participantCount": participant_count,
        "unreadCount": int(unread.get("count") or 0),
        "lastMessage": public_chat_message(last_message, actor),
        "updatedAt": iso(room.get("updated_at")),
    }


def chat_list_contacts_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    chat_actor_with_conn = runtime.chat_actor_with_conn
    connection = runtime.connection
    iso = runtime.iso
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    success = runtime.success
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        if actor["type"] != "STUDENT":
            raise ApiError("CHAT_CONTACTS_FORBIDDEN", "A lista de colegas está disponível apenas para estudantes.")
        rows = conn.execute(
            """
            select peer.student_id, peer.public_student_id, peer.full_name,
                   peer.profile_photo_url, peer.organization,
                   c.course_id, c.title,
                   direct_room.room_id,
                   presence.last_seen_at,
                   coalesce(presence.last_seen_at > now() - interval '75 seconds', false) as is_online
            from courseplatform.enrollments mine
            join courseplatform.enrollments shared
              on shared.course_id = mine.course_id
             and shared.student_id <> mine.student_id
             and shared.status in ('ACTIVE', 'COMPLETED')
            join courseplatform.students peer
              on peer.student_id = shared.student_id
             and peer.status = 'ACTIVE'
             and nullif(trim(peer.public_student_id), '') is not null
            join courseplatform.courses c
              on c.course_id = mine.course_id and c.status = 'ACTIVE'
            left join courseplatform.chat_rooms direct_room
              on direct_room.room_type = 'DIRECT'
             and direct_room.status = 'ACTIVE'
             and direct_room.direct_student_one_id = least(mine.student_id, peer.student_id)
             and direct_room.direct_student_two_id = greatest(mine.student_id, peer.student_id)
            left join courseplatform.chat_presence presence
              on presence.actor_type = 'STUDENT' and presence.actor_id = peer.student_id
            where mine.student_id = %s
              and mine.status in ('ACTIVE', 'COMPLETED')
            order by peer.full_name, c.title
            """,
            (actor["id"],),
        ).fetchall()
        contacts: dict[str, dict[str, Any]] = {}
        for row in rows:
            contact = contacts.setdefault(row["student_id"], {
                "publicStudentId": row.get("public_student_id") or "",
                "fullName": row.get("full_name") or "Colega de curso",
                "profilePhotoUrl": row.get("profile_photo_url") or "",
                "organization": row.get("organization") or "",
                "roomId": row.get("room_id") or "",
                "isOnline": bool(row.get("is_online")),
                "lastSeenAt": iso(row.get("last_seen_at")),
                "sharedCourses": [],
            })
            course = {"courseId": row.get("course_id") or "", "title": row.get("title") or "Curso"}
            if course not in contact["sharedCourses"]:
                contact["sharedCourses"].append(course)
        conn.commit()
    return success({"contacts": list(contacts.values())})


def chat_start_direct_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_direct_pair = runtime.chat_direct_pair
    connection = runtime.connection
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    public_chat_room = runtime.public_chat_room
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    upsert_chat_room = runtime.upsert_chat_room
    require_fields(payload, ["publicStudentId"])
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        if actor["type"] != "STUDENT":
            raise ApiError("CHAT_DIRECT_FORBIDDEN", "Apenas estudantes podem iniciar esta conversa privada.")
        peer = conn.execute(
            """
            select student_id, public_student_id, full_name
            from courseplatform.students
            where public_student_id = %s and status = 'ACTIVE'
            """,
            (str_value(payload["publicStudentId"]),),
        ).fetchone()
        if not peer:
            raise ApiError("CHAT_CONTACT_NOT_FOUND", "O colega selecionado não está disponível.")
        first_id, second_id = chat_direct_pair(actor["id"], peer["student_id"])
        shared_course = conn.execute(
            """
            select 1
            from courseplatform.enrollments mine
            join courseplatform.enrollments shared
              on shared.course_id = mine.course_id
             and shared.student_id = %s
             and shared.status in ('ACTIVE', 'COMPLETED')
            join courseplatform.courses c
              on c.course_id = mine.course_id and c.status = 'ACTIVE'
            where mine.student_id = %s
              and mine.status in ('ACTIVE', 'COMPLETED')
            limit 1
            """,
            (peer["student_id"], actor["id"]),
        ).fetchone()
        if not shared_course:
            raise ApiError("CHAT_CONTACT_FORBIDDEN", "Só pode conversar em privado com colegas dos seus cursos.")
        room_key = f"DIRECT:{first_id}:{second_id}"
        room = upsert_chat_room(
            conn,
            room_key,
            "DIRECT",
            "Conversa privada",
            "Conversa privada entre colegas de curso.",
            direct_student_one_id=first_id,
            direct_student_two_id=second_id,
        )
        if not room:
            room = conn.execute(
                "select * from courseplatform.chat_rooms where room_key = %s and status = 'ACTIVE'",
                (room_key,),
            ).fetchone()
        if not room:
            raise ApiError("CHAT_ROOM_NOT_FOUND", "Não foi possível preparar a conversa privada.")
        room_payload = public_chat_room(conn, room, actor)
        conn.commit()
    return success({"room": room_payload})


def chat_presence_heartbeat_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    chat_actor_with_conn = runtime.chat_actor_with_conn
    connection = runtime.connection
    iso = runtime.iso
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    success = runtime.success
    utc_now = runtime.utc_now
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        conn.commit()
    return success({
        "online": True,
        "actorType": actor["type"],
        "capturedAt": iso(utc_now()),
    })


def chat_list_rooms_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_room_summary_context = runtime.chat_room_summary_context
    connection = runtime.connection
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    public_chat_room = runtime.public_chat_room
    success = runtime.success
    sync_chat_rooms = runtime.sync_chat_rooms
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        sync_chat_rooms(conn, actor)
        if actor["type"] == "STUDENT":
            access_sql = """
              and (
                r.room_type = 'COMMUNITY'
                or (r.room_type = 'SUPPORT' and r.owner_student_id = %s)
                or (
                  r.room_type = 'DIRECT'
                  and %s in (r.direct_student_one_id, r.direct_student_two_id)
                )
                or (
                  r.room_type = 'COURSE'
                  and exists (
                    select 1 from courseplatform.enrollments e
                    where e.student_id = %s and e.course_id = r.course_id
                      and e.status in ('ACTIVE', 'COMPLETED')
                  )
                )
                or (
                  r.room_type = 'GROUP'
                  and (
                    exists (
                      select 1 from courseplatform.group_members gm
                      where gm.student_id = %s and gm.group_id = r.group_id and gm.status = 'ACTIVE'
                    )
                    or exists (
                      select 1 from courseplatform.enrollments e
                      where e.student_id = %s and e.group_id = r.group_id
                        and e.status in ('ACTIVE', 'COMPLETED')
                    )
                  )
                )
              )
            """
            access_params = (actor["id"], actor["id"], actor["id"], actor["id"], actor["id"])
        else:
            access_sql = "and r.room_type <> 'DIRECT'"
            access_params = ()
        rooms = conn.execute(
            f"""
            select r.*,
                   (select max(m.created_at) from courseplatform.chat_messages m where m.room_id = r.room_id) as last_message_at
            from courseplatform.chat_rooms r
            where r.status = 'ACTIVE'
              {access_sql}
            order by last_message_at desc nulls last,
                     case r.room_type when 'COMMUNITY' then 1 when 'GROUP' then 2 when 'COURSE' then 3 else 4 end,
                     r.name,
                     r.room_id
            """,
            access_params,
        ).fetchall()
        active_admins = conn.execute(
            """
            select count(*) as count
            from courseplatform.admins a
            left join courseplatform.students s on s.student_id = a.student_id
            where a.status = 'ACTIVE'
              and (a.student_id is null or s.status = 'ACTIVE')
            """
        ).fetchone() or {}
        active_admin_count = int(active_admins.get("count") or 0)
        summaries = chat_room_summary_context(conn, rooms, actor, active_admin_count)
        result = [
            public_chat_room(conn, room, actor, active_admin_count, summaries.get(room["room_id"], {}))
            for room in rooms
        ]
        conn.commit()
    return success({
        "rooms": result,
        "unreadCount": sum(item["unreadCount"] for item in result),
        "actor": {
            "type": actor["type"],
            "id": actor["record"].get("public_student_id") if actor["type"] == "STUDENT" else "",
            "name": actor["record"].get("full_name") or "Participante",
        },
    })


def chat_list_messages_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_message_row = runtime.chat_message_row
    connection = runtime.connection
    int_value = runtime.int_value
    parse_datetime = runtime.parse_datetime
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    public_chat_message = runtime.public_chat_message
    public_chat_room = runtime.public_chat_room
    record_chat_message_receipts = runtime.record_chat_message_receipts
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    require_fields(payload, ["roomId"])
    prepare_chat_feature_schema()
    limit = max(1, min(int_value(payload.get("limit"), 80), 120))
    since = parse_datetime(payload.get("since")) if payload.get("since") else None
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        room = accessible_chat_room(conn, str_value(payload["roomId"]), actor)
        if since:
            rows = conn.execute(
                """
                select message_id from courseplatform.chat_messages
                where room_id = %s and updated_at > %s
                order by updated_at asc limit %s
                """,
                (room["room_id"], since, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                select message_id from courseplatform.chat_messages
                where room_id = %s
                order by created_at desc limit %s
                """,
                (room["room_id"], limit),
            ).fetchall()
            rows.reverse()
        message_ids = [row["message_id"] for row in rows]
        record_chat_message_receipts(conn, message_ids, actor)
        messages = [public_chat_message(chat_message_row(conn, message_id), actor) for message_id in message_ids]
        room_payload = public_chat_room(conn, room, actor)
        conn.commit()
    return success({"room": room_payload, "messages": messages})


def chat_send_message_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_message_body = runtime.chat_message_body
    chat_message_row = runtime.chat_message_row
    connection = runtime.connection
    create_student_notification = runtime.create_student_notification
    generate_id = runtime.generate_id
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    prepare_notification_feature_schema = runtime.prepare_notification_feature_schema
    public_chat_message = runtime.public_chat_message
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    upsert_chat_room_read_cursor = runtime.upsert_chat_room_read_cursor
    require_fields(payload, ["roomId"])
    body = chat_message_body(payload.get("body"))
    prepare_chat_feature_schema()
    prepare_notification_feature_schema()
    notification_ids: list[str] = []
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        room = accessible_chat_room(conn, str_value(payload["roomId"]), actor)
        sender_column = "sender_student_id" if actor["type"] == "STUDENT" else "sender_admin_id"
        recent = conn.execute(
            f"""
            select count(*) as count from courseplatform.chat_messages
            where {sender_column} = %s and created_at > now() - interval '1 minute'
            """,
            (actor["id"],),
        ).fetchone() or {}
        if int(recent.get("count") or 0) >= 25:
            raise ApiError("CHAT_RATE_LIMIT", "Aguarde um momento antes de enviar novas mensagens.")
        reply_id = str_value(payload.get("replyToMessageId"))
        if reply_id:
            reply = conn.execute(
                "select message_id from courseplatform.chat_messages where message_id = %s and room_id = %s",
                (reply_id, room["room_id"]),
            ).fetchone()
            if not reply:
                raise ApiError("CHAT_REPLY_NOT_FOUND", "A mensagem selecionada para resposta já não está disponível.")
        message_id = generate_id("CMSG")
        conn.execute(
            """
            insert into courseplatform.chat_messages
              (message_id, room_id, sender_type, sender_student_id, sender_admin_id,
               body, reply_to_message_id, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, 'ACTIVE', now(), now())
            """,
            (
                message_id, room["room_id"], actor["type"],
                actor["id"] if actor["type"] == "STUDENT" else None,
                actor["id"] if actor["type"] == "ADMIN" else None,
                body, reply_id or None,
            ),
        )
        conn.execute(
            "update courseplatform.chat_rooms set updated_at = now() where room_id = %s",
            (room["room_id"],),
        )
        # The sender already has this room open. Advancing the cursor is enough
        # here and avoids rewriting up to 200 historical delivery receipts
        # before the API acknowledges the new message.
        upsert_chat_room_read_cursor(conn, room["room_id"], actor)
        if actor["type"] == "ADMIN" and room.get("room_type") == "SUPPORT" and room.get("owner_student_id"):
            notification_id = create_student_notification(
                conn,
                room["owner_student_id"],
                "GENERAL",
                "Nova mensagem do formador",
                f"{actor['record'].get('full_name') or 'A equipa de formação'} respondeu à sua conversa de apoio.",
                admin_id=actor["id"],
                action_url=f"#/chat/{room['room_id']}",
                entity_type="CHAT_ROOM",
                entity_id=room["room_id"],
                priority="NORMAL",
                send_whatsapp=False,
                send_email=False,
                send_telegram=False,
                send_push=True,
            )
            if notification_id:
                notification_ids.append(notification_id)
        elif actor["type"] == "STUDENT" and room.get("room_type") == "DIRECT":
            recipient_id = (
                room.get("direct_student_two_id")
                if room.get("direct_student_one_id") == actor["id"]
                else room.get("direct_student_one_id")
            )
            notification_id = create_student_notification(
                conn,
                recipient_id,
                "GENERAL",
                "Nova mensagem privada",
                f"{actor['record'].get('full_name') or 'Um colega'} enviou-lhe uma mensagem.",
                action_url=f"#/chat/{room['room_id']}",
                entity_type="CHAT_ROOM",
                entity_id=room["room_id"],
                priority="NORMAL",
                send_whatsapp=False,
                send_email=False,
                send_telegram=False,
                send_push=True,
            )
            if notification_id:
                notification_ids.append(notification_id)
        message = public_chat_message(chat_message_row(conn, message_id), actor)
        conn.commit()
    response = success({"message": message})
    if notification_ids:
        response["_backgroundNotificationIds"] = notification_ids
    return response


def chat_edit_message_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_message_body = runtime.chat_message_body
    chat_message_row = runtime.chat_message_row
    connection = runtime.connection
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    public_chat_message = runtime.public_chat_message
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    require_fields(payload, ["messageId"])
    body = chat_message_body(payload.get("body"))
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        message = conn.execute(
            "select * from courseplatform.chat_messages where message_id = %s",
            (str_value(payload["messageId"]),),
        ).fetchone()
        if not message:
            raise ApiError("CHAT_MESSAGE_NOT_FOUND", "A mensagem não foi encontrada.")
        accessible_chat_room(conn, message["room_id"], actor)
        sender_id = message.get("sender_student_id") if actor["type"] == "STUDENT" else message.get("sender_admin_id")
        if message.get("sender_type") != actor["type"] or sender_id != actor["id"]:
            raise ApiError("CHAT_MESSAGE_FORBIDDEN", "Só pode editar as suas próprias mensagens.")
        if message.get("status") != "ACTIVE":
            raise ApiError("CHAT_MESSAGE_NOT_EDITABLE", "Esta mensagem já não pode ser editada.")
        conn.execute(
            """
            update courseplatform.chat_messages
            set body = %s, edited_at = now(), updated_at = now()
            where message_id = %s
            """,
            (body, message["message_id"]),
        )
        updated = public_chat_message(chat_message_row(conn, message["message_id"]), actor)
        conn.commit()
    return success({"message": updated})


def chat_delete_message_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    audit = runtime.audit
    chat_actor_with_conn = runtime.chat_actor_with_conn
    chat_message_row = runtime.chat_message_row
    connection = runtime.connection
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    public_chat_message = runtime.public_chat_message
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    require_fields(payload, ["messageId"])
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        message = conn.execute(
            "select * from courseplatform.chat_messages where message_id = %s",
            (str_value(payload["messageId"]),),
        ).fetchone()
        if not message:
            raise ApiError("CHAT_MESSAGE_NOT_FOUND", "A mensagem não foi encontrada.")
        accessible_chat_room(conn, message["room_id"], actor)
        sender_id = message.get("sender_student_id") if actor["type"] == "STUDENT" else message.get("sender_admin_id")
        owns_message = message.get("sender_type") == actor["type"] and sender_id == actor["id"]
        if actor["type"] != "ADMIN" and not owns_message:
            raise ApiError("CHAT_MESSAGE_FORBIDDEN", "Não possui permissão para remover esta mensagem.")
        next_status = "DELETED" if owns_message else "MODERATED"
        conn.execute(
            """
            update courseplatform.chat_messages
            set body = '', status = %s, deleted_at = now(), updated_at = now()
            where message_id = %s
            """,
            (next_status, message["message_id"]),
        )
        if actor["type"] == "ADMIN":
            conn.execute(
                """
                update courseplatform.chat_message_reports
                set status = 'RESOLVED', resolved_by_admin_id = %s,
                    resolution_note = 'Mensagem removida pela moderação.', resolved_at = now()
                where message_id = %s and status = 'OPEN'
                """,
                (actor["id"], message["message_id"]),
            )
        audit(
            conn, actor["type"], actor["id"], "CHAT_MESSAGE_REMOVED",
            "CHAT_MESSAGE", message["message_id"], {"status": next_status, "roomId": message["room_id"]},
        )
        updated = public_chat_message(chat_message_row(conn, message["message_id"]), actor)
        conn.commit()
    return success({"message": updated})


def chat_mark_read_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    chat_actor_with_conn = runtime.chat_actor_with_conn
    connection = runtime.connection
    mark_chat_room_read_with_conn = runtime.mark_chat_room_read_with_conn
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    require_fields(payload, ["roomId"])
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        room = accessible_chat_room(conn, str_value(payload["roomId"]), actor)
        mark_chat_room_read_with_conn(conn, room["room_id"], actor)
        conn.commit()
    return success({"roomId": room["room_id"], "unreadCount": 0})


def chat_report_message_action(payload: dict[str, Any], *, runtime: CommunicationRuntime):
    accessible_chat_room = runtime.accessible_chat_room
    audit = runtime.audit
    chat_actor_with_conn = runtime.chat_actor_with_conn
    connection = runtime.connection
    generate_id = runtime.generate_id
    prepare_chat_feature_schema = runtime.prepare_chat_feature_schema
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    require_fields(payload, ["messageId"])
    reason = str_value(payload.get("reason"))
    if len(reason) < 5 or len(reason) > 500:
        raise ApiError("INVALID_CHAT_REPORT", "Descreva o motivo da denúncia entre 5 e 500 caracteres.")
    prepare_chat_feature_schema()
    with connection() as conn:
        actor = chat_actor_with_conn(conn, payload)
        if actor["type"] != "STUDENT":
            raise ApiError("CHAT_REPORT_FORBIDDEN", "Apenas estudantes podem utilizar esta denúncia.")
        message = conn.execute(
            "select * from courseplatform.chat_messages where message_id = %s and status = 'ACTIVE'",
            (str_value(payload["messageId"]),),
        ).fetchone()
        if not message:
            raise ApiError("CHAT_MESSAGE_NOT_FOUND", "A mensagem não foi encontrada.")
        accessible_chat_room(conn, message["room_id"], actor)
        if message.get("sender_student_id") == actor["id"]:
            raise ApiError("CHAT_REPORT_OWN_MESSAGE", "Não pode denunciar a sua própria mensagem.")
        existing = conn.execute(
            """
            select report_id from courseplatform.chat_message_reports
            where message_id = %s and reported_by_student_id = %s and status = 'OPEN'
            """,
            (message["message_id"], actor["id"]),
        ).fetchone()
        if existing:
            raise ApiError("CHAT_REPORT_EXISTS", "Esta mensagem já foi denunciada por si.")
        report_id = generate_id("CRP")
        conn.execute(
            """
            insert into courseplatform.chat_message_reports
              (report_id, message_id, reported_by_student_id, reason, status, created_at)
            values (%s, %s, %s, %s, 'OPEN', now())
            """,
            (report_id, message["message_id"], actor["id"], reason),
        )
        audit(
            conn, "STUDENT", actor["id"], "CHAT_MESSAGE_REPORTED",
            "CHAT_MESSAGE", message["message_id"], {"reportId": report_id},
        )
        conn.commit()
    return success({"reportId": report_id, "reported": True})
