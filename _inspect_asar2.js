const fs = require('fs');
const asarPath = 'D:\\dsh桌面版\\DSH Desktop\\resources\\app.asar';
const fd = fs.openSync(asarPath, 'r');
const fileSize = fs.statSync(asarPath).size;
const remainingLen = fileSize - 16;
const buf = Buffer.alloc(Math.min(remainingLen, 500000));
fs.readSync(fd, buf, 0, buf.length, 16);
const str = buf.toString('utf8');

// Parse the JSON structure properly
// The header starts with {"files":{
// After that, the top-level keys are the files/folders at the root of the asar
const filesStart = str.indexOf('{"files":{');
if (filesStart >= 0) {
  // The JSON after the opening { is: "files":{...}
  // We need to find the value of the "files" key
  // After '"files":{' we need to find top-level keys
  const afterFiles = str.substring(filesStart + 10); // after {"files":{
  
  // Now find the top-level keys (directories/files in the asar root)
  let depth = 1; // we're inside the files object
  let inString = false;
  let escaped = false;
  let topKeys = [];
  let currentKey = '';
  let collectingKey = false;
  let foundKey = false;
  
  for (let i = 0; i < Math.min(afterFiles.length, 100000); i++) {
    const ch = afterFiles[i];
    if (escaped) { escaped = false; continue; }
    if (ch === '\\' && inString) { escaped = true; continue; }
    
    if (ch === '"' && !escaped) {
      inString = !inString;
      if (inString && depth === 1) {
        collectingKey = true;
        currentKey = '';
      } else if (!inString && collectingKey) {
        collectingKey = false;
        topKeys.push(currentKey);
        currentKey = '';
      }
      continue;
    }
    
    if (collectingKey) currentKey += ch;
    
    if (!inString) {
      if (ch === '{') depth++;
      if (ch === '}') {
        depth--;
        if (depth === 0) break; // end of files object
      }
    }
  }
  
  console.log('=== Top-level files/directories in asar ===');
  topKeys.forEach(k => console.log('  ' + k));
  
  // Check for specific interesting directories
  const interesting = ['packages', 'apps', 'src', 'dist', 'lib', 'web', 'server', 'cli'];
  console.log('\n=== Interesting directories check ===');
  interesting.forEach(k => {
    if (topKeys.includes(k)) console.log('  FOUND: ' + k);
    else console.log('  NOT FOUND: ' + k);
  });
  
  // Now let's look for token/usage related files anywhere in the archive
  console.log('\n=== Searching for token/usage related files ===');
  const tokenPatterns = ['token', 'usage', 'cost', 'billing', 'meter', 'statistics', 'pricing'];
  tokenPatterns.forEach(pattern => {
    let idx = -1;
    let count = 0;
    let startSearch = 0;
    while ((idx = str.indexOf(pattern, startSearch)) >= 0 && count < 10) {
      // Check if this is in a filename
      const before = str.substring(Math.max(0, idx - 50), idx);
      const after = str.substring(idx, Math.min(str.length, idx + 100));
      console.log('  Found "' + pattern + '" at ' + idx + ': ...' + before + '>>>' + pattern + '<<<' + after.substring(pattern.length) + '...');
      startSearch = idx + 1;
      count++;
    }
  });
}

fs.closeSync(fd);