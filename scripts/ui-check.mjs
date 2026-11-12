/**
 * 用 Edge 的调试协议跑一遍登录态相关的界面流程，出截图。
 *
 * 这不是正式测试，只是「人工点一遍」的自动化替代：起一个隐身 Edge，
 * 连 WebSocket 打 CDP，登录 → 看守卫 → 静默续期 → 改密弹窗 → 设备页。
 * 截图落在 /tmp/shots 下，人工看一眼即可。
 *
 * 用法：node scripts/ui-check.mjs [--headful]
 */

import { spawn } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'

const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const PORT = 9333
const BASE = process.env.UI_BASE || 'http://127.0.0.1:5173'
const SHOTS = path.join(os.tmpdir(), 'shots')
const HEADFUL = process.argv.includes('--headful')

fs.mkdirSync(SHOTS, { recursive: true })

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'wv-edge-'))
const args = [
  `--remote-debugging-port=${PORT}`,
  `--user-data-dir=${profile}`,
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-features=Translate,MediaRouter',
  '--window-size=1440,960',
  ...(HEADFUL ? [] : ['--headless=new', '--disable-gpu']),
  'about:blank',
]
const chrome = spawn(EDGE, args, { stdio: 'ignore' })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function wsUrl() {
  for (let i = 0; i < 50; i += 1) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/json/version`)
      const json = await res.json()
      if (json.webSocketDebuggerUrl) return json.webSocketDebuggerUrl
    } catch {
      /* 还没起来 */
    }
    await sleep(200)
  }
  throw new Error('Edge 调试端口没起来')
}

let nextId = 0
const pending = new Map()
let ws
let sessionId

function send(method, params = {}, useSession = true) {
  const id = (nextId += 1)
  const payload = { id, method, params }
  if (useSession && sessionId) payload.sessionId = sessionId
  ws.send(JSON.stringify(payload))
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject })
  })
}

async function evaluate(expression) {
  const res = await send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  })
  if (res.exceptionDetails) {
    throw new Error(res.exceptionDetails.exception?.description || 'eval 失败')
  }
  return res.result?.value
}

async function shot(name) {
  const res = await send('Page.captureScreenshot', { format: 'png' })
  const file = path.join(SHOTS, `${name}.png`)
  fs.writeFileSync(file, Buffer.from(res.data, 'base64'))
  console.log(`  截图 → ${file}`)
  return file
}

async function goto(url) {
  await send('Page.navigate', { url })
  await sleep(1200)
}

/** 绕过 React 的受控 input：直接走原生 setter 再派发 input 事件 */
const fillJs = (selector, value) => `
(() => {
  const el = document.querySelector(${JSON.stringify(selector)});
  if (!el) return 'missing';
  const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
  setter.call(el, ${JSON.stringify(value)});
  el.dispatchEvent(new Event('input', { bubbles: true }));
  return 'ok';
})()
`

/** 按可见文字点按钮/链接 */
const clickJs = (text) => `
(() => {
  const nodes = [...document.querySelectorAll('button, a, [role="menuitem"], [role="button"]')];
  const hit = nodes.find((n) => (n.innerText || '').trim().includes(${JSON.stringify(text)}));
  if (!hit) return 'missing:' + nodes.map(n => (n.innerText||'').trim()).join('|');
  hit.click();
  return 'ok';
})()
`

async function click(text) {
  const r = await evaluate(clickJs(text))
  if (r !== 'ok') throw new Error(`点不到「${text}」→ ${r}`)
  await sleep(900)
}

async function main() {
  const url = await wsUrl()
  ws = new WebSocket(url)
  await new Promise((resolve, reject) => {
    ws.addEventListener('open', resolve, { once: true })
    ws.addEventListener('error', reject, { once: true })
  })
  ws.addEventListener('message', (ev) => {
    const msg = JSON.parse(ev.data)
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)
      pending.delete(msg.id)
      if (msg.error) reject(new Error(msg.error.message))
      else resolve(msg.result)
    }
  })

  const { targetId } = await send('Target.createTarget', { url: 'about:blank' }, false)
  const attached = await send('Target.attachToTarget', { targetId, flatten: true }, false)
  sessionId = attached.sessionId

  await send('Page.enable')
  await send('Runtime.enable')
  await send('Network.enable')
  await send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 960,
    deviceScaleFactor: 1,
    mobile: false,
  })

  console.log('\n① 未登录访问首页，应被守卫送回登录页')
  await goto(`${BASE}/`)
  const p1 = await evaluate('location.pathname')
  console.log(`  落在 ${p1}`)
  await shot('01-guard-redirect')

  console.log('\n② 登录 admin/admin')
  await evaluate(fillJs('#account', 'admin'))
  await evaluate(fillJs('#password', 'admin'))
  await shot('02-login-filled')
  await click('登录')
  await sleep(1500)
  const p2 = await evaluate('location.pathname')
  console.log(`  登录后落在 ${p2}`)
  await shot('03-after-login')

  console.log('\n③ Cookie 是否 httpOnly（JS 读不到令牌）')
  const cookie = await evaluate('document.cookie || "(空)"')
  console.log(`  document.cookie = ${cookie}`)

  console.log('\n④ 安全设置页')
  await goto(`${BASE}/settings/security`)
  await shot('04-security')

  console.log('\n⑤ 打开改密弹窗')
  await click('修改密码')
  await shot('05-change-password')

  console.log('\n⑥ 设备管理页')
  await goto(`${BASE}/settings/sessions`)
  await shot('06-sessions')

  console.log('\n⑦ 删掉访问令牌后刷新：应静默续期而不是被踢')
  // 两个令牌的 path 不同（/api 与 /api/auth），必须按各自的 URL 查，否则查不到
  const cookies = await send('Network.getCookies', {
    urls: [`${BASE}/api`, `${BASE}/api/auth`],
  })
  for (const c of cookies.cookies) {
    if (c.name.startsWith('wv_')) {
      console.log(`  ${c.name} path=${c.path} httpOnly=${c.httpOnly} 剩余=${Math.round((c.expires - Date.now() / 1000) / 60)} 分钟`)
    }
  }
  await send('Network.deleteCookies', { name: 'wv_at', url: `${BASE}/api` })
  await goto(`${BASE}/settings/sessions`)
  const p7 = await evaluate('location.pathname')
  const still = await evaluate(
    "document.body.innerText.includes('设备') || document.body.innerText.includes('会话')",
  )
  console.log(`  刷新后落在 ${p7}，页面正常=${still}`)
  await shot('07-after-silent-refresh')

  console.log('\n⑧ 用户菜单里的「登录有效期」')
  await evaluate("document.querySelector('[aria-label=\"账号菜单\"]').click()")
  await sleep(600)
  const footer = await evaluate(`
    (() => {
      const menu = document.querySelector('[role="menu"]');
      return menu ? menu.innerText.replace(/\\n+/g, ' | ') : '(菜单没打开)';
    })()
  `)
  console.log(`  菜单内容：${footer}`)
  await shot('08-user-menu')

  console.log('\n⑨ 退出登录')
  await click('退出登录')
  await sleep(1200)
  const p9 = await evaluate('location.pathname')
  console.log(`  退出后落在 ${p9}`)
  await shot('09-after-logout')

  console.log('\n⑩ 忘记密码页')
  await goto(`${BASE}/forgot-password`)
  console.log(`  落在 ${await evaluate('location.pathname')}`)
  await shot('10-forgot-password')

  console.log('\n⑪ 重置密码页（链接里没有令牌，应显示无效提示而不是表单）')
  await goto(`${BASE}/reset-password`)
  console.log(`  落在 ${await evaluate('location.pathname')}`)
  console.log(
    `  正文：${(await evaluate("document.body.innerText.replace(/\\n+/g, ' | ')")).slice(0, 120)}`,
  )
  await shot('11-reset-invalid')

  // 真的走一遍重置：调用方先申请令牌，通过 UI_RESET_TOKEN 传进来
  const resetToken = process.env.UI_RESET_TOKEN
  if (resetToken) {
    const email = process.env.UI_RESET_EMAIL || ''
    const newPassword = process.env.UI_RESET_PASSWORD || 'Kp7#vnnrvj4071'
    console.log(`\n⑫ 用真实令牌重置 ${email}`)
    await goto(
      `${BASE}/reset-password?token=${encodeURIComponent(resetToken)}&email=${encodeURIComponent(email)}`,
    )
    await evaluate(fillJs('#password', newPassword))
    await evaluate(fillJs('#confirm', newPassword))
    await sleep(300)
    await shot('12-reset-filled')
    await click('确认重置密码')
    await sleep(1500)
    const result = await evaluate("document.body.innerText.replace(/\\n+/g, ' | ')")
    console.log(`  结果页：${result.slice(0, 160)}`)
    await shot('13-reset-done')
  }

  console.log('\n全部截图在 ' + SHOTS)
}

main()
  .catch((err) => {
    console.error('\n失败：', err.message)
    process.exitCode = 1
  })
  .finally(async () => {
    try {
      await send('Browser.close', {}, false)
    } catch {
      /* ignore */
    }
    chrome.kill()
    await sleep(500)
    fs.rmSync(profile, { recursive: true, force: true })
  })
