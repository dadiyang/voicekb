<template>
  <view class="chat-page">
    <!-- 消息区域（可滚动） -->
    <scroll-view scroll-y class="chat-messages" :scroll-top="scrollTop">
      <view v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role === 'user' ? 'user' : 'ai'">
        <view class="bubble">
          <rich-text v-if="msg.role === 'assistant'" :nodes="formatContent(msg.content)" />
          <text v-else>{{ msg.content }}</text>
        </view>
        <view v-if="msg.sources && msg.sources.length" class="source-link">
          <text>来源: </text>
          <text v-for="src in uniqueSources(msg.sources)" :key="src.recording_id"
                class="source-ref" @click="openRecording(src.recording_id)">{{ src.recording_filename }}</text>
        </view>
      </view>
      <view v-if="loading" class="chat-msg ai">
        <view class="bubble">
          <view class="typing-indicator">
            <text class="typing-dot"></text><text class="typing-dot"></text><text class="typing-dot"></text>
          </view>
        </view>
      </view>
      <!-- 底部占位，防止最后一条消息被遮挡 -->
      <view style="height: 20rpx"></view>
    </scroll-view>

    <!-- 底部固定区域：快捷提问 + 输入栏 -->
    <view class="chat-bottom">
      <scroll-view scroll-x class="quick-bar">
        <view class="quick-chips-row">
          <text class="quick-chip" v-for="q in quickQuestions" :key="q" @click="askQuestion(q)">{{ q }}</text>
          <text class="quick-chip clear-chip" @click="clearChat">
            <text class="ti ti-trash" style="margin-right:4rpx"></text>清除
          </text>
        </view>
      </scroll-view>
      <view class="chat-input-bar">
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
import { ref, nextTick, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { chatApi, speakerApi } from '@/api'
import { renderMarkdown } from '@/utils/format'

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const scrollTop = ref(0)
const quickQuestions = ref(['最近讨论了什么？', '有哪些待办事项？', '关键决策总结'])
const conversationId = 'default'
let initialized = false

function formatContent(text) { return renderMarkdown(text) }

function uniqueSources(sources) {
  if (!sources) return []
  const seen = new Set()
  return sources.filter(s => { if (seen.has(s.recording_id)) return false; seen.add(s.recording_id); return true })
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
  scrollToBottom()
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

async function sendMessage() {
  const q = inputText.value.trim()
  if (!q || loading.value) return
  inputText.value = ''
  messages.value.push({ role: 'user', content: q })
  loading.value = true
  scrollToBottom()

  try {
    const result = await chatApi.ask(q, conversationId)
    const msg = { role: 'assistant', content: result.answer }
    if (result.sources?.length) msg.sources = result.sources
    messages.value.push(msg)
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '抱歉，出了点问题，请稍后再试。' })
  }
  loading.value = false
  scrollToBottom()
}

async function clearChat() {
  uni.showModal({
    title: '清除对话', content: '确定清除所有对话记录？',
    cancelText: '取消', confirmText: '清除',
    success: async (res) => {
      if (res.confirm) {
        await chatApi.clear(conversationId)
        messages.value = [{ role: 'assistant', content: '对话已清除。有什么可以帮你的？' }]
        scrollToBottom()
      }
    },
  })
}

function scrollToBottom() {
  nextTick(() => { scrollTop.value = messages.value.length * 9999 })
}

onMounted(() => {
  if (!initialized) { loadHistory(); loadQuickQuestions(); initialized = true }
})
onShow(() => { if (initialized) scrollToBottom() })
</script>

<style lang="scss" scoped>
/* 整个页面用 fixed 定位，精确控制高度 */
.chat-page {
  position: fixed;
  top: var(--window-top, 44px);
  left: 0; right: 0;
  bottom: var(--window-bottom, 50px);
  background: $color-bg-card; /* 用白色背景消除灰色间隙 */
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 消息区域 — uni scroll-view 需要 height 不能只用 flex */
.chat-messages {
  flex: 1;
  min-height: 0;
  height: 0; /* 配合 flex:1 让 scroll-view 获得正确高度 */
  padding: 24rpx;
}

.chat-msg { margin-bottom: 28rpx; }
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

.source-link { font-size: 24rpx; color: $color-primary; margin-top: 8rpx; padding-left: 4rpx; }
.source-ref { color: $color-primary; margin-right: 12rpx; }

.typing-indicator { display: flex; gap: 8rpx; padding: 8rpx 0; }
.typing-dot {
  width: 12rpx; height: 12rpx; background: $color-text-tertiary;
  border-radius: 50%; display: inline-block; animation: typing 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing { 0%,100% { opacity: 0.3; } 50% { opacity: 1; } }

/* 底部固定区域 */
.chat-bottom {
  flex-shrink: 0;
  background: $color-bg-card;
}

.quick-bar { white-space: nowrap; padding: 8rpx $spacing-md; }
.quick-chips-row { display: inline-flex; gap: 12rpx; }
.quick-chip {
  display: inline-flex; align-items: center;
  height: 56rpx; line-height: 56rpx; padding: 0 $spacing-xl;
  border-radius: $radius-full; font-size: $font-xs;
  border: 2rpx solid $color-border; background: $color-bg-card;
  color: $color-text-secondary; white-space: nowrap; flex-shrink: 0;
}
.clear-chip { color: $color-text-disabled; border-color: transparent; }

.chat-input-bar {
  display: flex; gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: $color-bg-card; border-top: 1rpx solid $color-border;
}
.chat-input {
  flex: 1; height: 80rpx; padding: 0 $spacing-lg;
  background: $color-bg-hover; border: 3rpx solid transparent;
  border-radius: $radius-full; font-size: $font-base; color: $color-text-primary;
}
.chat-send {
  width: 80rpx; height: 80rpx; border-radius: 50%; flex-shrink: 0;
  background: $color-primary-gradient; color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.3);
}
.send-icon { font-size: 36rpx; }
</style>
