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


async function main() {
  const { CoursePlatformApi } = await loadClient();
  const api = new CoursePlatformApi({
    apiUrl: 'https://courseplatform.example.test/api/index',
    courseId: 'COURSE-1'
  });

  const typedCalls = [];
  global.fetch = async (url, options) => {
    typedCalls.push({ url: String(url), options });
    return jsonResponse({ success: true, data: { mediaConfig: { logoUrl: 'typed', videos: [] } } });
  };
  const typedResult = await api.publicMediaConfig();
  assert.equal(typedResult.mediaConfig.logoUrl, 'typed');
  assert.equal(typedCalls.length, 1);
  assert.equal(new URL(typedCalls[0].url).pathname, '/api/v1/catalog/courses/COURSE-1/media');
  assert.equal(typedCalls[0].options.method, 'GET');

  const fallbackCalls = [];
  global.fetch = async (url, options) => {
    fallbackCalls.push({ url: String(url), options });
    if (fallbackCalls.length === 1) {
      return jsonResponse({
        success: false,
        error: { code: 'NOT_FOUND', message: 'Recurso não encontrado.', details: null }
      }, 404);
    }
    return jsonResponse({ success: true, data: { mediaConfig: { logoUrl: 'legacy', videos: [] } } });
  };
  const fallbackResult = await api.publicMediaConfig();
  assert.equal(fallbackResult.mediaConfig.logoUrl, 'legacy');
  assert.equal(fallbackCalls.length, 2);
  assert.equal(new URL(fallbackCalls[1].url).searchParams.get('action'), 'publicMediaConfig');

  global.fetch = async () => jsonResponse({
    success: false,
    error: { code: 'DATABASE_UNAVAILABLE', message: 'Indisponível.', details: null }
  }, 503);
  await assert.rejects(
    () => api.publicMediaConfig(),
    (error) => error.code === 'DATABASE_UNAVAILABLE'
  );

  process.stdout.write('Cliente versionado e fallback legado validados.\n');
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
