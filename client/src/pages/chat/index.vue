<template>
  <view class="page flex-col">
    <!-- 清除对话按钮 -->
    <view class="chat-topbar">
      <text class="chat-clear" @click="clearChat">清除对话</text>
    </view>

    <!-- 消息区域 -->
    <scroll-view scroll-y class="chat-messages" :scroll-top="scrollTop" @scrolltolower="() => {}">
      <view v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role === 'user' ? 'user' : 'ai'">
        <view class="bubble">
          <rich-text v-if="msg.role === 'assistant'" :nodes="formatContent(msg.content)" />
          <text v-else>{{ msg.content }}</text>
        </view>
        <!-- 来源链接 -->
        <view v-if="msg.sources && msg.sources.length" class="source-link">
          <text>来源: </text>
          <text v-for="src in uniqueSources(msg.sources)" :key="src.recording_id"
                class="source-ref" @click="openRecording(src.recording_id)">
            {{ src.recording_filename }}
          </text>
        </view>
      </view>
      <!-- 打字指示器 -->
      <view v-if="loading" class="chat-msg ai">
        <view class="bubble">
          <view class="typing-indicator">
            <text class="typing-dot"></text>
            <text class="typing-dot"></text>
            <text class="typing-dot"></text>
          </view>
        </view>
      </view>
    </scroll-view>

    <!-- 快捷提问栏 -->
    <scroll-view scroll-x class="quick-bar">
      <view class="quick-chips-row">
        <text class="quick-chip" v-for="q in quickQuestions" :key="q" @click="askQuestion(q)">{{ q }}</text>
      </view>
    </scroll-view>

    <!-- 输入栏 -->
    <view class="chat-input-bar safe-bottom">
      <input class="chat-input" v-model="inputText" placeholder="输入你的问题..."
             confirm-type="send" @confirm="sendMessage" :adjust-position="true" />
      <view class="chat-send" @click="sendMessage">
        <text class="ti ti-send send-icon"></text>
      </view>
    </view>

    <TabBar current="chat" />
  </view>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import TabBar from '@/components/TabBar.vue'
import { chatApi, speakerApi } from '@/api'
import { renderMarkdown } from '@/utils/format'

const messages = ref([])
const inputText = ref('')
const loading = ref(false)
const scrollTop = ref(0)
const quickQuestions = ref(['最近讨论了什么？', '有哪些待办事项？', '关键决策总结'])
const conversationId = 'default'
let initialized = false

/** 格式化 AI 消息内容 — markdown 渲染 */
function formatContent(text) {
  return renderMarkdown(text)
}

/** 去重来源列表 */
function uniqueSources(sources) {
  if (!sources) return []
  const seen = new Set()
  return sources.filter(s => {
    if (seen.has(s.recording_id)) return false
    seen.add(s.recording_id)
    return true
  })
}

/** 跳转到录音详情 */
function openRecording(recordingId) {
  uni.navigateTo({ url: `/pages/detail/index?id=${recordingId}` })
}

/** 加载历史对话 */
async function loadHistory() {
  try {
    const history = await chatApi.history(conversationId)
    if (history.length) {
      messages.value = history.map(m => ({ role: m.role, content: m.content }))
    } else {
      messages.value = [{
        role: 'assistant',
        content: '你好！我是 VoiceKB 智能助手，可以帮你查找和分析录音内容。试试下方的快捷提问，或直接输入你的问题。'
      }]
    }
  } catch (e) {
    messages.value = [{ role: 'assistant', content: '你好！有什么可以帮你的？' }]
  }
  scrollToBottom()
}

/** 动态生成快捷提问（基于实际说话人） */
async function loadQuickQuestions() {
  try {
    const spks = await speakerApi.list()
    const named = spks.filter(s => !s.name.startsWith('说话人')).slice(0, 2)
    const qs = ['最近讨论了什么？', '有哪些待办事项？']
    named.forEach(s => qs.push(`${s.name}说了什么？`))
    if (qs.length < 4) qs.push('关键决策总结')
    quickQuestions.value = qs
  } catch (e) { /* keep defaults */ }
}

/** 快捷提问 */
function askQuestion(q) {
  inputText.value = q
  sendMessage()
}

/** 发送消息 — 多轮对话，带 conversation_id */
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
    // 附加来源信息
    if (result.sources?.length) {
      msg.sources = result.sources
    }
    messages.value.push(msg)
  } catch (e) {
    messages.value.push({ role: 'assistant', content: '抱歉，出了点问题，请稍后再试。' })
  }
  loading.value = false
  scrollToBottom()
}

/** 清除对话 */
async function clearChat() {
  uni.showModal({
    title: '清除对话',
    content: '确定清除所有对话记录？',
    cancelText: '取消',
    confirmText: '清除',
    success: async (res) => {
      if (res.confirm) {
        await chatApi.clear(conversationId)
        messages.value = [{ role: 'assistant', content: '对话已清除。有什么可以帮你的？' }]
        scrollToBottom()
      }
    },
  })
}

/** 自动滚到底部（requestAnimationFrame 等效） */
function scrollToBottom() {
  nextTick(() => {
    scrollTop.value = messages.value.length * 9999
  })
}

onMounted(() => {
  if (!initialized) {
    loadHistory()
    loadQuickQuestions()
    initialized = true
  }
})

// Tab 切换回来时保持对话状态，仅滚到底部
onShow(() => {
  if (initialized) scrollToBottom()
})
</script>

<style lang="scss" scoped>
.page {
  /* 减去自定义 tabBar(110rpx) */
  height: #{"calc(100vh - var(--window-top, 0px) - 110rpx)"};
  background: $color-bg-page;
  overflow: hidden;
}
.flex-col { display: flex; flex-direction: column; }

/* ── 顶部清除按钮 ── */
.chat-topbar {
  display: flex;
  justify-content: flex-end;
  padding: $spacing-sm $spacing-lg;
  flex-shrink: 0;
}
.chat-clear {
  font-size: $font-xs;
  color: $color-text-tertiary;
}

/* ── 消息列表 ── */
.chat-messages {
  flex: 1;
  padding: 24rpx;
  min-height: 0; /* 关键：让 flex 子项可以缩小 */
}

.chat-msg {
  margin-bottom: 28rpx;
}
.chat-msg.user {
  display: flex;
  justify-content: flex-end;
}

/* ── 气泡 ── */
.bubble {
  display: inline-block;
  max-width: 82%;
  padding: 20rpx 28rpx;
  border-radius: $radius-xl;
  font-size: $font-base;
  line-height: 1.6;
  text-align: left;
}

/* 用户气泡 — 紫色渐变 */
.chat-msg.user .bubble {
  background: $color-primary-gradient;
  color: #fff;
  border-bottom-right-radius: $radius-sm;
}

/* AI 气泡 — 白底带边框 */
.chat-msg.ai .bubble {
  background: $color-bg-card;
  border: 1rpx solid $color-border;
  border-bottom-left-radius: $radius-sm;
  box-shadow: $shadow-sm;
  line-height: 1.8;
}

/* ── 来源链接 ── */
.source-link {
  font-size: 24rpx;
  color: $color-primary;
  margin-top: 8rpx;
  padding-left: 4rpx;
}
.source-ref {
  color: $color-primary;
  margin-right: 12rpx;
}

/* ── 打字指示器（三圆点动画） ── */
.typing-indicator {
  display: flex;
  gap: 8rpx;
  padding: 8rpx 0;
}
.typing-dot {
  width: 12rpx;
  height: 12rpx;
  background: $color-text-tertiary;
  border-radius: 50%;
  display: inline-block;
  animation: typing 1.2s infinite;
}
.typing-dot:nth-child(2) { animation-delay: 0.2s; }
.typing-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

/* ── 快捷提问栏 ── */
.quick-bar {
  white-space: nowrap;
  padding: $spacing-xs $spacing-md;
  flex-shrink: 0;
}
.quick-chips-row {
  display: inline-flex;
  gap: 12rpx;
}
.quick-chip {
  display: inline-block;
  height: 56rpx;
  line-height: 56rpx;
  padding: 0 $spacing-xl;
  border-radius: $radius-full;
  font-size: $font-xs;
  border: 2rpx solid $color-border;
  background: $color-bg-card;
  color: $color-text-secondary;
  white-space: nowrap;
  flex-shrink: 0;
}

/* ── 底部输入栏 ── */
.chat-input-bar {
  display: flex;
  gap: $spacing-md;
  padding: $spacing-md $spacing-lg;
  background: $color-bg-card;
  border-top: 1rpx solid $color-border;
  flex-shrink: 0;
}
.chat-input {
  flex: 1;
  height: 80rpx;
  padding: 0 $spacing-lg;
  background: $color-bg-hover;
  border: 3rpx solid transparent;
  border-radius: $radius-full;
  font-size: $font-base;
  color: $color-text-primary;
}
.chat-send {
  width: 80rpx;
  height: 80rpx;
  border-radius: 50%;
  flex-shrink: 0;
  background: $color-primary-gradient;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4rpx 16rpx rgba(79, 70, 229, 0.3);
}
.send-icon {
  font-size: 36rpx;
}
</style>
