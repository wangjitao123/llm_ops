/**
 * Vue 模板编译校验器（补 vue-tsc 的盲区）
 *
 * 为什么需要它：
 *   `vue-tsc -b` 只做类型检查，不生成渲染函数。一些模板错误只有到
 *   vite/esbuild 打包阶段才暴露，最典型的就是：
 *       <a-input v-model:value="cfg?.api_url" />
 *   编译产物是 `(cfg?.api_url) = $event` —— 非法赋值目标，esbuild 报
 *   "Invalid assignment target"。而 esbuild 在受限环境里会 spawn EPERM，
 *   本地根本跑不了 vite build，这类错误就完全看不见。
 *
 * 做法（全程进程内，不 spawn 子进程，避免沙箱管道限制）：
 *   1) @vue/compiler-sfc 解析 .vue 并把 <template> 编译成渲染函数代码
 *   2) rollup/parseAst 对产物做纯语法解析（Rollup 内置解析器，无外部进程）
 *   3) 语法错误直接抛出，定位到具体文件
 *
 * 用法：
 *   node scripts/check-templates.cjs             # 全量 src
 *   node scripts/check-templates.cjs src/views   # 指定目录
 */
const { readFileSync, readdirSync, statSync } = require('fs')
const { join, resolve, relative } = require('path')
const { parse, compileTemplate } = require('@vue/compiler-sfc')
const { parseAst } = require('rollup/parseAst')

const ROOT = resolve(__dirname, '..')
const TARGET = process.argv[2] ? resolve(ROOT, process.argv[2]) : resolve(ROOT, 'src')

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === 'node_modules' || name.startsWith('.')) continue
    const full = join(dir, name)
    if (statSync(full).isDirectory()) walk(full, out)
    else if (name.endsWith('.vue')) out.push(full)
  }
  return out
}

function describeError(e) {
  // Rollup 抛出的语法错误通常带 loc 与 pos
  const msg = (e && e.message ? e.message : String(e)).split('\n')[0]
  if (e && e.loc && e.loc.line) {
    return `${msg} (产物第 ${e.loc.line}:${e.loc.column} 行)`
  }
  return msg
}

function main() {
  const files = walk(TARGET)
  if (!files.length) {
    console.log('未找到 .vue 文件')
    return 0
  }

  let failed = 0
  let checked = 0

  for (const file of files) {
    const rel = relative(ROOT, file).replace(/\\/g, '/')
    const source = readFileSync(file, 'utf-8')
    const { descriptor, errors } = parse(source, { filename: file })

    if (errors && errors.length) {
      failed++
      console.error(`✗ ${rel}`)
      for (const e of errors) console.error(`    SFC 解析错误: ${e.message || e}`)
      continue
    }
    if (!descriptor.template) continue

    let code
    try {
      const res = compileTemplate({
        source: descriptor.template.content,
        filename: file,
        id: 'check',
        compilerOptions: { mode: 'module' },
      })
      if (res.errors && res.errors.length) {
        failed++
        console.error(`✗ ${rel}`)
        for (const e of res.errors) {
          console.error(`    模板错误: ${typeof e === 'string' ? e : e.message || JSON.stringify(e)}`)
        }
        continue
      }
      code = res.code
    } catch (e) {
      failed++
      console.error(`✗ ${rel}`)
      console.error(`    模板编译异常: ${e.message}`)
      continue
    }

    checked++
    try {
      parseAst(code)
    } catch (e) {
      failed++
      console.error(`✗ ${rel}`)
      console.error(`    ${describeError(e)}`)

      // 定位到出错的模板行，方便直接改
      const m = /\(([\w$.?[\]]+)\)\s*=\s*\$event/.exec(code)
      if (m) {
        console.error(`    提示: 模板里把 v-model 绑到了带可选链的表达式 —— "${m[1]}"`)
        console.error(`    改法: 去掉 ?. 或改为 v-model:value="x" 绑定到确定存在的对象`)
      }
    }
  }

  if (failed === 0) {
    console.log(`✓ 模板编译校验通过（检查 ${checked}/${files.length} 个含模板的 .vue）`)
    return 0
  }
  console.error(`\n✗ ${failed} 个文件模板编译失败`)
  return 1
}

process.exit(main())
