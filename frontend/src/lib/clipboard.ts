/**
 * 复制文本到剪贴板。
 *
 * 异步剪贴板 API 在非安全上下文（内网 http 部署）或权限被拒时会直接抛错，
 * 而「复制账号 / 代理地址」是列表页最常用的动作，不能因此变成死按钮 ——
 * 失败就退回「建个隐藏 textarea 选中再 execCommand」这套老办法。
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.top = '-1000px'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    let ok = false
    try {
      ok = document.execCommand('copy')
    } catch {
      ok = false
    }
    document.body.removeChild(ta)
    return ok
  }
}
