const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8765';

function student(index) {
  return {
    student: {
      studentId: `STUDENT-${index}`,
      publicStudentId: `STU-${String(index).padStart(5, '0')}`,
      fullName: `Estudante de Validação ${index}`,
      email: `student${index}@example.test`,
      status: index % 9 === 0 ? 'BLOCKED' : 'ACTIVE',
      organization: 'Organização de Teste',
      country: 'Moçambique',
      lastLoginAt: '2026-09-15T10:00:00Z'
    },
    enrollments: [{ courseTitle: 'Gestão de Projetos Energéticos', progressPercent: index % 101 }],
    memberships: []
  };
}

function course(index) {
  return {
    course: {
      courseId: `COURSE-${index}`,
      courseCode: `CRS-${String(index).padStart(3, '0')}`,
      title: `Curso profissional ${index}`,
      description: 'Descrição sintética para validar a organização da lista administrativa.',
      status: index % 6 === 0 ? 'INACTIVE' : 'ACTIVE'
    },
    lessonCount: 8,
    groupCount: 3,
    enrollmentCount: 42
  };
}

function staff(index) {
  return {
    adminId: `ADMIN-${index}`,
    fullName: `Membro de Staff ${index}`,
    email: `staff${index}@example.test`,
    role: index % 3 === 0 ? 'REVIEWER' : 'ADMIN',
    status: 'ACTIVE',
    updatedAt: '2026-09-15T10:00:00Z'
  };
}

const fixtures = {
  students: Array.from({ length: 50 }, (_, index) => student(index + 1)),
  courses: Array.from({ length: 24 }, (_, index) => course(index + 1)),
  staff: Array.from({ length: 30 }, (_, index) => staff(index + 1)),
  surveys: Array.from({ length: 12 }, (_, index) => ({
    course: course(index + 1).course,
    congratulationsMessage: 'Parabéns pela conclusão do curso.',
    surveyQuestions: [],
    questionCount: 10,
    updatedAt: '2026-09-15T10:00:00Z'
  })),
  responses: Array.from({ length: 12 }, (_, index) => ({
    requestId: `REQUEST-${index + 1}`,
    courseTitle: `Curso profissional ${index + 1}`,
    studentName: `Estudante ${index + 1}`,
    status: 'SUBMITTED',
    surveyAnswers: { q1: 'Muito bom' }
  })),
  notifications: Array.from({ length: 20 }, (_, index) => ({
    notificationId: `NOTIFICATION-${index + 1}`,
    studentName: `Estudante ${index + 1}`,
    title: 'Atualização académica',
    message: 'Mensagem sintética para validar a tabela.',
    createdAt: '2026-09-15T10:00:00Z',
    email: { status: 'SENT' },
    whatsapp: { status: 'NOT_REQUESTED' },
    telegram: { status: 'NOT_REQUESTED' },
    push: { status: 'NOT_REQUESTED' }
  }))
};

async function main() {
  const output = path.join(root, 'tmp/ui/stage7-admin-lists');
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
  });
  const errors = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, locale: 'pt-PT' });
    page.on('pageerror', (error) => errors.push(error.message));
    page.on('requestfailed', (request) => errors.push(`${request.url()} ${request.failure()?.errorText}`));
    await page.route('**/*', async (route) => {
      const url = new URL(route.request().url());
      if (url.origin !== new URL(base).origin) {
        const type = route.request().resourceType();
        const contentType = type === 'script' ? 'application/javascript'
          : type === 'stylesheet' ? 'text/css'
            : type === 'image' ? 'image/svg+xml' : 'application/json';
        const body = type === 'image'
          ? '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16"/>'
          : type === 'script' || type === 'stylesheet' ? '' : '{}';
        return route.fulfill({ contentType, body });
      }
      if (url.pathname === '/api/index') {
        return route.fulfill({
          contentType: 'application/json',
          body: JSON.stringify({ success: true, data: { mediaConfig: {}, rooms: [], unreadCount: 0 } })
        });
      }
      if (url.pathname === '/assets/css/styles.css') {
        const source = await fs.readFile(path.join(root, 'public/assets/css/styles.css'), 'utf8');
        return route.fulfill({ contentType: 'text/css', body: source });
      }
      if (url.pathname === '/admin.js') {
        const source = await fs.readFile(path.join(root, 'public/admin.js'), 'utf8');
        const hook = `
          window.__qaStage7 = (view, data) => {
            sessionStorage.setItem('courseAdminToken', 'qa');
            state.admin = { adminId: 'ADMIN-QA', fullName: 'Administrador QA', role: 'OWNER' };
            renderAdminShell();
            setActiveAdminView(view);
            if (view === 'students') {
              state.students = data.students;
              state.studentSummary = { active: 420, blocked: 20, completed: 180, averageProgress: 64 };
              Object.assign(state.studentPagination, { returned: 50, total: 507, hasMore: true, nextCursor: 'next' });
              renderStudentsV2();
            } else if (view === 'courses') {
              state.courseMode = 'list';
              state.courses = data.courses;
              state.courseSummary = { active: 70, inactive: 10, lessons: 640, groups: 240 };
              Object.assign(state.coursePagination, { returned: 24, total: 80, hasMore: true, nextCursor: 'next' });
              renderCourseList();
            } else if (view === 'staff') {
              state.staff = data.staff;
              state.staffSummary = { active: 30, reviewers: 10 };
              Object.assign(state.staffPagination, { returned: 30, total: 72, hasMore: true, nextCursor: 'next' });
              renderStaff();
            } else if (view === 'surveys') {
              state.certificateSurveys = data.surveys;
              state.certificateSurveyResponses = data.responses;
              Object.assign(state.surveyPagination.definitions, { returned: 12, total: 40, hasMore: true, nextCursor: 'next' });
              Object.assign(state.surveyPagination.responses, { returned: 12, total: 90, hasMore: true, nextCursor: 'next' });
              renderCertificateSurveys();
            } else if (view === 'notifications') {
              state.students = data.students.slice(0, 20);
              state.notificationStudentTotal = 507;
              state.notificationLog = {
                notifications: data.notifications,
                summary: {},
                whatsappConfiguration: {}, emailConfiguration: {}, telegramConfiguration: {}, pushConfiguration: {},
                notificationTemplates: []
              };
              Object.assign(state.notificationPagination, { returned: 20, hasMore: true, nextCursor: 'next' });
              renderNotificationManagement();
            }
            clearInterval(adminPresencePollId);
          };
        `;
        return route.fulfill({ contentType: 'application/javascript', body: source + hook });
      }
      return route.continue();
    });
    await page.addInitScript((url) => { window.COURSE_PLATFORM_API_URL = `${url}/api/index`; }, base);
    await page.goto(`${base}/admin.html`);
    await page.waitForFunction(() => [...document.styleSheets].some((sheet) => {
      try {
        return sheet.href?.includes('/assets/css/styles.css') && sheet.cssRules.length > 100;
      } catch (_error) {
        return false;
      }
    }));
    await page.waitForFunction(() => Boolean(window.__qaStage7));

    for (const view of ['students', 'courses', 'staff', 'surveys', 'notifications']) {
      await page.evaluate(({ selectedView, data }) => window.__qaStage7(selectedView, data), {
        selectedView: view,
        data: fixtures
      });
      for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
        await page.setViewportSize({ width, height });
        await page.waitForTimeout(100);
        const geometry = await page.evaluate(() => {
          const pagination = [...document.querySelectorAll('.cursor-pagination')];
          const buttons = [...document.querySelectorAll('button')];
          const overflowing = [...document.querySelectorAll('body *')]
            .map((node) => {
              const rect = node.getBoundingClientRect();
              return {
                tag: node.tagName.toLowerCase(),
                id: node.id,
                className: typeof node.className === 'string' ? node.className : '',
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                width: Math.round(rect.width)
              };
            })
            .filter((item) => item.width > 0 && (item.left < -1 || item.right > window.innerWidth + 1))
            .slice(0, 12);
          return {
            pageWidth: document.documentElement.scrollWidth,
            viewportWidth: window.innerWidth,
            mobileMedia: window.matchMedia('(max-width: 760px)').matches,
            tableDisplay: document.querySelector('.student-list-table')
              ? getComputedStyle(document.querySelector('.student-list-table')).display
              : '',
            tableMinWidth: document.querySelector('.student-list-table')
              ? getComputedStyle(document.querySelector('.student-list-table')).minWidth
              : '',
            tableHeadDisplay: document.querySelector('.student-list-table thead')
              ? getComputedStyle(document.querySelector('.student-list-table thead')).display
              : '',
            paginations: pagination.length,
            paginationContained: pagination.every((node) => {
              const rect = node.getBoundingClientRect();
              return rect.left >= 0 && rect.right <= window.innerWidth;
            }),
            buttonOverflow: buttons.some((node) => node.scrollWidth > node.clientWidth + 1),
            overflowing
          };
        });
        await page.screenshot({ path: path.join(output, `${view}-${label}.png`), fullPage: true });
        if (geometry.pageWidth > geometry.viewportWidth) {
          console.error(`${view}/${label} overflow`, geometry);
        }
        assert.ok(geometry.pageWidth <= geometry.viewportWidth, `${view}/${label}: horizontal overflow`);
        assert.ok(geometry.paginations >= 1, `${view}/${label}: pagination missing`);
        assert.equal(geometry.paginationContained, true, `${view}/${label}: pagination outside viewport`);
        assert.equal(geometry.buttonOverflow, false, `${view}/${label}: button text overflow`);
      }
    }

    assert.deepEqual(errors, []);
    console.log('Stage 7 admin lists passed desktop/mobile layout and pagination checks.');
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
