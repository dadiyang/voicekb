<template>
  <view class="chat-page">
    <!-- 极简自定义导航栏 -->
    <view class="mini-nav">
      <text class="mini-nav-title">AI 问答</text>
    </view>
    <!-- 消息区域（可滚动） -->
    <scroll-view scroll-y class="chat-messages" :scroll-top="scrollTop">
      <view v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role === 'user' ? 'user' : 'ai'">
        <!-- Tool 执行步骤（通用渲染，不感知具体 tool） -->
        <view v-if="msg.toolSteps && msg.toolSteps.length" class="tool-steps">
          <view v-for="(step, si) in msg.toolSteps" :key="si" class="tool-step" :class="step.status">
            <text class="tool-icon">{{ step.status === 'done' ? '✓' : '⚡' }}</text>
            <text class="tool-name">{{ step.name }}</text>
            <text v-if="step.summary" class="tool-summary">{{ step.summary }}</text>
          </view>
        </view>
        <!-- 思考过程（折叠） -->
        <view v-if="msg.reasoning" class="reasoning-toggle" @click="msg._showReasoning = !msg._showReasoning">
          <text style="font-size:22rpx;margin-right:4rpx">{{ msg._showReasoning ? '▼' : '▶' }}</text>
          <text>{{ msg._showReasoning ? '收起思考过程' : '查看思考过程' }}</text>
        </view>
        <view v-if="msg.reasoning && msg._showReasoning" class="reasoning-box">
          <rich-text :nodes="formatContent(msg.reasoning)" />
        </view>
        <!-- 回答气泡 -->
        <view v-if="msg.content" class="bubble">
          <rich-text v-if="msg.role === 'assistant'" :nodes="formatContent(msg.content)" />
          <text v-else>{{ msg.content }}</text>
        </view>
        <!-- 来源 -->
        <view v-if="msg.sources && msg.sources.length" class="source-link">
          <text>来源: </text>
          <text v-for="src in uniqueSources(msg.sources)" :key="src.recording_id"
                class="source-ref" @click="openRecording(src.recording_id)">{{ shortName(src) }}</text>
        </view>
      </view>
      <view v-if="loading" class="chat-msg ai">
        <view class="bubble">
          <view class="typing-indicator">
            <text class="typing-dot"></text><text class="typing-dot"></text><text class="typing-dot"></text>
          </view>
          <text v-if="deepThink" style="font-size:22rpx;color:#999;margin-left:8rpx">深度思考中...</text>
        </view>
      </view>
      <view style="height: 20rpx"></view>
    </scroll-view>

    <!-- 底部固定区域 -->
    <view class="chat-bottom">
      <view class="quick-row">
        <scroll-view scroll-x class="quick-bar">
          <view class="quick-chips-row">
            <text class="quick-chip" v-for="q in quickQuestions" :key="q" @click="askQuestion(q)">{{ q }}</text>
            <text class="quick-chip clear-chip" @click="clearChat">
              <text class="ti ti-trash" style="margin-right:4rpx"></text>清除
            </text>
          </view>
        </scroll-view>
      </view>
      <view class="chat-input-bar">
        <view class="think-toggle" :class="{active: deepThink}" @click="deepThink = !deepThink; uni.setStorageSync('voicekb_deep_think', String(deepThink))">
          <text class="think-label">🧠深度</text>
        </view>
        <input class="chat-input" v-model="inputText" placeholder="输入你的问题..."
               confirm-type="send" @confirm="sendMessage" :adjust-position="true" />
        <view class="chat-send" @click="sendMessage">
          <text class="ti ti-send send-icon"></text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup>
import { ref, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { chatApi, speakerApi } from '@/api'
import { renderMarkdown } from '@/utils/format'

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const scrollTop = ref(0)
const deepThink = ref(uni.getStorageSync('voicekb_deep_think') === 'true')
const quickQuestions = ref(['最近讨论了什么？', '有哪些待办事项？', '关键决策总结'])
const conversationId = 'default'
let initialized = false
let activeAbortController = null  // 用于取消进行中的 fetch

function formatContent(text) { return renderMarkdown(text) }

function uniqueSources(sources) {
  if (!sources) return []
  const seen = new Set()
  return sources.filter(s => { if (seen.has(s.recording_id)) return false; seen.add(s.recording_id); return true })
}

function shortName(src) {
  if (src.recording_title) return src.recording_title
  const filename = src.recording_filename || ''
  if (!filename) return '录音'
  const name = filename.replace(/\.[^.]+$/, '')
  const parts = name.split('_')
  const hash = parts[parts.length - 1] || name
  return '录音 ' + hash.slice(0, 6)
}

function openRecording(id) {
  uni.navigateTo({ url: `/pages/recordings/detail?id=${id}` })
}

async function loadHistory() {
  try {
    const history = await chatApi.history(conversationId)
    if (history.length) {
      messages.value = history.map(m => ({ role: m.role, content: m.content }))
    } else {
      messages.value = [{ role: 'assistant', content: '你好！我是 VoiceKB 智能助手，可以帮你查找和分析录音内容。试试下方的快捷提问，或直接输入你的问题。' }]
    }
  } catch (e) {
    messages.value = [{ role: 'assistant', content: '你好！有什么可以帮你的？' }]
  }
  scrollToBottom(true)
}

async function loadQuickQuestions() {
  try {
    const spks = await speakerApi.list()
    const named = spks.filter(s => !s.name.startsWith('说话人')).slice(0, 2)
    const qs = ['最近讨论了什么？', '有哪些待办事项？']
    named.forEach(s => qs.push(`${s.name}说了什么？`))
    if (qs.length < 4) qs.push('关键决策总结')
    quickQuestions.value = qs
  } catch (e) {
    quickQuestions.value = ['最近讨论了什么？', '有哪些待办事项？']
  }
}

function askQuestion(q) { inputText.value = q; sendMessage() }

let currentRequestId = null

// 获取消息数组中最后一条的 reactive 引用
function lastMsg() { return messages.value[messages.value.length - 1] }
// 强制触发 Vue 响应式更新（修改数组元素）
function updateLastMsg(patch) {
  const idx = messages.value.length - 1
  messages.value[idx] = { ...messages.value[idx], ...patch }
}

async function sendMessage() {
  const q = inputText.value.trim()
  if (!q || loading.value) return
  inputText.value = ''
  messages.value.push({ role: 'user', content: q })
  loading.value = true
  scrollToBottom(true)

  try {
    activeAbortController = new AbortController()
    const resp = await fetch('/api/ask/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: q, conversation_id: conversationId, deep_think: deepThink.value }),
      signal: activeAbortController.signal,
    })

    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)

    // 收到响应后，去掉 loading 打字动画，push 真正的 AI 消息
    loading.value = false
    messages.value.push({
      role: 'assistant', content: '', reasoning: '',
      _showReasoning: deepThink.value, sources: [], toolSteps: [],
    })

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let reasoning = '', content = ''
    const toolSteps = []  // 收集 tool 执行步骤

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()

      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7)
        } else if (line.startsWith('data: ') && eventType) {
          const data = line.slice(6)
          try {
            const parsed = JSON.parse(data)
            if (eventType === 'request_id') {
              currentRequestId = parsed
            } else if (eventType === 'tool_start') {
              toolSteps.push({ name: parsed.name, status: 'running', summary: '', id: parsed.tool_call_id })
              updateLastMsg({ toolSteps: [...toolSteps] })
              scrollToBottom()
            } else if (eventType === 'tool_end') {
              const step = toolSteps.find(s => s.id === parsed.tool_call_id)
              if (step) { step.status = 'done'; step.summary = parsed.result_summary }
              updateLastMsg({ toolSteps: [...toolSteps] })
              scrollToBottom()
            } else if (eventType === 'reasoning') {
              reasoning += parsed
              updateLastMsg({ reasoning })
              scrollToBottom()
            } else if (eventType === 'content') {
              if (content === '' && reasoning) {
                updateLastMsg({ _showReasoning: false })
              }
              content += parsed
              updateLastMsg({ content })
              scrollToBottom()
            } else if (eventType === 'sources') {
              updateLastMsg({ sources: parsed })
            } else if (eventType === 'error') {
              content += '\n\n⚠️ ' + parsed
              updateLastMsg({ content })
            }
          } catch (_) { /* 非 JSON data */ }
          eventType = ''
        }
      }
    }
  } catch (e) {
    loading.value = false
    // 断连恢复
    if (currentRequestId) {
      try {
        const result = await chatApi.getResult(currentRequestId)
        if (lastMsg()?.role === 'assistant') {
          updateLastMsg({
            content: result.answer || '（连接中断，已恢复结果）',
            reasoning: result.reasoning || '',
            sources: result.sources || [],
          })
        } else {
          messages.value.push({
            role: 'assistant',
            content: result.answer || '（连接中断，已恢复结果）',
            reasoning: result.reasoning || '',
            sources: result.sources || [],
            _showReasoning: false,
          })
        }
      } catch (_) {
        if (!lastMsg()?.content) {
          messages.value.push({ role: 'assistant', content: '连接中断，请重试。', _showReasoning: false })
        }
      }
    } else {
      messages.value.push({ role: 'assistant', content: '抱歉，出了点问题，请稍后再试。', _showReasoning: false })
    }
  }

  currentRequestId = null
  activeAbortController = null
  loading.value = false
  scrollToBottom(true)
}

async function clearChat() {
  uni.showModal({
    title: '清除对话', content: '确定清除所有对话记录？',
    cancelText: '取消', confirmText: '清除',
    success: async (res) => {
      if (res.confirm) {
        await chatApi.clear(conversationId)
        messages.value = [{ role: 'assistant', content: '对话已清除。有什么可以帮你的？' }]
        scrollToBottom(true)
      }
    },
  })
}

let _scrollCounter = 0
let _scrollTimer = null
function scrollToBottom(immediate = false) {
  // uni scroll-view 需要每次设不同值才滚动
  if (immediate) {
    _scrollCounter++
    nextTick(() => { scrollTop.value = _scrollCounter * 99999 })
    return
  }
  // 节流：流式输出时最多 100ms 滚动一次
  if (_scrollTimer) return
  _scrollTimer = setTimeout(() => {
    _scrollCounter++
    scrollTop.value = _scrollCounter * 99999
    _scrollTimer = null
  }, 100)
}

// 页面从后台恢复时，检查是否有中断的流需要恢复
async function handleVisibilityChange() {
  if (document.visibilityState !== 'visible') return
  if (!currentRequestId || !loading.value) return

  // 页面恢复，stream 可能已断，尝试用 request_id 恢复结果
  try {
    // 等 2 秒让后端有时间完成生成
    await new Promise(r => setTimeout(r, 2000))
    const result = await chatApi.getResult(currentRequestId)
    // 成功拿到结果，更新最后一条消息
    if (lastMsg()?.role === 'assistant') {
      updateLastMsg({
        content: result.answer || lastMsg().content,
        reasoning: result.reasoning || lastMsg().reasoning || '',
        sources: result.sources || lastMsg().sources || [],
        _showReasoning: false,
      })
    }
    loading.value = false
    activeAbortController = null
    currentRequestId = null
    scrollToBottom(true)
  } catch (_) {
    // 结果还没生成完，继续等（stream 可能还在后台跑）
  }
}

onMounted(() => {
  if (!initialized) { loadHistory(); loadQuickQuestions(); initialized = true }
  // #ifdef H5
  document.addEventListener('visibilitychange', handleVisibilityChange)
  // #endif
})
onUnmounted(() => {
  // #ifdef H5
  document.removeEventListener('visibilitychange', handleVisibilityChange)
  // #endif
})
onShow(() => { if (initialized) scrollToBottom(true) })
</script>

<style lang="scss" scoped>
.chat-page {
  position: fixed;
  top: 0;
  left: 0; right: 0;
  bottom: var(--window-bottom, 50px);
  background: $color-bg-card;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mini-nav {
  flex-shrink: 0;
  padding-top: env(safe-area-inset-top, 20px);
  height: calc(env(safe-area-inset-top, 20px) + 36px);
  display: flex; align-items: flex-end; justify-content: center;
  padding-bottom: 6px;
  background: $color-bg-card;
  border-bottom: 1rpx solid $color-border;
}
.mini-nav-title {
  font-size: 30rpx; font-weight: 600; color: $color-text-primary;
}

.chat-messages {
  flex: 1;
  min-height: 0;
  height: 0;
  padding: 16rpx 20rpx;
}

.chat-msg { margin-bottom: 20rpx; }
.chat-msg.user { display: flex; justify-content: flex-end; }

.bubble {
  display: inline-block; max-width: 82%;
  padding: 20rpx 28rpx; border-radius: $radius-xl;
  font-size: $font-base; line-height: 1.6; text-align: left;
}
.chat-msg.user .bubble {
  background: $color-primary-gradient; color: #fff;
  border-bottom-right-radius: $radius-sm;
}
.chat-msg.ai .bubble {
  background: $color-bg-card; border: 1rpx solid $color-border;
  border-bottom-left-radius: $radius-sm; box-shadow: $shadow-sm; line-height: 1.8;
}

/* Tool 执行步骤 — 通用渲染 */
.tool-steps { margin-bottom: 8rpx; }
.tool-step {
  display: flex; align-items: center; gap: 8rpx;
  padding: 6rpx 0; font-size: 24rpx; color: $color-text-secondary;
}
.tool-step.running { color: $color-primary; }
.tool-step.done { color: $color-text-tertiary; }
.tool-icon { font-size: 22rpx; width: 28rpx; text-align: center; }
.tool-step.running .tool-icon { animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }
.tool-name { font-weight: 500; }
.tool-summary { color: $color-text-tertiary; margin-left: 4rpx; }

/* 思考过程 */
.reasoning-toggle {
  display: inline-flex; align-items: center;
  font-size: 22rpx; color: $color-text-tertiary;
  margin-top: 6rpx; padding-left: 4rpx; cursor: pointer;
}
.reasoning-box {
  margin-top: 6rpx; padding: 16rpx 20rpx;
  background: #f8f8fa; border-radius: $radius-lg;
  font-size: 24rpx; line-height: 1.7; color: $color-text-secondary;
}

/* 来源 */
.source-link { font-size: 24rpx; color: $color-primary; margin-top: 6rpx; padding-left: 4rpx; display: flex; flex-wrap: wrap; align-items: center; }
.source-ref { color: $color-primary; margin-right: 12rpx; text-decoration: underline; }

.typing-indicator { display: inline-flex; gap: 8rpx; padding: 8rpx 0; align-items: center; }
.typing-dot {
  width: 12rpx; height: 12rpx; background: $color-text-tertiary;
  border-radius: 50%; display: inline-block; animation: typing 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%,100% { opacity: 0.3; } 50% { opacity: 1; } }

/* 底部 — 紧凑，不遮挡内容 */
.chat-bottom {
  flex-shrink: 0;
  background: $color-bg-card;
  border-top: 1rpx solid $color-border;
  padding-bottom: env(safe-area-inset-bottom, 0);
}

.quick-row { padding: 6rpx 16rpx 0; }
.quick-bar { white-space: nowrap; }
.quick-chips-row { display: inline-flex; gap: 10rpx; }
.quick-chip {
  display: inline-flex; align-items: center;
  height: 44rpx; line-height: 44rpx; padding: 0 18rpx;
  border-radius: $radius-full; font-size: 22rpx;
  border: 1rpx solid $color-border; background: $color-bg-card;
  color: $color-text-secondary; white-space: nowrap; flex-shrink: 0;
}
.clear-chip { color: $color-text-disabled; border-color: transparent; }

.chat-input-bar {
  display: flex; align-items: center; gap: 10rpx;
  padding: 8rpx 16rpx 10rpx;
}
.think-toggle {
  height: 64rpx; border-radius: $radius-full; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center; gap: 4rpx;
  padding: 0 16rpx;
  color: $color-text-disabled; border: 1rpx solid $color-border;
  transition: all 0.2s;
}
.think-icon { font-size: 30rpx; }
.think-label { font-size: 20rpx; }
.think-toggle.active {
  color: $color-primary; border-color: $color-primary;
  background: rgba(79,70,229,0.08);
}
.chat-input {
  flex: 1; height: 64rpx; padding: 0 20rpx;
  background: $color-bg-hover; border: 2rpx solid transparent;
  border-radius: $radius-full; font-size: $font-base; color: $color-text-primary;
}
.chat-send {
  width: 64rpx; height: 64rpx; border-radius: 50%; flex-shrink: 0;
  background: $color-primary-gradient; color: #fff;
  display: flex; align-items: center; justify-content: center;
}
.send-icon { font-size: 30rpx; }
</style>
