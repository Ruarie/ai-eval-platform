/**
 * Agent 回答质量回归：真实登录 + 固定题库，按关键词与"禁止编造"规则打分。
 *
 * 不进入常规 e2e（会真实调用模型、需要账号）：手动运行
 *   cd frontend && node tests/agent-quality/run.mjs
 * 需要环境变量：AGENT_QA_BASE_URL（默认 http://127.0.0.1:16675）、
 * AGENT_QA_USER（默认 admin）、AGENT_QA_PASSWORD（缺省时从 docker inspect 读取）。
 */
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium } from 'playwright'

const here = path.dirname(fileURLToPath(import.meta.url))
const allCases = JSON.parse(fs.readFileSync(path.join(here, 'cases.json'), 'utf8'))
const limit = Number(process.env.AGENT_QA_LIMIT || 0)
const only = (process.env.AGENT_QA_ONLY || '').split(',').map(s => s.trim()).filter(Boolean)
const filtered = only.length ? allCases.filter(item => only.includes(item.id)) : allCases
const cases = limit > 0 ? filtered.slice(0, limit) : filtered

const BASE_URL = process.env.AGENT_QA_BASE_URL || 'http://127.0.0.1:16675'
const USER = process.env.AGENT_QA_USER || 'admin'
const ANSWER_TIMEOUT_MS = Number(process.env.AGENT_QA_TIMEOUT_MS || 180000)

function adminPassword() {
  if (process.env.AGENT_QA_PASSWORD) return process.env.AGENT_QA_PASSWORD
  const out = execSync(
    "docker inspect ai-eval-platform-api-1 --format '{{range .Config.Env}}{{println .}}{{end}}'",
    { encoding: 'utf8' },
  )
  const line = out.split('\n').find(item => item.startsWith('BOOTSTRAP_ADMIN_PASSWORD='))
  return line ? line.slice('BOOTSTRAP_ADMIN_PASSWORD='.length).trim() : ''
}

async function login(page) {
  await page.goto(`${BASE_URL}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('请输入用户名').fill(USER)
  await page.getByPlaceholder('请输入密码').fill(adminPassword())
  await page.locator('.login-submit-btn').click()
  await page.waitForURL(/\/agent$/, { timeout: 30000 })
}

/** 问一个问题并返回助手正文（去掉运行信息面板）。 */
async function ask(page, question) {
  const create = page.getByRole('button', { name: '+ 新建会话' })
  if (await create.isVisible().catch(() => false)) {
    await create.click().catch(() => {})
    await page.waitForTimeout(600)
  }
  const composer = page.locator('textarea[aria-label="消息"]')
  await composer.waitFor({ timeout: 20000 })
  await composer.fill(question)
  await page.locator('.loop-send').click()

  // 完成判定：消息区出现本轮问题后，连续两轮（4s）文本不再变化、且不处于
  // 生成/等待确认状态才算结束。多步工具调用之间会有短暂空档，只看瞬时状态
  // 会把「思考中」当成「已结束」，抓到空回答。
  const readLog = () =>
    page.evaluate(() => {
      const node = document.querySelector('[role="log"]')
      return node ? node.innerText : document.body.innerText
    })
  let lastText = ''
  let stable = 0
  const deadline = Date.now() + ANSWER_TIMEOUT_MS
  while (Date.now() < deadline) {
    await page.waitForTimeout(2000)
    const current = await readLog()
    const busy = current.includes('正在响应') || current.includes('等待交互参数')
    if (busy || !current.includes(question)) {
      stable = 0
      lastText = current
      continue
    }
    if (current === lastText) {
      stable += 1
      if (stable >= 2) break
    } else {
      stable = 0
      lastText = current
    }
  }

  const log = await page.evaluate(() => {
    const node = document.querySelector('[role="log"]')
    if (!node) return document.body.innerText
    // 只保留对话正文：思考块是模型内部推理，工具卡/执行过程/请求头是界面装饰，
    // 计入回答会让「回答过长」断言把工具面板文字误判成模型啰嗦。
    const clone = node.cloneNode(true)
    clone
      .querySelectorAll(
        '.reasoning-block, .turn-process-tool, .turn-media-results, .assistant-header, .turn-segment-label'
      )
      .forEach(el => el.remove())
    return clone.innerText
  })
  const index = log.lastIndexOf(question)
  let answer = index >= 0 ? log.slice(index + question.length) : log
  const cut = answer.search(/绑定工作区|生成token速度|本轮失败|缓存命中率/)
  if (cut > 0) answer = answer.slice(0, cut)
  return answer.replace(/\n{3,}/g, '\n\n').trim()
}

function evaluate(item, answer) {
  const reasons = []
  const length = answer.length
  if (length < (item.minChars || 0)) reasons.push(`回答过短(${length}<${item.minChars})`)
  if (item.maxChars && length > item.maxChars) reasons.push(`回答过长(${length}>${item.maxChars})`)
  for (const word of item.mustInclude || []) {
    if (!answer.includes(word)) reasons.push(`缺少关键词「${word}」`)
  }
  if (item.mustMentionAny && !item.mustMentionAny.some(word => answer.includes(word))) {
    reasons.push(`未提及任一：${item.mustMentionAny.join('/')}`)
  }
  if (item.mustMentionAny2 && !item.mustMentionAny2.some(word => answer.includes(word))) {
    reasons.push(`未提及任一：${item.mustMentionAny2.join('/')}`)
  }
  for (const pattern of item.mustNotMatch || []) {
    if (new RegExp(pattern).test(answer)) reasons.push(`命中禁止模式 /${pattern}/`)
  }
  return reasons
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1500, height: 950 } })
const failures = []

try {
  await login(page)
  for (const [index, item] of cases.entries()) {
    const started = Date.now()
    let answer = ''
    let error = ''
    try {
      answer = await ask(page, item.question)
    } catch (exc) {
      error = exc instanceof Error ? exc.message.split('\n')[0] : String(exc)
    }
    let reasons = error ? [`执行失败：${error}`] : evaluate(item, answer)
    if (reasons.length) {
      // 模型输出有随机性：失败项再问一次，取较好的一次，降低假失败。
      try {
        const retry = await ask(page, item.question)
        const retryReasons = evaluate(item, retry)
        if (retryReasons.length < reasons.length) {
          answer = retry
          reasons = retryReasons
        }
      } catch {
        // 重试失败就保留首次结果
      }
    }
    const seconds = ((Date.now() - started) / 1000).toFixed(1)
    if (reasons.length) {
      failures.push({ id: item.id, reasons })
      console.log(`FAIL [${index + 1}/${cases.length}] ${item.id} (${seconds}s) :: ${reasons.join('；')}`)
      console.log(`     回答片段：${answer.slice(0, 400).replace(/\n/g, ' ')}`)
    } else {
      console.log(`PASS [${index + 1}/${cases.length}] ${item.id} (${seconds}s)`)
    }
  }
} finally {
  await browser.close()
}

const passed = cases.length - failures.length
const ratio = cases.length ? passed / cases.length : 1
const minPass = Number(process.env.AGENT_QA_MIN_PASS || 0.8)
console.log(`\nSUMMARY ${passed}/${cases.length} passed (${(ratio * 100).toFixed(0)}%, 阈值 ${(minPass * 100).toFixed(0)}%)`)
if (failures.length) {
  console.log(JSON.stringify(failures, null, 2))
}
// 模型输出有随机性，题库定位是巡检而非逐字契约：低于阈值才算失败。
if (ratio < minPass) {
  process.exitCode = 1
}
