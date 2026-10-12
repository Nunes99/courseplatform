const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  getItem(key) {
    return this.values.has(key) ? this.values.get(key) : null;
  }

  setItem(key, value) {
    this.values.set(key, String(value));
  }

  removeItem(key) {
    this.values.delete(key);
  }
}

async function main() {
  global.sessionStorage = new MemoryStorage();
  global.localStorage = new MemoryStorage();
  global.navigator = { userAgent: 'm3-cache-verifier' };

  const sourcePath = process.argv[2]
    ? path.resolve(process.argv[2])
    : path.resolve(__dirname, '../public/api.js');
  const source = fs.readFileSync(sourcePath, 'utf8');
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source).toString('base64')}`;
  const { CoursePlatformApi } = await import(moduleUrl);
  const api = new CoursePlatformApi({ apiUrl: 'https://example.invalid/api', apiCacheTtlMs: 60000 });
  const requests = [];
  api.adminRequest = async (action, payload) => {
    const organizationId = sessionStorage.getItem('courseAdminOrganizationId');
    requests.push({ action, organizationId, payload });
    return { organizationId, requestNumber: requests.length };
  };

  sessionStorage.setItem('courseAdminToken', 'shared-test-token');
  sessionStorage.setItem('courseAdminOrganizationId', 'ORG-A');
  const firstA = await api.cachedAdminRequest('adminListCourses', { query: 'curso' });

  sessionStorage.setItem('courseAdminOrganizationId', 'ORG-B');
  const firstB = await api.cachedAdminRequest('adminListCourses', { query: 'curso' });
  assert.equal(firstA.organizationId, 'ORG-A');
  assert.equal(firstB.organizationId, 'ORG-B');
  assert.equal(requests.length, 2);

  api.clearCache('organization:ORG-B');
  const secondB = await api.cachedAdminRequest('adminListCourses', { query: 'curso' });
  assert.equal(secondB.organizationId, 'ORG-B');
  assert.equal(requests.length, 3);

  sessionStorage.setItem('courseAdminOrganizationId', 'ORG-A');
  const secondA = await api.cachedAdminRequest('adminListCourses', { query: 'curso' });
  assert.deepEqual(secondA, firstA);
  assert.equal(requests.length, 3, 'Invalidar B não pode invalidar o cache de A.');

  console.log('Cache M3 validado: namespaces A/B e invalidação institucional estão isolados.');
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
