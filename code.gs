/** ===== 00_Config.gs ===== */

/**
 * CoursePlatformDB API
 * Configuração global.
 */
var CP = {
  VERSION: '1.0.0',

  // Folha criada para este projeto. Pode ser substituída pela Script Property SPREADSHEET_ID.
  DEFAULT_SPREADSHEET_ID: '1ARC2icgzL9BD7zXxFK0unWLNXnsNnsdGUokpsK0yvWc',

  SHEETS: {
    STUDENTS: 'Students',
    ADMINS: 'Admins',
    SESSIONS: 'Sessions',
    COURSES: 'Courses',
    LESSONS: 'Lessons',
    LESSON_CONTENT: 'LessonContent',
    QUESTIONS: 'Questions',
    QUESTION_OPTIONS: 'QuestionOptions',
    ENROLLMENTS: 'Enrollments',
    GROUPS: 'Groups',
    GROUP_MEMBERS: 'GroupMembers',
    LESSON_PROGRESS: 'LessonProgress',
    ATTEMPTS: 'Attempts',
    ANSWERS: 'Answers',
    FILES: 'Files',
    REVIEWS: 'Reviews',
    CERTIFICATES: 'Certificates',
    AUDIT_LOG: 'AuditLog',
    SETTINGS: 'Settings',
    LISTS: 'Lists',
    SCHEMA_GUIDE: 'SchemaGuide'
  },

  HEADERS: {
    Students: [
      'studentId', 'publicStudentId', 'fullName', 'email', 'accessCode', 'status',
      'country', 'organization', 'phone', 'jobTitle', 'interests', 'profilePhotoUrl',
      'createdAt', 'updatedAt', 'lastLoginAt'
    ],
    Admins: [
      'adminId', 'fullName', 'email', 'role', 'status',
      'createdAt', 'updatedAt'
    ],
    Sessions: [
      'sessionToken', 'studentId', 'createdAt', 'expiresAt',
      'active', 'userAgent', 'ipHash', 'revokedAt'
    ],
    Courses: [
      'courseId', 'courseCode', 'title', 'description', 'totalHours',
      'passingScore', 'status', 'createdAt', 'updatedAt'
    ],
    Lessons: [
      'lessonId', 'courseId', 'lessonNumber', 'title', 'slug', 'summary',
      'theoryMinutes', 'exerciseMinutes', 'individualMinutes', 'passingScore',
      'prerequisiteLessonId', 'status', 'createdAt', 'updatedAt'
    ],
    LessonContent: [
      'contentId', 'lessonId', 'sectionOrder', 'sectionType', 'title',
      'bodyHtml', 'estimatedMinutes', 'isRequired', 'status',
      'createdAt', 'updatedAt'
    ],
    Questions: [
      'questionId', 'lessonId', 'questionOrder', 'questionType', 'prompt',
      'points', 'correctAnswer', 'explanation', 'isRequired', 'status',
      'createdAt', 'updatedAt'
    ],
    QuestionOptions: [
      'optionId', 'questionId', 'optionOrder', 'optionLabel',
      'optionText', 'isCorrect', 'createdAt'
    ],
    Enrollments: [
      'enrollmentId', 'studentId', 'courseId', 'groupId', 'status', 'enrolledAt',
      'completedAt', 'progressPercent', 'finalScore', 'certificateId', 'updatedAt'
    ],
    Groups: [
      'groupId', 'groupCode', 'name', 'courseId', 'startDate', 'endDate',
      'status', 'createdAt', 'updatedAt'
    ],
    GroupMembers: [
      'groupMemberId', 'groupId', 'studentId', 'status', 'joinedAt', 'updatedAt'
    ],
    LessonProgress: [
      'progressId', 'enrollmentId', 'studentId', 'lessonId', 'status',
      'unlockedAt', 'startedAt', 'submittedAt', 'approvedAt',
      'score', 'attemptCount', 'updatedAt'
    ],
    Attempts: [
      'attemptId', 'progressId', 'studentId', 'lessonId', 'attemptNumber',
      'startedAt', 'deadlineAt', 'submittedAt', 'status', 'score',
      'reviewerId', 'reviewedAt', 'reviewComments', 'retryAuthorized',
      'createdAt', 'updatedAt'
    ],
    Answers: [
      'answerId', 'attemptId', 'questionId', 'answerText',
      'selectedOptionId', 'isCorrect', 'awardedPoints',
      'savedAt', 'submittedAt'
    ],
    Files: [
      'fileId', 'attemptId', 'studentId', 'lessonId', 'fileName',
      'mimeType', 'sizeBytes', 'driveFileId', 'driveUrl',
      'uploadedAt', 'status'
    ],
    Reviews: [
      'reviewId', 'attemptId', 'reviewerId', 'decision', 'score',
      'comments', 'correctionDeadline', 'unlockNextLesson', 'reviewedAt'
    ],
    Certificates: [
      'certificateId', 'studentId', 'courseId', 'certificateNumber',
      'verificationCode', 'issueDate', 'finalScore',
      'driveFileId', 'driveUrl', 'status'
    ],
    AuditLog: [
      'logId', 'actorType', 'actorId', 'action', 'entityType',
      'entityId', 'detailsJson', 'createdAt'
    ],
    Settings: [
      'key', 'value', 'valueType', 'description', 'updatedAt'
    ],
    Lists: [
      'listName', 'value', 'labelPt', 'sortOrder', 'active'
    ],
    SchemaGuide: [
      'sheetName', 'purpose', 'primaryKey', 'notes'
    ]
  },

  STATUS: {
    ACTIVE: 'ACTIVE',
    INACTIVE: 'INACTIVE',
    BLOCKED: 'BLOCKED',

    LOCKED: 'LOCKED',
    AVAILABLE: 'AVAILABLE',
    IN_PROGRESS: 'IN_PROGRESS',
    UNDER_REVIEW: 'UNDER_REVIEW',
    CORRECTION_REQUIRED: 'CORRECTION_REQUIRED',
    APPROVED: 'APPROVED',
    FAILED: 'FAILED',
    TIME_EXCEEDED: 'TIME_EXCEEDED',
    SUBMITTED: 'SUBMITTED',
    COMPLETED: 'COMPLETED',
    DELETED: 'DELETED',
    ISSUED: 'ISSUED',
    REVOKED: 'REVOKED'
  },

  REVIEW_DECISIONS: [
    'APPROVED',
    'APPROVED_WITH_NOTES',
    'CORRECTION_REQUIRED',
    'FAILED'
  ],

  ADMIN_ROLES: {
    OWNER: 'OWNER',
    ADMIN: 'ADMIN',
    REVIEWER: 'REVIEWER'
  },

  ALLOWED_FILE_TYPES: [
    'image/jpeg',
    'image/png',
    'image/webp',
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'application/vnd.ms-excel',
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ],

  DEFAULTS: {
    DEFAULT_COURSE_ID: 'COURSE-EAPI-001',
    SESSION_HOURS: 12,
    PASSING_SCORE: 60,
    MAX_FILES_PER_SUBMISSION: 10,
    MAX_FILE_SIZE_MB: 8,
    MAX_SUBMISSION_SIZE_MB: 25,
    REQUIRE_FILE_UPLOAD: true,
    COURSE_TIMEZONE: 'Africa/Maputo',
    CERTIFICATE_PREFIX: 'EAPI',
    DRIVE_ROOT_FOLDER_NAME: 'CoursePlatform Submissions',
    MEDIA_CONFIG: {
      logoUrl: 'https://drive.google.com/file/d/1yXIA8DfsUXvIe8Asrs_PqNNNPRVHZ3Ez/view?usp=drive_link',
      videos: []
    }
  }
};

/** ===== 01_Router.gs ===== */

/**
 * Router HTTP da aplicação Web.
 *
 * GET:
 *   ?action=health
 *   ?action=publicCourseConfig
 *   ?action=publicMediaConfig
 *   ?action=verifyCertificate&code=...
 *
 * POST:
 *   JSON ou text/plain com {"action":"..."}
 *
 * Acoes de media:
 *   getMediaConfig
 *   adminGetMediaConfig
 *   adminSaveMediaConfig
 */
function doGet(e) {
  try {
    var action = stringValue_(e && e.parameter && e.parameter.action) || 'health';
    var callback = stringValue_(e && e.parameter && e.parameter.callback);

    var result;
    switch (action) {
      case 'health':
        result = health_();
        break;
      case 'publicCourseConfig':
        result = getPublicCourseConfig_(e && e.parameter ? e.parameter.courseId : '');
        break;
      case 'publicMediaConfig':
        result = getPublicMediaConfig_(e && e.parameter ? e.parameter.courseId : '');
        break;
      case 'verifyCertificate':
        result = verifyCertificatePublic_(e && e.parameter ? e.parameter.code : '');
        break;
      default:
        throw apiError_('INVALID_ACTION', 'Ação GET inválida: ' + action);
    }

    return outputResponse_(result, callback);
  } catch (error) {
    return outputResponse_(errorResponse_(error));
  }
}

function doPost(e) {
  try {
    var payload = parseRequestBody_(e);
    var action = stringValue_(payload.action);

    if (!action) {
      throw apiError_('ACTION_REQUIRED', 'O campo "action" é obrigatório.');
    }

    rateLimitRequest_(action, payload);

    var result;
    switch (action) {
      // Público
      case 'login':
        result = loginStudent_(payload);
        break;
      case 'adminLogin':
        result = loginAdmin_(payload);
        break;

      // Estudante
      case 'logout':
        result = withStudentSession_(payload, logoutStudent_);
        break;
      case 'getDashboard':
        result = withStudentSession_(payload, getStudentDashboard_);
        break;
      case 'getMyCourses':
        result = withStudentSession_(payload, getMyCourses_);
        break;
      case 'updateMyProfile':
        result = withStudentSession_(payload, updateMyProfile_);
        break;
      case 'changeMyAccessCode':
        result = withStudentSession_(payload, changeMyAccessCode_);
        break;
      case 'getLesson':
        result = withStudentSession_(payload, getLessonForStudent_);
        break;
      case 'startAttempt':
        result = withStudentSession_(payload, startAttempt_);
        break;
      case 'saveAnswer':
        result = withStudentSession_(payload, saveAnswer_);
        break;
      case 'uploadFile':
        result = withStudentSession_(payload, uploadSubmissionFile_);
        break;
      case 'deleteUploadedFile':
        result = withStudentSession_(payload, deleteUploadedFile_);
        break;
      case 'submitAttempt':
        result = withStudentSession_(payload, submitAttempt_);
        break;
      case 'getAttemptStatus':
        result = withStudentSession_(payload, getAttemptStatus_);
        break;
      case 'getMyCertificate':
        result = withStudentSession_(payload, getStudentCertificate_);
        break;
      case 'getMediaConfig':
        result = withStudentSession_(payload, getMediaConfig_);
        break;

      // Administração
      case 'adminLogout':
        result = withAdminSession_(payload, adminLogout_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminMe':
        result = withAdminSession_(payload, adminMe_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminListStaff':
        result = withAdminSession_(payload, adminListStaff_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSaveStaff':
        result = withAdminSession_(payload, adminSaveStaff_, ['OWNER']);
        break;
      case 'adminSetStaffStatus':
        result = withAdminSession_(payload, adminSetStaffStatus_, ['OWNER']);
        break;
      case 'adminListPendingSubmissions':
        result = withAdminSession_(payload, adminListPendingSubmissions_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminListSubmissions':
        result = withAdminSession_(payload, adminListSubmissions_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminGetSubmission':
        result = withAdminSession_(payload, adminGetSubmission_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminReviewSubmission':
        result = withAdminSession_(payload, adminReviewSubmission_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminAuthorizeRetry':
        result = withAdminSession_(payload, adminAuthorizeRetry_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminCreateStudent':
        result = withAdminSession_(payload, adminCreateStudent_, ['OWNER', 'ADMIN']);
        break;
      case 'adminListStudents':
        result = withAdminSession_(payload, adminListStudents_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminSetStudentStatus':
        result = withAdminSession_(payload, adminSetStudentStatus_, ['OWNER', 'ADMIN']);
        break;
      case 'adminResetStudentAccessCode':
        result = withAdminSession_(payload, adminResetStudentAccessCode_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSaveCourse':
        result = withAdminSession_(payload, adminSaveCourse_, ['OWNER', 'ADMIN']);
        break;
      case 'adminListCourses':
        result = withAdminSession_(payload, adminListCourses_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminSaveLesson':
        result = withAdminSession_(payload, adminSaveLesson_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSaveLessonContent':
        result = withAdminSession_(payload, adminSaveLessonContent_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSaveQuestion':
        result = withAdminSession_(payload, adminSaveQuestion_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSaveQuestionOption':
        result = withAdminSession_(payload, adminSaveQuestionOption_, ['OWNER', 'ADMIN']);
        break;
      case 'adminGetCourseStructure':
        result = withAdminSession_(payload, adminGetCourseStructure_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminListGroups':
        result = withAdminSession_(payload, adminListGroups_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminSaveGroup':
        result = withAdminSession_(payload, adminSaveGroup_, ['OWNER', 'ADMIN']);
        break;
      case 'adminAssignStudentsToGroup':
        result = withAdminSession_(payload, adminAssignStudentsToGroup_, ['OWNER', 'ADMIN']);
        break;
      case 'adminSetLessonAccess':
        result = withAdminSession_(payload, adminSetLessonAccess_, ['OWNER', 'ADMIN']);
        break;
      case 'adminGetMediaConfig':
        result = withAdminSession_(payload, adminGetMediaConfig_, ['OWNER', 'ADMIN', 'REVIEWER']);
        break;
      case 'adminSaveMediaConfig':
        result = withAdminSession_(payload, adminSaveMediaConfig_, ['OWNER', 'ADMIN']);
        break;

      default:
        throw apiError_('INVALID_ACTION', 'Ação POST inválida: ' + action);
    }

    return outputResponse_(result);
  } catch (error) {
    return outputResponse_(errorResponse_(error));
  }
}


/** ===== 02_Setup.gs ===== */

/**
 * Execute setupCoursePlatformApi() uma vez no editor do Apps Script.
 *
 * A função:
 * - valida/cria as abas e colunas;
 * - guarda o ID da Sheet em Script Properties;
 * - cria a pasta principal no Drive;
 * - cria o primeiro administrador com o email do proprietário;
 * - gera a chave mestra administrativa.
 */
function setupCoursePlatformApi() {
  var props = PropertiesService.getScriptProperties();

  if (!props.getProperty('SPREADSHEET_ID')) {
    props.setProperty('SPREADSHEET_ID', CP.DEFAULT_SPREADSHEET_ID);
  }

  ensureSchema_();
  ensureSecurityProperties_();
  ensureBaseSettings_();

  var folder = ensureRootFolder_();
  setSetting_(
    'DRIVE_ROOT_FOLDER_ID',
    folder.getId(),
    'STRING',
    'ID da pasta principal para documentos submetidos.'
  );

  var admin = ensureInitialAdmin_();
  var generatedKey = null;

  if (!props.getProperty('ADMIN_MASTER_KEY_HASH')) {
    generatedKey = generateAccessCode_(24);
    props.setProperty('ADMIN_MASTER_KEY_HASH', hashSecret_(generatedKey));
  }

  var result = {
    success: true,
    spreadsheetId: getSpreadsheetId_(),
    spreadsheetUrl: getDb_().getUrl(),
    driveRootFolderId: folder.getId(),
    driveRootFolderUrl: folder.getUrl(),
    initialAdmin: admin,
    adminMasterKeyCreated: Boolean(generatedKey),
    adminMasterKey: generatedKey || 'Já existente. Use rotateAdminMasterKey() para gerar uma nova.',
    apiVersion: CP.VERSION
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

function rotateAdminMasterKey() {
  ensureSecurityProperties_();

  var plainKey = generateAccessCode_(24);
  PropertiesService
    .getScriptProperties()
    .setProperty('ADMIN_MASTER_KEY_HASH', hashSecret_(plainKey));

  revokeAllAdminSessions_();

  var result = {
    success: true,
    adminMasterKey: plainKey,
    message: 'Guarde esta chave num local seguro. As sessões administrativas anteriores foram revogadas.'
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

/**
 * Cria um estudante pelo editor e devolve o código em texto simples uma única vez.
 */
function createStudentFromEditor(fullName, email, country, organization) {
  return createStudentRecord_({
    fullName: fullName,
    email: email,
    country: country || '',
    organization: organization || ''
  }, {
    actorType: 'SYSTEM',
    actorId: 'EDITOR'
  });
}

function ensureSchema_() {
  var ss = getDb_();
  var sheetNames = Object.keys(CP.HEADERS);

  sheetNames.forEach(function(sheetName) {
    var sheet = ss.getSheetByName(sheetName);
    if (!sheet) {
      sheet = ss.insertSheet(sheetName);
    }

    var requiredHeaders = CP.HEADERS[sheetName];
    var currentLastColumn = Math.max(sheet.getLastColumn(), 1);
    var currentHeaders = sheet
      .getRange(1, 1, 1, currentLastColumn)
      .getValues()[0]
      .map(stringValue_);

    if (currentHeaders.length === 1 && !currentHeaders[0]) {
      currentHeaders = [];
    }

    requiredHeaders.forEach(function(header) {
      if (currentHeaders.indexOf(header) === -1) {
        currentHeaders.push(header);
      }
    });

    if (currentHeaders.length) {
      sheet.getRange(1, 1, 1, currentHeaders.length).setValues([currentHeaders]);
      sheet.setFrozenRows(1);
      sheet.getRange(1, 1, 1, currentHeaders.length)
        .setFontWeight('bold')
        .setBackground('#E5E7EB')
        .setWrap(true);
    }
  });
}

function ensureSecurityProperties_() {
  var props = PropertiesService.getScriptProperties();

  if (!props.getProperty('PASSWORD_PEPPER')) {
    props.setProperty(
      'PASSWORD_PEPPER',
      Utilities.getUuid() + Utilities.getUuid() + Utilities.getUuid()
    );
  }
}

function ensureBaseSettings_() {
  var defaults = [
    ['API_VERSION', CP.VERSION, 'STRING', 'Versão atual da API.'],
    ['API_ENABLED', 'true', 'BOOLEAN', 'Ativa ou desativa a API.'],
    ['DEFAULT_COURSE_ID', CP.DEFAULTS.DEFAULT_COURSE_ID, 'STRING', 'Curso carregado por defeito.'],
    ['SESSION_HOURS', String(CP.DEFAULTS.SESSION_HOURS), 'NUMBER', 'Duração padrão da sessão.'],
    ['PASSING_SCORE', String(CP.DEFAULTS.PASSING_SCORE), 'NUMBER', 'Classificação mínima.'],
    ['MAX_FILES_PER_SUBMISSION', String(CP.DEFAULTS.MAX_FILES_PER_SUBMISSION), 'NUMBER', 'Máximo de ficheiros.'],
    ['MAX_FILE_SIZE_MB', String(CP.DEFAULTS.MAX_FILE_SIZE_MB), 'NUMBER', 'Máximo por ficheiro.'],
    ['MAX_SUBMISSION_SIZE_MB', String(CP.DEFAULTS.MAX_SUBMISSION_SIZE_MB), 'NUMBER', 'Máximo por submissão.'],
    ['REQUIRE_FILE_UPLOAD', String(CP.DEFAULTS.REQUIRE_FILE_UPLOAD), 'BOOLEAN', 'Exigir pelo menos um ficheiro.'],
    ['COURSE_TIMEZONE', CP.DEFAULTS.COURSE_TIMEZONE, 'STRING', 'Fuso horário oficial.'],
    ['CERTIFICATE_PREFIX', CP.DEFAULTS.CERTIFICATE_PREFIX, 'STRING', 'Prefixo dos certificados.'],
    ['DRIVE_ROOT_FOLDER_ID', '', 'STRING', 'Pasta principal dos documentos.'],
    ['MEDIA_CONFIG', JSON.stringify(CP.DEFAULTS.MEDIA_CONFIG), 'JSON', 'Logotipo e galeria de videos da plataforma.']
  ];

  defaults.forEach(function(row) {
    if (!findOne_(CP.SHEETS.SETTINGS, { key: row[0] })) {
      appendRecord_(CP.SHEETS.SETTINGS, {
        key: row[0],
        value: row[1],
        valueType: row[2],
        description: row[3],
        updatedAt: new Date()
      });
    }
  });
}

function ensureInitialAdmin_() {
  var email = normalizeEmail_(Session.getEffectiveUser().getEmail());

  if (!email) {
    return {
      warning: 'Não foi possível identificar o email do utilizador. Adicione um administrador manualmente na aba Admins.'
    };
  }

  var existing = findOne_(CP.DEFAULT_SHEETS.ADMINS, { email: email });
  if (existing) {
    return publicAdmin_(existing);
  }

  var admin = {
    adminId: newId_('ADM'),
    fullName: email.split('@')[0],
    email: email,
    role: CP.ADMIN_ROLES.OWNER,
    status: CP.STATUS.ACTIVE,
    createdAt: new Date(),
    updatedAt: new Date()
  };

  appendRecord_(CP.SHEETS.ADMINS, admin);
  return publicAdmin_(admin);
}

/** ===== 03_Http.gs ===== */

function parseRequestBody_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    return {};
  }

  var raw = e.postData.contents;
  try {
    return JSON.parse(raw);
  } catch (error) {
    throw apiError_('INVALID_JSON', 'O corpo do pedido não contém JSON válido.');
  }
}

function outputResponse_(payload, callback) {
  var serialized = JSON.stringify(serializeForJson_(payload));

  if (callback && /^[A-Za-z_$][0-9A-Za-z_$\.]*$/.test(callback)) {
    return ContentService
      .createTextOutput(callback + '(' + serialized + ');')
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }

  return ContentService
    .createTextOutput(serialized)
    .setMimeType(ContentService.MimeType.JSON);
}

function successResponse_(data) {
  return {
    success: true,
    apiVersion: CP.VERSION,
    timestamp: new Date().toISOString(),
    data: data
  };
}

function errorResponse_(error) {
  console.error(error && error.stack ? error.stack : error);

  return {
    success: false,
    apiVersion: CP.VERSION,
    timestamp: new Date().toISOString(),
    error: {
      code: error && error.code ? error.code : 'INTERNAL_ERROR',
      message: error && error.message ? error.message : 'Erro interno do servidor.',
      details: error && error.details ? error.details : null
    }
  };
}

function apiError_(code, message, details) {
  var error = new Error(message);
  error.code = code;
  error.details = details || null;
  return error;
}

function health_() {
  var apiEnabled = getSetting_('API_ENABLED', true);

  return successResponse_({
    service: 'CoursePlatformDB API',
    status: apiEnabled ? 'ONLINE' : 'DISABLED',
    spreadsheetId: getSpreadsheetId_(),
    timezone: getSetting_('COURSE_TIMEZONE', CP.DEFAULTS.COURSE_TIMEZONE),
    supportedMediaActions: [
      'publicMediaConfig',
      'getMediaConfig',
      'adminGetMediaConfig',
      'adminSaveMediaConfig'
    ]
  });
}

/**
 * Limite leve contra abuso. Não substitui WAF/rate limiting externo.
 */
function rateLimitRequest_(action, payload) {
  var sensitive = ['login', 'adminLogin', 'uploadFile'];
  if (sensitive.indexOf(action) === -1) {
    return;
  }

  var identity = normalizeEmail_(payload.email || '') ||
    stringValue_(payload.sessionToken || '').slice(0, 16) ||
    'anonymous';

  var key = 'rate:' + action + ':' + sha256Hex_(identity).slice(0, 24);
  var cache = CacheService.getScriptCache();
  var count = Number(cache.get(key) || 0);
  var limit = action === 'uploadFile' ? 60 : 15;

  if (count >= limit) {
    throw apiError_(
      'RATE_LIMITED',
      'Foram efetuados muitos pedidos. Aguarde alguns minutos e tente novamente.'
    );
  }

  cache.put(key, String(count + 1), 300);
}

/** ===== 04_Security.gs ===== */

function hashSecret_(plainText) {
  ensureSecurityProperties_();

  var pepper = PropertiesService
    .getScriptProperties()
    .getProperty('PASSWORD_PEPPER');

  return sha256Hex_(pepper + '|' + stringValue_(plainText));
}

function sha256Hex_(value) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    stringValue_(value),
    Utilities.Charset.UTF_8
  );

  return bytes.map(function(byte) {
    var normalized = byte < 0 ? byte + 256 : byte;
    return ('0' + normalized.toString(16)).slice(-2);
  }).join('');
}

function constantTimeEquals_(a, b) {
  a = stringValue_(a);
  b = stringValue_(b);

  var length = Math.max(a.length, b.length);
  var difference = a.length ^ b.length;

  for (var i = 0; i < length; i++) {
    difference |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }

  return difference === 0;
}

function generateToken_() {
  return Utilities.base64EncodeWebSafe(
    Utilities.getUuid() +
    Utilities.getUuid() +
    Utilities.getUuid() +
    String(new Date().getTime())
  ).replace(/=+$/g, '');
}

function generateAccessCode_(length) {
  var alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%';
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    Utilities.getUuid() + Utilities.getUuid() + Math.random()
  );

  var code = '';
  for (var i = 0; i < length; i++) {
    var value = bytes[i % bytes.length];
    if (value < 0) value += 256;
    code += alphabet.charAt(value % alphabet.length);
  }
  return code;
}

function createSession_(subjectId, userAgent, ipHash) {
  var plainToken = generateToken_();
  var tokenHash = hashSecret_(plainToken);
  var now = new Date();
  var sessionHours = Number(getSetting_('SESSION_HOURS', CP.DEFAULTS.SESSION_HOURS));
  var expiresAt = new Date(now.getTime() + sessionHours * 60 * 60 * 1000);

  appendRecord_(CP.SHEETS.SESSIONS, {
    sessionToken: tokenHash,
    studentId: subjectId,
    createdAt: now,
    expiresAt: expiresAt,
    active: true,
    userAgent: truncate_(userAgent || '', 500),
    ipHash: truncate_(ipHash || '', 128),
    revokedAt: ''
  });

  return {
    token: plainToken,
    expiresAt: expiresAt
  };
}

function validateSession_(plainToken, expectedType) {
  if (!plainToken) {
    throw apiError_('SESSION_REQUIRED', 'A sessão não foi informada.');
  }

  var tokenHash = hashSecret_(plainToken);
  var session = findOne_(CP.SHEETS.SESSIONS, {
    sessionToken: tokenHash
  });

  if (!session || !toBoolean_(session.active)) {
    throw apiError_('INVALID_SESSION', 'A sessão é inválida ou foi encerrada.');
  }

  if (new Date(session.expiresAt).getTime() <= Date.now()) {
    updateRecordByKey_(CP.SHEETS.SESSIONS, 'sessionToken', tokenHash, {
      active: false,
      revokedAt: new Date()
    });
    throw apiError_('SESSION_EXPIRED', 'A sessão expirou. Inicie sessão novamente.');
  }

  var isAdmin = stringValue_(session.studentId).indexOf('ADMIN:') === 0;

  if (expectedType === 'ADMIN' && !isAdmin) {
    throw apiError_('ADMIN_SESSION_REQUIRED', 'É necessária uma sessão administrativa.');
  }
  if (expectedType === 'STUDENT' && isAdmin) {
    throw apiError_('STUDENT_SESSION_REQUIRED', 'É necessária uma sessão de estudante.');
  }

  return session;
}

function withStudentSession_(payload, handler) {
  ensureApiEnabled_();

  var session = validateSession_(payload.sessionToken, 'STUDENT');
  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: session.studentId
  });

  if (!student || stringValue_(student.status) !== CP.STATUS.ACTIVE) {
    throw apiError_('STUDENT_NOT_ACTIVE', 'A conta do estudante não está ativa.');
  }

  payload._session = session;
  payload._student = student;
  payload.studentId = student.studentId;

  return handler(payload);
}

function withAdminSession_(payload, handler, allowedRoles) {
  ensureApiEnabled_();

  var session = validateSession_(payload.adminToken, 'ADMIN');
  var adminId = stringValue_(session.studentId).replace(/^ADMIN:/, '');
  var admin = findOne_(CP.SHEETS.ADMINS, { adminId: adminId });

  if (!admin || stringValue_(admin.status) !== CP.STATUS.ACTIVE) {
    throw apiError_('ADMIN_NOT_ACTIVE', 'A conta administrativa não está ativa.');
  }

  if (allowedRoles && allowedRoles.indexOf(stringValue_(admin.role)) === -1) {
    throw apiError_('FORBIDDEN', 'O seu perfil não possui permissão para esta operação.');
  }

  payload._session = session;
  payload._admin = admin;
  payload.adminId = admin.adminId;

  return handler(payload);
}

function revokeSession_(plainToken) {
  var tokenHash = hashSecret_(plainToken);
  var session = findOne_(CP.SHEETS.SESSIONS, { sessionToken: tokenHash });

  if (session) {
    updateRecordByKey_(CP.SHEETS.SESSIONS, 'sessionToken', tokenHash, {
      active: false,
      revokedAt: new Date()
    });
  }
}

function revokeSessionsForSubject_(subjectId) {
  var sessions = findMany_(CP.SHEETS.SESSIONS, { studentId: subjectId });
  sessions.forEach(function(session) {
    if (toBoolean_(session.active)) {
      updateRecordByKey_(CP.SHEETS.SESSIONS, 'sessionToken', session.sessionToken, {
        active: false,
        revokedAt: new Date()
      });
    }
  });
}

function revokeAllAdminSessions_() {
  var sessions = readAll_(CP.SHEETS.SESSIONS);

  sessions.forEach(function(session) {
    if (
      toBoolean_(session.active) &&
      stringValue_(session.studentId).indexOf('ADMIN:') === 0
    ) {
      updateRecordByKey_(CP.SHEETS.SESSIONS, 'sessionToken', session.sessionToken, {
        active: false,
        revokedAt: new Date()
      });
    }
  });
}

function ensureApiEnabled_() {
  if (!getSetting_('API_ENABLED', true)) {
    throw apiError_('API_DISABLED', 'A API está temporariamente desativada.');
  }
}

/** ===== 05_Repository.gs ===== */

function getSpreadsheetId_() {
  return PropertiesService
    .getScriptProperties()
    .getProperty('SPREADSHEET_ID') || CP.DEFAULT_SPREADSHEET_ID;
}

function getDb_() {
  return SpreadsheetApp.openById(getSpreadsheetId_());
}

function getSheet_(sheetName) {
  var sheet = getDb_().getSheetByName(sheetName);
  if (!sheet) {
    throw apiError_('SHEET_NOT_FOUND', 'A aba "' + sheetName + '" não existe.');
  }
  return sheet;
}

function getHeaders_(sheet) {
  var lastColumn = sheet.getLastColumn();
  if (!lastColumn) return [];

  return sheet
    .getRange(1, 1, 1, lastColumn)
    .getValues()[0]
    .map(stringValue_);
}

function readAll_(sheetName) {
  var sheet = getSheet_(sheetName);
  var values = sheet.getDataRange().getValues();

  if (values.length < 2) return [];

  var headers = values[0].map(stringValue_);
  var records = [];

  for (var rowIndex = 1; rowIndex < values.length; rowIndex++) {
    var row = values[rowIndex];
    var isEmpty = row.every(function(value) {
      return value === '' || value === null;
    });

    if (isEmpty) continue;

    var record = { _rowNumber: rowIndex + 1 };
    headers.forEach(function(header, columnIndex) {
      record[header] = row[columnIndex];
    });
    records.push(record);
  }

  return records;
}

function matchesCriteria_(record, criteria) {
  return Object.keys(criteria).every(function(key) {
    var expected = criteria[key];
    var actual = record[key];

    if (typeof expected === 'function') {
      return expected(actual, record);
    }

    if (expected instanceof Array) {
      return expected.map(stringValue_).indexOf(stringValue_(actual)) !== -1;
    }

    return stringValue_(actual) === stringValue_(expected);
  });
}

function findOne_(sheetName, criteria) {
  var records = readAll_(sheetName);
  for (var i = 0; i < records.length; i++) {
    if (matchesCriteria_(records[i], criteria)) {
      return records[i];
    }
  }
  return null;
}

function findMany_(sheetName, criteria) {
  return readAll_(sheetName).filter(function(record) {
    return matchesCriteria_(record, criteria);
  });
}

function appendRecord_(sheetName, record) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    return appendRecordUnlocked_(sheetName, record);
  } finally {
    lock.releaseLock();
  }
}

function appendRecordUnlocked_(sheetName, record) {
  var sheet = getSheet_(sheetName);
  var headers = getHeaders_(sheet);

  if (!headers.length) {
    throw apiError_('HEADERS_MISSING', 'A aba "' + sheetName + '" não possui cabeçalhos.');
  }

  var row = headers.map(function(header) {
    return Object.prototype.hasOwnProperty.call(record, header)
      ? normalizeCellValue_(record[header])
      : '';
  });

  sheet.appendRow(row);
  SpreadsheetApp.flush();

  record._rowNumber = sheet.getLastRow();
  return record;
}

function updateRecordByKey_(sheetName, keyField, keyValue, patch) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var sheet = getSheet_(sheetName);
    var headers = getHeaders_(sheet);
    var records = readAll_(sheetName);
    var record = null;

    for (var i = 0; i < records.length; i++) {
      if (stringValue_(records[i][keyField]) === stringValue_(keyValue)) {
        record = records[i];
        break;
      }
    }

    if (!record) {
      throw apiError_(
        'RECORD_NOT_FOUND',
        'Registo não encontrado em "' + sheetName + '" para ' + keyField + '=' + keyValue
      );
    }

    Object.keys(patch).forEach(function(key) {
      record[key] = patch[key];
    });

    var row = headers.map(function(header) {
      return normalizeCellValue_(record[header]);
    });

    sheet.getRange(record._rowNumber, 1, 1, headers.length).setValues([row]);
    SpreadsheetApp.flush();

    return record;
  } finally {
    lock.releaseLock();
  }
}

function upsertRecord_(sheetName, keyField, record) {
  var all = readAll_(sheetName);
  var existing = null;
  for (var i = 0; i < all.length; i++) {
    if (stringValue_(all[i][keyField]) === stringValue_(record[keyField])) {
      existing = all[i];
      break;
    }
  }

  if (existing) {
    return updateRecordByKey_(sheetName, keyField, record[keyField], record);
  }

  return appendRecord_(sheetName, record);
}

function upsertByCompositeKey_(sheetName, criteria, record) {
  var existing = findOne_(sheetName, criteria);

  if (!existing) {
    return appendRecord_(sheetName, record);
  }

  var keyFields = Object.keys(criteria);
  var firstKey = keyFields[0];

  if (!firstKey) {
    throw apiError_('INVALID_COMPOSITE_KEY', 'Critério de upsert inválido.');
  }

  // Atualização direta pela linha para evitar depender de uma chave composta como coluna.
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var sheet = getSheet_(sheetName);
    var headers = getHeaders_(sheet);
    var merged = {};

    headers.forEach(function(header) {
      merged[header] = existing[header];
    });
    Object.keys(record).forEach(function(key) {
      merged[key] = record[key];
    });

    var row = headers.map(function(header) {
      return normalizeCellValue_(merged[header]);
    });

    sheet.getRange(existing._rowNumber, 1, 1, headers.length).setValues([row]);
    SpreadsheetApp.flush();
    merged._rowNumber = existing._rowNumber;
    return merged;
  } finally {
    lock.releaseLock();
  }
}

function getSetting_(key, fallback) {
  var record = findOne_(CP.SHEETS.SETTINGS, { key: key });
  if (!record || record.value === '') return fallback;

  var type = stringValue_(record.valueType).toUpperCase();
  if (type === 'NUMBER') return Number(record.value);
  if (type === 'BOOLEAN') return toBoolean_(record.value);
  if (type === 'JSON') return safeJsonParse_(record.value, fallback);
  return record.value;
}

function setSetting_(key, value, valueType, description) {
  var existing = findOne_(CP.SHEETS.SETTINGS, { key: key });

  var record = {
    key: key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
    valueType: valueType || 'STRING',
    description: description || (existing ? existing.description : ''),
    updatedAt: new Date()
  };

  if (existing) {
    return updateRecordByKey_(CP.SHEETS.SETTINGS, 'key', key, record);
  }

  return appendRecord_(CP.SHEETS.SETTINGS, record);
}

/** ===== 06_AuthService.gs ===== */

function loginStudent_(payload) {
  ensureApiEnabled_();

  requireFields_(payload, ['email', 'accessCode']);

  var email = normalizeEmail_(payload.email);
  var student = findOne_(CP.SHEETS.STUDENTS, { email: email });

  if (!student) {
    logAudit_('PUBLIC', email, 'LOGIN_FAILED', 'STUDENT', '', { reason: 'NOT_FOUND' });
    throw apiError_('INVALID_CREDENTIALS', 'Email ou código de acesso inválido.');
  }

  if (stringValue_(student.status) !== CP.STATUS.ACTIVE) {
    throw apiError_('STUDENT_NOT_ACTIVE', 'A conta do estudante não está ativa.');
  }

  student = ensureStudentPublicId_(student);

  var submittedHash = hashSecret_(payload.accessCode);
  if (!constantTimeEquals_(submittedHash, student.accessCode)) {
    logAudit_('STUDENT', student.studentId, 'LOGIN_FAILED', 'STUDENT', student.studentId, {
      reason: 'INVALID_ACCESS_CODE'
    });
    throw apiError_('INVALID_CREDENTIALS', 'Email ou código de acesso inválido.');
  }

  revokeSessionsForSubject_(student.studentId);
  ensureEnrollmentAndProgress_(student.studentId, payload.courseId);

  var session = createSession_(
    student.studentId,
    payload.userAgent || '',
    payload.ipHash || ''
  );

  updateRecordByKey_(CP.SHEETS.STUDENTS, 'studentId', student.studentId, {
    lastLoginAt: new Date(),
    updatedAt: new Date()
  });

  logAudit_('STUDENT', student.studentId, 'LOGIN', 'SESSION', '', {});

  return successResponse_({
    sessionToken: session.token,
    expiresAt: session.expiresAt,
    student: publicStudent_(student)
  });
}

function logoutStudent_(payload) {
  revokeSession_(payload.sessionToken);

  logAudit_(
    'STUDENT',
    payload.studentId,
    'LOGOUT',
    'SESSION',
    '',
    {}
  );

  return successResponse_({ loggedOut: true });
}

function loginAdmin_(payload) {
  ensureApiEnabled_();
  requireFields_(payload, ['email', 'adminKey']);

  var email = normalizeEmail_(payload.email);
  var admin = findOne_(CP.SHEETS.ADMINS, { email: email });

  if (!admin || stringValue_(admin.status) !== CP.STATUS.ACTIVE) {
    throw apiError_('INVALID_ADMIN_CREDENTIALS', 'Credenciais administrativas inválidas.');
  }

  var expectedHash = PropertiesService
    .getScriptProperties()
    .getProperty('ADMIN_MASTER_KEY_HASH');

  if (!expectedHash) {
    throw apiError_(
      'ADMIN_KEY_NOT_CONFIGURED',
      'A chave administrativa ainda não foi configurada. Execute setupCoursePlatformApi().'
    );
  }

  if (!constantTimeEquals_(hashSecret_(payload.adminKey), expectedHash)) {
    logAudit_('ADMIN', admin.adminId, 'ADMIN_LOGIN_FAILED', 'ADMIN', admin.adminId, {});
    throw apiError_('INVALID_ADMIN_CREDENTIALS', 'Credenciais administrativas inválidas.');
  }

  var subjectId = 'ADMIN:' + admin.adminId;
  revokeSessionsForSubject_(subjectId);

  var session = createSession_(
    subjectId,
    payload.userAgent || '',
    payload.ipHash || ''
  );

  logAudit_('ADMIN', admin.adminId, 'ADMIN_LOGIN', 'SESSION', '', { role: admin.role });

  return successResponse_({
    adminToken: session.token,
    expiresAt: session.expiresAt,
    admin: publicAdmin_(admin)
  });
}

function adminLogout_(payload) {
  revokeSession_(payload.adminToken);

  logAudit_('ADMIN', payload.adminId, 'ADMIN_LOGOUT', 'SESSION', '', {});

  return successResponse_({ loggedOut: true });
}

function adminMe_(payload) {
  return successResponse_({
    admin: publicAdmin_(payload._admin)
  });
}

function adminListStaff_(payload) {
  var staff = readAll_(CP.SHEETS.ADMINS)
    .sort(function(a, b) {
      return stringValue_(a.fullName).localeCompare(stringValue_(b.fullName));
    })
    .map(publicAdmin_);

  return successResponse_({
    staff: staff,
    currentAdmin: publicAdmin_(payload._admin)
  });
}

function adminSaveStaff_(payload) {
  requireFields_(payload, ['fullName', 'email', 'role', 'status']);

  var email = normalizeEmail_(payload.email);
  if (!isValidEmail_(email)) {
    throw apiError_('INVALID_EMAIL', 'O email informado nao e valido.');
  }

  var role = stringValue_(payload.role).toUpperCase();
  var allowedRoles = [CP.ADMIN_ROLES.OWNER, CP.ADMIN_ROLES.ADMIN, CP.ADMIN_ROLES.REVIEWER];
  if (allowedRoles.indexOf(role) === -1) {
    throw apiError_('INVALID_ADMIN_ROLE', 'Perfil administrativo invalido.');
  }

  var status = stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase();
  var allowedStatuses = [CP.STATUS.ACTIVE, CP.STATUS.INACTIVE, CP.STATUS.BLOCKED, CP.STATUS.DELETED];
  if (allowedStatuses.indexOf(status) === -1) {
    throw apiError_('INVALID_STATUS', 'Estado de staff invalido.');
  }

  var adminId = stringValue_(payload.targetAdminId);
  var existing = adminId
    ? findOne_(CP.SHEETS.ADMINS, { adminId: adminId })
    : null;
  var duplicated = findOne_(CP.SHEETS.ADMINS, { email: email });

  if (duplicated && (!existing || duplicated.adminId !== existing.adminId)) {
    throw apiError_('EMAIL_ALREADY_EXISTS', 'Ja existe um membro da administracao com este email.');
  }

  if (existing && stringValue_(existing.adminId) === stringValue_(payload._admin.adminId) && status !== CP.STATUS.ACTIVE) {
    throw apiError_('CANNOT_DISABLE_SELF', 'Nao pode remover ou bloquear a sua propria permissao.');
  }

  if (existing && existing.role === CP.ADMIN_ROLES.OWNER && role !== CP.ADMIN_ROLES.OWNER) {
    var ownerCount = readAll_(CP.SHEETS.ADMINS).filter(function(admin) {
      return stringValue_(admin.role) === CP.ADMIN_ROLES.OWNER &&
        stringValue_(admin.status) === CP.STATUS.ACTIVE;
    }).length;
    if (ownerCount <= 1) {
      throw apiError_('LAST_OWNER_REQUIRED', 'Nao e possivel remover o ultimo OWNER ativo.');
    }
  }

  var now = new Date();
  var record = {
    adminId: existing ? existing.adminId : newId_('ADM'),
    fullName: truncate_(payload.fullName, 200),
    email: email,
    role: role,
    status: status,
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.ADMINS, 'adminId', existing.adminId, record)
    : appendRecord_(CP.SHEETS.ADMINS, record);

  if (status !== CP.STATUS.ACTIVE) {
    revokeSessionsForSubject_('ADMIN:' + record.adminId);
  }

  logAudit_('ADMIN', payload.adminId, 'STAFF_SAVED', 'ADMIN', record.adminId, {
    role: role,
    status: status
  });

  return successResponse_({ admin: publicAdmin_(record) });
}

function adminSetStaffStatus_(payload) {
  requireFields_(payload, ['targetAdminId', 'status']);

  var status = stringValue_(payload.status).toUpperCase();
  var allowed = [CP.STATUS.ACTIVE, CP.STATUS.INACTIVE, CP.STATUS.BLOCKED, CP.STATUS.DELETED];
  if (allowed.indexOf(status) === -1) {
    throw apiError_('INVALID_STATUS', 'Estado de staff invalido.');
  }

  if (stringValue_(payload.targetAdminId) === stringValue_(payload._admin.adminId) && status !== CP.STATUS.ACTIVE) {
    throw apiError_('CANNOT_DISABLE_SELF', 'Nao pode remover ou bloquear a sua propria permissao.');
  }

  var target = findOne_(CP.SHEETS.ADMINS, { adminId: payload.targetAdminId });
  if (!target) {
    throw apiError_('ADMIN_NOT_FOUND', 'Membro da administracao nao encontrado.');
  }

  if (stringValue_(target.role) === CP.ADMIN_ROLES.OWNER && status !== CP.STATUS.ACTIVE) {
    var activeOwners = readAll_(CP.SHEETS.ADMINS).filter(function(admin) {
      return stringValue_(admin.role) === CP.ADMIN_ROLES.OWNER &&
        stringValue_(admin.status) === CP.STATUS.ACTIVE &&
        stringValue_(admin.adminId) !== stringValue_(target.adminId);
    }).length;
    if (!activeOwners) {
      throw apiError_('LAST_OWNER_REQUIRED', 'Nao e possivel remover o ultimo OWNER ativo.');
    }
  }

  var admin = updateRecordByKey_(CP.SHEETS.ADMINS, 'adminId', payload.targetAdminId, {
    status: status,
    updatedAt: new Date()
  });

  if (status !== CP.STATUS.ACTIVE) {
    revokeSessionsForSubject_('ADMIN:' + admin.adminId);
  }

  logAudit_('ADMIN', payload.adminId, 'STAFF_STATUS_CHANGED', 'ADMIN', admin.adminId, {
    status: status
  });

  return successResponse_({ admin: publicAdmin_(admin) });
}

/** ===== 07_CourseService.gs ===== */

function getPublicCourseConfig_(courseId) {
  ensureApiEnabled_();

  var resolvedCourseId = stringValue_(courseId) ||
    stringValue_(getSetting_('DEFAULT_COURSE_ID', CP.DEFAULTS.DEFAULT_COURSE_ID));

  var course = findOne_(CP.SHEETS.COURSES, {
    courseId: resolvedCourseId,
    status: CP.STATUS.ACTIVE
  });

  if (!course) {
    throw apiError_('COURSE_NOT_FOUND', 'Curso não encontrado.');
  }

  var lessons = findMany_(CP.SHEETS.LESSONS, {
    courseId: course.courseId,
    status: CP.STATUS.ACTIVE
  }).sort(function(a, b) {
    return Number(a.lessonNumber) - Number(b.lessonNumber);
  });

  return successResponse_({
    course: publicCourse_(course),
    lessons: lessons.map(publicLesson_)
  });
}

function getPublicMediaConfig_(courseId) {
  ensureApiEnabled_();

  return successResponse_({
    mediaConfig: mediaConfigForPublic_(readMediaConfig_(courseId))
  });
}

function getMediaConfig_(payload) {
  ensureApiEnabled_();

  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: payload.studentId
  });

  return successResponse_({
    mediaConfig: mediaConfigForStudent_(
      readMediaConfig_(payload.courseId),
      student ? student.email : ''
    )
  });
}

function adminGetMediaConfig_(payload) {
  ensureApiEnabled_();

  return successResponse_({
    mediaConfig: readMediaConfig_(payload.courseId)
  });
}

function adminSaveMediaConfig_(payload) {
  ensureApiEnabled_();

  var source = payload.mediaConfig || {
    logoUrl: payload.logoUrl,
    videos: payload.videos
  };
  var mediaConfig = normalizeMediaConfig_(source);
  setSetting_(
    'MEDIA_CONFIG',
    mediaConfig,
    'JSON',
    'Logotipo e galeria de videos da plataforma.'
  );

  logAudit_('ADMIN', payload.adminId, 'MEDIA_CONFIG_SAVED', 'SETTING', 'MEDIA_CONFIG', {
    hasLogo: Boolean(mediaConfig.logoUrl),
    videoCount: mediaConfig.videos.length
  });

  return successResponse_({
    mediaConfig: mediaConfig
  });
}

function readMediaConfig_(courseId) {
  var mediaConfig = getSetting_('MEDIA_CONFIG', CP.DEFAULTS.MEDIA_CONFIG);
  return normalizeMediaConfig_(mediaConfig);
}

function normalizeMediaConfig_(mediaConfig) {
  if (typeof mediaConfig === 'string') {
    mediaConfig = safeJsonParse_(mediaConfig, CP.DEFAULTS.MEDIA_CONFIG);
  }

  mediaConfig = mediaConfig || {};

  var logoUrl = stringValue_(mediaConfig.logoUrl).trim();
  if (logoUrl && !isHttpUrl_(logoUrl)) {
    throw apiError_('INVALID_MEDIA_LOGO_URL', 'O link do logotipo deve comecar por http:// ou https://.');
  }

  var result = {
    logoUrl: truncate_(logoUrl, 2000),
    videos: []
  };

  var videos = mediaConfig.videos instanceof Array ? mediaConfig.videos : [];
  for (var i = 0; i < videos.length && result.videos.length < 50; i++) {
    var video = videos[i] || {};
    var url = stringValue_(video.url).trim();
    if (!url) continue;

    if (!isHttpUrl_(url)) {
      throw apiError_('INVALID_MEDIA_VIDEO_URL', 'O link do video deve comecar por http:// ou https://.');
    }

    var visibility = stringValue_(video.visibility || 'PUBLIC').toUpperCase();
    if (visibility !== 'SELECTED') visibility = 'PUBLIC';

    var status = stringValue_(video.status || CP.STATUS.ACTIVE).toUpperCase();
    if ([CP.STATUS.ACTIVE, CP.STATUS.INACTIVE, CP.STATUS.DELETED].indexOf(status) === -1) {
      status = CP.STATUS.ACTIVE;
    }

    result.videos.push({
      id: stringValue_(video.id).trim() || newId_('VID'),
      title: truncate_(stringValue_(video.title).trim() || 'Video da plataforma', 180),
      url: truncate_(url, 2000),
      description: truncate_(stringValue_(video.description).trim(), 1000),
      visibility: visibility,
      allowedEmails: normalizeMediaEmailList_(video.allowedEmails),
      status: status
    });
  }

  return result;
}

function mediaConfigForPublic_(mediaConfig) {
  return {
    logoUrl: mediaConfig.logoUrl,
    videos: mediaConfig.videos
      .filter(function(video) {
        return video.status === CP.STATUS.ACTIVE && video.visibility !== 'SELECTED';
      })
      .map(function(video) {
        return publicMediaVideo_(video, []);
      })
  };
}

function mediaConfigForStudent_(mediaConfig, studentEmail) {
  var normalizedEmail = normalizeEmail_(studentEmail);

  return {
    logoUrl: mediaConfig.logoUrl,
    videos: mediaConfig.videos
      .filter(function(video) {
        if (video.status !== CP.STATUS.ACTIVE) return false;
        if (video.visibility !== 'SELECTED') return true;
        return video.allowedEmails.indexOf(normalizedEmail) !== -1;
      })
      .map(function(video) {
        var allowedEmails = video.visibility === 'SELECTED' && normalizedEmail
          ? [normalizedEmail]
          : [];
        return publicMediaVideo_(video, allowedEmails);
      })
  };
}

function publicMediaVideo_(video, allowedEmails) {
  return {
    id: video.id,
    title: video.title,
    url: video.url,
    description: video.description,
    visibility: video.visibility,
    allowedEmails: allowedEmails || [],
    status: video.status
  };
}

function normalizeMediaEmailList_(value) {
  var raw = value instanceof Array
    ? value
    : stringValue_(value).split(/[\n,;]+/);
  var emails = [];

  raw.forEach(function(item) {
    var email = normalizeEmail_(item);
    if (email && isValidEmail_(email) && emails.indexOf(email) === -1) {
      emails.push(email);
    }
  });

  return emails;
}

function isHttpUrl_(url) {
  return /^https?:\/\/[^\s]+$/i.test(stringValue_(url).trim());
}

function ensureEnrollmentAndProgress_(studentId, courseId, groupId) {
  courseId = stringValue_(courseId) ||
    stringValue_(getSetting_('DEFAULT_COURSE_ID', CP.DEFAULTS.DEFAULT_COURSE_ID));

  var course = findOne_(CP.SHEETS.COURSES, {
    courseId: courseId,
    status: CP.STATUS.ACTIVE
  });

  if (!course) {
    throw apiError_('COURSE_NOT_FOUND', 'Curso ativo não encontrado.');
  }

  var enrollment = findOne_(CP.SHEETS.ENROLLMENTS, {
    studentId: studentId,
    courseId: courseId
  });

  if (!enrollment) {
    enrollment = appendRecord_(CP.SHEETS.ENROLLMENTS, {
      enrollmentId: newId_('ENR'),
      studentId: studentId,
      courseId: courseId,
      groupId: stringValue_(groupId),
      status: CP.STATUS.ACTIVE,
      enrolledAt: new Date(),
      completedAt: '',
      progressPercent: 0,
      finalScore: '',
      certificateId: '',
      updatedAt: new Date()
    });
  } else if (groupId && stringValue_(enrollment.groupId) !== stringValue_(groupId)) {
    enrollment = updateRecordByKey_(CP.SHEETS.ENROLLMENTS, 'enrollmentId', enrollment.enrollmentId, {
      groupId: stringValue_(groupId),
      updatedAt: new Date()
    });
  }

  var lessons = findMany_(CP.SHEETS.LESSONS, {
    courseId: courseId,
    status: CP.STATUS.ACTIVE
  }).sort(function(a, b) {
    return Number(a.lessonNumber) - Number(b.lessonNumber);
  });

  lessons.forEach(function(lesson, index) {
    var progress = findOne_(CP.SHEETS.LESSON_PROGRESS, {
      enrollmentId: enrollment.enrollmentId,
      lessonId: lesson.lessonId
    });

    if (!progress) {
      appendRecord_(CP.SHEETS.LESSON_PROGRESS, {
        progressId: newId_('PRG'),
        enrollmentId: enrollment.enrollmentId,
        studentId: studentId,
        lessonId: lesson.lessonId,
        status: index === 0 ? CP.STATUS.AVAILABLE : CP.STATUS.LOCKED,
        unlockedAt: index === 0 ? new Date() : '',
        startedAt: '',
        submittedAt: '',
        approvedAt: '',
        score: '',
        attemptCount: 0,
        updatedAt: new Date()
      });
    }
  });

  return enrollment;
}

function getStudentDashboard_(payload) {
  var enrollment = ensureEnrollmentAndProgress_(
    payload.studentId,
    payload.courseId
  );
  validateEnrollmentWindow_(enrollment);

  var course = findOne_(CP.SHEETS.COURSES, {
    courseId: enrollment.courseId
  });

  var lessons = findMany_(CP.SHEETS.LESSONS, {
    courseId: enrollment.courseId,
    status: CP.STATUS.ACTIVE
  }).sort(function(a, b) {
    return Number(a.lessonNumber) - Number(b.lessonNumber);
  });

  var progressRows = findMany_(CP.SHEETS.LESSON_PROGRESS, {
    enrollmentId: enrollment.enrollmentId
  });

  var progressMap = {};
  progressRows.forEach(function(progress) {
    progressMap[progress.lessonId] = progress;
  });

  var lessonCards = lessons.map(function(lesson) {
    var progress = progressMap[lesson.lessonId];
    var activeAttempt = getOpenAttempt_(payload.studentId, lesson.lessonId);

    if (activeAttempt) {
      expireAttemptIfNeeded_(activeAttempt);
      activeAttempt = findOne_(CP.SHEETS.ATTEMPTS, {
        attemptId: activeAttempt.attemptId
      });
    }

    return {
      lesson: publicLesson_(lesson),
      progress: publicProgress_(progress),
      activeAttempt: activeAttempt ? publicAttempt_(activeAttempt) : null
    };
  });

  return successResponse_({
    student: publicStudent_(payload._student),
    course: publicCourse_(course),
    enrollment: publicEnrollment_(enrollment),
    lessons: lessonCards
  });
}

function getMyCourses_(payload) {
  ensureApiEnabled_();

  var enrollments = findMany_(CP.SHEETS.ENROLLMENTS, {
    studentId: payload.studentId
  });

  if (!enrollments.length) {
    enrollments = [ensureEnrollmentAndProgress_(payload.studentId, payload.courseId)];
  }

  var courses = enrollments.map(function(enrollment) {
    var course = findOne_(CP.SHEETS.COURSES, {
      courseId: enrollment.courseId
    });
    var group = enrollment.groupId
      ? findOne_(CP.SHEETS.GROUPS, { groupId: enrollment.groupId })
      : null;
    var lessons = course
      ? findMany_(CP.SHEETS.LESSONS, {
        courseId: course.courseId,
        status: CP.STATUS.ACTIVE
      })
      : [];

    return {
      course: publicCourse_(course),
      enrollment: publicEnrollment_(enrollment),
      group: publicGroup_(group),
      lessonCount: lessons.length
    };
  }).filter(function(item) {
    return item.course;
  });

  return successResponse_({
    student: publicStudent_(ensureStudentPublicId_(payload._student)),
    courses: courses
  });
}

function updateMyProfile_(payload) {
  ensureApiEnabled_();
  ensureSchema_();

  var patch = {
    fullName: truncate_(payload.fullName || payload._student.fullName, 200),
    country: truncate_(payload.country || '', 100),
    organization: truncate_(payload.organization || '', 250),
    phone: truncate_(payload.phone || '', 80),
    jobTitle: truncate_(payload.jobTitle || '', 180),
    interests: truncate_(payload.interests || '', 1000),
    updatedAt: new Date()
  };

  if (stringValue_(payload.removeProfilePhoto) === 'true') {
    patch.profilePhotoUrl = '';
  } else if (stringValue_(payload.profilePhotoBase64)) {
    patch.profilePhotoUrl = saveStudentProfilePhoto_(payload);
  }

  var student = updateRecordByKey_(
    CP.SHEETS.STUDENTS,
    'studentId',
    payload.studentId,
    patch
  );

  logAudit_('STUDENT', payload.studentId, 'PROFILE_UPDATED', 'STUDENT', payload.studentId, {});

  return successResponse_({
    student: publicStudent_(student)
  });
}

function changeMyAccessCode_(payload) {
  ensureApiEnabled_();
  requireFields_(payload, ['currentAccessCode', 'newAccessCode']);

  var currentHash = hashSecret_(payload.currentAccessCode);
  if (!constantTimeEquals_(currentHash, payload._student.accessCode)) {
    throw apiError_('INVALID_CURRENT_ACCESS_CODE', 'A senha atual nÃ£o estÃ¡ correta.');
  }

  var newAccessCode = stringValue_(payload.newAccessCode).trim();
  if (newAccessCode.length < 8) {
    throw apiError_('WEAK_ACCESS_CODE', 'A nova senha deve ter pelo menos 8 caracteres.');
  }

  if (constantTimeEquals_(hashSecret_(newAccessCode), payload._student.accessCode)) {
    throw apiError_('ACCESS_CODE_UNCHANGED', 'A nova senha deve ser diferente da senha atual.');
  }

  updateRecordByKey_(CP.SHEETS.STUDENTS, 'studentId', payload.studentId, {
    accessCode: hashSecret_(newAccessCode),
    updatedAt: new Date()
  });

  revokeSessionsForSubject_(payload.studentId);
  logAudit_('STUDENT', payload.studentId, 'ACCESS_CODE_CHANGED', 'STUDENT', payload.studentId, {});

  return successResponse_({
    changed: true,
    requiresLogin: true
  });
}

function getLessonForStudent_(payload) {
  requireFields_(payload, ['lessonId']);

  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: payload.lessonId,
    status: CP.STATUS.ACTIVE
  });

  if (!lesson) {
    throw apiError_('LESSON_NOT_FOUND', 'A aula não foi encontrada.');
  }

  var progress = findOne_(CP.SHEETS.LESSON_PROGRESS, {
    studentId: payload.studentId,
    lessonId: lesson.lessonId
  });

  if (!progress || stringValue_(progress.status) === CP.STATUS.LOCKED) {
    throw apiError_('LESSON_LOCKED', 'Esta aula ainda está bloqueada.');
  }

  validateEnrollmentWindow_(findOne_(CP.SHEETS.ENROLLMENTS, {
    enrollmentId: progress.enrollmentId
  }));

  var content = findMany_(CP.SHEETS.LESSON_CONTENT, {
    lessonId: lesson.lessonId,
    status: CP.STATUS.ACTIVE
  }).sort(function(a, b) {
    return Number(a.sectionOrder) - Number(b.sectionOrder);
  }).map(publicContent_);

  var questions = findMany_(CP.SHEETS.QUESTIONS, {
    lessonId: lesson.lessonId,
    status: CP.STATUS.ACTIVE
  }).sort(function(a, b) {
    return Number(a.questionOrder) - Number(b.questionOrder);
  });

  var questionPayload = questions.map(function(question) {
    var options = findMany_(CP.SHEETS.QUESTION_OPTIONS, {
      questionId: question.questionId
    }).sort(function(a, b) {
      return Number(a.optionOrder) - Number(b.optionOrder);
    }).map(function(option) {
      return {
        optionId: option.optionId,
        optionOrder: Number(option.optionOrder),
        optionLabel: option.optionLabel,
        optionText: option.optionText
      };
    });

    return {
      questionId: question.questionId,
      questionOrder: Number(question.questionOrder),
      questionType: question.questionType,
      prompt: question.prompt,
      points: Number(question.points || 0),
      isRequired: toBoolean_(question.isRequired),
      options: options
    };
  });

  return successResponse_({
    lesson: publicLesson_(lesson),
    progress: publicProgress_(progress),
    content: content,
    questions: questionPayload
  });
}

function unlockNextLesson_(studentId, currentLessonId) {
  var currentLesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: currentLessonId
  });

  if (!currentLesson) return null;

  var nextLessons = findMany_(CP.SHEETS.LESSONS, {
    courseId: currentLesson.courseId,
    prerequisiteLessonId: currentLessonId,
    status: CP.STATUS.ACTIVE
  });

  if (!nextLessons.length) return null;

  var nextLesson = nextLessons.sort(function(a, b) {
    return Number(a.lessonNumber) - Number(b.lessonNumber);
  })[0];

  var nextProgress = findOne_(CP.SHEETS.LESSON_PROGRESS, {
    studentId: studentId,
    lessonId: nextLesson.lessonId
  });

  if (
    nextProgress &&
    stringValue_(nextProgress.status) === CP.STATUS.LOCKED
  ) {
    nextProgress = updateRecordByKey_(
      CP.SHEETS.LESSON_PROGRESS,
      'progressId',
      nextProgress.progressId,
      {
        status: CP.STATUS.AVAILABLE,
        unlockedAt: new Date(),
        updatedAt: new Date()
      }
    );
  }

  return nextProgress;
}

function recalculateEnrollment_(studentId, courseId) {
  var enrollment = findOne_(CP.SHEETS.ENROLLMENTS, {
    studentId: studentId,
    courseId: courseId
  });

  if (!enrollment) return null;

  var lessons = findMany_(CP.SHEETS.LESSONS, {
    courseId: courseId,
    status: CP.STATUS.ACTIVE
  });

  var progressRows = findMany_(CP.SHEETS.LESSON_PROGRESS, {
    enrollmentId: enrollment.enrollmentId
  });

  var approved = progressRows.filter(function(row) {
    return stringValue_(row.status) === CP.STATUS.APPROVED;
  });

  var percent = lessons.length
    ? Math.round((approved.length / lessons.length) * 100)
    : 0;

  var scores = approved
    .map(function(row) { return Number(row.score); })
    .filter(function(score) { return !isNaN(score); });

  var finalScore = scores.length
    ? round2_(scores.reduce(function(sum, score) { return sum + score; }, 0) / scores.length)
    : '';

  var patch = {
    progressPercent: percent,
    finalScore: finalScore,
    updatedAt: new Date()
  };

  if (lessons.length && approved.length === lessons.length) {
    patch.status = CP.STATUS.COMPLETED;
    patch.completedAt = new Date();

    var certificate = ensureCertificate_(studentId, courseId, finalScore);
    patch.certificateId = certificate.certificateId;
  } else {
    patch.status = CP.STATUS.ACTIVE;
    patch.completedAt = '';
    patch.certificateId = '';
  }

  return updateRecordByKey_(
    CP.SHEETS.ENROLLMENTS,
    'enrollmentId',
    enrollment.enrollmentId,
    patch
  );
}

function validateEnrollmentWindow_(enrollment) {
  if (!enrollment || !enrollment.groupId) return;

  var group = findOne_(CP.SHEETS.GROUPS, {
    groupId: enrollment.groupId
  });
  if (!group) return;

  if (stringValue_(group.status) !== CP.STATUS.ACTIVE) {
    throw apiError_('GROUP_NOT_ACTIVE', 'A turma associada a este curso nao esta ativa.');
  }

  var now = Date.now();
  var start = group.startDate ? new Date(group.startDate).getTime() : 0;
  var end = group.endDate ? new Date(group.endDate).getTime() : 0;

  if (start && now < start) {
    throw apiError_('GROUP_NOT_STARTED', 'O periodo desta turma ainda nao iniciou.');
  }

  if (end && now > end) {
    throw apiError_('GROUP_ENDED', 'O periodo desta turma ja terminou.');
  }
}

/** ===== 08_AttemptService.gs ===== */

function startAttempt_(payload) {
  requireFields_(payload, ['lessonId']);

  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: payload.lessonId,
    status: CP.STATUS.ACTIVE
  });

  if (!lesson) {
    throw apiError_('LESSON_NOT_FOUND', 'A aula não foi encontrada.');
  }

  var progress = findOne_(CP.SHEETS.LESSON_PROGRESS, {
    studentId: payload.studentId,
    lessonId: lesson.lessonId
  });

  if (!progress) {
    throw apiError_('PROGRESS_NOT_FOUND', 'O progresso desta aula não foi criado.');
  }

  validateEnrollmentWindow_(findOne_(CP.SHEETS.ENROLLMENTS, {
    enrollmentId: progress.enrollmentId
  }));

  if (stringValue_(progress.status) === CP.STATUS.LOCKED) {
    throw apiError_('LESSON_LOCKED', 'A aula ainda está bloqueada.');
  }

  if (stringValue_(progress.status) === CP.STATUS.APPROVED) {
    throw apiError_('LESSON_ALREADY_APPROVED', 'Esta aula já foi aprovada.');
  }

  var openAttempt = getOpenAttempt_(payload.studentId, lesson.lessonId);
  if (openAttempt) {
    expireAttemptIfNeeded_(openAttempt);
    openAttempt = findOne_(CP.SHEETS.ATTEMPTS, {
      attemptId: openAttempt.attemptId
    });

    if (stringValue_(openAttempt.status) === CP.STATUS.IN_PROGRESS) {
      return successResponse_({
        resumed: true,
        attempt: publicAttempt_(openAttempt)
      });
    }
  }

  var attempts = findMany_(CP.SHEETS.ATTEMPTS, {
    studentId: payload.studentId,
    lessonId: lesson.lessonId
  }).sort(function(a, b) {
    return Number(b.attemptNumber) - Number(a.attemptNumber);
  });

  var latest = attempts.length ? attempts[0] : null;

  if (
    latest &&
    [CP.STATUS.FAILED, CP.STATUS.TIME_EXCEEDED, CP.STATUS.CORRECTION_REQUIRED]
      .indexOf(stringValue_(latest.status)) !== -1 &&
    !toBoolean_(latest.retryAuthorized)
  ) {
    throw apiError_(
      'RETRY_NOT_AUTHORIZED',
      'É necessária autorização para iniciar uma nova tentativa.'
    );
  }

  var now = new Date();
  var totalMinutes =
    Number(lesson.exerciseMinutes || 0) +
    Number(lesson.individualMinutes || 0);

  if (totalMinutes <= 0) {
    throw apiError_('INVALID_LESSON_TIME', 'A aula não possui tempo prático configurado.');
  }

  var deadlineAt = new Date(now.getTime() + totalMinutes * 60 * 1000);

  var attempt = appendRecord_(CP.SHEETS.ATTEMPTS, {
    attemptId: newId_('ATT'),
    progressId: progress.progressId,
    studentId: payload.studentId,
    lessonId: lesson.lessonId,
    attemptNumber: attempts.length + 1,
    startedAt: now,
    deadlineAt: deadlineAt,
    submittedAt: '',
    status: CP.STATUS.IN_PROGRESS,
    score: '',
    reviewerId: '',
    reviewedAt: '',
    reviewComments: '',
    retryAuthorized: false,
    createdAt: now,
    updatedAt: now
  });

  updateRecordByKey_(
    CP.SHEETS.LESSON_PROGRESS,
    'progressId',
    progress.progressId,
    {
      status: CP.STATUS.IN_PROGRESS,
      startedAt: progress.startedAt || now,
      attemptCount: attempts.length + 1,
      updatedAt: now
    }
  );

  logAudit_('STUDENT', payload.studentId, 'ATTEMPT_STARTED', 'ATTEMPT', attempt.attemptId, {
    lessonId: lesson.lessonId,
    deadlineAt: deadlineAt
  });

  return successResponse_({
    resumed: false,
    attempt: publicAttempt_(attempt)
  });
}

function saveAnswer_(payload) {
  requireFields_(payload, ['attemptId', 'questionId']);

  var attempt = validateStudentAttempt_(payload.studentId, payload.attemptId);
  assertAttemptEditable_(attempt);

  var question = findOne_(CP.SHEETS.QUESTIONS, {
    questionId: payload.questionId,
    lessonId: attempt.lessonId,
    status: CP.STATUS.ACTIVE
  });

  if (!question) {
    throw apiError_('QUESTION_NOT_FOUND', 'A pergunta não pertence a esta aula.');
  }

  var now = new Date();
  var existing = findOne_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId,
    questionId: question.questionId
  });

  var answer = {
    answerId: existing ? existing.answerId : newId_('ANS'),
    attemptId: attempt.attemptId,
    questionId: question.questionId,
    answerText: truncate_(payload.answerText || '', 50000),
    selectedOptionId: normalizeSelectedOptions_(payload.selectedOptionId),
    isCorrect: '',
    awardedPoints: '',
    savedAt: now,
    submittedAt: ''
  };

  if (existing) {
    updateRecordByKey_(
      CP.SHEETS.ANSWERS,
      'answerId',
      existing.answerId,
      answer
    );
  } else {
    appendRecord_(CP.SHEETS.ANSWERS, answer);
  }

  return successResponse_({
    answerId: answer.answerId,
    savedAt: now
  });
}

function submitAttempt_(payload) {
  requireFields_(payload, ['attemptId']);

  var attempt = validateStudentAttempt_(payload.studentId, payload.attemptId);
  assertAttemptEditable_(attempt);

  validateRequiredAnswers_(attempt);
  validateRequiredFiles_(attempt);

  var now = new Date();
  gradeObjectiveAnswers_(attempt);

  attempt = updateRecordByKey_(
    CP.SHEETS.ATTEMPTS,
    'attemptId',
    attempt.attemptId,
    {
      submittedAt: now,
      status: CP.STATUS.UNDER_REVIEW,
      updatedAt: now
    }
  );

  updateRecordByKey_(
    CP.SHEETS.LESSON_PROGRESS,
    'progressId',
    attempt.progressId,
    {
      status: CP.STATUS.UNDER_REVIEW,
      submittedAt: now,
      updatedAt: now
    }
  );

  var answers = findMany_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId
  });

  answers.forEach(function(answer) {
    updateRecordByKey_(
      CP.SHEETS.ANSWERS,
      'answerId',
      answer.answerId,
      { submittedAt: now }
    );
  });

  logAudit_('STUDENT', payload.studentId, 'ATTEMPT_SUBMITTED', 'ATTEMPT', attempt.attemptId, {
    lessonId: attempt.lessonId
  });

  return successResponse_({
    attempt: publicAttempt_(attempt),
    message: 'A atividade foi submetida e encontra-se em avaliação.'
  });
}

function getAttemptStatus_(payload) {
  requireFields_(payload, ['attemptId']);

  var attempt = validateStudentAttempt_(payload.studentId, payload.attemptId);
  expireAttemptIfNeeded_(attempt);

  attempt = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: attempt.attemptId
  });

  var reviews = findMany_(CP.SHEETS.REVIEWS, {
    attemptId: attempt.attemptId
  }).sort(function(a, b) {
    return new Date(b.reviewedAt).getTime() - new Date(a.reviewedAt).getTime();
  });

  var answers = findMany_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId
  }).map(function(answer) {
    return {
      answerId: answer.answerId,
      questionId: answer.questionId,
      answerText: answer.answerText,
      selectedOptionId: parseSelectedOptions_(answer.selectedOptionId),
      savedAt: answer.savedAt,
      submittedAt: answer.submittedAt
    };
  });

  return successResponse_({
    attempt: publicAttempt_(attempt),
    answers: answers,
    files: listAttemptFiles_(attempt.attemptId),
    latestReview: reviews.length ? publicReview_(reviews[0]) : null
  });
}

function validateStudentAttempt_(studentId, attemptId) {
  var attempt = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: attemptId,
    studentId: studentId
  });

  if (!attempt) {
    throw apiError_('ATTEMPT_NOT_FOUND', 'A tentativa não foi encontrada.');
  }

  return attempt;
}

function assertAttemptEditable_(attempt) {
  expireAttemptIfNeeded_(attempt);

  var refreshed = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: attempt.attemptId
  });

  if (stringValue_(refreshed.status) === CP.STATUS.TIME_EXCEEDED) {
    throw apiError_('ATTEMPT_EXPIRED', 'O prazo desta tentativa terminou.');
  }

  if (stringValue_(refreshed.status) !== CP.STATUS.IN_PROGRESS) {
    throw apiError_('ATTEMPT_NOT_EDITABLE', 'Esta tentativa já não pode ser alterada.');
  }
}

function expireAttemptIfNeeded_(attempt) {
  if (
    stringValue_(attempt.status) === CP.STATUS.IN_PROGRESS &&
    new Date(attempt.deadlineAt).getTime() <= Date.now()
  ) {
    updateRecordByKey_(
      CP.SHEETS.ATTEMPTS,
      'attemptId',
      attempt.attemptId,
      {
        status: CP.STATUS.TIME_EXCEEDED,
        updatedAt: new Date()
      }
    );

    updateRecordByKey_(
      CP.SHEETS.LESSON_PROGRESS,
      'progressId',
      attempt.progressId,
      {
        status: CP.STATUS.TIME_EXCEEDED,
        updatedAt: new Date()
      }
    );

    logAudit_('SYSTEM', 'SYSTEM', 'ATTEMPT_EXPIRED', 'ATTEMPT', attempt.attemptId, {});
  }
}

function getOpenAttempt_(studentId, lessonId) {
  var attempts = findMany_(CP.SHEETS.ATTEMPTS, {
    studentId: studentId,
    lessonId: lessonId,
    status: CP.STATUS.IN_PROGRESS
  }).sort(function(a, b) {
    return new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime();
  });

  return attempts.length ? attempts[0] : null;
}

function validateRequiredAnswers_(attempt) {
  var requiredQuestions = findMany_(CP.SHEETS.QUESTIONS, {
    lessonId: attempt.lessonId,
    status: CP.STATUS.ACTIVE,
    isRequired: function(value) { return toBoolean_(value); }
  });

  if (!requiredQuestions.length) return;

  var answers = findMany_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId
  });

  var answeredMap = {};
  answers.forEach(function(answer) {
    var hasText = stringValue_(answer.answerText).trim() !== '';
    var hasOption = stringValue_(answer.selectedOptionId).trim() !== '';
    if (hasText || hasOption) {
      answeredMap[answer.questionId] = true;
    }
  });

  var missing = requiredQuestions.filter(function(question) {
    return !answeredMap[question.questionId];
  });

  if (missing.length) {
    throw apiError_(
      'REQUIRED_ANSWERS_MISSING',
      'Existem perguntas obrigatórias sem resposta.',
      {
        questionIds: missing.map(function(question) { return question.questionId; })
      }
    );
  }
}

function validateRequiredFiles_(attempt) {
  if (!getSetting_('REQUIRE_FILE_UPLOAD', CP.DEFAULTS.REQUIRE_FILE_UPLOAD)) {
    return;
  }

  var files = listAttemptFiles_(attempt.attemptId);
  if (!files.length) {
    throw apiError_(
      'FILE_REQUIRED',
      'Carregue pelo menos um documento ou fotografia antes de submeter.'
    );
  }
}

function gradeObjectiveAnswers_(attempt) {
  var questions = findMany_(CP.SHEETS.QUESTIONS, {
    lessonId: attempt.lessonId,
    status: CP.STATUS.ACTIVE
  });

  var answers = findMany_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId
  });

  var answerMap = {};
  answers.forEach(function(answer) {
    answerMap[answer.questionId] = answer;
  });

  questions.forEach(function(question) {
    var type = stringValue_(question.questionType);
    if (
      ['SINGLE_CHOICE', 'MULTIPLE_CHOICE', 'TRUE_FALSE']
        .indexOf(type) === -1
    ) {
      return;
    }

    var answer = answerMap[question.questionId];
    if (!answer) return;

    var options = findMany_(CP.SHEETS.QUESTION_OPTIONS, {
      questionId: question.questionId
    });

    var correctIds = options
      .filter(function(option) { return toBoolean_(option.isCorrect); })
      .map(function(option) { return stringValue_(option.optionId); })
      .sort();

    var selectedIds = parseSelectedOptions_(answer.selectedOptionId).sort();
    var correct = arraysEqual_(correctIds, selectedIds);
    var points = correct ? Number(question.points || 0) : 0;

    updateRecordByKey_(
      CP.SHEETS.ANSWERS,
      'answerId',
      answer.answerId,
      {
        isCorrect: correct,
        awardedPoints: points
      }
    );
  });
}

/** ===== 09_FileService.gs ===== */

function uploadSubmissionFile_(payload) {
  requireFields_(payload, [
    'attemptId',
    'fileName',
    'mimeType',
    'base64Data'
  ]);

  var attempt = validateStudentAttempt_(payload.studentId, payload.attemptId);
  assertAttemptEditable_(attempt);

  var mimeType = stringValue_(payload.mimeType).toLowerCase();
  if (CP.ALLOWED_FILE_TYPES.indexOf(mimeType) === -1) {
    throw apiError_('FILE_TYPE_NOT_ALLOWED', 'Tipo de ficheiro não permitido: ' + mimeType);
  }

  var activeFiles = listAttemptFiles_(attempt.attemptId);
  var maxFiles = Number(
    getSetting_('MAX_FILES_PER_SUBMISSION', CP.DEFAULTS.MAX_FILES_PER_SUBMISSION)
  );

  if (activeFiles.length >= maxFiles) {
    throw apiError_('TOO_MANY_FILES', 'Foi atingido o número máximo de ficheiros.');
  }

  var cleanBase64 = stripDataUrl_(payload.base64Data);
  var estimatedBytes = Math.floor(cleanBase64.length * 3 / 4);
  var maxFileBytes = Number(
    getSetting_('MAX_FILE_SIZE_MB', CP.DEFAULTS.MAX_FILE_SIZE_MB)
  ) * 1024 * 1024;

  if (estimatedBytes > maxFileBytes) {
    throw apiError_('FILE_TOO_LARGE', 'O ficheiro ultrapassa o limite permitido.');
  }

  var currentTotal = activeFiles.reduce(function(sum, file) {
    return sum + Number(file.sizeBytes || 0);
  }, 0);

  var maxSubmissionBytes = Number(
    getSetting_('MAX_SUBMISSION_SIZE_MB', CP.DEFAULTS.MAX_SUBMISSION_SIZE_MB)
  ) * 1024 * 1024;

  if (currentTotal + estimatedBytes > maxSubmissionBytes) {
    throw apiError_(
      'SUBMISSION_TOO_LARGE',
      'O tamanho total dos ficheiros ultrapassa o limite da submissão.'
    );
  }

  var bytes;
  try {
    bytes = Utilities.base64Decode(cleanBase64);
  } catch (error) {
    throw apiError_('INVALID_BASE64', 'O conteúdo do ficheiro não está em Base64 válido.');
  }

  if (bytes.length > maxFileBytes) {
    throw apiError_('FILE_TOO_LARGE', 'O ficheiro ultrapassa o limite permitido.');
  }

  var fileName = uniqueFileName_(
    sanitizeFileName_(payload.fileName),
    activeFiles
  );

  var folder = getAttemptFolder_(attempt);
  var blob = Utilities.newBlob(bytes, mimeType, fileName);
  var driveFile = folder.createFile(blob);

  var record = appendRecord_(CP.SHEETS.FILES, {
    fileId: newId_('FIL'),
    attemptId: attempt.attemptId,
    studentId: payload.studentId,
    lessonId: attempt.lessonId,
    fileName: fileName,
    mimeType: mimeType,
    sizeBytes: bytes.length,
    driveFileId: driveFile.getId(),
    driveUrl: driveFile.getUrl(),
    uploadedAt: new Date(),
    status: CP.STATUS.ACTIVE
  });

  logAudit_('STUDENT', payload.studentId, 'FILE_UPLOADED', 'FILE', record.fileId, {
    attemptId: attempt.attemptId,
    sizeBytes: bytes.length,
    mimeType: mimeType
  });

  return successResponse_({
    file: publicFile_(record)
  });
}

function deleteUploadedFile_(payload) {
  requireFields_(payload, ['fileId']);

  var fileRecord = findOne_(CP.SHEETS.FILES, {
    fileId: payload.fileId,
    studentId: payload.studentId,
    status: CP.STATUS.ACTIVE
  });

  if (!fileRecord) {
    throw apiError_('FILE_NOT_FOUND', 'O ficheiro não foi encontrado.');
  }

  var attempt = validateStudentAttempt_(payload.studentId, fileRecord.attemptId);
  assertAttemptEditable_(attempt);

  try {
    DriveApp.getFileById(fileRecord.driveFileId).setTrashed(true);
  } catch (error) {
    console.warn('Não foi possível mover o ficheiro do Drive para o lixo: ' + error.message);
  }

  updateRecordByKey_(CP.SHEETS.FILES, 'fileId', fileRecord.fileId, {
    status: CP.STATUS.DELETED
  });

  logAudit_('STUDENT', payload.studentId, 'FILE_DELETED', 'FILE', fileRecord.fileId, {});

  return successResponse_({ deleted: true });
}

function listAttemptFiles_(attemptId) {
  return findMany_(CP.SHEETS.FILES, {
    attemptId: attemptId,
    status: CP.STATUS.ACTIVE
  }).map(publicFile_);
}

function ensureRootFolder_() {
  var configuredId = stringValue_(getSetting_('DRIVE_ROOT_FOLDER_ID', ''));

  if (configuredId) {
    try {
      return DriveApp.getFolderById(configuredId);
    } catch (error) {
      console.warn('Pasta configurada não encontrada; será criada outra.');
    }
  }

  var folderName = CP.DEFAULTS.DRIVE_ROOT_FOLDER_NAME;
  var iterator = DriveApp.getFoldersByName(folderName);

  if (iterator.hasNext()) {
    return iterator.next();
  }

  return DriveApp.createFolder(folderName);
}

function getAttemptFolder_(attempt) {
  var root = ensureRootFolder_();
  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: attempt.studentId
  });
  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: attempt.lessonId
  });
  var course = lesson
    ? findOne_(CP.SHEETS.COURSES, { courseId: lesson.courseId })
    : null;

  var courseFolder = getOrCreateChildFolder_(
    root,
    sanitizeFolderName_(
      (course ? course.courseCode : 'COURSE') + ' — ' +
      (course ? course.title : 'Curso')
    )
  );

  var studentFolder = getOrCreateChildFolder_(
    courseFolder,
    sanitizeFolderName_(
      attempt.studentId + ' — ' + (student ? student.fullName : 'Estudante')
    )
  );

  var lessonFolder = getOrCreateChildFolder_(
    studentFolder,
    sanitizeFolderName_(
      (lesson ? lesson.lessonNumber : '') + ' — ' +
      (lesson ? lesson.title : attempt.lessonId)
    )
  );

  return getOrCreateChildFolder_(
    lessonFolder,
    sanitizeFolderName_(
      'Tentativa ' + attempt.attemptNumber + ' — ' + attempt.attemptId
    )
  );
}

function saveStudentProfilePhoto_(payload) {
  requireFields_(payload, [
    'profilePhotoFileName',
    'profilePhotoMimeType',
    'profilePhotoBase64'
  ]);

  var mimeType = stringValue_(payload.profilePhotoMimeType).toLowerCase();
  var allowedImageTypes = ['image/jpeg', 'image/png', 'image/webp'];
  if (allowedImageTypes.indexOf(mimeType) === -1) {
    throw apiError_('PROFILE_PHOTO_TYPE_NOT_ALLOWED', 'A fotografia deve ser JPG, PNG ou WebP.');
  }

  var cleanBase64 = stripDataUrl_(payload.profilePhotoBase64);
  var estimatedBytes = Math.floor(cleanBase64.length * 3 / 4);
  var maxBytes = 2 * 1024 * 1024;
  if (estimatedBytes > maxBytes) {
    throw apiError_('PROFILE_PHOTO_TOO_LARGE', 'A fotografia deve ter no mÃ¡ximo 2 MB.');
  }

  var bytes;
  try {
    bytes = Utilities.base64Decode(cleanBase64);
  } catch (error) {
    throw apiError_('INVALID_PROFILE_PHOTO', 'A fotografia nÃ£o estÃ¡ em Base64 vÃ¡lido.');
  }

  if (bytes.length > maxBytes) {
    throw apiError_('PROFILE_PHOTO_TOO_LARGE', 'A fotografia deve ter no mÃ¡ximo 2 MB.');
  }

  var root = ensureRootFolder_();
  var profileFolder = getOrCreateChildFolder_(root, 'Profile Photos');
  var studentFolder = getOrCreateChildFolder_(
    profileFolder,
    sanitizeFolderName_(payload.studentId + ' â€” ' + payload._student.fullName)
  );
  var extension = mimeType === 'image/png' ? 'png' : (mimeType === 'image/webp' ? 'webp' : 'jpg');
  var fileName = sanitizeFileName_(
    payload.studentId + '-profile-' + Utilities.formatDate(new Date(), 'UTC', 'yyyyMMdd-HHmmss') + '.' + extension
  );
  var blob = Utilities.newBlob(bytes, mimeType, fileName);
  var driveFile = studentFolder.createFile(blob);

  try {
    driveFile.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
  } catch (error) {
    console.warn('NÃ£o foi possÃ­vel tornar a fotografia pÃºblica: ' + error.message);
  }

  return 'https://drive.google.com/thumbnail?id=' + driveFile.getId() + '&sz=w512';
}

function getOrCreateChildFolder_(parent, name) {
  var iterator = parent.getFoldersByName(name);
  if (iterator.hasNext()) {
    return iterator.next();
  }
  return parent.createFolder(name);
}

/** ===== 10_AdminService.gs ===== */

function adminListPendingSubmissions_(payload) {
  var attempts = readAll_(CP.SHEETS.ATTEMPTS)
    .filter(function(attempt) {
      return stringValue_(attempt.status) === CP.STATUS.UNDER_REVIEW;
    })
    .sort(function(a, b) {
      return new Date(a.submittedAt).getTime() - new Date(b.submittedAt).getTime();
    });

  var result = attempts.map(function(attempt) {
    var student = findOne_(CP.SHEETS.STUDENTS, {
      studentId: attempt.studentId
    });
    var lesson = findOne_(CP.SHEETS.LESSONS, {
      lessonId: attempt.lessonId
    });

    return {
      attempt: publicAttempt_(attempt),
      student: publicStudent_(student),
      lesson: publicLesson_(lesson),
      fileCount: listAttemptFiles_(attempt.attemptId).length
    };
  });

  return successResponse_({ submissions: result });
}

function adminListSubmissions_(payload) {
  var statusFilter = stringValue_(payload.status || 'ALL').toUpperCase();
  var reviewableStatuses = [
    CP.STATUS.UNDER_REVIEW,
    CP.STATUS.APPROVED,
    CP.STATUS.CORRECTION_REQUIRED,
    CP.STATUS.FAILED,
    CP.STATUS.TIME_EXCEEDED
  ];

  var attempts = readAll_(CP.SHEETS.ATTEMPTS)
    .filter(function(attempt) {
      var status = stringValue_(attempt.status);
      if (reviewableStatuses.indexOf(status) === -1) return false;
      if (statusFilter === 'ALL') return true;
      if (statusFilter === 'REVIEWED') {
        return [CP.STATUS.APPROVED, CP.STATUS.CORRECTION_REQUIRED, CP.STATUS.FAILED].indexOf(status) !== -1;
      }
      return status === statusFilter;
    })
    .sort(function(a, b) {
      var aDate = new Date(a.reviewedAt || a.submittedAt || a.updatedAt || a.createdAt).getTime();
      var bDate = new Date(b.reviewedAt || b.submittedAt || b.updatedAt || b.createdAt).getTime();
      return bDate - aDate;
    })
    .slice(0, Number(payload.limit || 250));

  return successResponse_({
    submissions: attempts.map(adminSubmissionListItem_)
  });
}

function adminSubmissionListItem_(attempt) {
  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: attempt.studentId
  });
  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: attempt.lessonId
  });
  var reviews = findMany_(CP.SHEETS.REVIEWS, {
    attemptId: attempt.attemptId
  }).sort(function(a, b) {
    return new Date(b.reviewedAt).getTime() - new Date(a.reviewedAt).getTime();
  });

  return {
    attempt: publicAttempt_(attempt),
    student: publicStudent_(student),
    lesson: publicLesson_(lesson),
    latestReview: reviews.length ? publicReview_(reviews[0]) : null,
    reviewCount: reviews.length,
    fileCount: listAttemptFiles_(attempt.attemptId).length
  };
}

function adminGetSubmission_(payload) {
  requireFields_(payload, ['attemptId']);

  var attempt = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: payload.attemptId
  });

  if (!attempt) {
    throw apiError_('ATTEMPT_NOT_FOUND', 'A tentativa não foi encontrada.');
  }

  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: attempt.studentId
  });
  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: attempt.lessonId
  });
  var answers = findMany_(CP.SHEETS.ANSWERS, {
    attemptId: attempt.attemptId
  }).map(function(answer) {
    var question = findOne_(CP.SHEETS.QUESTIONS, {
      questionId: answer.questionId
    });

    return {
      answer: publicAnswerForAdmin_(answer),
      question: question ? {
        questionId: question.questionId,
        questionOrder: Number(question.questionOrder),
        questionType: question.questionType,
        prompt: question.prompt,
        points: Number(question.points || 0),
        explanation: question.explanation
      } : null
    };
  });

  var reviews = findMany_(CP.SHEETS.REVIEWS, {
    attemptId: attempt.attemptId
  }).map(publicReview_);

  return successResponse_({
    attempt: publicAttempt_(attempt),
    student: publicStudent_(student),
    lesson: publicLesson_(lesson),
    answers: answers,
    files: listAttemptFiles_(attempt.attemptId),
    reviews: reviews
  });
}

function adminReviewSubmission_(payload) {
  requireFields_(payload, ['attemptId', 'decision', 'score']);

  var decision = stringValue_(payload.decision).toUpperCase();
  if (CP.REVIEW_DECISIONS.indexOf(decision) === -1) {
    throw apiError_('INVALID_DECISION', 'Decisão de avaliação inválida.');
  }

  var score = Number(payload.score);
  if (isNaN(score) || score < 0 || score > 100) {
    throw apiError_('INVALID_SCORE', 'A classificação deve estar entre 0 e 100.');
  }

  var attempt = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: payload.attemptId
  });

  if (!attempt) {
    throw apiError_('ATTEMPT_NOT_FOUND', 'A tentativa não foi encontrada.');
  }

  if (
    [
      CP.STATUS.UNDER_REVIEW,
      CP.STATUS.CORRECTION_REQUIRED,
      CP.STATUS.APPROVED,
      CP.STATUS.FAILED,
      CP.STATUS.TIME_EXCEEDED
    ]
      .indexOf(stringValue_(attempt.status)) === -1
  ) {
    throw apiError_('ATTEMPT_NOT_REVIEWABLE', 'A tentativa não está disponível para avaliação.');
  }

  var lesson = findOne_(CP.SHEETS.LESSONS, {
    lessonId: attempt.lessonId
  });

  var passingScore = Number(
    lesson && lesson.passingScore !== ''
      ? lesson.passingScore
      : getSetting_('PASSING_SCORE', CP.DEFAULTS.PASSING_SCORE)
  );

  var approvedDecision =
    decision === 'APPROVED' ||
    decision === 'APPROVED_WITH_NOTES';

  if (approvedDecision && score < passingScore) {
    throw apiError_(
      'SCORE_BELOW_PASSING',
      'Uma atividade aprovada deve possuir classificação mínima de ' + passingScore + '%.'
    );
  }

  var now = new Date();
  var comments = truncate_(payload.comments || '', 20000);
  var attemptStatus;
  var progressStatus;
  var retryAuthorized = false;
  var unlockNext = false;

  if (approvedDecision) {
    attemptStatus = CP.STATUS.APPROVED;
    progressStatus = CP.STATUS.APPROVED;
    unlockNext = true;
  } else if (decision === 'CORRECTION_REQUIRED') {
    attemptStatus = CP.STATUS.CORRECTION_REQUIRED;
    progressStatus = CP.STATUS.CORRECTION_REQUIRED;
    retryAuthorized = true;
  } else {
    attemptStatus = CP.STATUS.FAILED;
    progressStatus = CP.STATUS.FAILED;
    retryAuthorized = false;
  }

  attempt = updateRecordByKey_(
    CP.SHEETS.ATTEMPTS,
    'attemptId',
    attempt.attemptId,
    {
      status: attemptStatus,
      score: score,
      reviewerId: payload.adminId,
      reviewedAt: now,
      reviewComments: comments,
      retryAuthorized: retryAuthorized,
      updatedAt: now
    }
  );

  var progressPatch = {
    status: progressStatus,
    score: score,
    updatedAt: now
  };

  if (approvedDecision) {
    progressPatch.approvedAt = now;
  } else {
    progressPatch.approvedAt = '';
  }

  updateRecordByKey_(
    CP.SHEETS.LESSON_PROGRESS,
    'progressId',
    attempt.progressId,
    progressPatch
  );

  var review = appendRecord_(CP.SHEETS.REVIEWS, {
    reviewId: newId_('REV'),
    attemptId: attempt.attemptId,
    reviewerId: payload.adminId,
    decision: decision,
    score: score,
    comments: comments,
    correctionDeadline: payload.correctionDeadline
      ? new Date(payload.correctionDeadline)
      : '',
    unlockNextLesson: unlockNext,
    reviewedAt: now
  });

  var nextProgress = null;
  if (unlockNext) {
    nextProgress = unlockNextLesson_(attempt.studentId, attempt.lessonId);
  }

  var courseId = lesson ? lesson.courseId : '';
  var enrollment = courseId
    ? recalculateEnrollment_(attempt.studentId, courseId)
    : null;

  logAudit_('ADMIN', payload.adminId, 'SUBMISSION_REVIEWED', 'ATTEMPT', attempt.attemptId, {
    decision: decision,
    score: score
  });

  return successResponse_({
    attempt: publicAttempt_(attempt),
    review: publicReview_(review),
    nextLessonProgress: nextProgress ? publicProgress_(nextProgress) : null,
    enrollment: enrollment ? publicEnrollment_(enrollment) : null
  });
}

function adminAuthorizeRetry_(payload) {
  requireFields_(payload, ['attemptId']);

  var attempt = findOne_(CP.SHEETS.ATTEMPTS, {
    attemptId: payload.attemptId
  });

  if (!attempt) {
    throw apiError_('ATTEMPT_NOT_FOUND', 'A tentativa não foi encontrada.');
  }

  if (
    [CP.STATUS.FAILED, CP.STATUS.TIME_EXCEEDED, CP.STATUS.CORRECTION_REQUIRED]
      .indexOf(stringValue_(attempt.status)) === -1
  ) {
    throw apiError_('RETRY_NOT_APPLICABLE', 'Esta tentativa não precisa de nova autorização.');
  }

  updateRecordByKey_(
    CP.SHEETS.ATTEMPTS,
    'attemptId',
    attempt.attemptId,
    {
      retryAuthorized: true,
      updatedAt: new Date()
    }
  );

  updateRecordByKey_(
    CP.SHEETS.LESSON_PROGRESS,
    'progressId',
    attempt.progressId,
    {
      status: CP.STATUS.AVAILABLE,
      updatedAt: new Date()
    }
  );

  logAudit_('ADMIN', payload.adminId, 'RETRY_AUTHORIZED', 'ATTEMPT', attempt.attemptId, {});

  return successResponse_({ authorized: true });
}

function adminCreateStudent_(payload) {
  return successResponse_(
    createStudentRecord_(payload, {
      actorType: 'ADMIN',
      actorId: payload.adminId
    })
  );
}

function createStudentRecord_(payload, actor) {
  requireFields_(payload, ['fullName', 'email']);

  var email = normalizeEmail_(payload.email);
  if (!isValidEmail_(email)) {
    throw apiError_('INVALID_EMAIL', 'O email informado não é válido.');
  }

  if (findOne_(CP.SHEETS.STUDENTS, { email: email })) {
    throw apiError_('EMAIL_ALREADY_EXISTS', 'Já existe um estudante com este email.');
  }

  var plainAccessCode = stringValue_(payload.accessCode) || generateAccessCode_(12);
  var now = new Date();

  var student = appendRecord_(CP.SHEETS.STUDENTS, {
    studentId: newId_('STU'),
    publicStudentId: generatePublicStudentId_(),
    fullName: truncate_(payload.fullName, 200),
    email: email,
    accessCode: hashSecret_(plainAccessCode),
    status: CP.STATUS.ACTIVE,
    country: truncate_(payload.country || '', 100),
    organization: truncate_(payload.organization || '', 250),
    phone: truncate_(payload.phone || '', 80),
    jobTitle: truncate_(payload.jobTitle || '', 180),
    interests: truncate_(payload.interests || '', 1000),
    createdAt: now,
    updatedAt: now,
    lastLoginAt: ''
  });

  var enrollment = ensureEnrollmentAndProgress_(
    student.studentId,
    payload.courseId,
    payload.groupId
  );

  logAudit_(
    actor.actorType,
    actor.actorId,
    'STUDENT_CREATED',
    'STUDENT',
    student.studentId,
    { email: email }
  );

  return {
    student: publicStudent_(student),
    accessCode: plainAccessCode,
    enrollment: publicEnrollment_(enrollment),
    warning: 'O código é apresentado apenas nesta resposta. Guarde-o antes de fechar.'
  };
}

function adminListStudents_(payload) {
  var students = readAll_(CP.SHEETS.STUDENTS)
    .sort(function(a, b) {
      return stringValue_(a.fullName).localeCompare(stringValue_(b.fullName));
    })
    .map(function(student) {
      student = ensureStudentPublicId_(student);
      var enrollments = findMany_(CP.SHEETS.ENROLLMENTS, {
        studentId: student.studentId
      }).map(publicEnrollment_);

      var memberships = findMany_(CP.SHEETS.GROUP_MEMBERS, {
        studentId: student.studentId,
        status: CP.STATUS.ACTIVE
      }).map(publicGroupMember_);

      return {
        student: publicStudent_(student),
        enrollments: enrollments,
        memberships: memberships
      };
    });

  return successResponse_({ students: students });
}

function adminSetStudentStatus_(payload) {
  requireFields_(payload, ['studentId', 'status']);

  var allowed = [CP.STATUS.ACTIVE, CP.STATUS.INACTIVE, CP.STATUS.BLOCKED];
  var status = stringValue_(payload.status).toUpperCase();

  if (allowed.indexOf(status) === -1) {
    throw apiError_('INVALID_STATUS', 'Estado de estudante inválido.');
  }

  var student = updateRecordByKey_(
    CP.SHEETS.STUDENTS,
    'studentId',
    payload.studentId,
    {
      status: status,
      updatedAt: new Date()
    }
  );

  if (status !== CP.STATUS.ACTIVE) {
    revokeSessionsForSubject_(student.studentId);
  }

  logAudit_('ADMIN', payload.adminId, 'STUDENT_STATUS_CHANGED', 'STUDENT', student.studentId, {
    status: status
  });

  return successResponse_({ student: publicStudent_(student) });
}

function adminResetStudentAccessCode_(payload) {
  requireFields_(payload, ['studentId']);

  var plainCode = stringValue_(payload.accessCode) || generateAccessCode_(12);

  var student = updateRecordByKey_(
    CP.SHEETS.STUDENTS,
    'studentId',
    payload.studentId,
    {
      accessCode: hashSecret_(plainCode),
      updatedAt: new Date()
    }
  );

  revokeSessionsForSubject_(student.studentId);

  logAudit_('ADMIN', payload.adminId, 'STUDENT_ACCESS_RESET', 'STUDENT', student.studentId, {});

  return successResponse_({
    student: publicStudent_(student),
    accessCode: plainCode,
    warning: 'O novo código é apresentado apenas nesta resposta.'
  });
}

function adminSaveCourse_(payload) {
  requireFields_(payload, ['courseCode', 'title']);

  var now = new Date();
  var courseId = stringValue_(payload.courseId) || newId_('COURSE');
  var existing = findOne_(CP.SHEETS.COURSES, { courseId: courseId });

  var record = {
    courseId: courseId,
    courseCode: truncate_(payload.courseCode, 80),
    title: truncate_(payload.title, 250),
    description: truncate_(payload.description || '', 20000),
    totalHours: Number(payload.totalHours || 0),
    passingScore: Number(payload.passingScore || CP.DEFAULTS.PASSING_SCORE),
    status: stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase(),
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.COURSES, 'courseId', courseId, record)
    : appendRecord_(CP.SHEETS.COURSES, record);

  logAudit_('ADMIN', payload.adminId, 'COURSE_SAVED', 'COURSE', courseId, {});
  return successResponse_({ course: publicCourse_(record) });
}

function adminListCourses_(payload) {
  var courses = readAll_(CP.SHEETS.COURSES)
    .sort(function(a, b) {
      return stringValue_(a.title).localeCompare(stringValue_(b.title));
    })
    .map(function(course) {
      var lessons = findMany_(CP.SHEETS.LESSONS, { courseId: course.courseId });
      var groups = findMany_(CP.SHEETS.GROUPS, { courseId: course.courseId });
      var enrollments = findMany_(CP.SHEETS.ENROLLMENTS, { courseId: course.courseId });

      return {
        course: publicCourse_(course),
        lessonCount: lessons.length,
        groupCount: groups.length,
        enrollmentCount: enrollments.length
      };
    });

  return successResponse_({ courses: courses });
}

function adminSaveLesson_(payload) {
  requireFields_(payload, ['courseId', 'lessonNumber', 'title']);

  var now = new Date();
  var lessonId = stringValue_(payload.lessonId) || newId_('LESSON');
  var existing = findOne_(CP.SHEETS.LESSONS, { lessonId: lessonId });

  var record = {
    lessonId: lessonId,
    courseId: payload.courseId,
    lessonNumber: Number(payload.lessonNumber),
    title: truncate_(payload.title, 300),
    slug: slugify_(payload.slug || payload.title),
    summary: truncate_(payload.summary || '', 20000),
    theoryMinutes: Number(payload.theoryMinutes || 0),
    exerciseMinutes: Number(payload.exerciseMinutes || 0),
    individualMinutes: Number(payload.individualMinutes || 0),
    passingScore: Number(payload.passingScore || CP.DEFAULTS.PASSING_SCORE),
    prerequisiteLessonId: stringValue_(payload.prerequisiteLessonId),
    status: stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase(),
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.LESSONS, 'lessonId', lessonId, record)
    : appendRecord_(CP.SHEETS.LESSONS, record);

  logAudit_('ADMIN', payload.adminId, 'LESSON_SAVED', 'LESSON', lessonId, {});
  return successResponse_({ lesson: publicLesson_(record) });
}

function adminSaveLessonContent_(payload) {
  requireFields_(payload, ['lessonId', 'sectionOrder', 'sectionType', 'title']);

  var now = new Date();
  var contentId = stringValue_(payload.contentId) || newId_('CNT');
  var existing = findOne_(CP.SHEETS.LESSON_CONTENT, { contentId: contentId });

  var record = {
    contentId: contentId,
    lessonId: payload.lessonId,
    sectionOrder: Number(payload.sectionOrder),
    sectionType: stringValue_(payload.sectionType).toUpperCase(),
    title: truncate_(payload.title, 300),
    bodyHtml: truncate_(payload.bodyHtml || '', 100000),
    estimatedMinutes: Number(payload.estimatedMinutes || 0),
    isRequired: payload.isRequired === undefined ? true : toBoolean_(payload.isRequired),
    status: stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase(),
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.LESSON_CONTENT, 'contentId', contentId, record)
    : appendRecord_(CP.SHEETS.LESSON_CONTENT, record);

  logAudit_('ADMIN', payload.adminId, 'CONTENT_SAVED', 'CONTENT', contentId, {});
  return successResponse_({ content: publicContent_(record) });
}

function adminSaveQuestion_(payload) {
  requireFields_(payload, ['lessonId', 'questionOrder', 'questionType', 'prompt']);

  var now = new Date();
  var questionId = stringValue_(payload.questionId) || newId_('QUE');
  var existing = findOne_(CP.SHEETS.QUESTIONS, { questionId: questionId });

  var record = {
    questionId: questionId,
    lessonId: payload.lessonId,
    questionOrder: Number(payload.questionOrder),
    questionType: stringValue_(payload.questionType).toUpperCase(),
    prompt: truncate_(payload.prompt, 50000),
    points: Number(payload.points || 0),
    correctAnswer: truncate_(payload.correctAnswer || '', 10000),
    explanation: truncate_(payload.explanation || '', 30000),
    isRequired: payload.isRequired === undefined ? true : toBoolean_(payload.isRequired),
    status: stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase(),
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.QUESTIONS, 'questionId', questionId, record)
    : appendRecord_(CP.SHEETS.QUESTIONS, record);

  logAudit_('ADMIN', payload.adminId, 'QUESTION_SAVED', 'QUESTION', questionId, {});
  return successResponse_({ question: record });
}

function adminSaveQuestionOption_(payload) {
  requireFields_(payload, [
    'questionId',
    'optionOrder',
    'optionLabel',
    'optionText'
  ]);

  var optionId = stringValue_(payload.optionId) || newId_('OPT');
  var existing = findOne_(CP.SHEETS.QUESTION_OPTIONS, { optionId: optionId });

  var record = {
    optionId: optionId,
    questionId: payload.questionId,
    optionOrder: Number(payload.optionOrder),
    optionLabel: truncate_(payload.optionLabel, 20),
    optionText: truncate_(payload.optionText, 20000),
    isCorrect: toBoolean_(payload.isCorrect),
    createdAt: existing ? existing.createdAt : new Date()
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.QUESTION_OPTIONS, 'optionId', optionId, record)
    : appendRecord_(CP.SHEETS.QUESTION_OPTIONS, record);

  logAudit_('ADMIN', payload.adminId, 'QUESTION_OPTION_SAVED', 'OPTION', optionId, {});
  return successResponse_({ option: record });
}

function adminGetCourseStructure_(payload) {
  var courseId = stringValue_(payload.courseId) ||
    stringValue_(getSetting_('DEFAULT_COURSE_ID', CP.DEFAULTS.DEFAULT_COURSE_ID));

  var course = findOne_(CP.SHEETS.COURSES, { courseId: courseId });
  if (!course) throw apiError_('COURSE_NOT_FOUND', 'Curso não encontrado.');

  var lessons = findMany_(CP.SHEETS.LESSONS, { courseId: courseId })
    .sort(function(a, b) {
      return Number(a.lessonNumber) - Number(b.lessonNumber);
    })
    .map(function(lesson) {
      var content = findMany_(CP.SHEETS.LESSON_CONTENT, {
        lessonId: lesson.lessonId
      }).sort(function(a, b) {
        return Number(a.sectionOrder) - Number(b.sectionOrder);
      });

      var questions = findMany_(CP.SHEETS.QUESTIONS, {
        lessonId: lesson.lessonId
      }).sort(function(a, b) {
        return Number(a.questionOrder) - Number(b.questionOrder);
      }).map(function(question) {
        return {
          question: question,
          options: findMany_(CP.SHEETS.QUESTION_OPTIONS, {
            questionId: question.questionId
          }).sort(function(a, b) {
            return Number(a.optionOrder) - Number(b.optionOrder);
          })
        };
      });

      return {
        lesson: lesson,
        content: content,
        questions: questions
      };
    });

  return successResponse_({
    course: course,
    lessons: lessons
  });
}

function adminListGroups_(payload) {
  var courseId = stringValue_(payload.courseId);
  var groups = readAll_(CP.SHEETS.GROUPS)
    .filter(function(group) {
      return !courseId || stringValue_(group.courseId) === courseId;
    })
    .sort(function(a, b) {
      return stringValue_(a.name).localeCompare(stringValue_(b.name));
    })
    .map(function(group) {
      var members = findMany_(CP.SHEETS.GROUP_MEMBERS, {
        groupId: group.groupId,
        status: CP.STATUS.ACTIVE
      });

      return {
        group: publicGroup_(group),
        memberCount: members.length
      };
    });

  return successResponse_({ groups: groups });
}

function adminSaveGroup_(payload) {
  requireFields_(payload, ['name', 'courseId']);

  var now = new Date();
  var groupId = stringValue_(payload.groupId) || newId_('GRP');
  var existing = findOne_(CP.SHEETS.GROUPS, { groupId: groupId });
  var record = {
    groupId: groupId,
    groupCode: truncate_(payload.groupCode || generateGroupCode_(payload.name), 60),
    name: truncate_(payload.name, 200),
    courseId: payload.courseId,
    startDate: payload.startDate ? new Date(payload.startDate) : '',
    endDate: payload.endDate ? new Date(payload.endDate) : '',
    status: stringValue_(payload.status || CP.STATUS.ACTIVE).toUpperCase(),
    createdAt: existing ? existing.createdAt : now,
    updatedAt: now
  };

  record = existing
    ? updateRecordByKey_(CP.SHEETS.GROUPS, 'groupId', groupId, record)
    : appendRecord_(CP.SHEETS.GROUPS, record);

  if (payload.studentIds instanceof Array) {
    syncGroupStudents_(record, payload.studentIds);
  }

  logAudit_('ADMIN', payload.adminId, 'GROUP_SAVED', 'GROUP', groupId, {
    courseId: record.courseId
  });

  return successResponse_({ group: publicGroup_(record) });
}

function adminAssignStudentsToGroup_(payload) {
  requireFields_(payload, ['groupId']);
  var group = findOne_(CP.SHEETS.GROUPS, { groupId: payload.groupId });
  if (!group) throw apiError_('GROUP_NOT_FOUND', 'Grupo nao encontrado.');

  var result = syncGroupStudents_(group, payload.studentIds || []);
  logAudit_('ADMIN', payload.adminId, 'GROUP_STUDENTS_ASSIGNED', 'GROUP', group.groupId, result);
  return successResponse_(result);
}

function syncGroupStudents_(group, studentIds) {
  var normalized = [];
  (studentIds || []).forEach(function(studentId) {
    studentId = stringValue_(studentId);
    if (studentId && normalized.indexOf(studentId) === -1) normalized.push(studentId);
  });

  var existing = findMany_(CP.SHEETS.GROUP_MEMBERS, { groupId: group.groupId });
  var now = new Date();
  var active = 0;
  var removed = 0;

  existing.forEach(function(member) {
    var shouldBeActive = normalized.indexOf(stringValue_(member.studentId)) !== -1;
    if (!shouldBeActive && stringValue_(member.status) === CP.STATUS.ACTIVE) {
      updateRecordByKey_(CP.SHEETS.GROUP_MEMBERS, 'groupMemberId', member.groupMemberId, {
        status: CP.STATUS.INACTIVE,
        updatedAt: now
      });
      removed++;
    }
  });

  normalized.forEach(function(studentId) {
    var student = findOne_(CP.SHEETS.STUDENTS, { studentId: studentId });
    if (!student) return;

    var member = findOne_(CP.SHEETS.GROUP_MEMBERS, {
      groupId: group.groupId,
      studentId: studentId
    });

    if (member) {
      updateRecordByKey_(CP.SHEETS.GROUP_MEMBERS, 'groupMemberId', member.groupMemberId, {
        status: CP.STATUS.ACTIVE,
        updatedAt: now
      });
    } else {
      appendRecord_(CP.SHEETS.GROUP_MEMBERS, {
        groupMemberId: newId_('GM'),
        groupId: group.groupId,
        studentId: studentId,
        status: CP.STATUS.ACTIVE,
        joinedAt: now,
        updatedAt: now
      });
    }

    ensureEnrollmentAndProgress_(studentId, group.courseId, group.groupId);
    active++;
  });

  return {
    success: true,
    activeMembers: active,
    removedMembers: removed
  };
}

function adminSetLessonAccess_(payload) {
  requireFields_(payload, ['courseId', 'status']);

  var status = stringValue_(payload.status).toUpperCase();
  if ([CP.STATUS.AVAILABLE, CP.STATUS.LOCKED].indexOf(status) === -1) {
    throw apiError_('INVALID_ACCESS_STATUS', 'Use AVAILABLE para disponibilizar ou LOCKED para restringir.');
  }

  var lessonIds = payload.lessonIds instanceof Array
    ? payload.lessonIds.map(stringValue_).filter(Boolean)
    : [];
  if (!lessonIds.length) {
    lessonIds = findMany_(CP.SHEETS.LESSONS, { courseId: payload.courseId })
      .map(function(lesson) { return lesson.lessonId; });
  }

  var studentIds = resolveTargetStudentIds_(payload);
  var changed = 0;
  var now = new Date();

  studentIds.forEach(function(studentId) {
    var enrollment = ensureEnrollmentAndProgress_(studentId, payload.courseId);
    lessonIds.forEach(function(lessonId) {
      var progress = findOne_(CP.SHEETS.LESSON_PROGRESS, {
        enrollmentId: enrollment.enrollmentId,
        studentId: studentId,
        lessonId: lessonId
      });
      if (!progress) return;
      updateRecordByKey_(CP.SHEETS.LESSON_PROGRESS, 'progressId', progress.progressId, {
        status: status,
        unlockedAt: status === CP.STATUS.AVAILABLE && !progress.unlockedAt ? now : progress.unlockedAt,
        updatedAt: now
      });
      if (status === CP.STATUS.AVAILABLE) {
        authorizeLatestRetryForStudentLesson_(studentId, lessonId, now);
      }
      changed++;
    });
  });

  logAudit_('ADMIN', payload.adminId, 'LESSON_ACCESS_CHANGED', 'LESSON_PROGRESS', '', {
    courseId: payload.courseId,
    status: status,
    lessonIds: lessonIds,
    studentCount: studentIds.length,
    changed: changed
  });

  return successResponse_({
    changed: changed,
    studentCount: studentIds.length,
    lessonCount: lessonIds.length
  });
}

function authorizeLatestRetryForStudentLesson_(studentId, lessonId, now) {
  var attempts = findMany_(CP.SHEETS.ATTEMPTS, {
    studentId: studentId,
    lessonId: lessonId
  }).sort(function(a, b) {
    return Number(b.attemptNumber) - Number(a.attemptNumber);
  });

  if (!attempts.length) return null;

  var latest = attempts[0];
  if (
    [CP.STATUS.FAILED, CP.STATUS.TIME_EXCEEDED, CP.STATUS.CORRECTION_REQUIRED]
      .indexOf(stringValue_(latest.status)) === -1
  ) {
    return null;
  }

  return updateRecordByKey_(CP.SHEETS.ATTEMPTS, 'attemptId', latest.attemptId, {
    retryAuthorized: true,
    updatedAt: now || new Date()
  });
}

function resolveTargetStudentIds_(payload) {
  var ids = [];

  if (payload.studentIds instanceof Array) {
    payload.studentIds.forEach(function(studentId) {
      studentId = stringValue_(studentId);
      if (studentId && ids.indexOf(studentId) === -1) ids.push(studentId);
    });
  }

  if (payload.groupIds instanceof Array) {
    payload.groupIds.forEach(function(groupId) {
      findMany_(CP.SHEETS.GROUP_MEMBERS, {
        groupId: groupId,
        status: CP.STATUS.ACTIVE
      }).forEach(function(member) {
        var studentId = stringValue_(member.studentId);
        if (studentId && ids.indexOf(studentId) === -1) ids.push(studentId);
      });
    });
  }

  if (!ids.length) {
    throw apiError_('TARGET_STUDENTS_REQUIRED', 'Selecione pelo menos um estudante ou grupo.');
  }

  return ids;
}

function generateGroupCode_(name) {
  var base = slugify_(name).replace(/-/g, '').toUpperCase().slice(0, 8) || 'GRUPO';
  return base + '-' + ('000' + Math.floor(Math.random() * 1000)).slice(-3);
}

/** ===== 11_CertificateService.gs ===== */

function ensureCertificate_(studentId, courseId, finalScore) {
  var existing = findOne_(CP.SHEETS.CERTIFICATES, {
    studentId: studentId,
    courseId: courseId,
    status: CP.STATUS.ISSUED
  });

  if (existing) return existing;

  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    existing = findOne_(CP.SHEETS.CERTIFICATES, {
      studentId: studentId,
      courseId: courseId,
      status: CP.STATUS.ISSUED
    });

    if (existing) return existing;

    var prefix = stringValue_(
      getSetting_('CERTIFICATE_PREFIX', CP.DEFAULTS.CERTIFICATE_PREFIX)
    );
    var year = new Date().getFullYear();
    var sequence = readAll_(CP.SHEETS.CERTIFICATES).length + 1;
    var number = prefix + '-' + year + '-' + ('000000' + sequence).slice(-6);

    var certificate = appendRecordUnlocked_(CP.SHEETS.CERTIFICATES, {
      certificateId: newId_('CERT'),
      studentId: studentId,
      courseId: courseId,
      certificateNumber: number,
      verificationCode: Utilities.getUuid().replace(/-/g, '').toUpperCase(),
      issueDate: new Date(),
      finalScore: finalScore,
      driveFileId: '',
      driveUrl: '',
      status: CP.STATUS.ISSUED
    });

    logAudit_('SYSTEM', 'SYSTEM', 'CERTIFICATE_CREATED', 'CERTIFICATE', certificate.certificateId, {
      certificateNumber: number
    });

    return certificate;
  } finally {
    lock.releaseLock();
  }
}

function getStudentCertificate_(payload) {
  var courseId = stringValue_(payload.courseId) ||
    stringValue_(getSetting_('DEFAULT_COURSE_ID', CP.DEFAULTS.DEFAULT_COURSE_ID));

  var certificate = findOne_(CP.SHEETS.CERTIFICATES, {
    studentId: payload.studentId,
    courseId: courseId,
    status: CP.STATUS.ISSUED
  });

  return successResponse_({
    certificate: certificate ? publicCertificate_(certificate) : null
  });
}

function verifyCertificatePublic_(code) {
  code = stringValue_(code).trim();

  if (!code) {
    throw apiError_('VERIFICATION_CODE_REQUIRED', 'Informe o código de verificação.');
  }

  var certificate = findOne_(CP.SHEETS.CERTIFICATES, {
    verificationCode: code
  });

  if (!certificate) {
    certificate = findOne_(CP.SHEETS.CERTIFICATES, {
      certificateNumber: code
    });
  }

  if (!certificate) {
    return successResponse_({
      valid: false,
      message: 'Certificado não encontrado.'
    });
  }

  var student = findOne_(CP.SHEETS.STUDENTS, {
    studentId: certificate.studentId
  });
  var course = findOne_(CP.SHEETS.COURSES, {
    courseId: certificate.courseId
  });

  return successResponse_({
    valid: stringValue_(certificate.status) === CP.STATUS.ISSUED,
    certificate: {
      certificateNumber: certificate.certificateNumber,
      verificationCode: certificate.verificationCode,
      studentName: student ? student.fullName : '',
      courseTitle: course ? course.title : '',
      issueDate: certificate.issueDate,
      finalScore: Number(certificate.finalScore || 0),
      status: certificate.status
    }
  });
}

/** ===== 12_AuditService.gs ===== */

function logAudit_(actorType, actorId, action, entityType, entityId, details) {
  try {
    appendRecord_(CP.SHEETS.AUDIT_LOG, {
      logId: newId_('LOG'),
      actorType: actorType,
      actorId: actorId,
      action: action,
      entityType: entityType,
      entityId: entityId,
      detailsJson: truncate_(JSON.stringify(serializeForJson_(details || {})), 45000),
      createdAt: new Date()
    });
  } catch (error) {
    console.error('Falha ao escrever no AuditLog: ' + error.message);
  }
}

/** ===== 13_PublicMappers.gs ===== */

function publicStudent_(student) {
  if (!student) return null;
  return {
    studentId: student.studentId,
    publicStudentId: student.publicStudentId || student.studentId,
    fullName: student.fullName,
    email: student.email,
    status: student.status,
    country: student.country,
    organization: student.organization,
    phone: student.phone,
    jobTitle: student.jobTitle,
    interests: student.interests,
    profilePhotoUrl: student.profilePhotoUrl,
    createdAt: student.createdAt,
    lastLoginAt: student.lastLoginAt
  };
}

function publicGroup_(group) {
  if (!group) return null;
  return {
    groupId: group.groupId,
    groupCode: group.groupCode,
    name: group.name,
    courseId: group.courseId,
    startDate: group.startDate,
    endDate: group.endDate,
    status: group.status,
    createdAt: group.createdAt,
    updatedAt: group.updatedAt
  };
}

function publicGroupMember_(member) {
  if (!member) return null;
  return {
    groupMemberId: member.groupMemberId,
    groupId: member.groupId,
    studentId: member.studentId,
    status: member.status,
    joinedAt: member.joinedAt,
    updatedAt: member.updatedAt
  };
}

function publicAdmin_(admin) {
  if (!admin) return null;
  return {
    adminId: admin.adminId,
    fullName: admin.fullName,
    email: admin.email,
    role: admin.role,
    status: admin.status,
    createdAt: admin.createdAt,
    updatedAt: admin.updatedAt
  };
}

function publicCourse_(course) {
  if (!course) return null;
  return {
    courseId: course.courseId,
    courseCode: course.courseCode,
    title: course.title,
    description: course.description,
    totalHours: Number(course.totalHours || 0),
    passingScore: Number(course.passingScore || 0),
    status: course.status
  };
}

function publicLesson_(lesson) {
  if (!lesson) return null;
  return {
    lessonId: lesson.lessonId,
    courseId: lesson.courseId,
    lessonNumber: Number(lesson.lessonNumber || 0),
    title: lesson.title,
    slug: lesson.slug,
    summary: lesson.summary,
    theoryMinutes: Number(lesson.theoryMinutes || 0),
    exerciseMinutes: Number(lesson.exerciseMinutes || 0),
    individualMinutes: Number(lesson.individualMinutes || 0),
    passingScore: Number(lesson.passingScore || 0),
    prerequisiteLessonId: lesson.prerequisiteLessonId,
    status: lesson.status
  };
}

function publicContent_(content) {
  if (!content) return null;
  return {
    contentId: content.contentId,
    lessonId: content.lessonId,
    sectionOrder: Number(content.sectionOrder || 0),
    sectionType: content.sectionType,
    title: content.title,
    bodyHtml: content.bodyHtml,
    estimatedMinutes: Number(content.estimatedMinutes || 0),
    isRequired: toBoolean_(content.isRequired)
  };
}

function publicEnrollment_(enrollment) {
  if (!enrollment) return null;
  return {
    enrollmentId: enrollment.enrollmentId,
    studentId: enrollment.studentId,
    courseId: enrollment.courseId,
    groupId: enrollment.groupId,
    status: enrollment.status,
    enrolledAt: enrollment.enrolledAt,
    completedAt: enrollment.completedAt,
    progressPercent: Number(enrollment.progressPercent || 0),
    finalScore: enrollment.finalScore === '' ? null : Number(enrollment.finalScore),
    certificateId: enrollment.certificateId
  };
}

function publicProgress_(progress) {
  if (!progress) return null;
  return {
    progressId: progress.progressId,
    lessonId: progress.lessonId,
    status: progress.status,
    unlockedAt: progress.unlockedAt,
    startedAt: progress.startedAt,
    submittedAt: progress.submittedAt,
    approvedAt: progress.approvedAt,
    score: progress.score === '' ? null : Number(progress.score),
    attemptCount: Number(progress.attemptCount || 0)
  };
}

function publicAttempt_(attempt) {
  if (!attempt) return null;

  var deadline = attempt.deadlineAt
    ? new Date(attempt.deadlineAt).getTime()
    : 0;

  return {
    attemptId: attempt.attemptId,
    progressId: attempt.progressId,
    lessonId: attempt.lessonId,
    attemptNumber: Number(attempt.attemptNumber || 0),
    startedAt: attempt.startedAt,
    deadlineAt: attempt.deadlineAt,
    submittedAt: attempt.submittedAt,
    status: attempt.status,
    score: attempt.score === '' ? null : Number(attempt.score),
    reviewedAt: attempt.reviewedAt,
    reviewComments: attempt.reviewComments,
    retryAuthorized: toBoolean_(attempt.retryAuthorized),
    remainingSeconds: deadline
      ? Math.max(0, Math.floor((deadline - Date.now()) / 1000))
      : 0
  };
}

function publicFile_(file) {
  if (!file) return null;
  return {
    fileId: file.fileId,
    attemptId: file.attemptId,
    fileName: file.fileName,
    mimeType: file.mimeType,
    sizeBytes: Number(file.sizeBytes || 0),
    driveUrl: file.driveUrl,
    uploadedAt: file.uploadedAt,
    status: file.status
  };
}

function publicReview_(review) {
  if (!review) return null;
  return {
    reviewId: review.reviewId,
    attemptId: review.attemptId,
    reviewerId: review.reviewerId,
    decision: review.decision,
    score: Number(review.score || 0),
    comments: review.comments,
    correctionDeadline: review.correctionDeadline,
    unlockNextLesson: toBoolean_(review.unlockNextLesson),
    reviewedAt: review.reviewedAt
  };
}

function publicCertificate_(certificate) {
  if (!certificate) return null;
  return {
    certificateId: certificate.certificateId,
    certificateNumber: certificate.certificateNumber,
    verificationCode: certificate.verificationCode,
    issueDate: certificate.issueDate,
    finalScore: Number(certificate.finalScore || 0),
    driveUrl: certificate.driveUrl,
    status: certificate.status
  };
}

function publicAnswerForAdmin_(answer) {
  return {
    answerId: answer.answerId,
    attemptId: answer.attemptId,
    questionId: answer.questionId,
    answerText: answer.answerText,
    selectedOptionId: answer.selectedOptionId,
    isCorrect: answer.isCorrect === '' ? null : toBoolean_(answer.isCorrect),
    awardedPoints: answer.awardedPoints === '' ? null : Number(answer.awardedPoints),
    savedAt: answer.savedAt,
    submittedAt: answer.submittedAt
  };
}

/** ===== 14_Utils.gs ===== */

function stringValue_(value) {
  if (value === null || value === undefined) return '';
  return String(value);
}

function normalizeEmail_(email) {
  return stringValue_(email).trim().toLowerCase();
}

function isValidEmail_(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function toBoolean_(value) {
  if (value === true || value === 1) return true;
  var normalized = stringValue_(value).trim().toLowerCase();
  return ['true', '1', 'yes', 'sim', 'active'].indexOf(normalized) !== -1;
}

function normalizeCellValue_(value) {
  if (value === undefined || value === null) return '';
  if (value instanceof Date) return value;
  if (typeof value === 'object') return JSON.stringify(value);
  return value;
}

function newId_(prefix) {
  return prefix + '-' + Utilities.getUuid().replace(/-/g, '').toUpperCase();
}

function generatePublicStudentId_() {
  for (var attempt = 0; attempt < 200; attempt++) {
    var number = Math.floor(Math.random() * 100000);
    var candidate = 'STU-' + ('00000' + number).slice(-5);
    if (!findOne_(CP.SHEETS.STUDENTS, { publicStudentId: candidate })) {
      return candidate;
    }
  }
  throw apiError_('PUBLIC_STUDENT_ID_EXHAUSTED', 'Nao foi possivel gerar um ID publico unico para o estudante.');
}

function ensureStudentPublicId_(student) {
  if (!student) return student;
  if (stringValue_(student.publicStudentId)) return student;

  return updateRecordByKey_(CP.SHEETS.STUDENTS, 'studentId', student.studentId, {
    publicStudentId: generatePublicStudentId_(),
    updatedAt: new Date()
  });
}

function truncate_(value, maxLength) {
  value = stringValue_(value);
  return value.length > maxLength ? value.slice(0, maxLength) : value;
}

function requireFields_(payload, fields) {
  var missing = fields.filter(function(field) {
    var value = payload[field];
    return value === undefined || value === null || stringValue_(value).trim() === '';
  });

  if (missing.length) {
    throw apiError_(
      'REQUIRED_FIELDS_MISSING',
      'Campos obrigatórios em falta: ' + missing.join(', '),
      { fields: missing }
    );
  }
}

function serializeForJson_(value) {
  if (value instanceof Date) {
    return value.toISOString();
  }

  if (value instanceof Array) {
    return value.map(serializeForJson_);
  }

  if (value && typeof value === 'object') {
    var result = {};
    Object.keys(value).forEach(function(key) {
      if (key !== '_rowNumber') {
        result[key] = serializeForJson_(value[key]);
      }
    });
    return result;
  }

  return value;
}

function safeJsonParse_(value, fallback) {
  try {
    return JSON.parse(value);
  } catch (error) {
    return fallback;
  }
}

function round2_(value) {
  return Math.round(Number(value) * 100) / 100;
}

function stripDataUrl_(base64Data) {
  return stringValue_(base64Data)
    .replace(/^data:[^;]+;base64,/, '')
    .replace(/\s/g, '');
}

function sanitizeFileName_(name) {
  var clean = stringValue_(name)
    .replace(/[\\\/:*?"<>|#%{}\[\]~]/g, '_')
    .replace(/\s+/g, ' ')
    .trim();

  return truncate_(clean || 'ficheiro', 180);
}

function sanitizeFolderName_(name) {
  return truncate_(
    stringValue_(name)
      .replace(/[\\\/:*?"<>|#%{}\[\]~]/g, '_')
      .replace(/\s+/g, ' ')
      .trim() || 'Pasta',
    180
  );
}

function uniqueFileName_(fileName, existingFiles) {
  var names = existingFiles.map(function(file) {
    return stringValue_(file.fileName).toLowerCase();
  });

  if (names.indexOf(fileName.toLowerCase()) === -1) {
    return fileName;
  }

  var dotIndex = fileName.lastIndexOf('.');
  var base = dotIndex > 0 ? fileName.slice(0, dotIndex) : fileName;
  var extension = dotIndex > 0 ? fileName.slice(dotIndex) : '';

  var counter = 2;
  var candidate;
  do {
    candidate = base + ' (' + counter + ')' + extension;
    counter++;
  } while (names.indexOf(candidate.toLowerCase()) !== -1);

  return candidate;
}

function normalizeSelectedOptions_(value) {
  if (value instanceof Array) {
    return JSON.stringify(value.map(stringValue_));
  }

  var text = stringValue_(value).trim();
  if (!text) return '';

  // Mantém JSON válido; caso contrário guarda a opção única como JSON.
  var parsed = safeJsonParse_(text, null);
  if (parsed instanceof Array) {
    return JSON.stringify(parsed.map(stringValue_));
  }

  return JSON.stringify([text]);
}

function parseSelectedOptions_(value) {
  var parsed = safeJsonParse_(stringValue_(value), null);

  if (parsed instanceof Array) {
    return parsed.map(stringValue_);
  }

  if (!value) return [];
  return [stringValue_(value)];
}

function arraysEqual_(a, b) {
  if (a.length !== b.length) return false;

  for (var i = 0; i < a.length; i++) {
    if (stringValue_(a[i]) !== stringValue_(b[i])) return false;
  }

  return true;
}

function slugify_(value) {
  return stringValue_(value)
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 160);
}

/** ===== 15_Maintenance.gs ===== */

/**
 * Pode ser associada a um acionador horário.
 * Expira tentativas e remove sessões antigas.
 */
function runHourlyMaintenance() {
  var attempts = findMany_(CP.SHEETS.ATTEMPTS, {
    status: CP.STATUS.IN_PROGRESS
  });

  attempts.forEach(expireAttemptIfNeeded_);

  var sessions = readAll_(CP.SHEETS.SESSIONS);
  var now = Date.now();

  sessions.forEach(function(session) {
    if (
      toBoolean_(session.active) &&
      new Date(session.expiresAt).getTime() <= now
    ) {
      updateRecordByKey_(
        CP.SHEETS.SESSIONS,
        'sessionToken',
        session.sessionToken,
        {
          active: false,
          revokedAt: new Date()
        }
      );
    }
  });

  return {
    success: true,
    checkedAttempts: attempts.length,
    checkedSessions: sessions.length,
    timestamp: new Date()
  };
}

/**
 * Execute uma vez para criar o acionador de manutenção.
 */
function installMaintenanceTrigger() {
  var handlers = ScriptApp.getProjectTriggers().map(function(trigger) {
    return trigger.getHandlerFunction();
  });

  if (handlers.indexOf('runHourlyMaintenance') === -1) {
    ScriptApp
      .newTrigger('runHourlyMaintenance')
      .timeBased()
      .everyHours(1)
      .create();
  }

  return { success: true };
}

/**
 * Execute uma vez apos atualizar o codigo para garantir a chave MEDIA_CONFIG.
 */
function installMediaConfig() {
  var existing = findOne_(CP.SHEETS.SETTINGS, { key: 'MEDIA_CONFIG' });

  if (!existing) {
    setSetting_(
      'MEDIA_CONFIG',
      CP.DEFAULTS.MEDIA_CONFIG,
      'JSON',
      'Logotipo e galeria de videos da plataforma.'
    );
  }

  var result = {
    success: true,
    existed: Boolean(existing),
    mediaConfig: readMediaConfig_('')
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

/**
 * Diagnostico rapido para confirmar que este codigo contem as rotas de media.
 */
function debugMediaRoutes() {
  var result = {
    success: true,
    getActions: [
      'publicMediaConfig'
    ],
    postActions: [
      'getMediaConfig',
      'adminGetMediaConfig',
      'adminSaveMediaConfig'
    ],
    settingExists: Boolean(findOne_(CP.SHEETS.SETTINGS, { key: 'MEDIA_CONFIG' })),
    timestamp: new Date()
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

/** ===== 16_Tests.gs ===== */

/**
 * Testes manuais para executar no editor.
 */
function testHealth() {
  Logger.log(JSON.stringify(health_(), null, 2));
}

function testPublicCourseConfig() {
  Logger.log(JSON.stringify(getPublicCourseConfig_(''), null, 2));
}

function testDatabaseConnection() {
  var result = {
    spreadsheetId: getSpreadsheetId_(),
    title: getDb_().getName(),
    sheets: getDb_().getSheets().map(function(sheet) {
      return sheet.getName();
    })
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

/** ===== 17_CourseSeed.gs ===== */

/**
 * Execute seedCoursePlatformContent() depois de setupCoursePlatformApi().
 * A função preenche Courses, Lessons, LessonContent, Questions e QuestionOptions.
 */
function seedCoursePlatformContent() {
  ensureSchema_();

  var records = {
    courses: getSeedCourses_(),
    lessons: getSeedLessons_(),
    content: getSeedLessonContent_(),
    questions: getSeedQuestions_(),
    options: getSeedQuestionOptions_()
  };

  records.courses.forEach(function(record) {
    seedUpsert_(CP.SHEETS.COURSES, 'courseId', record);
  });
  records.lessons.forEach(function(record) {
    seedUpsert_(CP.SHEETS.LESSONS, 'lessonId', record);
  });
  records.content.forEach(function(record) {
    seedUpsert_(CP.SHEETS.LESSON_CONTENT, 'contentId', record);
  });
  records.questions.forEach(function(record) {
    seedUpsert_(CP.SHEETS.QUESTIONS, 'questionId', record);
  });
  records.options.forEach(function(record) {
    seedUpsert_(CP.SHEETS.QUESTION_OPTIONS, 'optionId', record);
  });

  var result = {
    success: true,
    courses: records.courses.length,
    lessons: records.lessons.length,
    contentSections: records.content.length,
    questions: records.questions.length,
    options: records.options.length
  };

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

function seedUpsert_(sheetName, keyField, record) {
  var criteria = {};
  criteria[keyField] = record[keyField];

  var existing = findOne_(sheetName, criteria);
  if (existing) {
    return updateRecordByKey_(sheetName, keyField, record[keyField], record);
  }
  return appendRecord_(sheetName, record);
}

function getSeedCourses_() {
  var now = new Date();
  return [{
    courseId: 'COURSE-EAPI-001',
    courseCode: 'EAPI-12H',
    title: 'Economia e Avaliação de Projetos Industriais',
    description: 'Curso individual de 12 horas aplicado às indústrias de Moçambique e de África.',
    totalHours: 12,
    passingScore: 60,
    status: CP.STATUS.ACTIVE,
    createdAt: now,
    updatedAt: now
  }];
}

function getSeedLessons_() {
  var now = new Date();
  return [
    {
      lessonId: 'LESSON-EAPI-001',
      courseId: 'COURSE-EAPI-001',
      lessonNumber: 1,
      title: 'Ativos Fixos, Equipamentos e Capital Circulante',
      slug: 'ativos-fixos-capital-circulante',
      summary: 'Avaliação de ativos, depreciação, utilização de equipamentos, stocks e rotação do capital circulante.',
      theoryMinutes: 60,
      exerciseMinutes: 120,
      individualMinutes: 60,
      passingScore: 60,
      prerequisiteLessonId: '',
      status: CP.STATUS.ACTIVE,
      createdAt: now,
      updatedAt: now
    },
    {
      lessonId: 'LESSON-EAPI-002',
      courseId: 'COURSE-EAPI-001',
      lessonNumber: 2,
      title: 'Recursos Humanos, Produtividade, Custos e Preços',
      slug: 'recursos-humanos-custos-precos',
      summary: 'Planeamento do efetivo, produtividade, remuneração, custos industriais e formação de preços.',
      theoryMinutes: 60,
      exerciseMinutes: 120,
      individualMinutes: 60,
      passingScore: 60,
      prerequisiteLessonId: 'LESSON-EAPI-001',
      status: CP.STATUS.ACTIVE,
      createdAt: now,
      updatedAt: now
    },
    {
      lessonId: 'LESSON-EAPI-003',
      courseId: 'COURSE-EAPI-001',
      lessonNumber: 3,
      title: 'Investimentos e Avaliação Económica de Projetos',
      slug: 'investimentos-avaliacao-projetos',
      summary: 'Fluxos de caixa, desconto, VAL, TIR, período de recuperação e decisão de investimento.',
      theoryMinutes: 60,
      exerciseMinutes: 120,
      individualMinutes: 60,
      passingScore: 60,
      prerequisiteLessonId: 'LESSON-EAPI-002',
      status: CP.STATUS.ACTIVE,
      createdAt: now,
      updatedAt: now
    }
  ];
}

function seedSection_(id, lessonId, order, type, title, bodyHtml, minutes) {
  var now = new Date();
  return {
    contentId: id,
    lessonId: lessonId,
    sectionOrder: order,
    sectionType: type,
    title: title,
    bodyHtml: bodyHtml,
    estimatedMinutes: minutes,
    isRequired: true,
    status: CP.STATUS.ACTIVE,
    createdAt: now,
    updatedAt: now
  };
}

function getSeedLessonContent_() {
  return [
    seedSection_(
      'CNT-L1-001', 'LESSON-EAPI-001', 1, 'THEORY', 'Objetivos da aula',
      '<p>No final desta aula, o estudante deverá identificar ativos fixos, calcular o custo de aquisição, aplicar métodos de depreciação, analisar a utilização de equipamentos e dimensionar stocks.</p>',
      4
    ),
    seedSection_(
      'CNT-L1-002', 'LESSON-EAPI-001', 2, 'THEORY', 'Ativos fixos e classificação',
      '<p>Ativos fixos são recursos utilizados durante vários períodos económicos para apoiar a produção, a prestação de serviços ou a administração. Incluem edifícios, oficinas, estradas internas, britadores, moinhos, bombas, compressores, geradores, escavadoras, viaturas, servidores e software industrial.</p><div class="callout"><strong>Classificação:</strong> edifícios; estruturas e obras de engenharia; máquinas e equipamentos; meios de transporte; equipamentos de informação e comunicação; ativos intangíveis e propriedade intelectual.</div>',
      8
    ),
    seedSection_(
      'CNT-L1-003', 'LESSON-EAPI-001', 3, 'FORMULA', 'Custo de aquisição',
      '<p>O custo de aquisição reúne os gastos necessários para comprar, transportar, instalar e colocar o ativo em funcionamento.</p><div class="formula">\\(CA=P+D+I\\)</div><p><strong>CA</strong>: custo de aquisição; <strong>P</strong>: preço; <strong>D</strong>: transporte e entrega; <strong>I</strong>: instalação, montagem e testes.</p><div class="example"><strong>Exemplo:</strong> 8 400 000 + 650 000 + 450 000 = 9 500 000 MZN.</div>',
      7
    ),
    seedSection_(
      'CNT-L1-004', 'LESSON-EAPI-001', 4, 'THEORY', 'Valor contabilístico e valor residual',
      '<div class="formula">\\(VLC=CA-DA\\)</div><p>O valor líquido contabilístico corresponde ao custo menos a depreciação acumulada. O valor residual é o montante estimado que poderá ser recuperado no fim da vida útil.</p><div class="formula">\\(JV=VC\\times K_r\\)</div><p>O justo valor resulta de uma avaliação atualizada do ativo.</p>',
      7
    ),
    seedSection_(
      'CNT-L1-005', 'LESSON-EAPI-001', 5, 'THEORY', 'Desgaste e obsolescência',
      '<p>O desgaste físico pode resultar de uso, corrosão, vibração, poeiras, temperatura e manutenção inadequada.</p><div class="formula">\\(D_f=\\frac{T_f}{T_n}\\times100\\%\\)</div><p>A obsolescência ocorre quando o equipamento continua operacional, mas deixa de ser competitivo devido a tecnologias mais produtivas, eficientes ou seguras.</p>',
      7
    ),
    seedSection_(
      'CNT-L1-006', 'LESSON-EAPI-001', 6, 'FORMULA', 'Métodos de depreciação',
      '<h4>Método linear</h4><div class="formula">\\(D_a=\\frac{CA-VR}{n}\\)</div><h4>Saldo decrescente</h4><div class="formula">\\(D=VLC\\times T_d\\times K\\)</div><h4>Unidades de produção</h4><div class="formula">\\(D_p=Q_p\\times\\frac{CA-VR}{Q_t}\\)</div><p>O método das unidades de produção pode utilizar toneladas, horas, metros perfurados ou quilómetros.</p>',
      10
    ),
    seedSection_(
      'CNT-L1-007', 'LESSON-EAPI-001', 7, 'FORMULA', 'Indicadores de utilização dos ativos',
      '<div class="formula">\\(PAF=\\frac{Q}{AF_m}\\)</div><div class="formula">\\(ICF=\\frac{AF_m}{Q}\\)</div><div class="formula">\\(RAP=\\frac{L}{AF_m}\\times100\\%\\)</div><div class="formula">\\(K_e=\\frac{H_f}{H_d},\\quad K_i=\\frac{P_f}{P_t},\\quad K_{int}=K_e\\times K_i\\)</div>',
      8
    ),
    seedSection_(
      'CNT-L1-008', 'LESSON-EAPI-001', 8, 'THEORY', 'Capital circulante e stocks',
      '<p>O capital circulante inclui matérias-primas, combustíveis, lubrificantes, peças, produção em curso, produtos acabados, valores a receber e disponibilidades.</p><div class="formula">\\(D-M-P-PA-D_1\\)</div><div class="formula">\\(S_{cd}=\\frac{I}{2},\\quad S_{cf}=S_{cd}\\times C_d,\\quad S_t=S_c+S_p+S_s\\)</div>',
      8
    ),
    seedSection_(
      'CNT-L1-009', 'LESSON-EAPI-001', 9, 'FORMULA', 'Rotação do capital circulante',
      '<div class="formula">\\(K_o=\\frac{V}{CC_m}\\)</div><div class="formula">\\(K_z=\\frac{CC_m}{V}\\)</div><div class="formula">\\(D=\\frac{T}{K_o}\\)</div><p>Uma rotação mais rápida reduz o tempo de imobilização dos recursos, desde que não provoque falta de materiais.</p>',
      5
    ),
    seedSection_(
      'CNT-L1-010', 'LESSON-EAPI-001', 10, 'EXERCISE', 'Exercícios práticos',
      '<ol><li>Calcule custo de aquisição, valor depreciável, depreciação e valor líquido de uma carregadora.</li><li>Calcule o valor médio anual e os indicadores de eficiência dos ativos.</li><li>Determine reparações correntes e inspeções num ciclo de manutenção.</li><li>Dimensione o stock de combustível.</li><li>Calcule o número e a duração das rotações do capital circulante.</li></ol><p>Apresente fórmulas, substituições, unidades e interpretação.</p>',
      120
    ),
    seedSection_(
      'CNT-L1-011', 'LESSON-EAPI-001', 11, 'INSTRUCTIONS', 'Trabalho individual',
      '<p>Escolha um ativo utilizado numa empresa industrial africana. Prepare uma ficha com setor, função, preço, transporte, instalação, custo de aquisição, vida útil, valor residual, depreciação, produção esperada, manutenção, riscos de desgaste, obsolescência e recomendação final.</p>',
      60
    ),

    seedSection_(
      'CNT-L2-001', 'LESSON-EAPI-002', 1, 'THEORY', 'Objetivos da aula',
      '<p>A aula analisa o planeamento da força de trabalho, produtividade, remuneração, classificação de custos, custo unitário, preço, lucro e rentabilidade.</p>',
      4
    ),
    seedSection_(
      'CNT-L2-002', 'LESSON-EAPI-002', 2, 'THEORY', 'Planeamento do efetivo',
      '<p>O efetivo presente assegura a operação diária. O efetivo total cobre folgas, férias, formação, doenças e outras ausências.</p><div class="formula">\\(N_t=N_p\\times K_c\\)</div><div class="formula">\\(K_c=\\frac{D_c}{D_u}\\)</div>',
      8
    ),
    seedSection_(
      'CNT-L2-003', 'LESSON-EAPI-002', 3, 'FORMULA', 'Produtividade',
      '<div class="formula">\\(P=\\frac{Q}{T}\\)</div><div class="formula">\\(PT=\\frac{Q}{N}\\)</div><div class="formula">\\(IMO=\\frac{T}{Q}\\)</div><div class="formula">\\(\\Delta P=\\frac{P_1-P_0}{P_0}\\times100\\%\\)</div><p>A produtividade não deve ser aumentada à custa da segurança ou da qualidade.</p>',
      8
    ),
    seedSection_(
      'CNT-L2-004', 'LESSON-EAPI-002', 4, 'THEORY', 'Sistemas de remuneração',
      '<div class="formula">\\(R=T_h\\times H\\)</div><div class="formula">\\(R=R_b+P\\)</div><div class="formula">\\(R=Q\\times T_u\\)</div><p>Os incentivos podem considerar produção, qualidade, segurança, desperdícios, assiduidade e cumprimento de prazos.</p>',
      8
    ),
    seedSection_(
      'CNT-L2-005', 'LESSON-EAPI-002', 5, 'THEORY', 'Classificação dos custos',
      '<ul><li><strong>Diretos:</strong> matéria-prima, mão de obra direta, explosivos, reagentes e energia identificável.</li><li><strong>Indiretos:</strong> supervisão, iluminação, segurança, administração e serviços comuns.</li><li><strong>Fixos:</strong> mantêm-se relativamente estáveis dentro de uma capacidade.</li><li><strong>Variáveis:</strong> alteram-se com a produção.</li></ul>',
      8
    ),
    seedSection_(
      'CNT-L2-006', 'LESSON-EAPI-002', 6, 'FORMULA', 'Custo total e unitário',
      '<div class="formula">\\(CV_t=CV_u\\times Q\\)</div><div class="formula">\\(CT=CF+CV\\)</div><div class="formula">\\(CU=\\frac{CT}{Q}\\)</div><p>O custo unitário apoia a formação de preços, a negociação de contratos e a análise de eficiência.</p>',
      7
    ),
    seedSection_(
      'CNT-L2-007', 'LESSON-EAPI-002', 7, 'THEORY', 'Redução de custos',
      '<div class="formula">\\(E=(CV_0-CV_1)\\times Q\\)</div><div class="formula">\\(E_m=(N_0-N_1)\\times P\\times Q\\)</div><p>A redução pode resultar de menor consumo, manutenção preventiva, formação, reorganização dos turnos e automatização.</p>',
      7
    ),
    seedSection_(
      'CNT-L2-008', 'LESSON-EAPI-002', 8, 'FORMULA', 'Lucro e rentabilidade',
      '<div class="formula">\\(L=R-I-CT\\)</div><div class="formula">\\(RC=\\frac{L}{CT}\\times100\\%\\)</div><div class="formula">\\(MV=\\frac{L}{R}\\times100\\%\\)</div><p>Rentabilidade sobre o custo e margem sobre as vendas utilizam bases diferentes.</p>',
      7
    ),
    seedSection_(
      'CNT-L2-009', 'LESSON-EAPI-002', 9, 'THEORY', 'Formação de preços',
      '<div class="formula">\\(PV=CU\\times(1+r)+I\\)</div><p>Além do custo, devem ser considerados concorrência, procura, qualidade, transporte, localização, risco cambial e condições de pagamento. Nos minerais, o preço pode variar com teor, recuperação, humidade, cinzas, enxofre, impurezas e beneficiamento.</p>',
      8
    ),
    seedSection_(
      'CNT-L2-010', 'LESSON-EAPI-002', 10, 'EXERCISE', 'Exercícios práticos',
      '<ol><li>Calcule o efetivo de uma operação contínua.</li><li>Calcule produção por trabalhador, produtividade horária e intensidade de mão de obra.</li><li>Calcule remuneração base, prémio e remuneração total.</li><li>Determine custo total, custo unitário, preço, receita, lucro, margem e rentabilidade.</li><li>Calcule a economia de combustível.</li><li>Ajuste o preço do carvão por cinzas e humidade.</li></ol>',
      120
    ),
    seedSection_(
      'CNT-L2-011', 'LESSON-EAPI-002', 11, 'INSTRUCTIONS', 'Trabalho individual',
      '<p>Escolha um produto ou serviço industrial. Apresente unidade de medida, quantidade mensal, custos diretos, indiretos, fixos e variáveis, custo total, custo unitário, preço, receita, lucro, margem, fatores de variação e uma proposta de redução de custos.</p>',
      60
    ),

    seedSection_(
      'CNT-L3-001', 'LESSON-EAPI-003', 1, 'THEORY', 'Objetivos da aula',
      '<p>O estudante aprenderá a construir fluxos de caixa, aplicar o desconto e avaliar projetos utilizando VAL, TIR, período de recuperação e índice de rentabilidade.</p>',
      4
    ),
    seedSection_(
      'CNT-L3-002', 'LESSON-EAPI-003', 2, 'THEORY', 'Conceito e tipos de investimento',
      '<p>Investimento é a aplicação de recursos com expectativa de benefícios futuros. Pode envolver máquinas, edifícios, tecnologia, formação, software, stocks e capital circulante.</p><ul><li>Investimento inicial.</li><li>Expansão.</li><li>Reinvestimento.</li><li>Modernização.</li><li>Investimentos financeiros e intangíveis.</li></ul>',
      7
    ),
    seedSection_(
      'CNT-L3-003', 'LESSON-EAPI-003', 3, 'THEORY', 'Projeto e eficiência',
      '<p>Um projeto reúne objetivos, estudos, recursos, atividades, cronograma e resultados. A eficiência comercial mede consequências financeiras; a socioeconómica considera emprego, desenvolvimento, segurança, ambiente e infraestrutura.</p>',
      7
    ),
    seedSection_(
      'CNT-L3-004', 'LESSON-EAPI-003', 4, 'FORMULA', 'Fluxo de caixa',
      '<div class="formula">\\(FC_t=E_t-S_t\\)</div><p>O fluxo de investimento inclui terreno, construção, máquinas, transporte, instalação e capital circulante. O fluxo operacional inclui vendas, materiais, energia, salários, manutenção e impostos. O fluxo financeiro inclui capital próprio, empréstimos, juros e amortizações.</p>',
      9
    ),
    seedSection_(
      'CNT-L3-005', 'LESSON-EAPI-003', 5, 'THEORY', 'Valor temporal do dinheiro',
      '<p>Um valor recebido hoje possui maior utilidade do que o mesmo valor recebido no futuro. Fluxos de períodos diferentes devem ser convertidos para uma data comum.</p><div class="formula">\\(FD_t=\\frac{FC_t}{(1+i)^t}\\)</div>',
      7
    ),
    seedSection_(
      'CNT-L3-006', 'LESSON-EAPI-003', 6, 'FORMULA', 'Valor Atual Líquido',
      '<div class="formula">\\(VAL=\\sum_{t=0}^{n}\\frac{FC_t}{(1+i)^t}\\)</div><ul><li><strong>VAL &gt; 0:</strong> cria valor acima da taxa exigida.</li><li><strong>VAL = 0:</strong> remunera exatamente a taxa exigida.</li><li><strong>VAL &lt; 0:</strong> não atinge a rentabilidade exigida.</li></ul>',
      8
    ),
    seedSection_(
      'CNT-L3-007', 'LESSON-EAPI-003', 7, 'FORMULA', 'TIR, recuperação e índice',
      '<div class="formula">\\(0=\\sum_{t=0}^{n}\\frac{FC_t}{(1+TIR)^t}\\)</div><p>A TIR é a taxa que torna o VAL igual a zero. O período de recuperação mede o tempo para recuperar o investimento.</p><div class="formula">\\(IR=\\frac{VAE}{Investimento}\\)</div>',
      9
    ),
    seedSection_(
      'CNT-L3-008', 'LESSON-EAPI-003', 8, 'THEORY', 'Riscos e cenários',
      '<p>Projetos africanos podem ser influenciados por variação cambial, inflação, importação, logística, energia, financiamento, clima, procura, preços internacionais, qualificação profissional, licenciamento e impactos ambientais e sociais.</p><p>Devem ser analisados cenários conservador, base e otimista.</p>',
      7
    ),
    seedSection_(
      'CNT-L3-009', 'LESSON-EAPI-003', 9, 'EXERCISE', 'Exercício integrado',
      '<p>Analise uma unidade com 18 000 000 MZN em equipamentos, 2 000 000 MZN em instalação e 3 000 000 MZN em capital circulante. Capacidade: 30 000 t/ano; preço: 1 500 MZN/t; custo variável: 850 MZN/t; custos fixos monetários: 8 000 000 MZN/ano.</p><p>Considere cinco anos, valor residual de 2 000 000 MZN, recuperação do capital circulante, imposto pedagógico de 30% e taxa de desconto de 15%. Calcule fluxos, VAL, TIR, período de recuperação e índice de rentabilidade.</p>',
      120
    ),
    seedSection_(
      'CNT-L3-010', 'LESSON-EAPI-003', 10, 'INSTRUCTIONS', 'Trabalho individual',
      '<p>Escolha um projeto industrial relevante para Moçambique ou África. Prepare um memorando com problema, produto, beneficiários, investimento, capacidade, receitas, custos, vida útil, valor residual, riscos, benefícios económicos e sociais, impactos ambientais e decisão recomendada.</p>',
      60
    )
  ];
}

function seedQuestion_(id, lessonId, order, type, prompt, points) {
  var now = new Date();
  return {
    questionId: id,
    lessonId: lessonId,
    questionOrder: order,
    questionType: type,
    prompt: prompt,
    points: points,
    correctAnswer: '',
    explanation: '',
    isRequired: true,
    status: CP.STATUS.ACTIVE,
    createdAt: now,
    updatedAt: now
  };
}

function getSeedQuestions_() {
  return [
    seedQuestion_('QUE-L1-001', 'LESSON-EAPI-001', 1, 'SINGLE_CHOICE', 'O custo de aquisição de uma máquina inclui:', 4),
    seedQuestion_('QUE-L1-002', 'LESSON-EAPI-001', 2, 'SINGLE_CHOICE', 'O valor líquido contabilístico corresponde:', 4),
    seedQuestion_('QUE-L1-003', 'LESSON-EAPI-001', 3, 'SINGLE_CHOICE', 'Qual método relaciona a depreciação com a utilização efetiva?', 4),
    seedQuestion_('QUE-L1-004', 'LESSON-EAPI-001', 4, 'SINGLE_CHOICE', 'O stock de segurança existe principalmente para:', 4),
    seedQuestion_('QUE-L1-005', 'LESSON-EAPI-001', 5, 'LONG_TEXT', 'Explique qual indicador considera mais importante para decidir se uma máquina deve continuar em operação.', 10),

    seedQuestion_('QUE-L2-001', 'LESSON-EAPI-002', 1, 'SINGLE_CHOICE', 'A intensidade de mão de obra é:', 4),
    seedQuestion_('QUE-L2-002', 'LESSON-EAPI-002', 2, 'SINGLE_CHOICE', 'Qual dos seguintes é um custo direto?', 4),
    seedQuestion_('QUE-L2-003', 'LESSON-EAPI-002', 3, 'SINGLE_CHOICE', 'Quando a produção aumenta dentro da capacidade existente, o custo fixo total:', 4),
    seedQuestion_('QUE-L2-004', 'LESSON-EAPI-002', 4, 'SINGLE_CHOICE', 'A margem sobre as vendas é calculada por:', 4),
    seedQuestion_('QUE-L2-005', 'LESSON-EAPI-002', 5, 'LONG_TEXT', 'Indique uma medida que permitiria reduzir custos sem comprometer a qualidade ou a segurança.', 10),

    seedQuestion_('QUE-L3-001', 'LESSON-EAPI-003', 1, 'SINGLE_CHOICE', 'O investimento inicial em máquinas pertence ao:', 4),
    seedQuestion_('QUE-L3-002', 'LESSON-EAPI-003', 2, 'SINGLE_CHOICE', 'O desconto é utilizado para:', 4),
    seedQuestion_('QUE-L3-003', 'LESSON-EAPI-003', 3, 'SINGLE_CHOICE', 'Um projeto com VAL positivo:', 4),
    seedQuestion_('QUE-L3-004', 'LESSON-EAPI-003', 4, 'SINGLE_CHOICE', 'A TIR é:', 4),
    seedQuestion_('QUE-L3-005', 'LESSON-EAPI-003', 5, 'LONG_TEXT', 'Qual é o maior risco do projeto analisado e que medida poderia reduzir esse risco?', 10)
  ];
}

function seedOption_(id, questionId, order, label, text, correct) {
  return {
    optionId: id,
    questionId: questionId,
    optionOrder: order,
    optionLabel: label,
    optionText: text,
    isCorrect: correct,
    createdAt: new Date()
  };
}

function getSeedQuestionOptions_() {
  return [
    seedOption_('OPT-L1-001-A', 'QUE-L1-001', 1, 'A', 'Apenas o preço de compra.', false),
    seedOption_('OPT-L1-001-B', 'QUE-L1-001', 2, 'B', 'Preço, transporte e instalação.', true),
    seedOption_('OPT-L1-001-C', 'QUE-L1-001', 3, 'C', 'Apenas transporte e manutenção.', false),
    seedOption_('OPT-L1-001-D', 'QUE-L1-001', 4, 'D', 'Preço menos valor residual.', false),

    seedOption_('OPT-L1-002-A', 'QUE-L1-002', 1, 'A', 'Ao preço de mercado.', false),
    seedOption_('OPT-L1-002-B', 'QUE-L1-002', 2, 'B', 'Ao custo menos a depreciação acumulada.', true),
    seedOption_('OPT-L1-002-C', 'QUE-L1-002', 3, 'C', 'Ao custo mais a manutenção.', false),
    seedOption_('OPT-L1-002-D', 'QUE-L1-002', 4, 'D', 'Ao valor residual.', false),

    seedOption_('OPT-L1-003-A', 'QUE-L1-003', 1, 'A', 'Método linear.', false),
    seedOption_('OPT-L1-003-B', 'QUE-L1-003', 2, 'B', 'Método de reavaliação.', false),
    seedOption_('OPT-L1-003-C', 'QUE-L1-003', 3, 'C', 'Método das unidades de produção.', true),
    seedOption_('OPT-L1-003-D', 'QUE-L1-003', 4, 'D', 'Método do custo médio.', false),

    seedOption_('OPT-L1-004-A', 'QUE-L1-004', 1, 'A', 'Aumentar o preço do material.', false),
    seedOption_('OPT-L1-004-B', 'QUE-L1-004', 2, 'B', 'Reduzir o número de trabalhadores.', false),
    seedOption_('OPT-L1-004-C', 'QUE-L1-004', 3, 'C', 'Proteger a produção contra atrasos e incertezas.', true),
    seedOption_('OPT-L1-004-D', 'QUE-L1-004', 4, 'D', 'Substituir o stock corrente.', false),

    seedOption_('OPT-L2-001-A', 'QUE-L2-001', 1, 'A', 'Produção dividida pelo número de máquinas.', false),
    seedOption_('OPT-L2-001-B', 'QUE-L2-001', 2, 'B', 'Tempo de trabalho dividido pela produção.', true),
    seedOption_('OPT-L2-001-C', 'QUE-L2-001', 3, 'C', 'Lucro dividido pelo número de trabalhadores.', false),
    seedOption_('OPT-L2-001-D', 'QUE-L2-001', 4, 'D', 'Custo fixo dividido pela receita.', false),

    seedOption_('OPT-L2-002-A', 'QUE-L2-002', 1, 'A', 'Salário da administração.', false),
    seedOption_('OPT-L2-002-B', 'QUE-L2-002', 2, 'B', 'Iluminação geral do escritório.', false),
    seedOption_('OPT-L2-002-C', 'QUE-L2-002', 3, 'C', 'Matéria-prima utilizada num produto.', true),
    seedOption_('OPT-L2-002-D', 'QUE-L2-002', 4, 'D', 'Segurança do edifício administrativo.', false),

    seedOption_('OPT-L2-003-A', 'QUE-L2-003', 1, 'A', 'Aumenta obrigatoriamente na mesma proporção.', false),
    seedOption_('OPT-L2-003-B', 'QUE-L2-003', 2, 'B', 'Mantém-se relativamente estável.', true),
    seedOption_('OPT-L2-003-C', 'QUE-L2-003', 3, 'C', 'Torna-se um custo variável.', false),
    seedOption_('OPT-L2-003-D', 'QUE-L2-003', 4, 'D', 'Deixa de existir.', false),

    seedOption_('OPT-L2-004-A', 'QUE-L2-004', 1, 'A', 'Lucro dividido pelo custo.', false),
    seedOption_('OPT-L2-004-B', 'QUE-L2-004', 2, 'B', 'Receita dividida pelo custo.', false),
    seedOption_('OPT-L2-004-C', 'QUE-L2-004', 3, 'C', 'Lucro dividido pela receita.', true),
    seedOption_('OPT-L2-004-D', 'QUE-L2-004', 4, 'D', 'Custo dividido pela produção.', false),

    seedOption_('OPT-L3-001-A', 'QUE-L3-001', 1, 'A', 'Fluxo operacional.', false),
    seedOption_('OPT-L3-001-B', 'QUE-L3-001', 2, 'B', 'Fluxo de investimento.', true),
    seedOption_('OPT-L3-001-C', 'QUE-L3-001', 3, 'C', 'Fluxo de vendas.', false),
    seedOption_('OPT-L3-001-D', 'QUE-L3-001', 4, 'D', 'Fluxo de salários.', false),

    seedOption_('OPT-L3-002-A', 'QUE-L3-002', 1, 'A', 'Aumentar artificialmente as receitas.', false),
    seedOption_('OPT-L3-002-B', 'QUE-L3-002', 2, 'B', 'Comparar fluxos ocorridos em diferentes períodos.', true),
    seedOption_('OPT-L3-002-C', 'QUE-L3-002', 3, 'C', 'Eliminar os custos.', false),
    seedOption_('OPT-L3-002-D', 'QUE-L3-002', 4, 'D', 'Calcular apenas a depreciação.', false),

    seedOption_('OPT-L3-003-A', 'QUE-L3-003', 1, 'A', 'Não gera receitas.', false),
    seedOption_('OPT-L3-003-B', 'QUE-L3-003', 2, 'B', 'Cria valor acima da taxa de desconto utilizada.', true),
    seedOption_('OPT-L3-003-C', 'QUE-L3-003', 3, 'C', 'Possui necessariamente risco zero.', false),
    seedOption_('OPT-L3-003-D', 'QUE-L3-003', 4, 'D', 'Não precisa de financiamento.', false),

    seedOption_('OPT-L3-004-A', 'QUE-L3-004', 1, 'A', 'A taxa que torna o VAL igual a zero.', true),
    seedOption_('OPT-L3-004-B', 'QUE-L3-004', 2, 'B', 'O número de trabalhadores do projeto.', false),
    seedOption_('OPT-L3-004-C', 'QUE-L3-004', 3, 'C', 'O custo fixo anual.', false),
    seedOption_('OPT-L3-004-D', 'QUE-L3-004', 4, 'D', 'A depreciação do investimento.', false)
  ];
}

/**
 * Módulo de gestão de estudantes e credenciais.
 *
 * Dependências existentes no projeto:
 * - CP.DEFAULT_SPREADSHEET_ID ou CP.SPREADSHEET_ID
 * - CP.SHEETS.STUDENTS (opcional; usa "Students" como fallback)
 * - normalizeEmail_(email) (opcional; há fallback local)
 * - findOne_(sheetName, criteria)
 * - createStudentFromEditor(fullName, email, country, organization)
 * - updateRecordByKey_(sheetName, keyName, keyValue, changes)
 * - hashSecret_(plainText)
 * - revokeSessionsForSubject_(studentId) (opcional)
 */

/* ========================================================================== */
/* CONFIGURAÇÃO E HELPERS                                                     */
/* ========================================================================== */

function getCoursePlatformSpreadsheet_() {
  if (typeof CP === 'undefined' || !CP) {
    throw new Error('A configuração global CP não foi encontrada.');
  }

  var spreadsheetId =
    CP.DEFAULT_SPREADSHEET_ID ||
    CP.SPREADSHEET_ID ||
    '';

  spreadsheetId = String(spreadsheetId || '').trim();

  if (!spreadsheetId) {
    throw new Error(
      'Defina CP.DEFAULT_SPREADSHEET_ID ou CP.SPREADSHEET_ID.'
    );
  }

  return SpreadsheetApp.openById(spreadsheetId);
}


function getStudentsSheetName_() {
  if (
    typeof CP !== 'undefined' &&
    CP &&
    CP.SHEETS &&
    CP.SHEETS.STUDENTS
  ) {
    return CP.SHEETS.STUDENTS;
  }

  return 'Students';
}


function normalizeEmailSafe_(email) {
  if (typeof normalizeEmail_ === 'function') {
    return normalizeEmail_(email);
  }

  return String(email || '')
    .trim()
    .toLowerCase();
}


function validateEmailBasic_(email) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(
    String(email || '').trim()
  );
}


function getHeaderMap_(headers) {
  var map = {};

  headers.forEach(function(header, index) {
    var key = String(header || '').trim();

    if (key) {
      map[key] = index;
    }
  });

  return map;
}


function requireHeaders_(headerMap, requiredHeaders, sheetName) {
  var missing = requiredHeaders.filter(function(header) {
    return headerMap[header] === undefined;
  });

  if (missing.length > 0) {
    throw new Error(
      'A aba ' +
      sheetName +
      ' não contém as colunas obrigatórias: ' +
      missing.join(', ') +
      '.'
    );
  }
}


function errorMessage_(error) {
  if (!error) {
    return 'Erro desconhecido.';
  }

  return error.message || String(error);
}


function ensureSheetWithHeaders_(spreadsheet, sheetName, expectedHeaders) {
  var sheet = spreadsheet.getSheetByName(sheetName);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }

  var lastColumn = sheet.getLastColumn();

  if (sheet.getLastRow() === 0 || lastColumn === 0) {
    sheet
      .getRange(1, 1, 1, expectedHeaders.length)
      .setValues([expectedHeaders]);

    sheet.setFrozenRows(1);
    return sheet;
  }

  var currentHeaders = sheet
    .getRange(1, 1, 1, Math.max(lastColumn, expectedHeaders.length))
    .getValues()[0]
    .map(function(value) {
      return String(value || '').trim();
    });

  expectedHeaders.forEach(function(header, index) {
    if (!currentHeaders[index]) {
      sheet.getRange(1, index + 1).setValue(header);
      currentHeaders[index] = header;
    } else if (currentHeaders[index] !== header) {
      throw new Error(
        'Estrutura incompatível na aba ' +
        sheetName +
        '. A coluna ' +
        (index + 1) +
        ' deveria ser "' +
        header +
        '", mas contém "' +
        currentHeaders[index] +
        '".'
      );
    }
  });

  sheet.setFrozenRows(1);
  return sheet;
}


function generateSecureAccessCode_(length) {
  var codeLength = Number(length) || 10;
  var alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    Utilities.getUuid() +
      '|' +
      new Date().getTime() +
      '|' +
      Math.random()
  );

  var code = '';

  for (var i = 0; i < codeLength; i++) {
    var byteValue = bytes[i % bytes.length];

    if (byteValue < 0) {
      byteValue += 256;
    }

    code += alphabet.charAt(byteValue % alphabet.length);
  }

  if (!code || code.length !== codeLength) {
    throw new Error('Falha interna ao gerar o código de acesso.');
  }

  return code;
}


function generateUniqueAccessCode_(usedCodes, length) {
  var maxAttempts = 50;

  for (var attempt = 0; attempt < maxAttempts; attempt++) {
    var code = generateSecureAccessCode_(length);

    if (!usedCodes[code]) {
      usedCodes[code] = true;
      return code;
    }
  }

  throw new Error(
    'Não foi possível gerar um código de acesso único após ' +
    maxAttempts +
    ' tentativas.'
  );
}


function hashAccessCodeOrFail_(accessCode) {
  if (typeof hashSecret_ !== 'function') {
    throw new Error('A função hashSecret_() não foi encontrada.');
  }

  var hash = hashSecret_(accessCode);
  hash = String(hash || '').trim();

  if (!hash) {
    throw new Error('hashSecret_() devolveu um valor vazio.');
  }

  if (hash === accessCode) {
    throw new Error(
      'hashSecret_() devolveu o próprio código sem proteção.'
    );
  }

  return hash;
}


/* ========================================================================== */
/* IMPORTAÇÃO DE ESTUDANTES                                                   */
/* ========================================================================== */

function importarEstudantesDaPlanilha() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var spreadsheet = getCoursePlatformSpreadsheet_();
    var importSheet = spreadsheet.getSheetByName('StudentImport');

    if (!importSheet) {
      throw new Error('A aba StudentImport não foi encontrada.');
    }

    var values = importSheet.getDataRange().getValues();

    if (values.length < 2) {
      throw new Error('Não existem estudantes para importar.');
    }

    var headers = values[0].map(function(header) {
      return String(header || '').trim();
    });

    var headerMap = getHeaderMap_(headers);

    requireHeaders_(
      headerMap,
      ['fullName', 'email'],
      'StudentImport'
    );

    var processedIndex = headerMap.processed;

    if (processedIndex === undefined) {
      processedIndex = headers.length;
      headers.push('processed');
      headerMap.processed = processedIndex;

      importSheet
        .getRange(1, processedIndex + 1)
        .setValue('processed');
    }

    var resultados = [];
    var statusUpdates = [];
    var emailsDaImportacao = {};

    for (var rowIndex = 1; rowIndex < values.length; rowIndex++) {
      var row = values[rowIndex];

      var fullName = String(
        row[headerMap.fullName] || ''
      ).trim();

      var email = normalizeEmailSafe_(
        row[headerMap.email]
      );

      var country =
        headerMap.country !== undefined
          ? String(row[headerMap.country] || '').trim()
          : '';

      var organization =
        headerMap.organization !== undefined
          ? String(row[headerMap.organization] || '').trim()
          : '';

      var processed = String(
        row[processedIndex] || ''
      )
        .trim()
        .toUpperCase();

      if (
        processed === 'YES' ||
        processed === 'SIM' ||
        processed === 'EXISTS' ||
        processed === 'DUPLICATE'
      ) {
        continue;
      }

      var result = {
        row: rowIndex + 1,
        success: false,
        fullName: fullName,
        email: email,
        studentId: '',
        accessCode: '',
        error: ''
      };

      var finalStatus = 'ERROR';

      if (!fullName || !email) {
        result.error = 'Nome ou email em falta.';
      } else if (!validateEmailBasic_(email)) {
        result.error = 'Formato de email inválido.';
      } else if (emailsDaImportacao[email]) {
        result.error = 'Email duplicado na lista de importação.';
        finalStatus = 'DUPLICATE';
      } else {
        emailsDaImportacao[email] = true;

        try {
          if (typeof findOne_ !== 'function') {
            throw new Error('A função findOne_() não foi encontrada.');
          }

          var existingStudent = findOne_(
            getStudentsSheetName_(),
            { email: email }
          );

          if (existingStudent) {
            result.studentId =
              existingStudent.studentId || '';

            result.error =
              'Estudante já registado. O código anterior foi mantido.';

            finalStatus = 'EXISTS';
          } else {
            if (
              typeof createStudentFromEditor !== 'function'
            ) {
              throw new Error(
                'A função createStudentFromEditor() não foi encontrada.'
              );
            }

            var creationResult = createStudentFromEditor(
              fullName,
              email,
              country,
              organization
            );

            if (
              !creationResult ||
              !creationResult.student ||
              !creationResult.student.studentId
            ) {
              throw new Error(
                'createStudentFromEditor() não devolveu o estudante criado.'
              );
            }

            var visibleAccessCode = String(
              creationResult.accessCode || ''
            ).trim();

            if (!visibleAccessCode) {
              throw new Error(
                'createStudentFromEditor() não devolveu o accessCode visível.'
              );
            }

            result.success = true;
            result.studentId =
              creationResult.student.studentId;

            result.accessCode = visibleAccessCode;
            finalStatus = 'YES';
          }
        } catch (error) {
          result.error = errorMessage_(error);
          finalStatus = 'ERROR';
        }
      }

      resultados.push(result);
      statusUpdates.push({
        row: rowIndex + 1,
        value: finalStatus
      });
    }

    statusUpdates.forEach(function(update) {
      importSheet
        .getRange(update.row, processedIndex + 1)
        .setValue(update.value);
    });

    guardarResultadosImportacao_(
      spreadsheet,
      resultados
    );

    SpreadsheetApp.flush();
    Logger.log(JSON.stringify(resultados, null, 2));

    return resultados;
  } finally {
    lock.releaseLock();
  }
}


function guardarResultadosImportacao_(spreadsheet, resultados) {
  if (!resultados || resultados.length === 0) {
    return;
  }

  var headers = [
    'importId',
    'sourceRow',
    'success',
    'fullName',
    'email',
    'studentId',
    'accessCode',
    'error',
    'importedAt'
  ];

  var sheet = ensureSheetWithHeaders_(
    spreadsheet,
    'StudentImportResults',
    headers
  );

  var importId = Utilities.getUuid();
  var importedAt = new Date();

  var rows = resultados.map(function(resultado) {
    return [
      importId,
      resultado.row || '',
      resultado.success === true,
      resultado.fullName || '',
      resultado.email || '',
      resultado.studentId || '',
      resultado.accessCode || '',
      resultado.error || '',
      importedAt
    ];
  });

  sheet
    .getRange(
      sheet.getLastRow() + 1,
      1,
      rows.length,
      headers.length
    )
    .setValues(rows);

  sheet.autoResizeColumns(1, headers.length);
}


function limparLinhasProcessadasDaImportacao() {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    var spreadsheet = getCoursePlatformSpreadsheet_();
    var sheet = spreadsheet.getSheetByName(
      'StudentImport'
    );

    if (!sheet) {
      throw new Error(
        'A aba StudentImport não foi encontrada.'
      );
    }

    var values = sheet.getDataRange().getValues();

    if (values.length < 2) {
      return {
        success: true,
        deletedRows: 0
      };
    }

    var headers = values[0].map(function(value) {
      return String(value || '').trim();
    });

    var headerMap = getHeaderMap_(headers);

    requireHeaders_(
      headerMap,
      ['processed'],
      'StudentImport'
    );

    var deletedRows = 0;
    var removableStatuses = {
      YES: true,
      SIM: true,
      EXISTS: true,
      DUPLICATE: true
    };

    for (
      var rowIndex = values.length - 1;
      rowIndex >= 1;
      rowIndex--
    ) {
      var status = String(
        values[rowIndex][headerMap.processed] || ''
      )
        .trim()
        .toUpperCase();

      if (removableStatuses[status]) {
        sheet.deleteRow(rowIndex + 1);
        deletedRows++;
      }
    }

    return {
      success: true,
      deletedRows: deletedRows
    };
  } finally {
    lock.releaseLock();
  }
}


/* ========================================================================== */
/* REDEFINIÇÃO INDIVIDUAL                                                     */
/* ========================================================================== */

function redefinirCodigoDeEstudante(email, novoCodigo) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);

  try {
    email = normalizeEmailSafe_(email);
    novoCodigo = String(novoCodigo || '').trim();

    if (!email || !validateEmailBasic_(email)) {
      throw new Error(
        'Informe um email válido do estudante.'
      );
    }

    if (novoCodigo.length < 8) {
      throw new Error(
        'O novo código deve ter pelo menos 8 caracteres.'
      );
    }

    if (/\s/.test(novoCodigo)) {
      throw new Error(
        'O novo código não pode conter espaços.'
      );
    }

    if (typeof findOne_ !== 'function') {
      throw new Error(
        'A função findOne_() não foi encontrada.'
      );
    }

    var student = findOne_(
      getStudentsSheetName_(),
      { email: email }
    );

    if (!student) {
      throw new Error(
        'Estudante não encontrado: ' + email
      );
    }

    var accessCodeHash = hashAccessCodeOrFail_(
      novoCodigo
    );

    if (typeof updateRecordByKey_ !== 'function') {
      throw new Error(
        'A função updateRecordByKey_() não foi encontrada.'
      );
    }

    updateRecordByKey_(
      getStudentsSheetName_(),
      'studentId',
      student.studentId,
      {
        accessCode: accessCodeHash,
        updatedAt: new Date()
      }
    );

    if (
      typeof revokeSessionsForSubject_ === 'function'
    ) {
      revokeSessionsForSubject_(student.studentId);
    }

    guardarNovoCodigoNoHistorico_(
      student,
      novoCodigo,
      'RESET'
    );

    return {
      success: true,
      studentId: student.studentId,
      fullName: student.fullName || '',
      email: student.email || email,
      accessCode: novoCodigo
    };
  } finally {
    lock.releaseLock();
  }
}


function guardarNovoCodigoNoHistorico_(
  student,
  accessCode,
  operation
) {
  if (!student || !student.studentId) {
    throw new Error(
      'Dados inválidos para o histórico de credenciais.'
    );
  }

  accessCode = String(accessCode || '').trim();

  if (!accessCode) {
    throw new Error(
      'O accessCode do histórico está vazio.'
    );
  }

  var spreadsheet = getCoursePlatformSpreadsheet_();

  var headers = [
    'credentialId',
    'operation',
    'studentId',
    'fullName',
    'email',
    'accessCode',
    'createdAt'
  ];

  var sheet = ensureSheetWithHeaders_(
    spreadsheet,
    'CredentialHistory',
    headers
  );

  sheet.appendRow([
    Utilities.getUuid(),
    operation || 'CREATED',
    student.studentId,
    student.fullName || '',
    student.email || '',
    accessCode,
    new Date()
  ]);
}


/* ========================================================================== */
/* GERAÇÃO DE CREDENCIAIS PARA TODOS                                          */
/* ========================================================================== */

function gerarNovasCredenciaisParaTodos() {
  var lock = LockService.getScriptLock();

  if (!lock.tryLock(30000)) {
    throw new Error(
      'Já existe outra operação de credenciais em execução. Tente novamente.'
    );
  }

  var spreadsheet;
  var studentsSheet;
  var credentialsBatchInfo = null;
  var originalStudentData = null;

  try {
    spreadsheet = getCoursePlatformSpreadsheet_();

    var studentsSheetName = getStudentsSheetName_();
    studentsSheet = spreadsheet.getSheetByName(
      studentsSheetName
    );

    if (!studentsSheet) {
      throw new Error(
        'A aba ' +
        studentsSheetName +
        ' não foi encontrada.'
      );
    }

    var dataRange = studentsSheet.getDataRange();
    var values = dataRange.getValues();

    if (values.length < 2) {
      throw new Error(
        'Não existem estudantes registados.'
      );
    }

    var headers = values[0].map(function(header) {
      return String(header || '').trim();
    });

    var headerMap = getHeaderMap_(headers);

    requireHeaders_(
      headerMap,
      ['studentId', 'email', 'accessCode'],
      studentsSheetName
    );

    originalStudentData = values.map(function(row) {
      return row.slice();
    });

    var credentials = [];
    var usedCodes = {};
    var now = new Date();

    for (
      var rowIndex = 1;
      rowIndex < values.length;
      rowIndex++
    ) {
      var row = values[rowIndex];

      var studentId = String(
        row[headerMap.studentId] || ''
      ).trim();

      var email = normalizeEmailSafe_(
        row[headerMap.email]
      );

      var fullName =
        headerMap.fullName !== undefined
          ? String(row[headerMap.fullName] || '').trim()
          : '';

      var isBlankRow =
        !studentId &&
        !email &&
        !fullName;

      if (isBlankRow) {
        continue;
      }

      if (!studentId) {
        throw new Error(
          'studentId em falta na linha ' +
          (rowIndex + 1) +
          '.'
        );
      }

      if (!email || !validateEmailBasic_(email)) {
        throw new Error(
          'Email inválido na linha ' +
          (rowIndex + 1) +
          ': ' +
          email
        );
      }

      var newAccessCode = generateUniqueAccessCode_(
        usedCodes,
        10
      );

      var accessCodeHash = hashAccessCodeOrFail_(
        newAccessCode
      );

      values[rowIndex][headerMap.accessCode] =
        accessCodeHash;

      if (headerMap.status !== undefined) {
        values[rowIndex][headerMap.status] = 'ACTIVE';
      }

      if (headerMap.updatedAt !== undefined) {
        values[rowIndex][headerMap.updatedAt] = now;
      }

      credentials.push({
        sourceRow: rowIndex + 1,
        studentId: studentId,
        fullName: fullName,
        email: email,
        accessCode: newAccessCode
      });
    }

    if (credentials.length === 0) {
      throw new Error(
        'Nenhum estudante válido foi encontrado.'
      );
    }

    /*
     * 1. Guarda os códigos visíveis.
     * Caso a atualização seguinte falhe, este lote será removido.
     */
    credentialsBatchInfo =
      guardarCredenciaisGeradas_(
        spreadsheet,
        credentials
      );

    /*
     * 2. Atualiza os hashes em Students.
     */
    studentsSheet
      .getRange(
        1,
        1,
        values.length,
        headers.length
      )
      .setValues(values);

    SpreadsheetApp.flush();

    /*
     * 3. Invalida as sessões somente após concluir as gravações.
     */
    limparDadosDaAbaMantendoCabecalho_(
      spreadsheet,
      'Sessions'
    );

    SpreadsheetApp.flush();

    var response = {
      success: true,
      message:
        'Novas credenciais geradas com sucesso.',
      batchId: credentialsBatchInfo.batchId,
      total: credentials.length,
      credentials: credentials
    };

    Logger.log(JSON.stringify(response, null, 2));
    return response;
  } catch (error) {
    /*
     * Rollback do lote visível.
     */
    if (
      spreadsheet &&
      credentialsBatchInfo &&
      credentialsBatchInfo.batchId
    ) {
      try {
        removerLoteDeCredenciais_(
          spreadsheet,
          credentialsBatchInfo.batchId
        );
      } catch (rollbackCredentialsError) {
        console.error(
          'Falha ao remover lote no rollback: ' +
          errorMessage_(rollbackCredentialsError)
        );
      }
    }

    /*
     * Rollback da aba Students, caso já tenha sido alterada.
     */
    if (
      studentsSheet &&
      originalStudentData &&
      originalStudentData.length > 0
    ) {
      try {
        studentsSheet
          .getRange(
            1,
            1,
            originalStudentData.length,
            originalStudentData[0].length
          )
          .setValues(originalStudentData);

        SpreadsheetApp.flush();
      } catch (rollbackStudentsError) {
        console.error(
          'Falha ao restaurar Students no rollback: ' +
          errorMessage_(rollbackStudentsError)
        );
      }
    }

    throw new Error(
      'Não foi possível gerar as novas credenciais: ' +
      errorMessage_(error)
    );
  } finally {
    lock.releaseLock();
  }
}


function guardarCredenciaisGeradas_(
  spreadsheet,
  credentials
) {
  if (!credentials || credentials.length === 0) {
    throw new Error(
      'Nenhuma credencial foi recebida para guardar.'
    );
  }

  var headers = [
    'batchId',
    'credentialId',
    'sourceRow',
    'studentId',
    'fullName',
    'email',
    'accessCode',
    'generatedAt',
    'status'
  ];

  var sheet = ensureSheetWithHeaders_(
    spreadsheet,
    'NewCredentials',
    headers
  );

  var batchId = Utilities.getUuid();
  var generatedAt = new Date();

  var rows = credentials.map(function(item) {
    var visibleCode = String(
      item.accessCode || ''
    ).trim();

    if (!visibleCode) {
      throw new Error(
        'AccessCode vazio para o estudante: ' +
        (item.email || item.studentId || 'desconhecido')
      );
    }

    return [
      batchId,
      Utilities.getUuid(),
      item.sourceRow || '',
      item.studentId || '',
      item.fullName || '',
      item.email || '',
      visibleCode,
      generatedAt,
      'NEW'
    ];
  });

  var startRow = sheet.getLastRow() + 1;

  sheet
    .getRange(
      startRow,
      1,
      rows.length,
      headers.length
    )
    .setValues(rows);

  sheet.autoResizeColumns(1, headers.length);

  return {
    batchId: batchId,
    startRow: startRow,
    rowCount: rows.length
  };
}


function removerLoteDeCredenciais_(
  spreadsheet,
  batchId
) {
  var sheet = spreadsheet.getSheetByName(
    'NewCredentials'
  );

  if (!sheet || sheet.getLastRow() < 2) {
    return;
  }

  var values = sheet.getDataRange().getValues();
  var headers = values[0].map(function(value) {
    return String(value || '').trim();
  });

  var headerMap = getHeaderMap_(headers);

  if (headerMap.batchId === undefined) {
    return;
  }

  for (
    var rowIndex = values.length - 1;
    rowIndex >= 1;
    rowIndex--
  ) {
    if (
      String(values[rowIndex][headerMap.batchId] || '') ===
      String(batchId)
    ) {
      sheet.deleteRow(rowIndex + 1);
    }
  }
}


function limparDadosDaAbaMantendoCabecalho_(
  spreadsheet,
  sheetName
) {
  var sheet = spreadsheet.getSheetByName(sheetName);

  if (!sheet) {
    return;
  }

  var lastRow = sheet.getLastRow();
  var lastColumn = sheet.getLastColumn();

  if (lastRow > 1 && lastColumn > 0) {
    sheet
      .getRange(
        2,
        1,
        lastRow - 1,
        lastColumn
      )
      .clearContent();
  }
}


/* ========================================================================== */
/* TESTE CONTROLADO                                                           */
/* ========================================================================== */

/**
 * Testa apenas a geração local e o hash.
 * Não altera estudantes, sessões ou credenciais.
 */
function testarGeracaoDeAccessCode_() {
  var usedCodes = {};
  var results = [];

  for (var i = 0; i < 10; i++) {
    var code = generateUniqueAccessCode_(
      usedCodes,
      10
    );

    var hash = hashAccessCodeOrFail_(code);

    results.push({
      accessCode: code,
      length: code.length,
      hashGenerated: Boolean(hash),
      hashLength: hash.length
    });
  }

  Logger.log(JSON.stringify(results, null, 2));

  return {
    success: true,
    total: results.length,
    results: results
  };
}

function createReviewerFromEditor(
  fullName,
  email
) {
  email = normalizeEmail_(email);

  if (!fullName || !email) {
    throw apiError_(
      'REQUIRED_FIELDS',
      'Nome e email são obrigatórios.'
    );
  }

  var existing = findOne_(
    CP.SHEETS.ADMINS,
    { email: email }
  );

  if (existing) {
    throw apiError_(
      'ADMIN_ALREADY_EXISTS',
      'Já existe um administrador com este email.'
    );
  }

  var reviewer = {
    adminId: newId_('ADM'),
    fullName: stringValue_(fullName),
    email: email,
    role: CP.ADMIN_ROLES.REVIEWER,
    status: CP.STATUS.ACTIVE,
    createdAt: new Date(),
    updatedAt: new Date()
  };

  appendRecord_(
    CP.SHEETS.ADMINS,
    reviewer
  );

  return {
    success: true,
    reviewer: publicAdmin_(reviewer),
    message:
      'Avaliador criado. Utilize a chave administrativa mestra para iniciar sessão.'
  };
}
