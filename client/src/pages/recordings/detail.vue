<template>
  <view class="page-white">
    <!-- 自定义导航栏 -->
    <view class="nav-bar" :style="{paddingTop: statusBarHeight + 'px'}">
      <view class="nav-back" @click="goBack">
        <text class="ti ti-arrow-left nav-back-icon"></text>
        <text>返回</text>
      </view>
      <view class="nav-more" @click="showRecordingMenu" v-if="recording && recording.status !== 'processing'">
        <text class="ti ti-dots"></text>
      </view>
    </view>

    <!-- 处理中 -->
    <view v-if="recording && recording.status === 'processing'" class="card" style="margin-top: 24rpx">
      <text class="card-title">{{ recording.title || recording.filename }}</text>
      <view class="progress-bg"><view class="progress-fill" :style="{width: progress.percent + '%'}" /></view>
      <text class="progress-text">{{ progress.step }} ({{ progress.percent }}%)</text>
      <text class="progress-hint">正在处理，请稍候</text>
    </view>

    <!-- 详情内容 -->
    <template v-else-if="recording">
      <!-- 标题区域 -->
      <view class="detail-header">
        <view class="detail-title-row">
          <view class="detail-title-wrap">
            <text class="detail-title">{{ recording.title || recording.filename }}</text>
            <text class="detail-meta">{{ dateDisplay }} · {{ durDisplay }} · {{ (recording.speakers||[]).join(', ') }}</text>
          </view>
        </view>
      </view>

      <!-- 音频播放器 -->
      <view class="audio-player">
        <slider :value="audioPos" :min="0" :max="audioDur" block-size="14"
                activeColor="#4F46E5" backgroundColor="#E5E7EB"
                @change="onSliderChange" />
        <view class="audio-controls">
          <text class="audio-time">{{ formatTimestamp(audioPos) }} / {{ formatTimestamp(audioDur) }}</text>
          <view class="audio-play-btn" @click="togglePlay">
            <text class="play-icon">{{ isPlaying ? '⏸' : '▶' }}</text>
          </view>
        </view>
        <text class="player-hint">点击对话文字可跳转播放对应片段</text>
      </view>

      <!-- 摘要卡片（可折叠） -->
      <view v-if="recording.summary" class="summary-card">
        <view class="summary-header">
          <text class="summary-label">会议摘要</text>
          <view style="display:flex;gap:16rpx;align-items:center">
            <text class="summary-edit" @click="openPromptEditor">调整总结方式</text>
            <text class="summary-toggle" @click="summaryCollapsed = !summaryCollapsed">{{ summaryCollapsed ? '展开' : '收起' }}</text>
          </view>
        </view>
        <view class="summary-text" :class="{collapsed: summaryCollapsed}">
          <rich-text :nodes="renderMarkdown(recording.summary)" />
        </view>
      </view>

      <!-- 对话记录标题 + 流畅版/原文切换 -->
      <view class="transcript-title">
        <text class="transcript-title-text">对话记录</text>
        <view v-if="hasPolished" class="text-mode-toggle">
          <text class="text-mode-btn" :class="{active: textMode === 'polished'}" @click="textMode = 'polished'">流畅版</text>
          <text class="text-mode-btn" :class="{active: textMode === 'raw'}" @click="textMode = 'raw'">原文</text>
        </view>
      </view>
      <view v-if="hasUnnamed" style="padding:0 24rpx;margin-bottom:16rpx">
        <text class="transcript-title-hint">点击说话人标签可标注真实姓名</text>
      </view>

      <!-- 对话记录 -->
      <view class="transcript">
        <view v-for="(g, gi) in mergedSegs" :key="gi"
              class="transcript-item" :class="{playing: playingIdx === g.indices[0]}"
              :data-start="g.start" :data-end="g.end"
              @click="seekAudio(g.start, g.indices[0])">
          <view class="transcript-avatar" :class="'spk-' + (speakerColors[g.speaker_id] % 5)">
            <text class="avatar-letter">{{ g.speaker_id.charAt(0) || 'S' }}</text>
          </view>
          <view class="transcript-bubble">
            <view class="transcript-speaker">
              <text class="speaker-tag" @click.stop="showRenameModal(g.speaker_id)">{{ g.speaker_id }}</text>
              <text class="ts">{{ formatTimestamp(g.start) }}</text>
            </view>
            <!-- 根据模式显示原文或润色版 -->
            <template v-if="textMode === 'polished' && g.polished.length">
              <text class="transcript-text" v-for="(t, ti) in g.polished" :key="'p'+ti">{{ t }}</text>
            </template>
            <template v-else>
              <text class="transcript-text" v-for="(t, ti) in g.texts" :key="'r'+ti">{{ t }}</text>
            </template>
          </view>
        </view>
      </view>
    </template>

    <!-- 加载失败 -->
    <view v-else-if="loadError" class="card" style="margin-top: 40rpx; text-align: center">
      <text>加载失败，请稍后重试</text>
    </view>

    <!-- ==================== 操作菜单 ==================== -->
    <view v-if="menuVisible" class="modal-overlay" @click.self="menuVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">操作</text>
        <view class="menu-item" @click="doMenuAction('category')">
          <text class="ti ti-tag menu-item-icon"></text>
          <text class="menu-item-text">修改分类</text>
        </view>
        <view class="menu-item" @click="doMenuAction('resummarize')">
          <text class="ti ti-file-text menu-item-icon"></text>
          <text class="menu-item-text">重新总结</text>
        </view>
        <view class="menu-item" @click="doMenuAction('reprocess')">
          <text class="ti ti-refresh menu-item-icon"></text>
          <text class="menu-item-text">重新识别</text>
          <text class="menu-item-sub">(较慢)</text>
        </view>
        <view class="menu-item" @click="doMenuAction('delete')">
          <text class="ti ti-trash menu-item-icon" style="color:#FF3B30"></text>
          <text class="menu-item-text" style="color:#FF3B30">删除录音</text>
        </view>
        <view style="margin-top: 24rpx">
          <button class="btn-outline btn-block" @click="menuVisible = false">取消</button>
        </view>
      </view>
    </view>

    <!-- ==================== 分类选择 ==================== -->
    <view v-if="categoryVisible" class="modal-overlay" @click.self="categoryVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">修改分类</text>
        <view class="cat-chips">
          <text v-for="c in categoryList" :key="c.name"
                class="filter-chip" :class="{active: c.name === currentCategory}"
                @click="selectCategory(c.name)">{{ c.name }}</text>
        </view>
        <text class="cat-add-hint">没有合适的？添加新分类</text>
        <view class="cat-add-row">
          <input class="modal-input" v-model="newCategoryName" placeholder="输入新分类名称..." />
          <button class="btn-primary btn-small" @click="addAndSelectCategory">添加</button>
        </view>
      </view>
    </view>

    <!-- ==================== 说话人标注 ==================== -->
    <view v-if="renameVisible" class="modal-overlay" @click.self="renameVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">标注说话人</text>
        <input class="modal-input" v-model="renameInput" placeholder="输入真实姓名"
               :focus="renameVisible" @confirm="doRename" />
        <view class="modal-actions">
          <button class="btn-outline" @click="renameVisible = false">取消</button>
          <button class="btn-primary" @click="doRename">保存</button>
        </view>
      </view>
    </view>

    <!-- ==================== 摘要模板编辑 ==================== -->
    <view v-if="promptEditorVisible" class="page-white prompt-editor-page">
      <view class="nav-bar" :style="{paddingTop: statusBarHeight + 'px'}">
        <view class="nav-back" @click="closePromptEditor">
          <text class="nav-back-icon">&lt;</text>
          <text>返回</text>
        </view>
      </view>
      <view class="prompt-editor-body">
        <text class="prompt-editor-title">调整总结方式</text>
        <text class="prompt-editor-subtitle">{{ promptCategoryLabel }}{{ promptIsCustom ? '' : '' }}<text v-if="promptIsCustom" style="color:#4F46E5"> · 已自定义</text></text>

        <text class="prompt-editor-desc">告诉 AI 你希望怎么总结这类录音：</text>
        <textarea class="prompt-textarea" v-model="promptText"
                  :maxlength="-1" auto-height
                  placeholder="例如：&#10;· 重点列出行动项和负责人&#10;· 用表格形式整理决策&#10;· 提取关键数据和数字" />

        <!-- 作用范围按钮 -->
        <view class="prompt-actions">
          <button class="btn-primary btn-block" @click="savePromptWithScope('this')">保存并重新总结</button>
          <button class="btn-outline btn-block" style="margin-top: 16rpx"
                  @click="savePromptWithScope('all')">应用到所有「{{ promptCategoryLabel }}」类</button>
        </view>

        <!-- 恢复默认 -->
        <view v-if="promptIsCustom" class="prompt-reset-wrap">
          <text class="prompt-reset" @click="resetToDefault">恢复默认</text>
        </view>
      </view>
    </view>

    <!-- ==================== 删除确认 ==================== -->
    <view v-if="deleteConfirmVisible" class="modal-overlay" @click.self="deleteConfirmVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">确认删除</text>
        <text class="delete-warn">删除后不可恢复。</text>
        <view class="modal-actions">
          <button class="btn-outline" @click="deleteConfirmVisible = false">取消</button>
          <button class="btn-danger" @click="confirmDelete">删除</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onUnmounted, nextTick } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { recordingApi, speakerApi, categoryApi, promptApi } from '@/api'
import { formatTimestamp, mergeSegments, renderMarkdown } from '@/utils/format'

// ── 基础状态 ─────────────────────────────────────────────────────
const recording = ref(null)
const loadError = ref(false)
const progress = ref({ step: '', percent: 0 })
const statusBarHeight = ref(0)

// ── 音频播放 ─────────────────────────────────────────────────────
const isPlaying = ref(false)
const audioPos = ref(0)
const audioDur = ref(0)
const playingIdx = ref(-1)

let recId = ''
let seekTime = 0
let audioCtx = null
let pollTimer = null
let timeupdateTimer = null

const audioUrl = computed(() => recId ? `/api/recordings/${recId}/audio` : '')

// ── 说话人颜色映射 ──────────────────────────────────────────────
const speakerColors = computed(() => {
  const map = {}
  let idx = 0
  ;(recording.value?.speakers || []).forEach(s => { map[s] = idx++ })
  return map
})

// ── 摘要折叠 ──────────────────────────────────────────────────
const summaryCollapsed = ref(false)

// ── 文本模式切换（流畅版/原文） ──────────────────────────────────
const textMode = ref('polished')

// ── 合并连续同一说话人发言（含润色版本） ────────────────────────
const mergedSegs = computed(() => {
  const segments = recording.value?.segments
  if (!segments?.length) return []
  const merged = []
  segments.forEach((seg, idx) => {
    const last = merged[merged.length - 1]
    if (last && last.speaker_id === seg.speaker_id && seg.start - last.end < 3) {
      last.texts.push(seg.text)
      if (seg.text_polished) last.polished.push(seg.text_polished)
      last.end = seg.end
      last.indices.push(idx)
    } else {
      merged.push({
        speaker_id: seg.speaker_id, start: seg.start, end: seg.end,
        texts: [seg.text],
        polished: seg.text_polished ? [seg.text_polished] : [],
        indices: [idx],
      })
    }
  })
  return merged
})

// ── 是否有润色版本 ──────────────────────────────────────────────
const hasPolished = computed(() => mergedSegs.value.some(g => g.polished.length > 0))

// ── 是否有未命名说话人 ──────────────────────────────────────────
const hasUnnamed = computed(() =>
  (recording.value?.speakers || []).some(s => s.startsWith('说话人'))
)

// ── 日期/时长格式化 ─────────────────────────────────────────────
const dateDisplay = computed(() => {
  if (!recording.value) return ''
  return new Date(recording.value.created_at).toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
})

const durDisplay = computed(() => {
  if (!recording.value) return ''
  const d = recording.value.duration || 0
  const m = Math.floor(d / 60)
  const s = Math.floor(d % 60)
  return s > 0 ? `${m}分${s}秒` : `${m}分钟`
})

// ── 弹窗状态 ────────────────────────────────────────────────────
const menuVisible = ref(false)
const categoryVisible = ref(false)
const categoryList = ref([])
const currentCategory = ref('')
const newCategoryName = ref('')
const renameVisible = ref(false)
const renameInput = ref('')
const deleteConfirmVisible = ref(false)
let renameSpeakerId = ''

// ── 摘要模板编辑状态 ────────────────────────────────────────────
const promptEditorVisible = ref(false)
const promptText = ref('')
const promptCategory = ref('_default')
const promptIsCustom = ref(false)
let promptCustomId = null

const promptCategoryLabel = computed(() =>
  promptCategory.value === '_default' ? '通用' : promptCategory.value
)

// ── 生命周期 ────────────────────────────────────────────────────
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
  if (timeupdateTimer) clearInterval(timeupdateTimer)
  destroyAudio()
})

// ── 加载录音详情 ────────────────────────────────────────────────
async function loadRecording() {
  try {
    loadError.value = false
    recording.value = await recordingApi.get(recId)
    if (recording.value.status === 'processing') {
      startPolling()
    } else {
      audioDur.value = recording.value.duration || 0
      // 搜索结果跳转：延迟 seek 到对应位置
      if (seekTime > 0) {
        await nextTick()
        const segs = mergedSegs.value
        let targetIdx = 0
        for (let i = 0; i < segs.length; i++) {
          if (segs[i].start >= seekTime - 1) {
            targetIdx = segs[i].indices[0]
            break
          }
        }
        setTimeout(() => seekAudio(seekTime, targetIdx), 500)
      }
    }
  } catch (e) {
    loadError.value = true
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

// ── 轮询处理进度 ────────────────────────────────────────────────
function startPolling() {
  pollTimer = setInterval(async () => {
    try {
      const st = await recordingApi.status(recId)
      progress.value = { step: st.step, percent: Math.max(0, st.percent) }
      if (st.percent >= 100 || st.percent < 0) {
        clearInterval(pollTimer)
        pollTimer = null
        if (st.percent >= 100) {
          uni.showToast({ title: '处理完成', icon: 'success' })
        } else {
          uni.showToast({ title: '处理失败', icon: 'none' })
        }
        // 重新加载详情
        seekTime = 0
        destroyAudio()
        loadRecording()
      }
    } catch (e) { /* continue polling */ }
  }, 2000)
}

// ── 音频控制 ────────────────────────────────────────────────────
function ensureAudio() {
  if (audioCtx) return
  // #ifdef H5
  audioCtx = new Audio(audioUrl.value)
  audioCtx.addEventListener('timeupdate', onTimeUpdate)
  audioCtx.addEventListener('ended', onEnded)
  audioCtx.addEventListener('loadedmetadata', () => {
    if (audioCtx.duration && isFinite(audioCtx.duration)) {
      audioDur.value = Math.floor(audioCtx.duration)
    }
  })
  // #endif
  // #ifndef H5
  audioCtx = uni.createInnerAudioContext()
  audioCtx.src = audioUrl.value
  audioCtx.onTimeUpdate(() => { onTimeUpdate() })
  audioCtx.onEnded(() => { onEnded() })
  // #endif
}

function destroyAudio() {
  if (!audioCtx) return
  // #ifdef H5
  audioCtx.pause()
  audioCtx.removeEventListener('timeupdate', onTimeUpdate)
  audioCtx.removeEventListener('ended', onEnded)
  audioCtx.src = ''
  // #endif
  // #ifndef H5
  audioCtx.stop()
  audioCtx.destroy()
  // #endif
  audioCtx = null
  isPlaying.value = false
  audioPos.value = 0
  playingIdx.value = -1
}

function onTimeUpdate() {
  if (!audioCtx) return
  const t = audioCtx.currentTime
  audioPos.value = Math.floor(t)
  // 自动高亮当前播放的对话段
  autoHighlight(t)
}

function onEnded() {
  isPlaying.value = false
  playingIdx.value = -1
}

/** 音频 timeupdate 时自动高亮对应 transcript-item */
function autoHighlight(currentTime) {
  const segs = mergedSegs.value
  if (!segs.length) return
  for (let i = 0; i < segs.length; i++) {
    if (currentTime >= segs[i].start && currentTime < segs[i].end) {
      const targetIdx = segs[i].indices[0]
      if (playingIdx.value !== targetIdx) {
        playingIdx.value = targetIdx
      }
      return
    }
  }
}

function togglePlay() {
  ensureAudio()
  if (isPlaying.value) {
    audioCtx.pause()
  } else {
    audioCtx.play()
  }
  isPlaying.value = !isPlaying.value
}

function onSliderChange(e) {
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

/** 点击对话文字跳转播放并高亮 */
function seekAudio(startTime, idx) {
  ensureAudio()
  playingIdx.value = idx
  // #ifdef H5
  audioCtx.currentTime = startTime
  // #endif
  // #ifndef H5
  audioCtx.seek(startTime)
  // #endif
  audioCtx.play()
  isPlaying.value = true
  audioPos.value = Math.floor(startTime)
}

// ── 操作菜单 ────────────────────────────────────────────────────
function showRecordingMenu() {
  menuVisible.value = true
}

async function doMenuAction(action) {
  menuVisible.value = false
  if (action === 'category') {
    await showCategoryEditor()
  } else if (action === 'resummarize') {
    await resummarizeRecording()
  } else if (action === 'reprocess') {
    await reprocessRecording()
  } else if (action === 'delete') {
    deleteConfirmVisible.value = true
  }
}

// ── 重新总结 ────────────────────────────────────────────────────
async function resummarizeRecording() {
  uni.showToast({ title: '正在重新总结...', icon: 'none' })
  try {
    await recordingApi.resummarize(recId)
    uni.showToast({ title: '总结已更新', icon: 'success' })
    loadRecording()
  } catch (e) {
    uni.showToast({ title: '总结失败', icon: 'none' })
  }
}

// ── 重新识别 ────────────────────────────────────────────────────
async function reprocessRecording() {
  if (recording.value?.status === 'processing') {
    uni.showToast({ title: '正在处理中，请稍候', icon: 'none' })
    return
  }
  uni.showToast({ title: '已开始重新识别，可返回列表', icon: 'none' })
  try {
    await recordingApi.reprocess(recId)
    recording.value.status = 'processing'
    progress.value = { step: '准备中...', percent: 0 }
    destroyAudio()
    startPolling()
  } catch (e) {
    uni.showToast({ title: '操作失败', icon: 'none' })
  }
}

// ── 删除录音 ────────────────────────────────────────────────────
async function confirmDelete() {
  deleteConfirmVisible.value = false
  try {
    await recordingApi.delete(recId)
    uni.showToast({ title: '已删除', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 300)
  } catch (e) {
    uni.showToast({ title: '删除失败', icon: 'none' })
  }
}

// ── 分类编辑 ────────────────────────────────────────────────────
async function showCategoryEditor() {
  try {
    categoryList.value = await categoryApi.list()
    currentCategory.value = recording.value?.category || ''
    newCategoryName.value = ''
    categoryVisible.value = true
  } catch (e) {
    uni.showToast({ title: '加载分类失败', icon: 'none' })
  }
}

async function selectCategory(name) {
  categoryVisible.value = false
  try {
    await recordingApi.updateCategory(recId, name)
    uni.showToast({ title: `已分类为「${name}」`, icon: 'success' })
    loadRecording()
  } catch (e) {
    uni.showToast({ title: '分类失败', icon: 'none' })
  }
}

async function addAndSelectCategory() {
  const name = newCategoryName.value.trim()
  if (!name) return
  try {
    await categoryApi.add(name)
    await selectCategory(name)
  } catch (e) {
    uni.showToast({ title: '添加失败', icon: 'none' })
  }
}

// ── 说话人标注 ──────────────────────────────────────────────────
function showRenameModal(speakerId) {
  renameSpeakerId = speakerId
  renameInput.value = ''
  renameVisible.value = true
}

async function doRename() {
  const newName = renameInput.value.trim()
  if (!newName) return
  renameVisible.value = false
  try {
    await speakerApi.rename(renameSpeakerId, newName)
    uni.showToast({ title: `已标注为"${newName}"`, icon: 'success' })
    loadRecording()
  } catch (e) {
    uni.showToast({ title: '标注失败', icon: 'none' })
  }
}

// ── 摘要模板编辑 ────────────────────────────────────────────────
async function openPromptEditor() {
  const category = recording.value?.category || '_default'
  promptCategory.value = category

  try {
    // 获取已有的自定义 prompts
    const allPrompts = await promptApi.list()
    const catPrompt = allPrompts.find(p => p.category === category)

    // 获取该录音的单独 prompt
    let recPrompt = recording.value?.custom_prompt || ''

    // 获取内置默认
    let builtinText = ''
    try {
      const resp = await promptApi.builtin(category)
      builtinText = resp.prompt || ''
    } catch (e) { /* ignore */ }

    // 当前生效的 prompt
    const activePrompt = recPrompt || catPrompt?.prompt || builtinText || '请总结这段录音的关键内容。'
    promptText.value = activePrompt
    promptIsCustom.value = !!(recPrompt || catPrompt)
    promptCustomId = catPrompt?.id || null

    promptEditorVisible.value = true
  } catch (e) {
    uni.showToast({ title: '加载模板失败', icon: 'none' })
  }
}

function closePromptEditor() {
  promptEditorVisible.value = false
}

async function savePromptWithScope(scope) {
  const prompt = promptText.value.trim()
  if (!prompt) {
    uni.showToast({ title: '请输入总结要求', icon: 'none' })
    return
  }

  try {
    if (scope === 'this') {
      // 仅本条录音
      await recordingApi.setPrompt(recId, prompt)
    } else {
      // 所有同类
      await promptApi.save(promptCategory.value, prompt)
    }

    // 保存后重新总结
    uni.showToast({ title: '正在重新总结...', icon: 'none' })
    await recordingApi.resummarize(recId)
    uni.showToast({ title: '总结已更新', icon: 'success' })

    promptEditorVisible.value = false
    loadRecording()
  } catch (e) {
    uni.showToast({ title: '保存失败', icon: 'none' })
  }
}

async function resetToDefault() {
  // 删除自定义 prompt
  if (promptCustomId) {
    try {
      await promptApi.delete(promptCustomId)
    } catch (e) { /* ignore */ }
  }
  // 加载内置默认内容填入
  try {
    const resp = await promptApi.builtin(promptCategory.value)
    if (resp.prompt) {
      promptText.value = resp.prompt
      promptIsCustom.value = false
      promptCustomId = null
      uni.showToast({ title: '已恢复为默认内容', icon: 'none' })
    }
  } catch (e) {
    uni.showToast({ title: '恢复失败', icon: 'none' })
  }
}

// ── 导航 ────────────────────────────────────────────────────────
function goBack() { uni.navigateBack() }
</script>

<style lang="scss" scoped>
.page-white { min-height: 100vh; background: $color-bg-card; }

/* ── 自定义导航栏 ─────────────────────────────────────── */
.nav-bar {
  display: flex; justify-content: space-between; align-items: center;
  padding: $spacing-md $spacing-lg; background: $color-bg-card;
  border-bottom: 1rpx solid $color-border; position: relative; z-index: 60;
}
.nav-back { display: flex; align-items: center; gap: $spacing-xs; font-size: $font-base; color: $color-primary; }
.nav-back-icon { font-size: 36rpx; }
.nav-more { font-size: 40rpx; color: $color-text-tertiary; padding: 0 $spacing-md; }

/* ── 详情头部 ─────────────────────────────────────────── */
.detail-header { padding: $spacing-lg; }
.detail-title-row { display: flex; align-items: flex-start; justify-content: space-between; }
.detail-title-wrap { flex: 1; }
.detail-title {
  font-size: $font-xl; font-weight: 700; word-break: break-all;
  display: block; margin-bottom: $spacing-sm;
}
.detail-meta { font-size: $font-xs; color: $color-text-tertiary; display: block; }

/* ── 音频播放器 ───────────────────────────────────────── */
.audio-player {
  position: sticky; top: 0; z-index: 50;
  background: $color-bg-card; border-bottom: 1rpx solid $color-border;
  padding: $spacing-md $spacing-lg; box-shadow: $shadow-sm;
}
.audio-controls {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: $spacing-xs;
}
.audio-time { font-size: $font-xs; color: $color-text-tertiary; }
.audio-play-btn {
  width: 64rpx; height: 64rpx; border-radius: 50%;
  background: $color-primary; color: #fff;
  display: flex; align-items: center; justify-content: center;
}
.play-icon { font-size: 28rpx; }
.player-hint {
  font-size: 20rpx; color: $color-text-disabled;
  text-align: center; margin-top: $spacing-xs; display: block;
}

/* ── 摘要卡片 ─────────────────────────────────────────── */
.summary-card {
  margin: $spacing-md $spacing-lg; padding: $spacing-lg;
  background: linear-gradient(135deg, #EEF2FF 0%, #E0E7FF 100%);
  border-radius: $radius-xl;
}
.summary-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: $spacing-md;
}
.summary-label { font-size: $font-base; font-weight: 600; color: $color-primary-dark; }
.summary-edit { font-size: 22rpx; color: $color-primary; }
.summary-toggle { font-size: 22rpx; color: $color-text-tertiary; }
.summary-text {
  font-size: $font-sm; color: $color-text-secondary; line-height: 1.8;
  transition: max-height 0.3s ease; overflow: hidden;
}
.summary-text.collapsed {
  max-height: 240rpx;
  /* 小程序不支持 mask-image，用渐变 overlay 替代 */
  position: relative;
}

/* ── 文本模式切换 ────────────────────────────────────── */
.text-mode-toggle {
  display: inline-flex; gap: 0; background: $color-bg-hover;
  border-radius: $radius-full; padding: 4rpx;
}
.text-mode-btn {
  padding: 8rpx 24rpx; border-radius: $radius-full; font-size: 24rpx;
  color: $color-text-tertiary; font-weight: 500; white-space: nowrap;
}
.text-mode-btn.active {
  background: $color-primary; color: #fff;
  box-shadow: 0 4rpx 12rpx rgba(79,70,229,0.25);
}

/* ── 对话记录标题 ─────────────────────────────────────── */
.transcript-title {
  padding: 0 $spacing-lg; margin-bottom: $spacing-md;
  display: flex; align-items: center; justify-content: space-between;
}
.transcript-title-text { font-size: $font-md; font-weight: 600; }
.transcript-title-hint { font-size: 20rpx; color: $color-text-disabled; }

/* ── 对话记录 ─────────────────────────────────────────── */
.transcript { padding: 0 $spacing-lg $spacing-xxl; }
.transcript-item {
  display: flex; gap: $spacing-md; margin-bottom: $spacing-lg;
  padding: $spacing-sm; border-radius: $radius-lg;
  transition: background 0.15s;
}
.transcript-item.playing {
  background: $color-primary-light;
  border-left: 6rpx solid $color-primary;
  padding-left: $spacing-md;
}
.transcript-avatar {
  width: 56rpx; height: 56rpx; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.avatar-letter { font-size: $font-xs; font-weight: 600; color: #fff; }
.spk-0 { background: $color-primary; }
.spk-1 { background: #D97706; }
.spk-2 { background: #059669; }
.spk-3 { background: #DB2777; }
.spk-4 { background: #7C3AED; }
.transcript-bubble { flex: 1; }
.transcript-speaker {
  display: flex; align-items: center; gap: $spacing-sm; margin-bottom: 4rpx;
}
.speaker-tag {
  font-size: 22rpx; font-weight: 500;
  padding: 2rpx 12rpx; border-radius: $radius-sm;
  background: $color-primary-light; color: $color-primary-dark;
}
.ts { font-size: 20rpx; color: $color-text-disabled; }
.transcript-text {
  font-size: $font-base; color: $color-text-primary;
  line-height: 1.7; display: block;
}

/* ── 进度条 ───────────────────────────────────────────── */
.progress-bg {
  height: 12rpx; background: $color-bg-hover;
  border-radius: 6rpx; overflow: hidden; margin: $spacing-md 0;
}
.progress-fill {
  height: 100%; background: $color-primary-gradient;
  border-radius: 6rpx; transition: width 0.3s;
}
.progress-text { font-size: $font-xs; color: $color-text-tertiary; text-align: center; display: block; }
.progress-hint { font-size: 20rpx; color: $color-text-disabled; text-align: center; display: block; margin-top: $spacing-sm; }

/* ── Modal 通用 ───────────────────────────────────────── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.45); z-index: 200;
  display: flex; align-items: flex-end; justify-content: center;
}
.modal-sheet {
  background: $color-bg-card;
  border-radius: $radius-xl $radius-xl 0 0;
  padding: 40rpx 32rpx calc(40rpx + env(safe-area-inset-bottom));
  width: 100%;
}
.modal-title {
  font-size: 32rpx; font-weight: 700; margin-bottom: 32rpx; color: $color-text-primary;
}
.modal-input {
  width: 100%; height: 88rpx; padding: 0 $spacing-lg;
  background: $color-bg-hover; border: 2rpx solid transparent;
  border-radius: $radius-lg; font-size: $font-base; color: $color-text-primary;
  margin-bottom: $spacing-lg;
}
.modal-actions {
  display: flex; gap: $spacing-lg;
  button { flex: 1; }
}

/* ── 操作菜单项 ───────────────────────────────────────── */
.menu-item {
  display: flex; align-items: center; gap: $spacing-lg;
  padding: 28rpx 32rpx; background: $color-bg-card;
  border-radius: $radius-md; margin-bottom: $spacing-md;
  box-shadow: $shadow-sm;
}
.menu-item-icon { font-size: 36rpx; color: $color-text-secondary; flex-shrink: 0; }
.menu-item-text { flex: 1; font-size: $font-base; }
.menu-item-sub { font-size: 20rpx; color: $color-text-tertiary; flex: none; }

/* ── 分类选择 ─────────────────────────────────────────── */
.cat-chips { display: flex; flex-wrap: wrap; gap: $spacing-md; margin-bottom: $spacing-lg; }
.filter-chip {
  height: 56rpx; line-height: 56rpx; padding: 0 $spacing-xl;
  border-radius: $radius-full; font-size: $font-sm;
  border: 2rpx solid $color-border; background: $color-bg-card; color: $color-text-secondary;
  &.active { background: $color-primary; color: #fff; border-color: $color-primary; }
}
.cat-add-hint { font-size: $font-xs; color: $color-text-tertiary; margin-bottom: $spacing-md; display: block; }
.cat-add-row { display: flex; gap: $spacing-md; align-items: center;
  .modal-input { margin-bottom: 0; flex: 1; }
}

/* ── 按钮通用 ─────────────────────────────────────────── */
.btn-primary {
  background: $color-primary-gradient; color: #fff; border: none;
  border-radius: $radius-lg; height: 80rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: $font-base; font-weight: 600;
}
.btn-outline {
  background: $color-bg-card; color: $color-primary-dark;
  border: 2rpx solid $color-primary; border-radius: $radius-lg; height: 80rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: $font-base; font-weight: 500;
}
.btn-danger {
  background: $color-danger; color: #fff; border: none;
  border-radius: $radius-lg; height: 80rpx;
  display: flex; align-items: center; justify-content: center;
  font-size: $font-base; font-weight: 600;
}
.btn-block { width: 100%; }
.btn-small { height: 64rpx; padding: 0 $spacing-xl; font-size: $font-sm; flex-shrink: 0; }
.delete-warn { font-size: $font-base; color: $color-text-secondary; margin-bottom: $spacing-xl; display: block; }

/* ── 摘要模板编辑器 ───────────────────────────────────── */
.prompt-editor-page {
  position: fixed; inset: 0; z-index: 300; background: $color-bg-card;
  display: flex; flex-direction: column; overflow-y: auto;
}
.prompt-editor-body { padding: $spacing-lg; flex: 1; }
.prompt-editor-title {
  font-size: $font-xl; font-weight: 700;
  margin: $spacing-lg 0 $spacing-sm; display: block;
}
.prompt-editor-subtitle {
  font-size: $font-sm; color: $color-text-tertiary;
  margin-bottom: $spacing-xl; display: block;
}
.prompt-editor-desc {
  font-size: $font-sm; color: $color-text-secondary;
  margin-bottom: $spacing-md; display: block;
}
.prompt-textarea {
  width: 100%; min-height: 240rpx;
  border: 2rpx solid $color-border; border-radius: $radius-lg;
  padding: 24rpx; font-size: $font-base; font-family: inherit;
  color: $color-text-primary; line-height: 1.7;
  background: $color-bg-card;
}
.prompt-actions { margin-top: $spacing-xl; }
.prompt-reset-wrap { text-align: center; margin-top: $spacing-lg; }
.prompt-reset {
  font-size: $font-xs; color: $color-text-tertiary;
  text-decoration: underline;
}
</style>
