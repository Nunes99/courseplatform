const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');


async function loadClient() {
  const source = await fs.readFile(path.resolve(__dirname, '../public/api.js'), 'utf8');
  const encoded = Buffer.from(source, 'utf8').toString('base64');
  return import(`data:text/javascript;base64,${encoded}`);
}


function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' }
  });
}


function memoryStorage() {
  const values = new Map();
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null;
    },
    setItem(key, value) {
      values.set(key, String(value));
    },
    removeItem(key) {
      values.delete(key);
    }
  };
}


function assertQuery(url, expectedQuery) {
  const parsed = new URL(url);
  assert.deepEqual(
    Object.fromEntries(parsed.searchParams.entries()),
    expectedQuery
  );
}


async function main() {
  const { CoursePlatformApi } = await loadClient();
  global.localStorage = memoryStorage();
  localStorage.setItem('courseSessionToken', 'student-session');

  const api = new CoursePlatformApi({
    apiUrl: 'https://courseplatform.example.test/api/index',
    courseId: 'COURSE-1'
  });

  const operations = [
    {
      name: 'publicCourseConfig',
      invoke: () => api.publicCourseConfig(),
      path: '/api/v1/catalog/courses/COURSE-1',
      query: {},
      action: 'publicCourseConfig',
      authenticated: false
    },
    {
      name: 'publicMediaConfig',
      invoke: () => api.publicMediaConfig(),
      path: '/api/v1/catalog/courses/COURSE-1/media',
      query: {},
      action: 'publicMediaConfig',
      authenticated: false
    },
    {
      name: 'studentHome',
      invoke: () => api.studentHome('COURSE-1', 'ENROLLMENT-1'),
      path: '/api/v1/students/me/home',
      query: { courseId: 'COURSE-1', enrollmentId: 'ENROLLMENT-1' },
      action: 'getStudentHome',
      authenticated: true
    },
    {
      name: 'dashboard',
      invoke: () => api.dashboard('COURSE-1', 'ENROLLMENT-1'),
      path: '/api/v1/students/me/dashboard',
      query: { courseId: 'COURSE-1', enrollmentId: 'ENROLLMENT-1' },
      action: 'getDashboard',
      authenticated: true
    },
    {
      name: 'myCourses',
      invoke: () => api.myCourses(),
      path: '/api/v1/students/me/courses',
      query: {},
      action: 'getMyCourses',
      authenticated: true
    },
    {
      name: 'getLesson',
      invoke: () => api.getLesson('LESSON-1', 'ENROLLMENT-1'),
      path: '/api/v1/students/me/lessons/LESSON-1',
      query: { enrollmentId: 'ENROLLMENT-1' },
      action: 'getLesson',
      authenticated: true
    }
  ];

  for (const operation of operations) {
    const typedCalls = [];
    global.fetch = async (url, options) => {
      typedCalls.push({ url: String(url), options });
      return jsonResponse({ success: true, data: { source: operation.name } });
    };

    const typedResult = await operation.invoke();
    assert.equal(typedResult.source, operation.name);
    assert.equal(typedCalls.length, 1);
    assert.equal(new URL(typedCalls[0].url).pathname, operation.path);
    assertQuery(typedCalls[0].url, operation.query);
    assert.equal(typedCalls[0].options.method, 'GET');
    if (operation.authenticated) {
      assert.equal(typedCalls[0].options.headers['x-session-token'], 'student-session');
    }

    const fallbackCalls = [];
    global.fetch = async (url, options) => {
      fallbackCalls.push({ url: String(url), options });
      if (fallbackCalls.length === 1) {
        return jsonResponse({
          success: false,
          error: { code: 'NOT_FOUND', message: 'Recurso não encontrado.', details: null }
        }, 404);
      }
      return jsonResponse({ success: true, data: { source: 'legacy' } });
    };

    const fallbackResult = await operation.invoke();
    assert.equal(fallbackResult.source, 'legacy');
    assert.equal(fallbackCalls.length, 2);
    if (operation.authenticated) {
      assert.equal(fallbackCalls[1].options.method, 'POST');
      const body = JSON.parse(fallbackCalls[1].options.body);
      assert.equal(body.action, operation.action);
      assert.equal(body.sessionToken, 'student-session');
      if (operation.name === 'myCourses') {
        assert.equal(body.courseId, 'COURSE-1');
      }
    } else {
      assert.equal(fallbackCalls[1].options.method, 'GET');
      assert.equal(new URL(fallbackCalls[1].url).searchParams.get('action'), operation.action);
    }

    let unavailableCalls = 0;
    global.fetch = async () => {
      unavailableCalls += 1;
      return jsonResponse({
        success: false,
        error: { code: 'DATABASE_UNAVAILABLE', message: 'Indisponível.', details: null }
      }, 503);
    };
    await assert.rejects(
      operation.invoke,
      (error) => error.code === 'DATABASE_UNAVAILABLE'
    );
    assert.equal(unavailableCalls, 1);
  }

  process.stdout.write('Seis leituras versionadas e respetivos fallbacks foram validados.\n');
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
