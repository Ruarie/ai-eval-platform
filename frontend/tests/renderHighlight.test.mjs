import test from 'node:test'
import assert from 'node:assert/strict'
import { escapeHtml, highlightText } from '../src/utils/render.ts'

test('escapeHtml 转义五个 HTML 特殊字符（含单引号，可用于属性值）', () => {
  assert.equal(escapeHtml(`<a href="x" title='y'>&</a>`), '&lt;a href=&quot;x&quot; title=&#039;y&#039;&gt;&amp;&lt;/a&gt;')
})

test('highlightText 无关键词时只做转义', () => {
  assert.equal(highlightText('<b>登录</b>', ''), '&lt;b&gt;登录&lt;/b&gt;')
  assert.equal(highlightText('', '登录'), '')
})

test('highlightText 大小写不敏感地包裹全部命中，并保留原文大小写', () => {
  assert.equal(
    highlightText('Login 与 login', 'LOGIN'),
    '<mark class="highlight-match">Login</mark> 与 <mark class="highlight-match">login</mark>',
  )
})

test('查询 amp/quot 不会把标签插进 HTML 实体中间', () => {
  assert.equal(highlightText('A & B', 'amp'), 'A &amp; B')
  assert.equal(highlightText('say "hi"', 'quot'), 'say &quot;hi&quot;')
})

test('含特殊字符的关键词按原文命中，命中片段同样被转义', () => {
  assert.equal(highlightText('a<b & c', '<b &'), 'a<mark class="highlight-match">&lt;b &amp;</mark> c')
  assert.equal(highlightText("it's ok", "it's"), '<mark class="highlight-match">it&#039;s</mark> ok')
})

test('正则元字符被当作普通文本，原文中的标签不会被执行', () => {
  assert.equal(highlightText('1+1=2 (a.b)', '(a.b)'), '1+1=2 <mark class="highlight-match">(a.b)</mark>')
  assert.equal(
    highlightText('<img src=x onerror=alert(1)>', 'img'),
    '&lt;<mark class="highlight-match">img</mark> src=x onerror=alert(1)&gt;',
  )
})
