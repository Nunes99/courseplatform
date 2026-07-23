export class ApiError extends Error {
  constructor(message, code = 'API_ERROR', details = null) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.details = details;
  }
}

export class CoursePlatformApi {
  constructor(config) {
    this.config = config;
    this.apiUrl = String(config.apiUrl || '').trim();
    this.courseId = config.courseId || '';

    if (!this.apiUrl || this.apiUrl.includes('COLE_AQUI')) {
      throw new ApiError(
        'A URL da API ainda não foi configurada em assets/js/config.js.',
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
      'Não foi possível comunicar com a API. Confirme a publicação do Apps Script e execute o teste de ligação.',
      'NETWORK_ERROR',
      { originalMessage: error.message }
    );
  }

  async parseResponse(response) {
    if (!response.ok) {
      throw new ApiError(`Erro HTTP ${response.status}.`, 'HTTP_ERROR');
    }

    let result;
    try {
      result = await response.json();
    } catch {
      throw new ApiError(
        'A API não devolveu JSON válido. Confirme que está a usar a URL terminada em /exec.',
        'INVALID_API_RESPONSE'
      );
    }

    if (!result.success) {
      throw new ApiError(
        result.error?.message || 'Erro na API.',
        result.error?.code || 'API_ERROR',
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

  async logout() {
    const sessionToken = this.studentToken();
    try {
      return await this.request('logout', { sessionToken });
    } finally {
      localStorage.removeItem('courseSessionToken');
    }
  }

  dashboard() {
    return this.studentRequest('getDashboard', { courseId: this.courseId });
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

  certificate() {
    return this.studentRequest('getMyCertificate', { courseId: this.courseId });
  }

  mediaConfig() {
    return this.studentRequest('getMediaConfig', { courseId: this.courseId });
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

  async adminLogout() {
    const adminToken = this.adminToken();
    try {
      return await this.request('adminLogout', { adminToken });
    } finally {
      sessionStorage.removeItem('courseAdminToken');
    }
  }

  adminPending() {
    return this.adminRequest('adminListPendingSubmissions');
  }

  adminSubmission(attemptId) {
    return this.adminRequest('adminGetSubmission', { attemptId });
  }

  adminReview(payload) {
    return this.adminRequest('adminReviewSubmission', payload);
  }

  adminAuthorizeRetry(attemptId) {
    return this.adminRequest('adminAuthorizeRetry', { attemptId });
  }

  adminStudents() {
    return this.adminRequest('adminListStudents');
  }

  adminCreateStudent(payload) {
    return this.adminRequest('adminCreateStudent', payload);
  }

  adminSetStudentStatus(studentId, status) {
    return this.adminRequest('adminSetStudentStatus', { studentId, status });
  }

  adminResetAccess(studentId) {
    return this.adminRequest('adminResetStudentAccessCode', { studentId });
  }

  adminCourseStructure() {
    return this.adminRequest('adminGetCourseStructure', {
      courseId: this.courseId
    });
  }

  adminMediaConfig() {
    return this.adminRequest('adminGetMediaConfig', {
      courseId: this.courseId
    });
  }

  adminSaveMediaConfig(mediaConfig) {
    return this.adminRequest('adminSaveMediaConfig', {
      courseId: this.courseId,
      mediaConfig
    });
  }

  adminRequest(action, payload = {}) {
    return this.request(action, {
      adminToken: this.adminToken(),
      ...payload
    });
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
