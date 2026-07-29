export class ApiError extends Error {
  constructor(message, code = 'API_ERROR', details = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map((item) => stableStringify(item)).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(',')}}`;
  }
  return JSON.stringify(value);
}

function isCacheOptions(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const keys = Object.keys(value);
  return Boolean(keys.length) && keys.every((key) => ['force', 'ttlMs'].includes(key));
}

function splitPayloadOptions(payload = {}, options = {}) {
  if (isCacheOptions(payload) && !Object.keys(options || {}).length) {
    return [{}, payload];
  }
  return [payload || {}, options || {}];
}

export class CoursePlatformApi {
  constructor(config) {
    this.config = config;
    this.apiUrl = String(config.apiUrl || '').trim();
    this.courseId = config.courseId || '';
    this.cache = new Map();
    this.cacheVersion = 0;
    this.cacheTtlMs = Number(config.apiCacheTtlMs || 45000);

    if (!this.apiUrl || this.apiUrl.includes('CHANGE_ME') || this.apiUrl.includes('YOUR_API_URL')) {
      throw new ApiError(
        'A URL da API ainda nao foi configurada em config.js.',
        'API_URL_NOT_CONFIGURED'
      );
    }
  }

  async publicGet(action, params = {}) {
    const url = new URL(this.apiUrl);
    url.searchParams.set('action', action);

    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value));
      }
    });

    let response;
    try {
      response = await fetch(url.toString(), {
        method: 'GET',
        redirect: 'follow',
        cache: 'no-store'
      });
    } catch (error) {
      throw this.networkError(error);
    }

    return this.parseResponse(response);
  }

  async request(action, payload = {}) {
    let response;

    try {
      response = await fetch(this.apiUrl, {
        method: 'POST',
        redirect: 'follow',
        cache: 'no-store',
        headers: {
          'Content-Type': 'text/plain;charset=utf-8'
        },
        body: JSON.stringify({ action, ...payload })
      });
    } catch (error) {
      throw this.networkError(error);
    }

    return this.parseResponse(response);
  }

  networkError(error) {
    return new ApiError(
      'Nao foi possivel comunicar com a API. Confirme a URL em config.js e as variaveis do backend.',
      'NETWORK_ERROR',
      { originalMessage: error.message }
    );
  }

  async parseResponse(response) {
    let result;
    try {
      result = await response.json();
    } catch {
      if (!response.ok) {
        throw new ApiError(`Erro HTTP ${response.status}.`, 'HTTP_ERROR');
      }
      throw new ApiError(
        'A API nao devolveu JSON valido. Confirme que a URL aponta para /api/index no backend Python.',
        'INVALID_API_RESPONSE'
      );
    }

    if (!response.ok || !result.success) {
      throw new ApiError(
        result.error?.message || `Erro HTTP ${response.status}.`,
        result.error?.code || 'HTTP_ERROR',
        result.error?.details || null
      );
    }

    return result.data;
  }

  health() {
    return this.publicGet('health');
  }

  publicCourseConfig() {
    return this.publicGet('publicCourseConfig', { courseId: this.courseId });
  }

  publicMediaConfig() {
    return this.publicGet('publicMediaConfig', { courseId: this.courseId });
  }

  verifyCertificate(code) {
    return this.publicGet('verifyCertificate', { code });
  }

  async login(email, accessCode) {
    const data = await this.request('login', {
      email,
      accessCode,
      courseId: this.courseId,
      userAgent: navigator.userAgent
    });
    localStorage.setItem('courseSessionToken', data.sessionToken);
    return data;
  }

  recoverStudentAccess(email, publicStudentId) {
    return this.request('recoverStudentAccess', {
      email,
      publicStudentId
    });
  }

  async logout() {
    const sessionToken = this.studentToken();
    try {
      return await this.request('logout', { sessionToken });
    } finally {
      localStorage.removeItem('courseSessionToken');
    }
  }

  dashboard(courseId = this.courseId) {
    return this.studentRequest('getDashboard', { courseId });
  }

  studentHome(courseId = this.courseId) {
    return this.studentRequest('getStudentHome', { courseId });
  }

  myCourses() {
    return this.studentRequest('getMyCourses', { courseId: this.courseId });
  }

  async updateMyProfile(profile) {
    const payload = { ...profile };
    const profilePhotoFile = payload.profilePhotoFile;
    delete payload.profilePhotoFile;

    if (profilePhotoFile && profilePhotoFile.size) {
      const prepared = await prepareProfilePhoto(profilePhotoFile, this.config);
      payload.profilePhotoFileName = prepared.fileName;
      payload.profilePhotoMimeType = prepared.mimeType;
      payload.profilePhotoBase64 = prepared.base64Data;
    }

    return this.studentRequest('updateMyProfile', payload);
  }

  async changeMyAccessCode(currentAccessCode, newAccessCode) {
    const result = await this.studentRequest('changeMyAccessCode', {
      currentAccessCode,
      newAccessCode
    });

    if (result.requiresLogin) {
      localStorage.removeItem('courseSessionToken');
    }

    return result;
  }

  getLesson(lessonId) {
    return this.studentRequest('getLesson', { lessonId });
  }

  startAttempt(lessonId) {
    return this.studentRequest('startAttempt', { lessonId });
  }

  saveAnswer(attemptId, questionId, values = {}) {
    return this.studentRequest('saveAnswer', {
      attemptId,
      questionId,
      answerText: values.answerText || '',
      selectedOptionId: values.selectedOptionId || ''
    });
  }

  async uploadFile(attemptId, file) {
    const prepared = await prepareFileForUpload(file, this.config);
    return this.studentRequest('uploadFile', {
      attemptId,
      fileName: prepared.fileName,
      mimeType: prepared.mimeType,
      base64Data: prepared.base64Data
    });
  }

  deleteUploadedFile(fileId) {
    return this.studentRequest('deleteUploadedFile', { fileId });
  }

  submitAttempt(attemptId) {
    return this.studentRequest('submitAttempt', { attemptId });
  }

  attemptStatus(attemptId) {
    return this.studentRequest('getAttemptStatus', { attemptId });
  }

  certificate(courseId = this.courseId) {
    return this.studentRequest('getMyCertificate', { courseId });
  }

  certifications(courseId = this.courseId) {
    return this.studentRequest('getMyCertifications', { courseId });
  }

  requestProfessionalCertificate(courseId = this.courseId, surveyAnswers = {}) {
    return this.studentRequest('requestProfessionalCertificate', {
      courseId,
      surveyAnswers
    });
  }

  async submitProfessionalCertificatePayment(requestId, file) {
    const prepared = await prepareFileForUpload(file, this.config);
    return this.studentRequest('submitProfessionalCertificatePayment', {
      requestId,
      receiptFileName: prepared.fileName,
      receiptMimeType: prepared.mimeType,
      receiptBase64: prepared.base64Data
    });
  }

  recordCertificateDownload(certificateId) {
    return this.studentRequest('recordCertificateDownload', { certificateId });
  }

  mediaConfig(courseId = this.courseId) {
    return this.studentRequest('getMediaConfig', { courseId });
  }

  studentRequest(action, payload = {}) {
    return this.request(action, {
      sessionToken: this.studentToken(),
      ...payload
    });
  }

  studentToken() {
    const token = localStorage.getItem('courseSessionToken');
    if (!token) {
      throw new ApiError('Inicie sessão para continuar.', 'SESSION_REQUIRED');
    }
    return token;
  }

  hasStudentSession() {
    return Boolean(localStorage.getItem('courseSessionToken'));
  }

  async adminLogin(email, adminKey) {
    const data = await this.request('adminLogin', {
      email,
      adminKey,
      userAgent: navigator.userAgent
    });
    sessionStorage.setItem('courseAdminToken', data.adminToken);
    return data;
  }

  recoverAdminAccess(email, recoveryKey) {
    return this.request('recoverAdminAccess', {
      email,
      recoveryKey
    });
  }

  async adminLogout() {
    const adminToken = this.adminToken();
    try {
      return await this.request('adminLogout', { adminToken });
    } finally {
      this.clearCache();
      sessionStorage.removeItem('courseAdminToken');
    }
  }

  adminMe() {
    return this.adminRequest('adminMe');
  }

  adminStaff(options = {}) {
    return this.cachedAdminRequest('adminListStaff', {}, options);
  }

  adminstaff(options = {}) {
    return this.adminStaff(options);
  }

  adminSaveStaff(payload) {
    const { adminId, ...rest } = payload;
    return this.mutateAdmin('adminSaveStaff', {
      ...rest,
      targetAdminId: adminId || ''
    });
  }

  adminSetStaffStatus(adminId, status) {
    return this.mutateAdmin('adminSetStaffStatus', {
      targetAdminId: adminId,
      status
    });
  }

  adminPending(filters = {}, options = {}) {
    const [payload, cacheOptions] = splitPayloadOptions(filters, options);
    return this.cachedAdminRequest('adminListPendingSubmissions', payload, cacheOptions);
  }

  adminSubmissions(filters = {}, options = {}) {
    return this.cachedAdminRequest('adminListSubmissions', filters, options);
  }

  adminSubmission(attemptId, options = {}) {
    return this.cachedAdminRequest('adminGetSubmission', { attemptId }, options);
  }

  adminReview(payload) {
    return this.mutateAdmin('adminReviewSubmission', payload);
  }

  adminAuthorizeRetry(attemptId) {
    return this.mutateAdmin('adminAuthorizeRetry', { attemptId });
  }

  adminStudents(filters = {}, options = {}) {
    const [payload, cacheOptions] = splitPayloadOptions(filters, options);
    return this.cachedAdminRequest('adminListStudents', payload, cacheOptions);
  }

  adminStudentDetails(studentId, options = {}) {
    return this.cachedAdminRequest('adminGetStudentDetails', { studentId }, options);
  }

  adminCreateStudent(payload) {
    return this.mutateAdmin('adminCreateStudent', payload);
  }

  adminSetStudentStatus(studentId, status) {
    return this.mutateAdmin('adminSetStudentStatus', { studentId, status });
  }

  adminResetAccess(studentId) {
    return this.mutateAdmin('adminResetStudentAccessCode', { studentId });
  }

  adminRestoreCredentials(payload = {}) {
    return this.mutateAdmin('adminRestoreCredentials', payload);
  }

  adminCourseStructure(options = {}) {
    return this.cachedAdminRequest('adminGetCourseStructure', {
      courseId: this.courseId
    }, options);
  }

  adminCourses(filters = {}, options = {}) {
    const [payload, cacheOptions] = splitPayloadOptions(filters, options);
    return this.cachedAdminRequest('adminListCourses', payload, cacheOptions);
  }

  adminCourseStructureFor(courseId, options = {}) {
    return this.cachedAdminRequest('adminGetCourseStructure', {
      courseId: courseId || this.courseId
    }, options);
  }

  adminSaveCourse(payload) {
    return this.mutateAdmin('adminSaveCourse', payload);
  }

  adminSaveLesson(payload) {
    return this.mutateAdmin('adminSaveLesson', payload);
  }

  adminSaveLessonContent(payload) {
    return this.mutateAdmin('adminSaveLessonContent', payload);
  }

  adminGroups(courseId = '', filters = {}, options = {}) {
    const [payload, cacheOptions] = splitPayloadOptions(filters, options);
    return this.cachedAdminRequest('adminListGroups', {
      courseId,
      ...payload
    }, cacheOptions);
  }

  adminSaveGroup(payload) {
    return this.mutateAdmin('adminSaveGroup', payload);
  }

  adminAssignStudentsToGroup(groupId, studentIds) {
    return this.mutateAdmin('adminAssignStudentsToGroup', { groupId, studentIds });
  }

  adminSetLessonAccess(payload) {
    return this.mutateAdmin('adminSetLessonAccess', payload);
  }

  adminCertificateRequests(filters = {}, options = {}) {
    return this.cachedAdminRequest('adminListCertificateRequests', filters, options);
  }

  adminReviewCertificateRequest(payload) {
    return this.mutateAdmin('adminReviewCertificateRequest', payload);
  }

  adminCertificateSettings(courseId = this.courseId, options = {}) {
    return this.cachedAdminRequest('adminGetCertificateSettings', { courseId }, options);
  }

  adminSaveCertificateSettings(payload) {
    return this.mutateAdmin('adminSaveCertificateSettings', payload);
  }

  adminMediaConfig(options = {}) {
    return this.cachedAdminRequest('adminGetMediaConfig', {
      courseId: this.courseId
    }, options);
  }

  adminSaveMediaConfig(mediaConfig) {
    return this.mutateAdmin('adminSaveMediaConfig', {
      courseId: this.courseId,
      mediaConfig
    });
  }

  cachedAdminRequest(action, payload = {}, options = {}) {
    const ttlMs = Number(options.ttlMs || this.cacheTtlMs);
    const key = this.cacheKey('admin', action, {
      adminToken: this.adminToken(),
      ...payload
    });
    const cached = this.cache.get(key);
    const now = Date.now();
    const cacheVersion = this.cacheVersion;

    if (!options.force && cached) {
      if (cached.promise) return cached.promise;
      if (cached.expiresAt > now) return Promise.resolve(cached.data);
    }

    const promise = this.adminRequest(action, payload)
      .then((data) => {
        if (this.cacheVersion === cacheVersion) {
          this.cache.set(key, {
            data,
            expiresAt: Date.now() + ttlMs
          });
        }
        return data;
      })
      .catch((error) => {
        this.cache.delete(key);
        throw error;
      });

    this.cache.set(key, {
      promise,
      expiresAt: now + ttlMs
    });

    return promise;
  }

  mutateAdmin(action, payload = {}) {
    return this.adminRequest(action, payload).then((data) => {
      this.clearCache();
      return data;
    });
  }

  adminRequest(action, payload = {}) {
    return this.request(action, {
      adminToken: this.adminToken(),
      ...payload
    });
  }

  cacheKey(scope, action, payload = {}) {
    return `${scope}:${action}:${stableStringify(payload)}`;
  }

  clearCache() {
    this.cacheVersion += 1;
    this.cache.clear();
  }

  adminToken() {
    const token = sessionStorage.getItem('courseAdminToken');
    if (!token) {
      throw new ApiError('Inicie sessão como administrador.', 'ADMIN_SESSION_REQUIRED');
    }
    return token;
  }

  hasAdminSession() {
    return Boolean(sessionStorage.getItem('courseAdminToken'));
  }
}

async function prepareFileForUpload(file, config) {
  if (file.type.startsWith('image/') && file.type !== 'image/gif') {
    const optimized = await optimizeImage(
      file,
      config.maxImageDimension || 1800,
      config.imageQuality || 0.84
    );

    return {
      fileName: normalizedImageName(file.name, optimized.type),
      mimeType: optimized.type,
      base64Data: await blobToBase64(optimized)
    };
  }

  return {
    fileName: file.name,
    mimeType: file.type || 'application/octet-stream',
    base64Data: await blobToBase64(file)
  };
}

async function prepareProfilePhoto(file, config) {
  if (!file.type.startsWith('image/')) {
    throw new ApiError('Selecione uma imagem JPG, PNG ou WebP.', 'INVALID_PROFILE_PHOTO');
  }

  const optimized = await optimizeImage(
    file,
    config.profilePhotoMaxDimension || 720,
    config.profilePhotoQuality || 0.82
  );

  return {
    fileName: normalizedImageName(file.name || 'profile-photo', optimized.type),
    mimeType: optimized.type,
    base64Data: await blobToBase64(optimized)
  };
}

function normalizedImageName(originalName, mimeType) {
  const stem = originalName.replace(/\.[^.]+$/, '');
  const extension = mimeType === 'image/png' ? 'png' : 'jpg';
  return `${stem}.${extension}`;
}

function optimizeImage(file, maxDimension, quality) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(file);

    image.onload = () => {
      try {
        const scale = Math.min(
          1,
          maxDimension / Math.max(image.naturalWidth, image.naturalHeight)
        );
        const width = Math.round(image.naturalWidth * scale);
        const height = Math.round(image.naturalHeight * scale);
        const canvas = document.createElement('canvas');

        canvas.width = width;
        canvas.height = height;

        const context = canvas.getContext('2d', { alpha: false });
        context.drawImage(image, 0, 0, width, height);

        canvas.toBlob(
          (blob) => {
            URL.revokeObjectURL(objectUrl);
            if (!blob) {
              reject(new Error('Não foi possível otimizar a imagem.'));
              return;
            }
            resolve(blob);
          },
          'image/jpeg',
          quality
        );
      } catch (error) {
        URL.revokeObjectURL(objectUrl);
        reject(error);
      }
    };

    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('A imagem selecionada não pôde ser lida.'));
    };

    image.src = objectUrl;
  });
}

function blobToBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || '').split(',').pop());
    reader.onerror = () => reject(reader.error || new Error('Falha ao ler o ficheiro.'));
    reader.readAsDataURL(blob);
  });
}
