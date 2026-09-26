import copy
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..contracts import ApiError
from ..reviewer_scopes import admin_from_context, require_course_scope, reviewer_course_predicate


ACTION_BINDINGS = (
    ("publicCourseConfig", "public_course_config"),
    ("publicMediaConfig", "public_media_config"),
    ("getMediaConfig", "student_media_config"),
    ("adminGetMediaConfig", "admin_media_config"),
    ("adminListCourses", "admin_list_courses"),
    ("adminGetCourseStructure", "admin_course_structure"),
    ("adminCreateCourseVersion", "admin_create_course_version"),
    ("adminRefreshCourseVersionDraft", "admin_refresh_course_version_draft"),
    ("adminEditCourseVersionDraft", "admin_edit_course_version_draft"),
    ("adminListQuestionBank", "admin_list_question_bank"),
    ("adminGetQuestionBankItem", "admin_get_question_bank_item"),
    ("adminSaveQuestionBankDraft", "admin_save_question_bank_draft"),
    ("adminPublishQuestionBankVersion", "admin_publish_question_bank_version"),
    ("adminAttachQuestionBankVersion", "admin_attach_question_bank_version"),
    ("adminPreviewCourseVersion", "admin_preview_course_version"),
    ("adminPublishCourseVersion", "admin_publish_course_version"),
    ("adminSaveMediaConfig", "admin_save_media_config"),
    ("adminSaveCourse", "admin_save_course"),
    ("adminSaveLesson", "admin_save_lesson"),
    ("adminSaveLessonContent", "admin_save_lesson_content"),
)


@dataclass(frozen=True)
class CatalogRuntime:
    FEEDBACK_RELEASE_MODES: Any
    admin_context: Any
    as_bool: Any
    audit: Any
    connection: Any
    course_structure_snapshot_with_conn: Any
    cursor_page_limit: Any
    cursor_pagination_result: Any
    cursor_scope: Any
    decode_list_cursor: Any
    feedback_release_mode: Any
    fetch_all: Any
    fetch_one: Any
    float_value: Any
    generate_id: Any
    get_settings: Any
    int_value: Any
    iso: Any
    normalize_brand_logo_url: Any
    normalize_email: Any
    persist_media_config: Any
    prepare_assessment_feature_schema: Any
    public_content: Any
    public_course: Any
    public_course_offering: Any
    public_course_version: Any
    public_lesson: Any
    read_media_config: Any
    require_fields: Any
    staff_option: Any
    staff_question: Any
    str_value: Any
    student_context: Any
    student_visible_media: Any
    success: Any
    utc_now: Any


def public_course_config_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    fetch_all = runtime.fetch_all
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    public_course = runtime.public_course
    public_lesson = runtime.public_lesson
    success = runtime.success
    course_id = payload.get("courseId") or get_settings().default_course_id
    course = fetch_one(
        "select * from courseplatform.courses where course_id = %s and status = 'ACTIVE'",
        (course_id,),
    )
    lessons = fetch_all(
        """
        select * from courseplatform.lessons
        where course_id = %s and status = 'ACTIVE'
        order by lesson_number
        """,
        (course_id,),
    )
    return success({"course": public_course(course), "lessons": [public_lesson(row) for row in lessons]})


def read_media_config_action(course_id: str, *, runtime: CatalogRuntime):
    fetch_one = runtime.fetch_one
    get_settings = runtime.get_settings
    key = f"MEDIA_CONFIG:{course_id or get_settings().default_course_id}"
    row = fetch_one("select value from courseplatform.settings where key = %s", (key,))
    if not row:
        row = fetch_one("select value from courseplatform.settings where key = 'MEDIA_CONFIG'")
    if not row or not row.get("value"):
        return {"logoUrl": "", "videos": []}
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return {"logoUrl": "", "videos": []}


def read_media_config_with_conn_action(conn, course_id: str, *, runtime: CatalogRuntime):
    get_settings = runtime.get_settings
    key = f"MEDIA_CONFIG:{course_id or get_settings().default_course_id}"
    row = conn.execute("select value from courseplatform.settings where key = %s", (key,)).fetchone()
    if not row:
        row = conn.execute("select value from courseplatform.settings where key = 'MEDIA_CONFIG'").fetchone()
    if not row or not row.get("value"):
        return {"logoUrl": "", "videos": []}
    try:
        return json.loads(row["value"])
    except json.JSONDecodeError:
        return {"logoUrl": "", "videos": []}


def persist_media_config_action(conn, media: dict[str, Any], *, runtime: CatalogRuntime):
    conn.execute(
        """
        insert into courseplatform.settings (key, value, value_type, description, updated_at)
        values ('MEDIA_CONFIG', %s, 'JSON', 'Logotipo e galeria de vídeos da plataforma.', now())
        on conflict (key) do update
        set value = excluded.value, value_type = excluded.value_type,
            description = excluded.description, updated_at = excluded.updated_at
        """,
        (json.dumps(media),),
    )


def student_visible_media_action(media: dict[str, Any], student: dict[str, Any], *, runtime: CatalogRuntime):
    normalize_email = runtime.normalize_email
    email = normalize_email(student.get("email") or "")
    videos = []
    for video in media.get("videos", []):
        if video.get("status", "ACTIVE") != "ACTIVE":
            continue
        if video.get("visibility") == "SELECTED":
            allowed = [normalize_email(item) for item in video.get("allowedEmails", [])]
            if email not in allowed:
                continue
            videos.append({**video, "allowedEmails": [email]})
        else:
            videos.append({**video, "allowedEmails": []})
    return {**media, "videos": videos}


def student_media_config_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    get_settings = runtime.get_settings
    read_media_config = runtime.read_media_config
    student_context = runtime.student_context
    student_visible_media = runtime.student_visible_media
    success = runtime.success
    _, student = student_context(payload)
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    return success({"mediaConfig": student_visible_media(media, student)})


def public_media_config_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    get_settings = runtime.get_settings
    read_media_config = runtime.read_media_config
    success = runtime.success
    media = read_media_config(payload.get("courseId") or get_settings().default_course_id)
    videos = [
        video
        for video in media.get("videos", [])
        if video.get("status", "ACTIVE") == "ACTIVE" and video.get("visibility") != "SELECTED"
    ]
    return success({"mediaConfig": {**media, "videos": videos}})


def admin_media_config_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    get_settings = runtime.get_settings
    read_media_config = runtime.read_media_config
    success = runtime.success
    admin = admin_from_context(admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"}))
    course_id = payload.get("courseId") or get_settings().default_course_id
    with runtime.connection() as conn:
        require_course_scope(conn, admin, course_id)
    media = read_media_config(course_id)
    return success({"mediaConfig": media})


def course_structure_snapshot_with_conn_action(conn, course_id: str, *, runtime: CatalogRuntime) -> dict[str, Any]:
    iso = runtime.iso
    utc_now = runtime.utc_now
    course = conn.execute(
        "select * from courseplatform.courses where course_id = %s",
        (course_id,),
    ).fetchone()
    if not course:
        raise ApiError("COURSE_NOT_FOUND", "Curso não encontrado.")
    lessons = conn.execute(
        "select * from courseplatform.lessons where course_id = %s order by lesson_number, lesson_id",
        (course_id,),
    ).fetchall()
    lesson_ids = [row["lesson_id"] for row in lessons]
    content_rows = []
    question_rows = []
    option_rows = []
    if lesson_ids:
        content_rows = conn.execute(
            "select * from courseplatform.lesson_content where lesson_id = any(%s) order by section_order, content_id",
            (lesson_ids,),
        ).fetchall()
        question_rows = conn.execute(
            "select * from courseplatform.questions where lesson_id = any(%s) order by question_order, question_id",
            (lesson_ids,),
        ).fetchall()
        question_ids = [row["question_id"] for row in question_rows]
        if question_ids:
            option_rows = conn.execute(
                "select * from courseplatform.question_options where question_id = any(%s) order by option_order, option_id",
                (question_ids,),
            ).fetchall()

    content_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
    questions_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
    options_by_question: dict[str, list[dict[str, Any]]] = {
        row["question_id"]: [] for row in question_rows
    }
    for row in content_rows:
        content_by_lesson[row["lesson_id"]].append({key: iso(value) if isinstance(value, datetime) else value for key, value in row.items()})
    for row in option_rows:
        options_by_question.setdefault(row["question_id"], []).append(
            {key: iso(value) if isinstance(value, datetime) else value for key, value in row.items()}
        )
    for row in question_rows:
        question = {key: iso(value) if isinstance(value, datetime) else value for key, value in row.items() if key != "lesson_id"}
        question["options"] = options_by_question.get(row["question_id"], [])
        questions_by_lesson[row["lesson_id"]].append(question)

    snapshot_lessons = []
    for row in lessons:
        lesson = {key: iso(value) if isinstance(value, datetime) else value for key, value in row.items() if key != "course_id"}
        lesson["content"] = content_by_lesson.get(row["lesson_id"], [])
        lesson["questions"] = questions_by_lesson.get(row["lesson_id"], [])
        snapshot_lessons.append(lesson)
    return {
        "schemaVersion": 1,
        "capturedAt": iso(utc_now()),
        "course": {
            "course_id": course["course_id"],
            "course_code": course.get("course_code"),
            "title": course.get("title"),
            "description": course.get("description"),
            "total_hours": float(course.get("total_hours") or 0),
            "passing_score": float(course.get("passing_score") or 0),
        },
        "lessons": snapshot_lessons,
    }


def validate_course_version_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    issues: list[dict[str, str]] = []

    def add_issue(severity: str, code: str, message: str, entity_type: str = "COURSE", entity_id: str = "") -> None:
        issues.append({
            "severity": severity,
            "code": code,
            "message": message,
            "entityType": entity_type,
            "entityId": entity_id,
        })

    course = snapshot.get("course") if isinstance(snapshot.get("course"), dict) else {}
    lessons = snapshot.get("lessons") if isinstance(snapshot.get("lessons"), list) else []
    active_lessons = [
        lesson for lesson in lessons
        if isinstance(lesson, dict) and str(lesson.get("status") or "ACTIVE").upper() == "ACTIVE"
    ]

    if not str(course.get("course_code") or "").strip():
        add_issue("ERROR", "COURSE_CODE_REQUIRED", "Defina o código do curso antes de publicar.")
    if not str(course.get("title") or "").strip():
        add_issue("ERROR", "COURSE_TITLE_REQUIRED", "Defina o título do curso antes de publicar.")
    try:
        total_hours = float(course.get("total_hours") or 0)
    except (TypeError, ValueError):
        total_hours = 0
    if total_hours <= 0:
        add_issue("ERROR", "COURSE_HOURS_REQUIRED", "A carga horária do curso deve ser superior a zero.")
    try:
        passing_score = float(course.get("passing_score"))
    except (TypeError, ValueError):
        passing_score = -1
    if not 0 <= passing_score <= 100:
        add_issue("ERROR", "COURSE_PASSING_SCORE_INVALID", "A nota mínima do curso deve estar entre 0 e 100.")
    if not active_lessons:
        add_issue("ERROR", "ACTIVE_LESSON_REQUIRED", "Adicione pelo menos um módulo ativo antes de publicar.")

    lesson_ids = {str(lesson.get("lesson_id") or "") for lesson in active_lessons}
    lesson_numbers: dict[str, int] = {}
    number_owners: dict[int, str] = {}
    prerequisite_by_lesson: dict[str, str] = {}
    content_count = 0
    question_count = 0

    for lesson in active_lessons:
        lesson_id = str(lesson.get("lesson_id") or "")
        title = str(lesson.get("title") or "").strip()
        try:
            lesson_number = int(lesson.get("lesson_number") or 0)
        except (TypeError, ValueError):
            lesson_number = 0
        lesson_numbers[lesson_id] = lesson_number
        if not title:
            add_issue("ERROR", "LESSON_TITLE_REQUIRED", "Existe um módulo ativo sem título.", "LESSON", lesson_id)
        if lesson_number <= 0:
            add_issue("ERROR", "LESSON_ORDER_INVALID", f'O módulo "{title or lesson_id}" precisa de uma posição positiva.', "LESSON", lesson_id)
        elif lesson_number in number_owners:
            add_issue("ERROR", "LESSON_ORDER_DUPLICATED", f'A posição {lesson_number} está atribuída a mais de um módulo.', "LESSON", lesson_id)
        else:
            number_owners[lesson_number] = lesson_id

        prerequisite_id = str(lesson.get("prerequisite_lesson_id") or "").strip()
        if prerequisite_id:
            prerequisite_by_lesson[lesson_id] = prerequisite_id
            if prerequisite_id not in lesson_ids:
                add_issue("ERROR", "PREREQUISITE_NOT_ACTIVE", f'O pré-requisito de "{title or lesson_id}" não pertence aos módulos ativos.', "LESSON", lesson_id)
            elif prerequisite_id == lesson_id:
                add_issue("ERROR", "PREREQUISITE_SELF_REFERENCE", f'O módulo "{title or lesson_id}" não pode depender de si próprio.', "LESSON", lesson_id)

        content = [
            item for item in (lesson.get("content") or [])
            if isinstance(item, dict) and str(item.get("status") or "ACTIVE").upper() == "ACTIVE"
        ]
        questions = [
            item for item in (lesson.get("questions") or [])
            if isinstance(item, dict) and str(item.get("status") or "ACTIVE").upper() == "ACTIVE"
        ]
        content_count += len(content)
        question_count += len(questions)
        if not content and not questions:
            add_issue("ERROR", "LESSON_EMPTY", f'O módulo "{title or lesson_id}" não possui conteúdo nem atividade ativa.', "LESSON", lesson_id)
        elif not content:
            add_issue("WARNING", "LESSON_WITHOUT_CONTENT", f'O módulo "{title or lesson_id}" contém avaliação, mas não possui conteúdo ativo.', "LESSON", lesson_id)

        for question in questions:
            question_id = str(question.get("question_id") or "")
            prompt = str(question.get("prompt") or "").strip()
            question_type = str(question.get("question_type") or "").strip().upper()
            if not prompt:
                add_issue("ERROR", "QUESTION_PROMPT_REQUIRED", f'Existe uma questão sem enunciado no módulo "{title or lesson_id}".', "QUESTION", question_id)
            try:
                points = float(question.get("points") or 0)
            except (TypeError, ValueError):
                points = 0
            if points <= 0:
                add_issue("ERROR", "QUESTION_POINTS_INVALID", f'A questão "{prompt or question_id}" deve ter pontuação superior a zero.', "QUESTION", question_id)
            if question_type in {"SINGLE_CHOICE", "TRUE_FALSE", "MULTIPLE_CHOICE"}:
                options = [item for item in (question.get("options") or []) if isinstance(item, dict)]
                valid_options = [item for item in options if str(item.get("option_text") or item.get("option_label") or "").strip()]
                correct_options = [
                    item for item in valid_options
                    if item.get("is_correct") is True or str(item.get("is_correct") or "").lower() in {"true", "1", "yes", "sim"}
                ]
                has_legacy_answer = bool(str(question.get("correct_answer") or "").strip())
                if len(valid_options) < 2:
                    add_issue("ERROR", "QUESTION_OPTIONS_REQUIRED", f'A questão "{prompt or question_id}" precisa de pelo menos duas opções.', "QUESTION", question_id)
                if not correct_options and not has_legacy_answer:
                    add_issue("ERROR", "QUESTION_CORRECT_ANSWER_REQUIRED", f'A questão "{prompt or question_id}" não possui resposta correta.', "QUESTION", question_id)

    for lesson_id, prerequisite_id in prerequisite_by_lesson.items():
        if prerequisite_id in lesson_numbers and lesson_numbers.get(prerequisite_id, 0) >= lesson_numbers.get(lesson_id, 0):
            add_issue("ERROR", "PREREQUISITE_ORDER_INVALID", "O pré-requisito deve aparecer antes do módulo dependente.", "LESSON", lesson_id)
        seen = {lesson_id}
        current = prerequisite_id
        while current and current in prerequisite_by_lesson:
            if current in seen:
                add_issue("ERROR", "PREREQUISITE_CYCLE", "Foi detetado um ciclo entre os pré-requisitos dos módulos.", "LESSON", lesson_id)
                break
            seen.add(current)
            current = prerequisite_by_lesson.get(current, "")

    errors = sum(1 for issue in issues if issue["severity"] == "ERROR")
    warnings = sum(1 for issue in issues if issue["severity"] == "WARNING")
    return {
        "valid": errors == 0,
        "issues": issues,
        "summary": {
            "lessonCount": len(active_lessons),
            "contentCount": content_count,
            "questionCount": question_count,
            "errorCount": errors,
            "warningCount": warnings,
        },
    }


def course_version_preview(snapshot: dict[str, Any]) -> dict[str, Any]:
    course = snapshot.get("course") if isinstance(snapshot.get("course"), dict) else {}
    lessons = snapshot.get("lessons") if isinstance(snapshot.get("lessons"), list) else []
    return {
        "course": {
            "courseCode": course.get("course_code"),
            "title": course.get("title"),
            "description": course.get("description"),
            "totalHours": course.get("total_hours"),
            "passingScore": course.get("passing_score"),
        },
        "lessons": [
            {
                "lessonId": lesson.get("lesson_id"),
                "lessonNumber": lesson.get("lesson_number"),
                "title": lesson.get("title"),
                "summary": lesson.get("summary"),
                "prerequisiteLessonId": lesson.get("prerequisite_lesson_id"),
                "contentCount": sum(
                    1 for item in (lesson.get("content") or [])
                    if isinstance(item, dict) and str(item.get("status") or "ACTIVE").upper() == "ACTIVE"
                ),
                "questionCount": sum(
                    1 for item in (lesson.get("questions") or [])
                    if isinstance(item, dict) and str(item.get("status") or "ACTIVE").upper() == "ACTIVE"
                ),
            }
            for lesson in lessons
            if isinstance(lesson, dict) and str(lesson.get("status") or "ACTIVE").upper() == "ACTIVE"
        ],
    }


def course_version_draft_editor(snapshot: dict[str, Any]) -> dict[str, Any]:
    course = snapshot.get("course") if isinstance(snapshot.get("course"), dict) else {}
    lessons = snapshot.get("lessons") if isinstance(snapshot.get("lessons"), list) else []
    return {
        "course": {
            "courseCode": course.get("course_code"),
            "title": course.get("title"),
            "description": course.get("description"),
            "totalHours": course.get("total_hours"),
            "passingScore": course.get("passing_score"),
        },
        "lessons": [
            {
                "lessonId": lesson.get("lesson_id"),
                "lessonNumber": lesson.get("lesson_number"),
                "title": lesson.get("title"),
                "summary": lesson.get("summary"),
                "status": lesson.get("status") or "ACTIVE",
                "prerequisiteLessonId": lesson.get("prerequisite_lesson_id"),
                "content": [
                    {
                        "contentId": item.get("content_id"),
                        "sectionOrder": item.get("section_order"),
                        "sectionType": item.get("section_type"),
                        "title": item.get("title"),
                        "bodyHtml": item.get("body_html"),
                        "estimatedMinutes": item.get("estimated_minutes"),
                        "isRequired": bool(item.get("is_required", True)),
                        "status": item.get("status") or "ACTIVE",
                    }
                    for item in (lesson.get("content") or [])
                    if isinstance(item, dict)
                ],
                "questionCount": sum(1 for item in (lesson.get("questions") or []) if isinstance(item, dict)),
            }
            for lesson in lessons
            if isinstance(lesson, dict)
        ],
    }


def _draft_text(value: Any, field: str, *, required: bool = False, maximum: int = 10000) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ApiError("COURSE_VERSION_FIELD_REQUIRED", f"O campo {field} é obrigatório.")
    if len(text) > maximum:
        raise ApiError("COURSE_VERSION_FIELD_TOO_LONG", f"O campo {field} excede o tamanho permitido.")
    return text


def _draft_number(value: Any, field: str, *, minimum: float = 0, maximum: float = 100000) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ApiError("COURSE_VERSION_FIELD_INVALID", f"O campo {field} deve ser numérico.") from exc
    if not minimum <= number <= maximum:
        raise ApiError("COURSE_VERSION_FIELD_INVALID", f"O campo {field} está fora do intervalo permitido.")
    return number


def _draft_entity(items: list[dict[str, Any]], id_field: str, entity_id: Any, label: str) -> dict[str, Any]:
    normalized_id = str(entity_id or "").strip()
    for item in items:
        if isinstance(item, dict) and str(item.get(id_field) or "") == normalized_id:
            return item
    raise ApiError("COURSE_VERSION_ENTITY_NOT_FOUND", f"{label} não encontrado no rascunho.")


QUESTION_BANK_TYPES = {
    "SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE", "SHORT_TEXT", "LONG_TEXT", "NUMERIC",
}
QUESTION_BANK_DIFFICULTIES = {"EASY", "MEDIUM", "HARD"}
QUESTION_BANK_OBJECTIVE_TYPES = {"SINGLE_CHOICE", "MULTIPLE_CHOICE", "TRUE_FALSE"}


def normalize_question_bank_draft(payload: dict[str, Any], *, require_publishable: bool = True) -> dict[str, Any]:
    question_type = str(payload.get("questionType") or "").strip().upper()
    difficulty = str(payload.get("difficulty") or "MEDIUM").strip().upper()
    if question_type not in QUESTION_BANK_TYPES:
        raise ApiError("QUESTION_BANK_TYPE_INVALID", "Selecione um tipo de questão válido.")
    if difficulty not in QUESTION_BANK_DIFFICULTIES:
        raise ApiError("QUESTION_BANK_DIFFICULTY_INVALID", "Selecione uma dificuldade válida.")
    title = _draft_text(payload.get("title"), "título da questão", required=True, maximum=240)
    prompt = _draft_text(payload.get("prompt"), "enunciado", required=True, maximum=10000)
    explanation = _draft_text(payload.get("explanation"), "explicação", maximum=10000)
    points = _draft_number(payload.get("points", 1), "pontuação", minimum=0.01, maximum=10000)
    tags_value = payload.get("tags") or []
    if isinstance(tags_value, str):
        tags_value = tags_value.split(",")
    if not isinstance(tags_value, list):
        raise ApiError("QUESTION_BANK_TAGS_INVALID", "As etiquetas da questão são inválidas.")
    tags = list(dict.fromkeys(str(tag).strip().lower() for tag in tags_value if str(tag).strip()))
    if len(tags) > 20 or any(len(tag) > 60 for tag in tags):
        raise ApiError("QUESTION_BANK_TAGS_INVALID", "Use no máximo 20 etiquetas com até 60 caracteres.")
    options = []
    raw_options = payload.get("options") or []
    if not isinstance(raw_options, list):
        raise ApiError("QUESTION_BANK_OPTIONS_INVALID", "As opções da questão são inválidas.")
    for index, option in enumerate(raw_options, start=1):
        if not isinstance(option, dict):
            raise ApiError("QUESTION_BANK_OPTIONS_INVALID", "As opções da questão são inválidas.")
        option_text = _draft_text(option.get("optionText"), f"opção {index}", required=True, maximum=2000)
        options.append({
            "optionOrder": index,
            "optionLabel": _draft_text(option.get("optionLabel"), f"rótulo da opção {index}", maximum=20),
            "optionText": option_text,
            "isCorrect": bool(option.get("isCorrect")),
        })
    if question_type in QUESTION_BANK_OBJECTIVE_TYPES:
        if require_publishable and len(options) < 2:
            raise ApiError("QUESTION_BANK_OPTIONS_REQUIRED", "Questões objetivas precisam de pelo menos duas opções.")
        correct_count = sum(1 for option in options if option["isCorrect"])
        expected = 1 if question_type in {"SINGLE_CHOICE", "TRUE_FALSE"} else None
        if (require_publishable and correct_count < 1) or (expected is not None and correct_count > 1):
            message = "Indique pelo menos uma opção correta."
            if expected == 1:
                message = "Este tipo de questão deve ter exatamente uma opção correta."
            raise ApiError("QUESTION_BANK_CORRECT_OPTION_INVALID", message)
        if question_type == "TRUE_FALSE" and ((require_publishable and len(options) != 2) or len(options) > 2):
            raise ApiError("QUESTION_BANK_TRUE_FALSE_INVALID", "Questões de verdadeiro ou falso devem ter duas opções.")
    elif options:
        raise ApiError("QUESTION_BANK_OPTIONS_NOT_ALLOWED", "Este tipo de questão não utiliza opções.")
    return {
        "title": title,
        "questionType": question_type,
        "prompt": prompt,
        "explanation": explanation,
        "difficulty": difficulty,
        "tags": tags,
        "points": points,
        "correctAnswer": _draft_text(payload.get("correctAnswer"), "resposta de referência", maximum=10000),
        "options": options,
    }


def public_question_bank_version(row: dict[str, Any], options: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "bankQuestionVersionId": row.get("bank_question_version_id"),
        "bankQuestionId": row.get("bank_question_id"),
        "versionNumber": row.get("version_number"),
        "status": row.get("status"),
        "questionType": row.get("question_type"),
        "prompt": row.get("prompt"),
        "explanation": row.get("explanation") or "",
        "difficulty": row.get("difficulty"),
        "tags": row.get("tags") or [],
        "points": float(row.get("points") or 0),
        "correctAnswer": row.get("correct_answer") or "",
        "updatedAt": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        "publishedAt": row.get("published_at").isoformat() if row.get("published_at") else None,
        "options": [{
            "bankOptionId": option.get("bank_option_id"),
            "optionOrder": option.get("option_order"),
            "optionLabel": option.get("option_label") or "",
            "optionText": option.get("option_text"),
            "isCorrect": bool(option.get("is_correct")),
        } for option in (options or [])],
    }


def admin_list_question_bank_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    runtime.admin_context(payload, {"OWNER", "ADMIN"})
    course_id = str(payload.get("courseId") or "").strip()
    query = str(payload.get("query") or "").strip()
    status = str(payload.get("status") or "ALL").strip().upper()
    params: list[Any] = []
    clauses = ["1 = 1"]
    if course_id:
        clauses.append("(item.course_id = %s or item.course_id is null)")
        params.append(course_id)
    if status in {"ACTIVE", "ARCHIVED"}:
        clauses.append("item.status = %s")
        params.append(status)
    if query:
        clauses.append("(item.title ilike %s or item.question_code ilike %s or coalesce(latest.prompt, '') ilike %s)")
        params.extend([f"%{query}%"] * 3)
    params.append(min(max(runtime.int_value(payload.get("limit"), 100), 1), 200))
    sql = f"""
        select item.*, latest.bank_question_version_id, latest.version_number,
               latest.status as version_status, latest.question_type, latest.prompt,
               latest.difficulty, latest.tags, latest.points, latest.updated_at as version_updated_at
               , published.bank_question_version_id as published_version_id,
               published.version_number as published_version_number,
               published.question_type as published_question_type,
               published.difficulty as published_difficulty
        from courseplatform.question_bank_items item
        left join lateral (
          select version.* from courseplatform.question_bank_versions version
          where version.bank_question_id = item.bank_question_id
          order by (version.status = 'DRAFT') desc, version.version_number desc limit 1
        ) latest on true
        left join lateral (
          select version.bank_question_version_id, version.version_number, version.question_type, version.difficulty
          from courseplatform.question_bank_versions version
          where version.bank_question_id = item.bank_question_id and version.status = 'PUBLISHED'
          order by version.version_number desc limit 1
        ) published on true
        where {' and '.join(clauses)}
        order by item.updated_at desc, item.bank_question_id
        limit %s
    """
    with runtime.connection() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    return runtime.success({"questions": [{
        "bankQuestionId": row.get("bank_question_id"),
        "questionCode": row.get("question_code"),
        "courseId": row.get("course_id"),
        "title": row.get("title"),
        "status": row.get("status"),
        "latestVersion": {
            "bankQuestionVersionId": row.get("bank_question_version_id"),
            "versionNumber": row.get("version_number"),
            "status": row.get("version_status"),
            "questionType": row.get("question_type"),
            "prompt": row.get("prompt"),
            "difficulty": row.get("difficulty"),
            "tags": row.get("tags") or [],
            "points": float(row.get("points") or 0),
        } if row.get("bank_question_version_id") else None,
        "publishedVersion": {
            "bankQuestionVersionId": row.get("published_version_id"),
            "versionNumber": row.get("published_version_number"),
            "questionType": row.get("published_question_type"),
            "difficulty": row.get("published_difficulty"),
        } if row.get("published_version_id") else None,
    } for row in rows]})


def _question_bank_detail(conn, bank_question_id: str) -> dict[str, Any]:
    item = conn.execute(
        "select * from courseplatform.question_bank_items where bank_question_id = %s",
        (bank_question_id,),
    ).fetchone()
    if not item:
        raise ApiError("QUESTION_BANK_NOT_FOUND", "Questão não encontrada no banco.")
    versions = conn.execute(
        "select * from courseplatform.question_bank_versions where bank_question_id = %s order by version_number desc",
        (bank_question_id,),
    ).fetchall()
    version_ids = [row["bank_question_version_id"] for row in versions]
    option_rows = []
    if version_ids:
        option_rows = conn.execute(
            "select * from courseplatform.question_bank_options where bank_question_version_id = any(%s) order by bank_question_version_id, option_order",
            (version_ids,),
        ).fetchall()
    options_by_version: dict[str, list[dict[str, Any]]] = {}
    for option in option_rows:
        options_by_version.setdefault(option["bank_question_version_id"], []).append(option)
    return {
        "bankQuestionId": item.get("bank_question_id"),
        "questionCode": item.get("question_code"),
        "courseId": item.get("course_id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "versions": [public_question_bank_version(row, options_by_version.get(row["bank_question_version_id"], [])) for row in versions],
    }


def admin_get_question_bank_item_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    runtime.admin_context(payload, {"OWNER", "ADMIN"})
    runtime.require_fields(payload, ["bankQuestionId"])
    with runtime.connection() as conn:
        item = _question_bank_detail(conn, str(payload["bankQuestionId"]))
    return runtime.success({"question": item})


def admin_save_question_bank_draft_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    _, admin = runtime.admin_context(payload, {"OWNER", "ADMIN"})
    normalized = normalize_question_bank_draft(payload, require_publishable=False)
    bank_question_id = str(payload.get("bankQuestionId") or "").strip() or runtime.generate_id("QBANK")
    course_id = str(payload.get("courseId") or "").strip() or None
    with runtime.connection() as conn:
        item = conn.execute(
            "select * from courseplatform.question_bank_items where bank_question_id = %s for update",
            (bank_question_id,),
        ).fetchone()
        if not item:
            item = conn.execute(
                """insert into courseplatform.question_bank_items
                   (bank_question_id, course_id, question_code, title, created_by, created_at, updated_at)
                   values (%s, %s, %s, %s, %s, now(), now()) returning *""",
                (bank_question_id, course_id, str(payload.get("questionCode") or bank_question_id), normalized["title"], admin["admin_id"]),
            ).fetchone()
        else:
            if course_id != item.get("course_id"):
                raise ApiError("QUESTION_BANK_COURSE_IMMUTABLE", "O âmbito do curso não pode ser alterado depois da criação.")
            item = conn.execute(
                "update courseplatform.question_bank_items set title = %s, updated_at = now() where bank_question_id = %s returning *",
                (normalized["title"], bank_question_id),
            ).fetchone()
        version = conn.execute(
            "select * from courseplatform.question_bank_versions where bank_question_id = %s and status = 'DRAFT' for update",
            (bank_question_id,),
        ).fetchone()
        if not version:
            latest = conn.execute(
                "select coalesce(max(version_number), 0) as version_number from courseplatform.question_bank_versions where bank_question_id = %s",
                (bank_question_id,),
            ).fetchone() or {}
            version = conn.execute(
                """insert into courseplatform.question_bank_versions
                   (bank_question_version_id, bank_question_id, version_number, status, question_type,
                    prompt, explanation, difficulty, tags, points, correct_answer, created_by, created_at, updated_at)
                   values (%s, %s, %s, 'DRAFT', %s, %s, %s, %s, %s, %s, %s, %s, now(), now()) returning *""",
                (runtime.generate_id("QBVER"), bank_question_id, int(latest.get("version_number") or 0) + 1,
                 normalized["questionType"], normalized["prompt"], normalized["explanation"], normalized["difficulty"],
                 normalized["tags"], normalized["points"], normalized["correctAnswer"], admin["admin_id"]),
            ).fetchone()
        else:
            version = conn.execute(
                """update courseplatform.question_bank_versions set question_type = %s, prompt = %s,
                   explanation = %s, difficulty = %s, tags = %s, points = %s, correct_answer = %s, updated_at = now()
                   where bank_question_version_id = %s and status = 'DRAFT' returning *""",
                (normalized["questionType"], normalized["prompt"], normalized["explanation"], normalized["difficulty"],
                 normalized["tags"], normalized["points"], normalized["correctAnswer"], version["bank_question_version_id"]),
            ).fetchone()
        conn.execute("delete from courseplatform.question_bank_options where bank_question_version_id = %s", (version["bank_question_version_id"],))
        for option in normalized["options"]:
            conn.execute(
                """insert into courseplatform.question_bank_options
                   (bank_option_id, bank_question_version_id, option_order, option_label, option_text, is_correct)
                   values (%s, %s, %s, %s, %s, %s)""",
                (runtime.generate_id("QBOPT"), version["bank_question_version_id"], option["optionOrder"],
                 option["optionLabel"] or None, option["optionText"], option["isCorrect"]),
            )
        runtime.audit(conn, "ADMIN", admin["admin_id"], "QUESTION_BANK_DRAFT_SAVED", "QUESTION_BANK", bank_question_id,
                      {"courseId": course_id, "versionNumber": version["version_number"]})
        conn.commit()
        detail = _question_bank_detail(conn, bank_question_id)
    return runtime.success({"question": detail})


def admin_publish_question_bank_version_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    _, admin = runtime.admin_context(payload, {"OWNER", "ADMIN"})
    runtime.require_fields(payload, ["bankQuestionVersionId"])
    version_id = str(payload["bankQuestionVersionId"])
    with runtime.connection() as conn:
        version = conn.execute(
            "select * from courseplatform.question_bank_versions where bank_question_version_id = %s for update",
            (version_id,),
        ).fetchone()
        if not version:
            raise ApiError("QUESTION_BANK_VERSION_NOT_FOUND", "Versão da questão não encontrada.")
        if version.get("status") != "DRAFT":
            raise ApiError("QUESTION_BANK_VERSION_NOT_DRAFT", "Apenas um rascunho pode ser publicado.")
        options = conn.execute(
            "select * from courseplatform.question_bank_options where bank_question_version_id = %s order by option_order",
            (version_id,),
        ).fetchall()
        normalize_question_bank_draft({
            "title": "Publicação", "questionType": version.get("question_type"), "prompt": version.get("prompt"),
            "explanation": version.get("explanation"), "difficulty": version.get("difficulty"), "tags": version.get("tags"),
            "points": version.get("points"), "correctAnswer": version.get("correct_answer"),
            "options": [{"optionText": row.get("option_text"), "optionLabel": row.get("option_label"), "isCorrect": row.get("is_correct")} for row in options],
        })
        published = conn.execute(
            """update courseplatform.question_bank_versions set status = 'PUBLISHED', published_by = %s,
               published_at = now(), updated_at = now() where bank_question_version_id = %s and status = 'DRAFT' returning *""",
            (admin["admin_id"], version_id),
        ).fetchone()
        runtime.audit(conn, "ADMIN", admin["admin_id"], "QUESTION_BANK_VERSION_PUBLISHED", "QUESTION_BANK_VERSION", version_id,
                      {"bankQuestionId": version["bank_question_id"], "versionNumber": version["version_number"]})
        conn.commit()
    return runtime.success({"version": public_question_bank_version(published, options)})


def admin_attach_question_bank_version_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    _, admin = runtime.admin_context(payload, {"OWNER", "ADMIN"})
    runtime.require_fields(payload, ["courseVersionId", "lessonId", "bankQuestionVersionId"])
    with runtime.connection() as conn:
        course_version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s for update",
            (payload["courseVersionId"],),
        ).fetchone()
        if not course_version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        if course_version.get("status") != "DRAFT":
            raise ApiError("COURSE_VERSION_NOT_DRAFT", "Questões só podem ser adicionadas a um rascunho.")
        version = conn.execute(
            """select version.*, item.course_id, item.title as bank_title
               from courseplatform.question_bank_versions version
               join courseplatform.question_bank_items item on item.bank_question_id = version.bank_question_id
               where version.bank_question_version_id = %s and version.status = 'PUBLISHED'""",
            (payload["bankQuestionVersionId"],),
        ).fetchone()
        if not version:
            raise ApiError("QUESTION_BANK_VERSION_NOT_PUBLISHED", "Selecione uma versão publicada da questão.")
        if version.get("course_id") and version.get("course_id") != course_version.get("course_id"):
            raise ApiError("QUESTION_BANK_COURSE_FORBIDDEN", "Esta questão pertence a outro curso.")
        options = conn.execute(
            "select * from courseplatform.question_bank_options where bank_question_version_id = %s order by option_order",
            (version["bank_question_version_id"],),
        ).fetchall()
        snapshot = stored_course_version_snapshot(course_version)
        lesson = _draft_entity(snapshot.get("lessons") or [], "lesson_id", payload["lessonId"], "Módulo")
        questions = lesson.setdefault("questions", [])
        if any(str(question.get("bank_question_version_id") or "") == version["bank_question_version_id"] for question in questions if isinstance(question, dict)):
            raise ApiError("QUESTION_BANK_ALREADY_ATTACHED", "Esta versão da questão já está no módulo.")
        questions.append({
            "question_id": runtime.generate_id("QSN"),
            "question_order": len(questions) + 1,
            "question_type": version["question_type"],
            "prompt": version["prompt"],
            "explanation": version.get("explanation") or "",
            "difficulty": version["difficulty"],
            "tags": version.get("tags") or [],
            "points": float(version.get("points") or 1),
            "correct_answer": version.get("correct_answer") or "",
            "bank_question_id": version["bank_question_id"],
            "bank_question_version_id": version["bank_question_version_id"],
            "bank_question_version_number": version["version_number"],
            "status": "ACTIVE",
            "options": [{
                "option_id": runtime.generate_id("OPT"),
                "option_order": option["option_order"],
                "option_label": option.get("option_label"),
                "option_text": option["option_text"],
                "is_correct": bool(option.get("is_correct")),
            } for option in options],
        })
        course_data = snapshot["course"]
        row = conn.execute(
            """update courseplatform.course_versions set title = %s, description = %s, total_hours = %s,
               passing_score = %s, content_snapshot_json = %s, updated_at = now()
               where course_version_id = %s and status = 'DRAFT' returning *""",
            (course_data.get("title"), course_data.get("description"), runtime.float_value(course_data.get("total_hours")),
             runtime.float_value(course_data.get("passing_score"), 60), json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
             course_version["course_version_id"]),
        ).fetchone()
        runtime.audit(conn, "ADMIN", admin["admin_id"], "QUESTION_BANK_VERSION_ATTACHED", "COURSE_VERSION", row["course_version_id"],
                      {"lessonId": payload["lessonId"], "bankQuestionVersionId": version["bank_question_version_id"]})
        conn.commit()
    return runtime.success({
        "courseVersion": runtime.public_course_version(row),
        "validation": validate_course_version_snapshot(snapshot),
        "preview": course_version_preview(snapshot),
        "draftEditor": course_version_draft_editor(snapshot),
    })


def _reorder_draft_items(items: list[dict[str, Any]], ids: Any, id_field: str, order_field: str, label: str) -> None:
    if not isinstance(ids, list) or any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ApiError("COURSE_VERSION_ORDER_INVALID", f"A ordem de {label} é inválida.")
    current_ids = [str(item.get(id_field) or "") for item in items if isinstance(item, dict)]
    if len(ids) != len(set(ids)) or set(ids) != set(current_ids):
        raise ApiError("COURSE_VERSION_ORDER_INCOMPLETE", f"A ordem deve incluir todos os {label}, sem repetições.")
    positions = {entity_id: index for index, entity_id in enumerate(ids, start=1)}
    items.sort(key=lambda item: positions[str(item.get(id_field) or "")])
    for item in items:
        item[order_field] = positions[str(item.get(id_field) or "")]


def edit_course_version_draft_snapshot(snapshot: dict[str, Any], operation: Any, changes: Any) -> dict[str, Any]:
    operation_name = str(operation or "").strip().upper()
    if not isinstance(changes, dict):
        raise ApiError("COURSE_VERSION_CHANGES_INVALID", "As alterações do rascunho são inválidas.")
    edited = copy.deepcopy(snapshot)
    course = edited.setdefault("course", {})
    lessons = edited.setdefault("lessons", [])

    if operation_name == "UPDATE_COURSE":
        course["course_code"] = _draft_text(changes.get("courseCode"), "código", required=True, maximum=80)
        course["title"] = _draft_text(changes.get("title"), "título", required=True, maximum=240)
        course["description"] = _draft_text(changes.get("description"), "descrição", maximum=5000)
        course["total_hours"] = _draft_number(changes.get("totalHours"), "carga horária")
        course["passing_score"] = _draft_number(changes.get("passingScore"), "nota mínima", maximum=100)
    elif operation_name == "UPDATE_LESSON":
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        lesson["title"] = _draft_text(changes.get("title"), "título do módulo", required=True, maximum=240)
        lesson["summary"] = _draft_text(changes.get("summary"), "resumo do módulo", maximum=5000)
    elif operation_name == "CREATE_LESSON":
        lesson_id = _draft_text(changes.get("lessonId"), "identificador do módulo", required=True, maximum=100)
        if any(str(item.get("lesson_id") or "") == lesson_id for item in lessons if isinstance(item, dict)):
            raise ApiError("COURSE_VERSION_ENTITY_EXISTS", "Já existe um módulo com este identificador no rascunho.")
        lessons.append({
            "lesson_id": lesson_id,
            "lesson_number": len(lessons) + 1,
            "title": _draft_text(changes.get("title"), "título do módulo", required=True, maximum=240),
            "slug": "",
            "summary": _draft_text(changes.get("summary"), "resumo do módulo", maximum=5000),
            "theory_minutes": 0,
            "exercise_minutes": 0,
            "individual_minutes": 0,
            "submission_duration_minutes": 180,
            "passing_score": 60,
            "feedback_release_mode": "AFTER_REVIEW",
            "show_correct_answers": False,
            "show_explanations": False,
            "prerequisite_lesson_id": None,
            "status": "ACTIVE",
            "content": [],
            "questions": [],
        })
    elif operation_name in {"REMOVE_LESSON", "RESTORE_LESSON"}:
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        lesson["status"] = "DELETED" if operation_name == "REMOVE_LESSON" else "ACTIVE"
    elif operation_name == "UPDATE_CONTENT":
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        content = _draft_entity(lesson.get("content") or [], "content_id", changes.get("contentId"), "Conteúdo")
        content["title"] = _draft_text(changes.get("title"), "título do conteúdo", required=True, maximum=240)
        content["body_html"] = _draft_text(changes.get("bodyHtml"), "conteúdo", maximum=100000)
        content["estimated_minutes"] = _draft_number(changes.get("estimatedMinutes"), "duração estimada")
        content["is_required"] = bool(changes.get("isRequired"))
    elif operation_name == "CREATE_CONTENT":
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        content_items = lesson.setdefault("content", [])
        content_id = _draft_text(changes.get("contentId"), "identificador do conteúdo", required=True, maximum=100)
        if any(str(item.get("content_id") or "") == content_id for item in content_items if isinstance(item, dict)):
            raise ApiError("COURSE_VERSION_ENTITY_EXISTS", "Já existe um conteúdo com este identificador no rascunho.")
        content_items.append({
            "content_id": content_id,
            "section_order": len(content_items) + 1,
            "section_type": _draft_text(changes.get("sectionType") or "TEORIA", "tipo de conteúdo", required=True, maximum=80).upper(),
            "title": _draft_text(changes.get("title"), "título do conteúdo", required=True, maximum=240),
            "body_html": _draft_text(changes.get("bodyHtml"), "conteúdo", maximum=100000),
            "estimated_minutes": _draft_number(changes.get("estimatedMinutes") or 0, "duração estimada"),
            "is_required": bool(changes.get("isRequired", True)),
            "status": "ACTIVE",
        })
    elif operation_name in {"REMOVE_CONTENT", "RESTORE_CONTENT"}:
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        content = _draft_entity(lesson.get("content") or [], "content_id", changes.get("contentId"), "Conteúdo")
        content["status"] = "DELETED" if operation_name == "REMOVE_CONTENT" else "ACTIVE"
    elif operation_name == "REORDER_LESSONS":
        _reorder_draft_items(lessons, changes.get("lessonIds"), "lesson_id", "lesson_number", "módulos")
    elif operation_name == "REORDER_CONTENT":
        lesson = _draft_entity(lessons, "lesson_id", changes.get("lessonId"), "Módulo")
        _reorder_draft_items(lesson.get("content") or [], changes.get("contentIds"), "content_id", "section_order", "conteúdos")
    else:
        raise ApiError("COURSE_VERSION_OPERATION_INVALID", "A operação solicitada para o rascunho não é válida.")
    return edited


def stored_course_version_snapshot(version: dict[str, Any]) -> dict[str, Any]:
    snapshot = version.get("content_snapshot_json") or {}
    if isinstance(snapshot, str):
        try:
            snapshot = json.loads(snapshot)
        except json.JSONDecodeError as exc:
            raise ApiError(
                "COURSE_VERSION_SNAPSHOT_INVALID",
                "O snapshot desta versão não é válido e precisa de intervenção administrativa.",
            ) from exc
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("course"), dict):
        raise ApiError(
            "COURSE_VERSION_SNAPSHOT_INVALID",
            "O snapshot desta versão não é válido e precisa de intervenção administrativa.",
        )
    return snapshot


def admin_list_courses_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    cursor_page_limit = runtime.cursor_page_limit
    cursor_pagination_result = runtime.cursor_pagination_result
    cursor_scope = runtime.cursor_scope
    decode_list_cursor = runtime.decode_list_cursor
    fetch_all = runtime.fetch_all
    public_course = runtime.public_course
    str_value = runtime.str_value
    success = runtime.success
    admin = admin_from_context(admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"}))
    limit = cursor_page_limit(payload)
    query = str_value(payload.get("query")).lower()
    status = (payload.get("status") or "ALL").upper()
    content = (payload.get("content") or "ALL").upper()
    if content not in {"ALL", "WITH_MODULES", "WITHOUT_MODULES", "WITH_GROUPS", "WITHOUT_GROUPS"}:
        raise ApiError("INVALID_COURSE_FILTER", "O filtro de conteúdo é inválido.")
    scope = cursor_scope("admin-courses", status, content, query)
    cursor = decode_list_cursor(payload.get("cursor"), "admin-courses", scope, sort_type="text")
    conditions = ["(%s = 'ALL' or c.status = %s)"]
    params: list[Any] = [status, status]
    reviewer_sql, reviewer_params = reviewer_course_predicate(admin, "c.course_id")
    conditions.append(f"({reviewer_sql})")
    params.extend(reviewer_params)
    if query:
        conditions.append("(lower(c.course_id || ' ' || c.course_code || ' ' || c.title || ' ' || coalesce(c.description,'')) like %s)")
        params.append(f"%{query}%")
    where = " and ".join(conditions)
    content_sql = {
        "ALL": "true",
        "WITH_MODULES": "lesson_count > 0",
        "WITHOUT_MODULES": "lesson_count = 0",
        "WITH_GROUPS": "group_count > 0",
        "WITHOUT_GROUPS": "group_count = 0",
    }[content]
    cursor_sql = ""
    cursor_params: list[Any] = []
    if cursor:
        cursor_title, cursor_id = cursor
        cursor_sql = "where (pagination_sort_text > %s or (pagination_sort_text = %s and course_id > %s))"
        cursor_params.extend((cursor_title, cursor_title, cursor_id))
    rows = fetch_all(
        f"""
        with course_rows as (
          select c.*,
            count(distinct l.lesson_id) filter (where coalesce(l.status, 'ACTIVE') <> 'DELETED') as lesson_count,
            count(distinct g.group_id) filter (where coalesce(g.status, 'ACTIVE') <> 'DELETED') as group_count,
            count(distinct e.enrollment_id) filter (where coalesce(e.status, 'ACTIVE') <> 'CANCELLED') as enrollment_count,
            lower(coalesce(c.title, '')) as pagination_sort_text
          from courseplatform.courses c
          left join courseplatform.lessons l on l.course_id = c.course_id
          left join courseplatform.groups g on g.course_id = c.course_id
          left join courseplatform.enrollments e on e.course_id = c.course_id
          where {where}
          group by c.course_id
        ), filtered_courses as (
          select * from course_rows where {content_sql}
        ), numbered_courses as (
          select *,
            count(*) over() as total_count,
            count(*) filter (where status = 'ACTIVE') over() as active_count,
            count(*) filter (where status = 'INACTIVE') over() as inactive_count,
            sum(lesson_count) over() as total_lessons,
            sum(group_count) over() as total_groups
          from filtered_courses
        )
        select * from numbered_courses
        {cursor_sql}
        order by pagination_sort_text, course_id
        limit %s
        """,
        (*params, *cursor_params, limit + 1),
    )
    summary_row = rows[0] if rows else {}
    total = int(summary_row.get("total_count") or 0)
    rows, page_info = cursor_pagination_result(
        rows, limit, "admin-courses", scope, "pagination_sort_text", "course_id"
    )
    page_info["total"] = total
    return success({
        "courses": [{
            "course": public_course(row),
            "lessonCount": int(row["lesson_count"]),
            "groupCount": int(row["group_count"]),
            "enrollmentCount": int(row["enrollment_count"]),
        } for row in rows],
        "pagination": page_info,
        "summary": {
            "active": int(summary_row.get("active_count") or 0),
            "inactive": int(summary_row.get("inactive_count") or 0),
            "lessons": int(summary_row.get("total_lessons") or 0),
            "groups": int(summary_row.get("total_groups") or 0),
        },
    })


def admin_course_structure_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    connection = runtime.connection
    get_settings = runtime.get_settings
    public_content = runtime.public_content
    public_course = runtime.public_course
    public_course_offering = runtime.public_course_offering
    public_course_version = runtime.public_course_version
    public_lesson = runtime.public_lesson
    staff_option = runtime.staff_option
    staff_question = runtime.staff_question
    success = runtime.success
    admin = admin_from_context(admin_context(payload, {"OWNER", "ADMIN", "REVIEWER"}))
    course_id = payload.get("courseId") or get_settings().default_course_id
    with connection() as conn:
        if admin.get("role") == "REVIEWER":
            allowed = conn.execute(
                """
                select 1 from courseplatform.reviewer_scopes
                where admin_id = %s and status = 'ACTIVE'
                  and (scope_type = 'GLOBAL' or course_id = %s)
                limit 1
                """,
                (admin["admin_id"], course_id),
            ).fetchone()
            if not allowed:
                raise ApiError("REVIEWER_SCOPE_REQUIRED", "Este curso está fora do seu âmbito de revisão.")
        course = conn.execute(
            "select * from courseplatform.courses where course_id = %s",
            (course_id,),
        ).fetchone()
        if not course:
            raise ApiError("COURSE_NOT_FOUND", "Curso não encontrado.")
        lessons = conn.execute(
            "select * from courseplatform.lessons where course_id = %s order by lesson_number",
            (course_id,),
        ).fetchall()
        versions = conn.execute(
            """
            select * from courseplatform.course_versions
            where course_id = %s
            order by version_number desc
            """,
            (course_id,),
        ).fetchall()
        offerings = conn.execute(
            """
            select o.*, count(e.enrollment_id) as enrollment_count
            from courseplatform.course_offerings o
            left join courseplatform.enrollments e on e.offering_id = o.offering_id
            where o.course_id = %s
            group by o.offering_id
            order by o.start_date desc nulls last, o.created_at desc
            """,
            (course_id,),
        ).fetchall()
        lesson_ids = [row["lesson_id"] for row in lessons]
        content_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
        questions_by_lesson: dict[str, list[dict[str, Any]]] = {lesson_id: [] for lesson_id in lesson_ids}
        if lesson_ids:
            content = conn.execute(
                "select * from courseplatform.lesson_content where lesson_id = any(%s) order by section_order",
                (lesson_ids,),
            ).fetchall()
            questions = conn.execute(
                "select * from courseplatform.questions where lesson_id = any(%s) order by question_order",
                (lesson_ids,),
            ).fetchall()
            question_ids = [row["question_id"] for row in questions]
            options_by_question: dict[str, list[dict[str, Any]]] = {question_id: [] for question_id in question_ids}
            if question_ids:
                options = conn.execute(
                    "select * from courseplatform.question_options where question_id = any(%s) order by option_order",
                    (question_ids,),
                ).fetchall()
                for option in options:
                    options_by_question[option["question_id"]].append(option)
            for item in content:
                content_by_lesson[item["lesson_id"]].append(item)
            for question in questions:
                questions_by_lesson[question["lesson_id"]].append({
                    "question": question,
                    "options": options_by_question.get(question["question_id"], []),
                })
    return success({
        "course": public_course(course),
        "versions": [public_course_version(row) for row in versions],
        "offerings": [public_course_offering(row) for row in offerings],
        "lessons": [
            {
                "lesson": public_lesson(lesson),
                "content": [public_content(item) for item in content_by_lesson.get(lesson["lesson_id"], [])],
                "questions": [
                    {
                        "question": staff_question(item["question"]),
                        "options": [staff_option(option) for option in item["options"]],
                    }
                    for item in questions_by_lesson.get(lesson["lesson_id"], [])
                ],
            }
            for lesson in lessons
        ],
    })


def admin_create_course_version_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    course_structure_snapshot_with_conn = runtime.course_structure_snapshot_with_conn
    float_value = runtime.float_value
    generate_id = runtime.generate_id
    public_course_version = runtime.public_course_version
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId"])
    course_id = str_value(payload.get("courseId"))
    with connection() as conn:
        course = conn.execute(
            "select * from courseplatform.courses where course_id = %s for update",
            (course_id,),
        ).fetchone()
        if not course:
            raise ApiError("COURSE_NOT_FOUND", "Curso não encontrado.")
        existing = conn.execute(
            "select * from courseplatform.course_versions where course_id = %s and status = 'DRAFT' for update",
            (course_id,),
        ).fetchone()
        if existing:
            return success({"courseVersion": public_course_version(existing), "created": False})
        latest = conn.execute(
            "select coalesce(max(version_number), 0) as version_number from courseplatform.course_versions where course_id = %s",
            (course_id,),
        ).fetchone() or {}
        version_number = int(latest.get("version_number") or 0) + 1
        snapshot = course_structure_snapshot_with_conn(conn, course_id)
        row = conn.execute(
            """
            insert into courseplatform.course_versions
              (course_version_id, course_id, version_number, status, title, description,
               total_hours, passing_score, content_snapshot_json, created_by, created_at, updated_at)
            values (%s, %s, %s, 'DRAFT', %s, %s, %s, %s, %s, %s, now(), now())
            returning *
            """,
            (
                generate_id("CRSV"), course_id, version_number, course.get("title"),
                course.get("description"), float_value(course.get("total_hours")),
                float_value(course.get("passing_score"), 60),
                json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
                admin["admin_id"],
            ),
        ).fetchone()
        audit(
            conn, "ADMIN", admin["admin_id"], "COURSE_VERSION_CREATED",
            "COURSE_VERSION", row["course_version_id"],
            {"courseId": course_id, "versionNumber": version_number},
        )
        conn.commit()
    return success({"courseVersion": public_course_version(row), "created": True})


def admin_refresh_course_version_draft_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    course_structure_snapshot_with_conn = runtime.course_structure_snapshot_with_conn
    float_value = runtime.float_value
    public_course_version = runtime.public_course_version
    require_fields = runtime.require_fields
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseVersionId"])
    with connection() as conn:
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s for update",
            (payload["courseVersionId"],),
        ).fetchone()
        if not version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        if version.get("status") != "DRAFT":
            raise ApiError("COURSE_VERSION_NOT_DRAFT", "Apenas um rascunho pode ser atualizado pelo editor.")
        snapshot = course_structure_snapshot_with_conn(conn, version["course_id"])
        course_data = snapshot["course"]
        row = conn.execute(
            """
            update courseplatform.course_versions
            set title = %s, description = %s, total_hours = %s, passing_score = %s,
                content_snapshot_json = %s, updated_at = now()
            where course_version_id = %s and status = 'DRAFT'
            returning *
            """,
            (
                course_data.get("title"),
                course_data.get("description"),
                float_value(course_data.get("total_hours")),
                float_value(course_data.get("passing_score"), 60),
                json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
                version["course_version_id"],
            ),
        ).fetchone()
        audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "COURSE_VERSION_DRAFT_REFRESHED",
            "COURSE_VERSION",
            row["course_version_id"],
            {"courseId": row["course_id"], "versionNumber": row["version_number"]},
        )
        conn.commit()
    validation = validate_course_version_snapshot(snapshot)
    return success({
        "courseVersion": public_course_version(row),
        "validation": validation,
        "preview": course_version_preview(snapshot),
    })


def admin_edit_course_version_draft_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    _, admin = runtime.admin_context(payload, {"OWNER", "ADMIN"})
    runtime.require_fields(payload, ["courseVersionId", "operation", "changes"])
    with runtime.connection() as conn:
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s for update",
            (payload["courseVersionId"],),
        ).fetchone()
        if not version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        if version.get("status") != "DRAFT":
            raise ApiError("COURSE_VERSION_NOT_DRAFT", "Apenas um rascunho pode ser editado.")
        expected_updated_at = str(payload.get("expectedUpdatedAt") or "").strip()
        current_updated_at = runtime.iso(version.get("updated_at")) or ""
        if expected_updated_at and expected_updated_at != current_updated_at:
            raise ApiError(
                "COURSE_VERSION_CONFLICT",
                "Este rascunho foi alterado por outra sessão. Atualize a página antes de continuar.",
            )
        operation = str(payload.get("operation") or "").strip().upper()
        changes = copy.deepcopy(payload.get("changes") or {})
        if operation == "CREATE_LESSON":
            changes["lessonId"] = runtime.generate_id("LESSON")
        elif operation == "CREATE_CONTENT":
            changes["contentId"] = runtime.generate_id("CNT")
        snapshot = edit_course_version_draft_snapshot(
            stored_course_version_snapshot(version),
            operation,
            changes,
        )
        course_data = snapshot["course"]
        row = conn.execute(
            """
            update courseplatform.course_versions
            set title = %s, description = %s, total_hours = %s, passing_score = %s,
                content_snapshot_json = %s, updated_at = now()
            where course_version_id = %s and status = 'DRAFT'
            returning *
            """,
            (
                course_data.get("title"),
                course_data.get("description"),
                runtime.float_value(course_data.get("total_hours")),
                runtime.float_value(course_data.get("passing_score"), 60),
                json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
                version["course_version_id"],
            ),
        ).fetchone()
        runtime.audit(
            conn,
            "ADMIN",
            admin["admin_id"],
            "COURSE_VERSION_DRAFT_EDITED",
            "COURSE_VERSION",
            row["course_version_id"],
            {
                "courseId": row["course_id"],
                "versionNumber": row["version_number"],
                "operation": operation,
                "entityId": changes.get("lessonId") if operation.endswith("LESSON") else changes.get("contentId"),
            },
        )
        conn.commit()
    return runtime.success({
        "courseVersion": runtime.public_course_version(row),
        "validation": validate_course_version_snapshot(snapshot),
        "preview": course_version_preview(snapshot),
        "draftEditor": course_version_draft_editor(snapshot),
    })


def admin_preview_course_version_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    connection = runtime.connection
    public_course_version = runtime.public_course_version
    require_fields = runtime.require_fields
    success = runtime.success
    admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseVersionId"])
    with connection() as conn:
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s",
            (payload["courseVersionId"],),
        ).fetchone()
        if not version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        snapshot = stored_course_version_snapshot(version)
    validation = validate_course_version_snapshot(snapshot)
    response = {
        "courseVersion": public_course_version(version),
        "validation": validation,
        "preview": course_version_preview(snapshot),
    }
    if version.get("status") == "DRAFT":
        response["draftEditor"] = course_version_draft_editor(snapshot)
    return success(response)


def admin_publish_course_version_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    float_value = runtime.float_value
    public_course_version = runtime.public_course_version
    require_fields = runtime.require_fields
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseVersionId"])
    with connection() as conn:
        version = conn.execute(
            "select * from courseplatform.course_versions where course_version_id = %s for update",
            (payload["courseVersionId"],),
        ).fetchone()
        if not version:
            raise ApiError("COURSE_VERSION_NOT_FOUND", "Versão do curso não encontrada.")
        if version.get("status") != "DRAFT":
            raise ApiError("COURSE_VERSION_NOT_DRAFT", "Apenas uma versão em rascunho pode ser publicada.")
        snapshot = stored_course_version_snapshot(version)
        validation = validate_course_version_snapshot(snapshot)
        if not validation["valid"]:
            raise ApiError(
                "COURSE_VERSION_INVALID",
                "A versão possui bloqueios que precisam de ser corrigidos antes da publicação.",
                validation,
            )
        course_data = snapshot["course"]
        row = conn.execute(
            """
            update courseplatform.course_versions
            set status = 'PUBLISHED', title = %s, description = %s,
                total_hours = %s, passing_score = %s, content_snapshot_json = %s,
                published_by = %s, published_at = now(), updated_at = now()
            where course_version_id = %s and status = 'DRAFT'
            returning *
            """,
            (
                course_data.get("title"), course_data.get("description"),
                float_value(course_data.get("total_hours")),
                float_value(course_data.get("passing_score"), 60),
                json.dumps(snapshot, ensure_ascii=True, separators=(",", ":")),
                admin["admin_id"], version["course_version_id"],
            ),
        ).fetchone()
        audit(
            conn, "ADMIN", admin["admin_id"], "COURSE_VERSION_PUBLISHED",
            "COURSE_VERSION", row["course_version_id"],
            {"courseId": row["course_id"], "versionNumber": row["version_number"]},
        )
        conn.commit()
    return success({"courseVersion": public_course_version(row), "validation": validation})


def admin_save_media_config_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    normalize_brand_logo_url = runtime.normalize_brand_logo_url
    persist_media_config = runtime.persist_media_config
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    media = payload.get("mediaConfig") or {"logoUrl": payload.get("logoUrl"), "videos": payload.get("videos", [])}
    if not isinstance(media, dict):
        raise ApiError("INVALID_MEDIA_CONFIG", "Configuração de media inválida.")
    media["logoUrl"] = normalize_brand_logo_url(media.get("logoUrl"))
    media.setdefault("videos", [])
    with connection() as conn:
        persist_media_config(conn, media)
        audit(conn, "ADMIN", admin["admin_id"], "MEDIA_CONFIG_SAVED", "SETTING", "MEDIA_CONFIG")
        conn.commit()
    return success({"mediaConfig": media})


def admin_save_course_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    audit = runtime.audit
    connection = runtime.connection
    float_value = runtime.float_value
    generate_id = runtime.generate_id
    public_course = runtime.public_course
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["title"])
    course_id = str_value(payload.get("courseId")) or generate_id("COURSE")
    status = str_value(payload.get("status") or "ACTIVE").upper()
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.courses
              (course_id, course_code, title, description, total_hours, passing_score, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (course_id) do update
            set course_code = excluded.course_code, title = excluded.title,
                description = excluded.description, total_hours = excluded.total_hours,
                passing_score = excluded.passing_score, status = excluded.status, updated_at = now()
            returning *
            """,
            (
                course_id,
                str_value(payload.get("courseCode") or course_id),
                str_value(payload.get("title")),
                str_value(payload.get("description")),
                float_value(payload.get("totalHours")),
                float_value(payload.get("passingScore"), 60),
                status,
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "COURSE_SAVED", "COURSE", course_id)
        conn.commit()
    return success({"course": public_course(row)})


def admin_save_lesson_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    FEEDBACK_RELEASE_MODES = runtime.FEEDBACK_RELEASE_MODES
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    feedback_release_mode = runtime.feedback_release_mode
    float_value = runtime.float_value
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    prepare_assessment_feature_schema = runtime.prepare_assessment_feature_schema
    public_lesson = runtime.public_lesson
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["courseId", "title"])
    prepare_assessment_feature_schema()
    lesson_id = str_value(payload.get("lessonId")) or generate_id("LESSON")
    status = str_value(payload.get("status") or "ACTIVE").upper()
    requested_release_mode = str_value(payload.get("feedbackReleaseMode")).upper()
    if requested_release_mode and requested_release_mode not in FEEDBACK_RELEASE_MODES:
        raise ApiError("INVALID_FEEDBACK_POLICY", "A política de divulgação do feedback é inválida.")
    release_mode = feedback_release_mode(payload.get("feedbackReleaseMode"))
    show_correct_answers = as_bool(payload.get("showCorrectAnswers"))
    show_explanations = as_bool(payload.get("showExplanations"))
    submission_duration = int_value(payload.get("submissionDurationMinutes"))
    if submission_duration <= 0:
        submission_duration = int_value(payload.get("exerciseMinutes")) + int_value(payload.get("individualMinutes"))
    submission_duration = max(1, min(submission_duration or 180, 43200))
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.lessons
              (lesson_id, course_id, lesson_number, title, slug, summary, theory_minutes,
               exercise_minutes, individual_minutes, passing_score, prerequisite_lesson_id,
               submission_duration_minutes, feedback_release_mode, show_correct_answers,
               show_explanations, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (lesson_id) do update
            set course_id = excluded.course_id, lesson_number = excluded.lesson_number,
                title = excluded.title, slug = excluded.slug, summary = excluded.summary,
                theory_minutes = excluded.theory_minutes, exercise_minutes = excluded.exercise_minutes,
                individual_minutes = excluded.individual_minutes, passing_score = excluded.passing_score,
                prerequisite_lesson_id = excluded.prerequisite_lesson_id,
                submission_duration_minutes = excluded.submission_duration_minutes,
                feedback_release_mode = excluded.feedback_release_mode,
                show_correct_answers = excluded.show_correct_answers,
                show_explanations = excluded.show_explanations,
                status = excluded.status,
                updated_at = now()
            returning *
            """,
            (
                lesson_id,
                payload["courseId"],
                int_value(payload.get("lessonNumber"), 1),
                str_value(payload.get("title")),
                str_value(payload.get("slug")),
                str_value(payload.get("summary")),
                float_value(payload.get("theoryMinutes")),
                float_value(payload.get("exerciseMinutes")),
                float_value(payload.get("individualMinutes")),
                float_value(payload.get("passingScore"), 60),
                str_value(payload.get("prerequisiteLessonId")) or None,
                submission_duration,
                release_mode,
                show_correct_answers,
                show_explanations,
                status,
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_SAVED", "LESSON", lesson_id)
        conn.commit()
    return success({"lesson": public_lesson(row)})


def admin_save_lesson_content_action(payload: dict[str, Any], *, runtime: CatalogRuntime):
    admin_context = runtime.admin_context
    as_bool = runtime.as_bool
    audit = runtime.audit
    connection = runtime.connection
    float_value = runtime.float_value
    generate_id = runtime.generate_id
    int_value = runtime.int_value
    public_content = runtime.public_content
    require_fields = runtime.require_fields
    str_value = runtime.str_value
    success = runtime.success
    _, admin = admin_context(payload, {"OWNER", "ADMIN"})
    require_fields(payload, ["lessonId", "title"])
    content_id = str_value(payload.get("contentId")) or generate_id("CNT")
    with connection() as conn:
        row = conn.execute(
            """
            insert into courseplatform.lesson_content
              (content_id, lesson_id, section_order, section_type, title, body_html,
               estimated_minutes, is_required, status, created_at, updated_at)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
            on conflict (content_id) do update
            set lesson_id = excluded.lesson_id, section_order = excluded.section_order,
                section_type = excluded.section_type, title = excluded.title,
                body_html = excluded.body_html, estimated_minutes = excluded.estimated_minutes,
                is_required = excluded.is_required, status = excluded.status, updated_at = now()
            returning *
            """,
            (
                content_id,
                payload["lessonId"],
                int_value(payload.get("sectionOrder"), 1),
                str_value(payload.get("sectionType") or "TEORIA"),
                str_value(payload.get("title")),
                str_value(payload.get("bodyHtml")),
                float_value(payload.get("estimatedMinutes")),
                as_bool(payload.get("isRequired", True)),
                str_value(payload.get("status") or "ACTIVE").upper(),
            ),
        ).fetchone()
        audit(conn, "ADMIN", admin["admin_id"], "LESSON_CONTENT_SAVED", "LESSON_CONTENT", content_id)
        conn.commit()
    return success({"content": public_content(row)})
