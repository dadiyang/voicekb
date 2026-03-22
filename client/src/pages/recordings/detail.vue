<template>
  <view class="page-white">
    <!-- 自定义导航栏 -->
    <view class="nav-bar" :style="{paddingTop: statusBarHeight + 'px'}">
      <view class="nav-back" @click="goBack">
        <text class="nav-back-icon">&lt;</text>
        <text>返回</text>
      </view>
      <view class="nav-more" @click="showMenu">···</view>
    </view>

    <!-- 处理中 -->
    <view v-if="recording?.status === 'processing'" class="card" style="margin-top: 24rpx">
      <text class="card-title">{{ recording.title || recording.filename }}</text>
      <view class="progress-bg"><view class="progress-fill" :style="{width: progress.percent + '%'}" /></view>
      <text class="progress-text">{{ progress.step }} ({{ progress.percent }}%)</text>
    </view>

    <template v-else-if="recording">
      <!-- 标题 -->
      <view class="detail-header">
        <text class="detail-title">{{ recording.title || recording.filename }}</text>
        <text class="detail-meta">{{ relativeTime(recording.created_at) }} · {{ friendlyDuration(recording.duration) }} · {{ (recording.speakers||[]).join(', ') }}</text>
      </view>

      <!-- 音频播放器 -->
      <view class="audio-bar">
        <slider :value="audioPos" :max="audioDur" block-size="14" active-color="#4F46E5" @change="onSeek" />
        <view class="audio-controls">
          <text class="audio-time">{{ formatTimestamp(audioPos) }} / {{ formatTimestamp(audioDur) }}</text>
          <view class="audio-play-btn" @click="togglePlay">
            <text>{{ isPlaying ? '⏸' : '▶' }}</text>
          </view>
        </view>
        <text class="audio-hint">点击对话文字可跳转播放</text>
      </view>

      <!-- 摘要 -->
      <view v-if="recording.summary" class="summary-card">
        <view class="summary-header">
          <text class="summary-label">会议摘要</text>
          <text class="summary-edit" @click="editPrompt">调整总结方式</text>
        </view>
        <rich-text class="summary-text" :nodes="renderMarkdown(recording.summary)" />
      </view>

      <!-- 对话记录 -->
      <view class="section-title">
        <text>对话记录</text>
        <text v-if="hasUnnamed" class="section-hint">点击说话人标签可标注真实姓名</text>
      </view>

      <view class="transcript">
        <view v-for="(g, gi) in mergedSegments" :key="gi"
              class="transcript-item" :class="{playing: playingIdx === g.indices[0]}"
              @click="seekTo(g.start, g.indices[0])">
          <view class="transcript-avatar" :class="'spk-' + (speakerColors[g.speaker_id] % 5)">
            {{ g.speaker_id.charAt(0) }}
          </view>
          <view class="transcript-bubble">
            <view class="transcript-speaker">
              <text class="speaker-tag" @click.stop="renameSpeaker(g.speaker_id)">{{ g.speaker_id }}</text>
              <text class="ts">{{ formatTimestamp(g.start) }}</text>
            </view>
            <text class="transcript-text" v-for="(t, ti) in g.texts" :key="ti">{{ t }}</text>
          </view>
        </view>
      </view>
    </template>

    <!-- H5 音频播放用 JS Audio 对象，不用 <audio> 标签 -->
  </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { recordingApi } from '@/api'
import { relativeTime, friendlyDuration, formatTimestamp, mergeSegments, renderMarkdown } from '@/utils/format'

const recording = ref(null)
const progress = ref({ step: '', percent: 0 })
const isPlaying = ref(false)
const audioPos = ref(0)
const audioDur = ref(0)
const playingIdx = ref(-1)
const audioEl = ref(null)
const statusBarHeight = ref(0)

let recId = ''
let seekTime = 0
let audioCtx = null
let pollTimer = null

const audioUrl = computed(() => recId ? `/api/recordings/${recId}/audio` : '')

const speakerColors = computed(() => {
  const map = {}
  let idx = 0
  ;(recording.value?.speakers || []).forEach(s => { map[s] = idx++ })
  return map
})

const mergedSegments = computed(() => mergeSegments(recording.value?.segments))

const hasUnnamed = computed(() =>
  (recording.value?.speakers || []).some(s => s.startsWith('说话人'))
)

onLoad((query) => {
  recId = query.id
  seekTime = parseFloat(query.seek || 0)
  // #ifdef H5
  statusBarHeight.value = 0
  // #endif
  // #ifndef H5
  statusBarHeight.value = uni.getSystemInfoSync().statusBarHeight
  // #endif
  loadRecording()
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (audioCtx) {
    // #ifdef H5
    audioCtx.pause()
    // #endif
    // #ifndef H5
    audioCtx.stop(); audioCtx.destroy()
    // #endif
  }
})

async function loadRecording() {
  try {
    recording.value = await recordingApi.get(recId)
    if (recording.value.status === 'processing') {
      startPolling()
    } else {
      audioDur.value = recording.value.duration || 0
      if (seekTime > 0) {
        // 找到对应的 segment index
        const segs = mergedSegments.value
        let targetIdx = 0
        for (let i = 0; i < segs.length; i++) {
          if (segs[i].start >= seekTime - 1) { targetIdx = segs[i].indices[0]; break }
        }
        setTimeout(() => seekTo(seekTime, targetIdx), 800)
      }
    }
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const st = await recordingApi.status(recId)
      progress.value = st
      if (st.percent >= 100 || st.percent < 0) {
        clearInterval(pollTimer)
        pollTimer = null
        loadRecording()
      }
    } catch (e) { /* continue */ }
  }, 2000)
}

function ensureAudio() {
  if (audioCtx) return
  // #ifdef H5
  audioCtx = new Audio(audioUrl.value)
  audioCtx.addEventListener('timeupdate', () => { audioPos.value = Math.floor(audioCtx.currentTime) })
  audioCtx.addEventListener('ended', () => { isPlaying.value = false })
  // #endif
  // #ifndef H5
  audioCtx = uni.createInnerAudioContext()
  audioCtx.src = audioUrl.value
  audioCtx.onTimeUpdate(() => { audioPos.value = Math.floor(audioCtx.currentTime) })
  audioCtx.onEnded(() => { isPlaying.value = false })
  // #endif
}

function togglePlay() {
  ensureAudio()
  if (isPlaying.value) { audioCtx.pause() } else { audioCtx.play() }
  isPlaying.value = !isPlaying.value
}

function onTimeUpdate() {}

function onSeek(e) {
  ensureAudio()
  const t = e.detail.value
  // #ifdef H5
  audioCtx.currentTime = t
  // #endif
  // #ifndef H5
  audioCtx.seek(t)
  // #endif
  audioPos.value = t
}

function seekTo(time, idx) {
  ensureAudio()
  playingIdx.value = idx
  // #ifdef H5
  audioCtx.currentTime = time
  // #endif
  // #ifndef H5
  audioCtx.seek(time)
  // #endif
  audioCtx.play()
  isPlaying.value = true
  audioPos.value = Math.floor(time)
}

function renameSpeaker(speakerId) {
  uni.showModal({
    title: '标注说话人',
    editable: true,
    placeholderText: '输入真实姓名',
    cancelText: '取消',
    confirmText: '保存',
    success: async (res) => {
      if (res.confirm && res.content?.trim()) {
        const { speakerApi } = await import('@/api')
        await speakerApi.rename(speakerId, res.content.trim())
        uni.showToast({ title: `已标注为"${res.content.trim()}"`, icon: 'success' })
        loadRecording()
      }
    },
  })
}

function editPrompt() {
  // 简单的自然语言输入
  uni.showModal({
    title: '调整总结方式',
    editable: true,
    placeholderText: '告诉 AI 你希望怎么总结，例如：重点列出行动项和负责人',
    cancelText: '取消',
    confirmText: '保存并重新总结',
    success: async (res) => {
      if (res.confirm && res.content?.trim()) {
        await recordingApi.setPrompt(recId, res.content.trim())
        uni.showToast({ title: '正在重新总结...', icon: 'none' })
        await recordingApi.resummarize(recId)
        uni.showToast({ title: '总结已更新', icon: 'success' })
        loadRecording()
      }
    },
  })
}

function showMenu() {
  uni.showActionSheet({
    itemList: ['重新总结', '重新识别（较慢）', '修改分类', '删除录音'],
    success: async (res) => {
      if (res.tapIndex === 0) {
        uni.showToast({ title: '正在重新总结...', icon: 'none' })
        await recordingApi.resummarize(recId)
        uni.showToast({ title: '总结已更新', icon: 'success' })
        loadRecording()
      } else if (res.tapIndex === 1) {
        await recordingApi.reprocess(recId)
        recording.value.status = 'processing'
        startPolling()
      } else if (res.tapIndex === 2) {
        // 分类修改
        const { categoryApi } = await import('@/api')
        const cats = await categoryApi.list()
        uni.showActionSheet({
          itemList: cats.map(c => c.name),
          success: async (r) => {
            await recordingApi.updateCategory(recId, cats[r.tapIndex].name)
            uni.showToast({ title: '分类已更新', icon: 'success' })
            loadRecording()
          },
        })
      } else if (res.tapIndex === 3) {
        uni.showModal({
          title: '确认删除', content: '删除后不可恢复',
          cancelText: '取消', confirmText: '删除',
          success: async (r) => {
            if (r.confirm) {
              await recordingApi.delete(recId)
              uni.showToast({ title: '已删除', icon: 'success' })
              uni.navigateBack()
            }
          },
        })
      }
    },
  })
}

function goBack() { uni.navigateBack() }
</script>

<style lang="scss" scoped>
.page-white { min-height: 100vh; background: $color-bg-card; }

.nav-bar { display: flex; justify-content: space-between; align-items: center; padding: $spacing-md $spacing-lg; background: $color-bg-card; border-bottom: 1rpx solid $color-border; }
.nav-back { display: flex; align-items: center; gap: $spacing-xs; font-size: $font-base; color: $color-primary; }
.nav-back-icon { font-size: $font-lg; }
.nav-more { font-size: 36rpx; color: $color-text-tertiary; padding: 0 $spacing-md; }

.detail-header { padding: $spacing-lg; }
.detail-title { font-size: $font-xl; font-weight: 700; word-break: break-all; display: block; margin-bottom: $spacing-sm; }
.detail-meta { font-size: $font-xs; color: $color-text-tertiary; }

.audio-bar { padding: $spacing-md $spacing-lg; background: $color-bg-page; }
.audio-controls { display: flex; align-items: center; justify-content: space-between; margin-top: $spacing-xs; }
.audio-time { font-size: $font-xs; color: $color-text-tertiary; }
.audio-play-btn { width: 64rpx; height: 64rpx; border-radius: 50%; background: $color-primary; color: #fff; display: flex; align-items: center; justify-content: center; }
.audio-hint { font-size: 20rpx; color: $color-text-disabled; text-align: center; margin-top: $spacing-xs; display: block; }

.summary-card { margin: $spacing-md $spacing-lg; padding: $spacing-lg; background: $color-primary-light; border-radius: $radius-xl; }
.summary-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: $spacing-md; }
.summary-label { font-size: $font-base; font-weight: 600; color: $color-primary-dark; }
.summary-edit { font-size: $font-xs; color: $color-primary; }
.summary-text { font-size: $font-sm; color: $color-text-secondary; line-height: 1.8; }

.section-title { padding: $spacing-lg; display: flex; align-items: baseline; gap: $spacing-md; }
.section-title text:first-child { font-size: $font-md; font-weight: 600; }
.section-hint { font-size: 20rpx; color: $color-text-disabled; }

.transcript { padding: 0 $spacing-lg $spacing-xxl; }
.transcript-item { display: flex; gap: $spacing-md; margin-bottom: $spacing-lg; padding: $spacing-sm; border-radius: $radius-lg; }
.transcript-item.playing { background: $color-primary-light; border-left: 4rpx solid $color-primary; padding-left: $spacing-md; }
.transcript-avatar { width: 56rpx; height: 56rpx; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: $font-xs; font-weight: 600; color: #fff; flex-shrink: 0; }
.spk-0 { background: $color-primary; }
.spk-1 { background: $color-warning; }
.spk-2 { background: $color-success; }
.spk-3 { background: #DB2777; }
.spk-4 { background: #7C3AED; }
.transcript-bubble { flex: 1; }
.transcript-speaker { display: flex; align-items: center; gap: $spacing-sm; margin-bottom: 4rpx; }
.speaker-tag { font-size: 22rpx; font-weight: 500; padding: 2rpx 12rpx; border-radius: $radius-sm; background: $color-primary-light; color: $color-primary-dark; }
.ts { font-size: 20rpx; color: $color-text-disabled; }
.transcript-text { font-size: $font-base; color: $color-text-primary; line-height: 1.7; display: block; }

.progress-bg { height: 12rpx; background: $color-bg-hover; border-radius: 6rpx; overflow: hidden; margin: $spacing-md 0; }
.progress-fill { height: 100%; background: $color-primary-gradient; border-radius: 6rpx; transition: width 0.3s; }
.progress-text { font-size: $font-xs; color: $color-text-tertiary; text-align: center; }
</style>
