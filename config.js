const COURSE_PLATFORM_API_URL =
  window.COURSE_PLATFORM_API_URL ||
  localStorage.getItem('coursePlatformApiUrl') ||
  (window.location.hostname.endsWith('.vercel.app')
    ? `${window.location.origin}/api`
    : 'https://script.google.com/macros/s/AKfycbxLAzx2IQ9n0uel0ehjagoG67ZwWv4EFFhBuuyCvd9eA22q6D8WaoRM399jhLeOsITA6w/exec');

window.COURSE_PLATFORM_CONFIG = Object.freeze({
  apiUrl: COURSE_PLATFORM_API_URL,
  courseId: 'COURSE-EAPI-001',
  appName: 'LMTWEBNAIRS Summer School 2026',
  organizationName: 'LMTWEBNAIRS Summer School',
  publicAppUrl: 'https://nunes99.github.io/courseplatform/',
  institutionalUrl: 'https://lmtwebnairs.com/summer_school_2026',
  supportEmail: '',
  pollIntervalMs: 60000,
  maxImageDimension: 1800,
  imageQuality: 0.84
});
