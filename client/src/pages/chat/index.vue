<template>
  <view class="page flex-col">
    <!-- 清除按钮 -->
    <view class="chat-topbar">
      <text class="chat-clear" @click="clearChat">清除对话</text>
    </view>

    <!-- 消息区域 -->
    <scroll-view scroll-y class="chat-messages" :scroll-top="scrollTop" @scrolltolower="() => {}">
      <view v-for="(msg, i) in messages" :key="i" class="chat-msg" :class="msg.role === 'user' ? 'user' : 'ai'">
        <view class="bubble">
          <rich-text v-if="msg.role === 'assistant'" :nodes="renderMarkdown(msg.content)" />
          <text v-else>{{ msg.content }}</text>
        </view>
      </view>
      <view v-if="loading" class="chat-msg ai">
        <view class="bubble typing">
          <text class="dot">·</text><text class="dot">·</text><text class="dot">·</text>
        </view>
      </view>
    </scroll-view>

    <!-- 快捷提问 -->
    <scroll-view scroll-x class="quick-bar">
      <view class="quick-chip" v-for="q in quickQuestions" :key="q" @click="askQuestion(q)">{{ q }}</view>
    </scroll-view>

    <!-- 输入栏 -->
    <view class="chat-input-bar safe-bottom">
      <input class="chat-input" v-model="inputText" placeholder="输入你的问题..."
             confirm-type="send" @confirm="sendMessage" />
      <view class="chat-send" @click="sendMessage">
        <text style="font-size: 28rpx">▶</text>
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

async function loadHistory() {
  try {
    const history = await chatApi.history(conversationId)
    if (history.length) {
      messages.value = history.map(m => ({ role: m.role, content: m.content }))
    } else {
      messages.value = [{ role: 'assistant', content: '你好！我是 VoiceKB 智能助手，可以帮你查找和分析录音内容。试试下方的快捷提问吧。' }]
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
  } catch (e) { /* keep defaults */ }
}

function askQuestion(q) {
  inputText.value = q
  sendMessage()
}

async function sendMessage() {
  const q = inputText.value.trim()
  if (!q || loading.value) return
  inputText.value = ''

  messages.value.push({ role: 'user', content: q })
  loading.value = true
  scrollToBottom()

  try {
    const result = await chatApi.ask(q, conversationId)
    messages.value.push({ role: 'assistant', content: result.answer })
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
      }
    },
  })
}

function scrollToBottom() {
  nextTick(() => { scrollTop.value = messages.value.length * 9999 })
}

onMounted(() => {
  if (!initialized) {
    loadHistory()
    loadQuickQuestions()
    initialized = true
  }
})
onShow(() => { if (initialized) scrollToBottom() })
</script>

<style lang="scss" scoped>
.page { min-height: #{"calc(100vh - var(--window-top, 0px))"}; background: $color-bg-page; }
.flex-col { display: flex; flex-direction: column; }

.chat-topbar { display: flex; justify-content: flex-end; padding: $spacing-sm $spacing-lg; }
.chat-clear { font-size: $font-xs; color: $color-text-tertiary; }

.chat-messages { flex: 1; padding: $spacing-md; }
.chat-msg { margin-bottom: $spacing-lg; }
.chat-msg.user { display: flex; justify-content: flex-end; }
.bubble {
  display: inline-block; max-width: 82%; padding: $spacing-md $spacing-lg;
  border-radius: $radius-xl; font-size: $font-base; line-height: 1.7;
}
.chat-msg.user .bubble { background: $color-primary-gradient; color: #fff; border-bottom-right-radius: $radius-sm; }
.chat-msg.ai .bubble { background: $color-bg-card; border: 1rpx solid $color-border; border-bottom-left-radius: $radius-sm; box-shadow: $shadow-sm; }
.typing .dot { display: inline-block; animation: blink 1.2s infinite; font-size: 40rpx; font-weight: 700; }
.typing .dot:nth-child(2) { animation-delay: 0.2s; }
.typing .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%,100% { opacity: 0.2; } 50% { opacity: 1; } }

.quick-bar { white-space: nowrap; padding: $spacing-xs $spacing-md; flex-shrink: 0; }
.quick-chip {
  display: inline-block; height: 56rpx; line-height: 56rpx; padding: 0 $spacing-xl;
  border-radius: $radius-full; font-size: $font-xs; margin-right: $spacing-sm;
  border: 2rpx solid $color-border; background: $color-bg-card; color: $color-text-secondary;
}

.chat-input-bar {
  display: flex; gap: $spacing-md; padding: $spacing-md $spacing-lg; background: $color-bg-card;
  border-top: 1rpx solid $color-border; flex-shrink: 0;
}
.chat-input {
  flex: 1; height: 80rpx; padding: 0 $spacing-lg; background: $color-bg-hover;
  border-radius: $radius-full; font-size: $font-base;
}
.chat-send {
  width: 80rpx; height: 80rpx; border-radius: 50%; flex-shrink: 0;
  background: $color-primary-gradient; color: #fff; display: flex; align-items: center; justify-content: center;
}
</style>
