#!/usr/bin/env bun
/**
 * 一键启动开发环境：后端 FastAPI（8010）+ 前端 Vite（5173），日志合并到同一个终端。
 *
 * 为什么是一个脚本而不是两条命令：在 WorkBuddy 右侧终端里只需要跑一条命令，
 * 两个服务的输出都带前缀（[api] 青 / [web] 紫），谁报错一眼能分清；
 * Ctrl+C 一次把两个进程都收掉，不会留下占着端口的孤儿进程。
 *
 * 用法（项目根目录，任意 shell 都行）：
 *   bun scripts/dev.mjs
 *   # 换端口：
 *   API_PORT=8020 WEB_PORT=5180 bun scripts/dev.mjs
 */
import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import net from 'node:net'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)))
const API_PORT = Number(process.env.API_PORT ?? 8010)
const WEB_PORT = Number(process.env.WEB_PORT ?? 5173)

// uv 不在 PATH 里（Windows 的常见情况），退回本机安装的绝对路径
const UV_FALLBACK = 'C:/Users/Demon/.local/bin/uv.exe'
const UV = process.env.UV ?? (existsSync(UV_FALLBACK) ? UV_FALLBACK : 'uv')

// bun 在 Windows 上常是 .cmd / shell 垫片，直接 spawn "bun" 会找不到；
// 本脚本自己就跑在 bun 里，用 process.execPath 指向真正的 bun.exe 最稳。
const BUN = process.versions.bun ? process.execPath : 'bun'

const paint = (code) =>
  process.stdout.isTTY ? (text) => `\x1b[${code}m${text}\x1b[0m` : (text) => text
const apiTag = paint(36)('[api]')
const webTag = paint(35)('[web]')

const portFree = (port) =>
  new Promise((resolve) => {
    const probe = net.createServer()
    probe.once('error', () => resolve(false))
    probe.once('listening', () => probe.close(() => resolve(true)))
    probe.listen(port, '127.0.0.1')
  })

const busy = []
for (const port of [API_PORT, WEB_PORT]) {
  if (!(await portFree(port))) busy.push(port)
}
if (busy.length > 0) {
  console.error(`\n× 端口 ${busy.join(' / ')} 已被占用，先把占用它的进程结束掉：`)
  console.error(`    netstat -ano | findstr :${busy[0]}`)
  console.error(`    taskkill /PID <上一行最后一列的 PID> /T /F\n`)
  process.exit(1)
}

const children = []
let shuttingDown = false

function stopAll(code = 0) {
  if (shuttingDown) return
  shuttingDown = true
  for (const child of children) {
    if (!child.pid) continue
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
    } else {
      child.kill('SIGTERM')
    }
  }
  setTimeout(() => process.exit(code), 300)
}

process.on('SIGINT', () => {
  console.log('\n正在停止前后端…')
  stopAll(0)
})
process.on('SIGTERM', () => stopAll(0))

/** 把子进程的输出按行加前缀，避免半行日志被切成两段。 */
function prefix(stream, tag, write) {
  let buffer = ''
  stream.setEncoding('utf8')
  stream.on('data', (chunk) => {
    buffer += chunk
    const lines = buffer.split(/\r?\n/)
    buffer = lines.pop() ?? ''
    for (const line of lines) write(`${tag} ${line}\n`)
  })
  stream.on('end', () => {
    if (buffer.trim()) write(`${tag} ${buffer}\n`)
  })
}

function start(name, tag, command, args, cwd) {
  const child = spawn(command, args, { cwd, env: process.env, shell: false })
  children.push(child)
  prefix(child.stdout, tag, (line) => process.stdout.write(line))
  prefix(child.stderr, tag, (line) => process.stderr.write(line))
  child.on('error', (error) => {
    console.error(`${tag} 启动失败：${error.message}`)
    stopAll(1)
  })
  child.on('exit', (code, signal) => {
    if (shuttingDown) return
    console.log(`${tag} ${name} 已退出（code=${code ?? 'null'}, signal=${signal ?? '无'}），一并停止另一个服务`)
    stopAll(code ?? 1)
  })
  return child
}

console.log(`▶ 后端  FastAPI  http://127.0.0.1:${API_PORT}   （--reload：改后端代码自动重载）`)
console.log(`▶ 前端  Vite     http://127.0.0.1:${WEB_PORT}`)
console.log('  Ctrl+C 一次停掉两个服务，日志在下方实时输出。\n')

start('uvicorn', apiTag, UV, [
  'run',
  'uvicorn',
  'app.main:app',
  '--host',
  '127.0.0.1',
  '--port',
  String(API_PORT),
  '--reload',
], join(ROOT, 'backend'))

start('vite', webTag, BUN, ['run', 'dev'], join(ROOT, 'frontend'))
