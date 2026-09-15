const DASHBOARD_ROUTES = new Set(['courses', 'lessons', 'submissions', 'grades']);


export function parseStudentRoute(hashValue) {
  const hash = String(hashValue || '').replace(/^#\/?/, '');
  const [name = '', value = ''] = hash.split('/');
  return { name, value };
}


export function isDashboardRoute(name) {
  return DASHBOARD_ROUTES.has(name);
}
