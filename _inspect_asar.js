const fs = require('fs');
const asarPath = 'D:\\dsh桌面版\\DSH Desktop\\resources\\app.asar';
const fd = fs.openSync(asarPath, 'r');
const fileSize = fs.statSync(asarPath).size;
const remainingLen = fileSize - 16;
const buf = Buffer.alloc(Math.min(remainingLen, 500000));
fs.readSync(fd, buf, 0, buf.length, 16);
const str = buf.toString('utf8');

// Find the top-level directories
const searchTerms = ['"packages"', '"apps"', '"dsh"', '"cli"', '"src"', '"dist"', '"token"', '"usage"', '"stats"', '"cost"', '"billing"', '"meter"'];
searchTerms.forEach(term => {
  const idx = str.indexOf(term);
  if (idx >= 0) {
    const start = Math.max(0, idx - 100);
    const end = Math.min(str.length, idx + 300);
    console.log('=== Found ' + term + ' at offset ' + idx + ' ===');
    console.log(str.substring(start, end));
    console.log('');
  }
});

// Also try to find what top-level directories/files exist
console.log('=== Looking for top-level files in the asar ===');
// The JSON starts with {"files":{...}}
// Find the first level of keys
const filesStart = str.indexOf('"files":{');
if (filesStart >= 0) {
  const afterFiles = str.substring(filesStart + 8);
  // Find top-level keys by looking for "key":{
  let depth = 0;
  let inString = false;
  let escaped = false;
  let topKeys = [];
  let currentKey = '';
  let collectingKey = false;
  
  for (let i = 0; i < Math.min(afterFiles.length, 50000); i++) {
    const ch = afterFiles[i];
    if (escaped) { escaped = false; continue; }
    if (ch === '\\' && inString) { escaped = true; continue; }
    if (ch === '"' && !escaped) { 
      inString = !inString; 
      if (inString) collectingKey = true;
      else { collectingKey = false; topKeys.push(currentKey); currentKey = ''; }
      continue; 
    }
    if (ch === '{' && !inString) depth++;
    if (ch === '}' && !inString) { depth--; if (depth === 0) break; }
    if (ch === ',' && !inString && depth === 1) { collectingKey = false; currentKey = ''; continue; }
    if (collectingKey && inString) currentKey += ch;
  }
  
  console.log('Top-level keys (first 50):', topKeys.slice(0, 50));
  console.log('Total top-level keys found:', topKeys.length);
  
  // Check if packages is a directory
  if (topKeys.includes('packages')) {
    console.log('\n=== packages directory found! ===');
  }
}

// Also search for the actual source code files
// Look for .ts, .js, .mjs files that are NOT in node_modules
console.log('\n=== Searching for source code files ===');
const filePattern = /"([^"]+\.(?:ts|js|mjs|json))":\s*\{/g;
let match;
let count = 0;
let nonNodeFiles = [];
while ((match = filePattern.exec(str)) !== null && count < 100) {
  const filePath = match[1];
  if (!filePath.startsWith('node_modules') && !filePath.includes('node_modules/')) {
    nonNodeFiles.push(filePath);
    count++;
  }
}
console.log('Non-node_modules source files (first 100):');
nonNodeFiles.forEach(f => console.log('  ' + f));

fs.closeSync(fd);