const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const sourceRoot = path.join(root, 'public');
const targetRoot = path.join(root, 'backend', 'courseplatform', 'static');
const checkOnly = process.argv.includes('--check');

function filesBelow(directory, base = directory) {
  if (!fs.existsSync(directory)) return [];
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    return entry.isDirectory() ? filesBelow(absolute, base) : [path.relative(base, absolute)];
  }).sort();
}

function digest(filePath) {
  return crypto.createHash('sha256').update(fs.readFileSync(filePath)).digest('hex');
}

function drift() {
  const sourceFiles = filesBelow(sourceRoot);
  const targetFiles = filesBelow(targetRoot);
  const differences = [];
  const sourceSet = new Set(sourceFiles);
  const targetSet = new Set(targetFiles);

  for (const relative of sourceFiles) {
    if (!targetSet.has(relative)) {
      differences.push(`em falta: ${relative}`);
    } else if (digest(path.join(sourceRoot, relative)) !== digest(path.join(targetRoot, relative))) {
      differences.push(`diferente: ${relative}`);
    }
  }
  for (const relative of targetFiles) {
    if (!sourceSet.has(relative)) differences.push(`obsoleto: ${relative}`);
  }
  return differences;
}

if (checkOnly) {
  const differences = drift();
  if (differences.length) {
    console.error('A cópia estática diverge de public/:');
    differences.forEach((item) => console.error(`- ${item}`));
    process.exitCode = 1;
  } else {
    console.log('Frontend sincronizado: public/ e backend/courseplatform/static/ são idênticos.');
  }
} else {
  fs.rmSync(targetRoot, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(targetRoot), { recursive: true });
  fs.cpSync(sourceRoot, targetRoot, { recursive: true });
  console.log('Frontend sincronizado a partir de public/.');
}
