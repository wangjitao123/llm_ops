const fs = require('fs');
const path = require('path');
const asarPath = 'D:\\dsh桌面版\\DSH Desktop\\resources\\app.asar';

// First, parse the full header
const fd = fs.openSync(asarPath, 'r');
const fileSize = fs.statSync(asarPath).size;

// Read the entire file
const fullBuf = Buffer.alloc(fileSize);
fs.readSync(fd, fullBuf, 0, fileSize, 0);
fs.closeSync(fd);

// Parse the header: the format is 4 bytes header size, then header JSON starting at offset 8
// But we found the JSON starts at offset 16
// Let's try to find the JSON by looking for "{"
let jsonStart = 0;
for (let i = 0; i < 100; i++) {
  if (fullBuf[i] === 0x7b) { // '{'
    jsonStart = i;
    break;
  }
}

// Find the end of the JSON by matching braces
let depth = 0;
let jsonEnd = -1;
for (let i = jsonStart; i < Math.min(fileSize, jsonStart + 5000000); i++) {
  if (fullBuf[i] === 0x7b) depth++; // {
  else if (fullBuf[i] === 0x7d) { // }
    depth--;
    if (depth === 0) { jsonEnd = i; break; }
  }
}

if (jsonEnd < 0) {
  console.log('Could not find end of JSON header');
  process.exit(1);
}

const headerStr = fullBuf.toString('utf8', jsonStart, jsonEnd + 1);
const header = JSON.parse(headerStr);
console.log('Header parsed. Top-level keys in files:', Object.keys(header.files || {}));

// Function to extract files matching a path pattern
function extractFilesRecursive(node, currentPath, results) {
  if (!node || typeof node !== 'object') return;
  if (node.size !== undefined) {
    // This is a file
    results.push(currentPath);
  }
  if (node.files) {
    for (const [name, child] of Object.entries(node.files)) {
      extractFilesRecursive(child, currentPath ? currentPath + '/' + name : name, results);
    }
  }
}

// Find all @deepseek-ai files
let dshFiles = [];
if (header.files && header.files.node_modules && header.files.node_modules.files) {
  const nm = header.files.node_modules.files;
  if (nm['@deepseek-ai']) {
    extractFilesRecursive(nm['@deepseek-ai'], '@deepseek-ai', dshFiles);
  }
}

console.log('\n=== @deepseek-ai files ===');
dshFiles.forEach(f => console.log('  ' + f));

// Specifically search for files related to token/usage/cost
console.log('\n=== Files related to token/usage ===');
const keywords = ['token', 'usage', 'cost', 'pricing', 'statistics', 'spend', 'meter', 'billing'];
dshFiles.forEach(f => {
  const lower = f.toLowerCase();
  if (keywords.some(k => lower.includes(k))) {
    console.log('  ' + f);
  }
});

// Also look for .js files that might contain token tracking logic
console.log('\n=== DSH JavaScript files (not type defs) ===');
dshFiles.filter(f => f.endsWith('.js') && !f.endsWith('.d.ts') && !f.endsWith('.d.mts') && !f.endsWith('.js.map')).forEach(f => console.log('  ' + f));