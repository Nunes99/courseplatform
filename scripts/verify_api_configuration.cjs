const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const vm = require('node:vm');


async function resolveConfig({ hostname, origin, savedUrl = '', overrideUrl = '' }) {
  const source = await fs.readFile(path.resolve(__dirname, '../public/config.js'), 'utf8');
  const context = {
    localStorage: {
      getItem(key) {
        return key === 'coursePlatformApiUrl' ? savedUrl || null : null;
      }
    },
    window: {
      COURSE_PLATFORM_API_URL: overrideUrl,
      location: { hostname, origin }
    }
  };
  vm.runInNewContext(source, context);
  return context.window.COURSE_PLATFORM_CONFIG;
}


async function main() {
  const production = await resolveConfig({
    hostname: 'lmtwebnairs.vercel.app',
    origin: 'https://lmtwebnairs.vercel.app',
    savedUrl: 'https://legacy.example.test/api/index'
  });
  assert.equal(production.apiUrl, 'https://lmtwebnairs.vercel.app/api/index');
  assert.equal(production.requestTimeoutMs, 30000);

  const local = await resolveConfig({
    hostname: 'localhost',
    origin: 'http://localhost:8000',
    savedUrl: 'http://localhost:9000/api/index'
  });
  assert.equal(local.apiUrl, 'http://localhost:9000/api/index');

  const publicFallback = await resolveConfig({
    hostname: 'nunes99.github.io',
    origin: 'https://nunes99.github.io'
  });
  assert.equal(publicFallback.apiUrl, 'https://lmtwebnairs.vercel.app/api/index');

  const explicit = await resolveConfig({
    hostname: 'lmtwebnairs.vercel.app',
    origin: 'https://lmtwebnairs.vercel.app',
    savedUrl: 'https://legacy.example.test/api/index',
    overrideUrl: 'https://preview.example.test/api/index'
  });
  assert.equal(explicit.apiUrl, 'https://preview.example.test/api/index');

  process.stdout.write('Seleção segura do endpoint da API validada em produção e desenvolvimento.\n');
}


main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
