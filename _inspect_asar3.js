const fs = require('fs');
const asarPath = 'D:\\dsh桌面版\\DSH Desktop\\resources\\app.asar';
const fd = fs.openSync(asarPath, 'r');
const fileSize = fs.statSync(asarPath).size;
const remainingLen = fileSize - 16;
const buf = Buffer.alloc(Math.min(remainingLen, 500000));
fs.readSync(fd, buf, 0, buf.length, 16);
const str = buf.toString('utf8');

// Search for @deepseek-ai packages
const dshIdx = str.indexOf('@deepseek-ai');
if (dshIdx >= 0) {
  console.log('=== @deepseek-ai packages found at offset ' + dshIdx + ' ===');
  // Show context around the first occurrence
  console.log(str.substring(Math.max(0, dshIdx - 100), dshIdx + 500));
}

// Also search for dsh-related module names
const dshModules = ['dsh', 'deepseek-harness', 'harness'];
dshModules.forEach(mod => {
  let idx = 0;
  let count = 0;
  while ((idx = str.indexOf(mod, idx + 1)) >= 0 && count < 5) {
    const context = str.substring(Math.max(0, idx - 50), idx + 200);
    // Only show if it looks like a module name or file path
    if (context.includes('"') || context.includes('files')) {
      console.log('\n=== Found "' + mod + '" at offset ' + idx + ' ===');
      console.log(context);
      count++;
    }
  }
});

// Search for token/usage tracking related code
console.log('\n=== Searching for token usage tracking code ===');
const searchTerms = ['usageTracking', 'tokenUsage', 'tokenCount', 'costTracker', 'usageStats', 'apiUsage', 'modelUsage', 'spendTracking', 'usageReport', 'tokenMeter'];
searchTerms.forEach(term => {
  let idx = 0;
  while ((idx = str.indexOf(term, idx + 1)) >= 0 && idx < 100) {
    console.log('\nFound "' + term + '" at offset ' + idx + ':');
    console.log(str.substring(Math.max(0, idx - 80), idx + 200));
  }
});

// Also search for the package.json to find the entry point
console.log('\n=== Searching for package.json ===');
let pkgIdx = 0;
while ((pkgIdx = str.indexOf('"package.json"', pkgIdx + 1)) >= 0 && pkgIdx < 500000) {
  // Show the context to find the directory structure
  const start = Math.max(0, pkgIdx - 300);
  const end = Math.min(str.length, pkgIdx + 100);
  console.log('\nFound package.json at offset ' + pkgIdx + ':');
  console.log(str.substring(start, end));
}

// Search for "main" entry point
console.log('\n=== Searching for main entry point ===');
let mainIdx = 0;
while ((mainIdx = str.indexOf('"main"', mainIdx + 1)) >= 0 && mainIdx < 500000) {
  const context = str.substring(Math.max(0, mainIdx - 200), mainIdx + 100);
  if (context.includes('.js') || context.includes('.mjs')) {
    console.log('\nFound at offset ' + mainIdx + ':');
    console.log(context);
  }
}

fs.closeSync(fd);