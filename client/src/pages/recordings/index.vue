<template>
  <view class="page">
    <!-- 搜索栏 -->
    <view class="search-bar">
      <input class="search-input" v-model="searchQuery" placeholder="搜索录音内容..."
             @input="debounceSearch" confirm-type="search" />
    </view>

    <!-- 分类筛选 -->
    <scroll-view v-if="usedCategories.length && !searchQuery" scroll-x class="filter-bar">
      <view class="filter-chip" :class="{active: activeCategory === ''}" @click="filterBy('')">全部</view>
      <view class="filter-chip" :class="{active: activeCategory === c}" v-for="c in usedCategories" :key="c" @click="filterBy(c)">{{ c }}</view>
    </scroll-view>

    <!-- 搜索结果 -->
    <view v-if="searchQuery && searchResults !== null">
      <view v-if="searching" class="loading-hint">搜索中...</view>
      <view v-else-if="searchResults.length === 0" class="loading-hint">没有找到相关内容</view>
      <view v-else>
        <view class="search-result-item" v-for="r in searchResults" :key="r.recording_id + r.segment.start"
              @click="goDetail(r.recording_id, r.segment.start)">
          <view style="font-size:24rpx;color:#86909C;margin-bottom:6rpx">{{ getRecTitle(r.recording_id) }} · {{ r.segment.speaker_id }}</view>
          <rich-text :nodes="highlightText(r.segment.text, searchQuery)" />
        </view>
      </view>
    </view>

    <!-- 录音列表 -->
    <view v-else-if="filteredRecordings.length">
      <view class="card rec-card" v-for="r in filteredRecordings" :key="r.id"
            @click="goDetail(r.id)" @longpress="showMenu(r.id)">
        <view class="rec-header">
          <view class="rec-icon">
            <text class="ti ti-microphone" style="font-size:40rpx;color:#4F46E5"></text>
          </view>
          <view class="rec-info">
            <text class="rec-name">{{ r.title || r.filename }}</text>
            <text class="rec-meta">{{ relativeTime(r.created_at) }} · {{ friendlyDuration(r.duration) }}
              <text v-if="r.status !== 'completed'" class="rec-status" :class="r.status">{{ statusLabel[r.status] }}</text>
            </text>
          </view>
        </view>
        <view class="rec-speakers">
          <text v-if="r.category && r.category !== '其他'" class="category-tag">{{ r.category }}</text>
          <text v-for="(s, i) in (r.speakers||[])" :key="s" class="speaker-tag" :class="'spk-idx-' + i">{{ s }}</text>
        </view>
      </view>
    </view>

    <!-- 空状态 -->
    <view v-else class="empty-state">
      <text class="empty-icon">🎙</text>
      <text class="empty-title">上传你的第一段录音</text>
      <text class="empty-desc">支持 m4a、mp3、wav 等格式</text>
      <button class="btn-primary" @click="chooseFile">选择音频文件</button>
      <view class="empty-features">
        <text class="empty-features-heading">VoiceKB 会帮你：</text>
        <text>🎤 自动识别每个人说了什么</text>
        <text>🔍 支持关键词和语义搜索</text>
        <text>📝 智能生成会议摘要</text>
        <text>💬 AI 问答，直接问录音内容</text>
      </view>
    </view>

    <!-- 上传 FAB -->
    <view class="btn-fab" @click="chooseFile">
      <text class="fab-icon">+</text>
    </view>

    <!-- Tab Bar -->
    <TabBar current="recordings" />

    <!-- 处理进度 -->
    <view v-if="processingId" class="progress-overlay">
      <view class="progress-container">
        <view class="card">
          <text class="card-title">{{ progressStep }}</text>
          <view class="progress-bar-bg"><view class="progress-bar-fill" :style="{width: progressPercent + '%'}" /></view>
          <text class="progress-text">{{ progressPercent }}%</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import TabBar from '@/components/TabBar.vue'
import { recordingApi, searchApi, categoryApi, uploadAudio } from '@/api'
import { relativeTime, friendlyDuration } from '@/utils/format'

const recordings = ref([])
const activeCategory = ref('')
const searchQuery = ref('')
const searchResults = ref(null)
const searching = ref(false)
const processingId = ref('')
const progressStep = ref('')
const progressPercent = ref(0)

const statusLabel = { pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败' }

const usedCategories = computed(() =>
  [...new Set(recordings.value.map(r => r.category).filter(c => c && c !== '其他'))]
)

const filteredRecordings = computed(() =>
  activeCategory.value
    ? recordings.value.filter(r => r.category === activeCategory.value)
    : recordings.value
)

function getRecTitle(id) {
  const r = recordings.value.find(r => r.id === id)
  return r?.title || r?.filename || ''
}

function filterBy(cat) { activeCategory.value = cat }

let listRefreshTimer = null

async function loadRecordings() {
  try {
    recordings.value = await recordingApi.list()
    // 有录音在处理中时自动刷新
    if (recordings.value.some(r => r.status === 'processing')) {
      clearTimeout(listRefreshTimer)
      listRefreshTimer = setTimeout(loadRecordings, 5000)
    }
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

// 搜索
let searchTimer
function debounceSearch() {
  clearTimeout(searchTimer)
  if (!searchQuery.value.trim()) { searchResults.value = null; return }
  searchTimer = setTimeout(doSearch, 400)
}

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) { searchResults.value = null; return }
  searching.value = true
  try {
    searchResults.value = await searchApi.search(q)
  } catch (e) {
    searchResults.value = []
  }
  searching.value = false
}

function highlightText(text, query) {
  const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<span class="search-highlight">$1</span>')
}

// 上传
function chooseFile() {
  // #ifdef H5
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'audio/*,.m4a,.mp3,.wav,.flac,.aac,.opus,.ogg,.wma'
  input.onchange = (e) => {
    const file = e.target.files[0]
    if (file) doUploadH5(file)
  }
  input.click()
  // #endif

  // #ifndef H5
  uni.chooseMessageFile({
    count: 1,
    type: 'file',
    extension: ['.m4a', '.mp3', '.wav', '.flac', '.aac', '.opus', '.ogg', '.wma'],
    success: (res) => {
      if (res.tempFiles[0]) doUploadFile(res.tempFiles[0].path)
    },
  })
  // #endif
}

// #ifdef H5
async function doUploadH5(file) {
  processingId.value = 'uploading'
  progressStep.value = '上传中: ' + file.name
  progressPercent.value = 0

  const fd = new FormData()
  fd.append('file', file)
  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: fd })
    if (!resp.ok) throw new Error('Upload failed')
    const data = await resp.json()
    uni.showToast({ title: '上传成功，开始处理', icon: 'success' })
    watchProgress(data.recording_id)
  } catch (e) {
    processingId.value = ''
    uni.showToast({ title: '上传失败', icon: 'none' })
  }
}
// #endif

async function doUploadFile(path) {
  processingId.value = 'uploading'
  progressStep.value = '上传中...'
  progressPercent.value = 0

  try {
    const data = await uploadAudio(path)
    uni.showToast({ title: '上传成功，开始处理', icon: 'success' })
    watchProgress(data.recording_id)
  } catch (e) {
    processingId.value = ''
    uni.showToast({ title: '上传失败', icon: 'none' })
  }
}

function watchProgress(recId) {
  processingId.value = recId
  progressStep.value = '准备中...'
  progressPercent.value = 0

  const poll = setInterval(async () => {
    try {
      const st = await recordingApi.status(recId)
      progressStep.value = `${st.step} (${Math.max(0, st.percent)}%)`
      progressPercent.value = Math.max(0, st.percent)
      if (st.percent >= 100 || st.percent < 0) {
        clearInterval(poll)
        processingId.value = ''
        if (st.percent >= 100) {
          uni.showToast({ title: '处理完成', icon: 'success' })
          setTimeout(() => goDetail(recId), 500)
        } else {
          uni.showToast({ title: '处理失败', icon: 'none' })
        }
        loadRecordings()
      }
    } catch (e) { /* continue polling */ }
  }, 1500)
}

function goDetail(id, seekTime) {
  uni.navigateTo({ url: `/pages/recordings/detail?id=${id}${seekTime ? '&seek=' + seekTime : ''}` })
}

function showMenu(id) {
  uni.showActionSheet({
    itemList: ['修改分类', '重新总结', '重新识别（较慢）', '删除录音'],
    success: async (res) => {
      if (res.tapIndex === 0) {
        showCategoryPicker(id)
      } else if (res.tapIndex === 1) {
        uni.showToast({ title: '正在重新总结...', icon: 'none' })
        await recordingApi.resummarize(id)
        uni.showToast({ title: '总结已更新', icon: 'success' })
        loadRecordings()
      } else if (res.tapIndex === 2) {
        await recordingApi.reprocess(id)
        watchProgress(id)
      } else if (res.tapIndex === 3) {
        uni.showModal({
          title: '确认删除',
          content: '删除后不可恢复',
          cancelText: '取消',
          confirmText: '删除',
          success: async (r) => {
            if (r.confirm) {
              await recordingApi.delete(id)
              uni.showToast({ title: '已删除', icon: 'success' })
              loadRecordings()
            }
          },
        })
      }
    },
  })
}

async function showCategoryPicker(recId) {
  try {
    const presets = await categoryApi.list()
    const names = presets.map(p => p.name || p)
    uni.showActionSheet({
      itemList: names,
      success: async (res) => {
        const chosen = names[res.tapIndex]
        await recordingApi.updateCategory(recId, chosen)
        uni.showToast({ title: '分类已更新', icon: 'success' })
        loadRecordings()
      },
    })
  } catch (e) {
    uni.showToast({ title: '获取分类失败', icon: 'none' })
  }
}

onMounted(loadRecordings)
onShow(loadRecordings)
</script>

<style lang="scss" scoped>
.page { min-height: #{"calc(100vh - var(--window-top, 0px))"}; background: $color-bg-page; padding-bottom: 140rpx; }

/* ===== Search Bar — 继承 hotel_shop input 规范 ===== */
.search-bar { display: flex; gap: 16rpx; padding: 0 $spacing-lg; margin-bottom: $spacing-md; }
.search-input {
  flex: 1; height: 88rpx; padding: 0 28rpx;
  background: $color-bg-hover; border: 3rpx solid transparent;
  border-radius: $radius-lg; font-size: $font-base; color: $color-text-primary;
  transition: border-color 0.15s, background 0.15s;
}

/* ===== Filter Bar — 分类筛选 ===== */
.filter-bar { white-space: nowrap; padding: 0 $spacing-lg $spacing-md; }
.filter-chip {
  display: inline-block; height: 60rpx; line-height: 60rpx;
  padding: 0 28rpx; border-radius: $radius-full;
  font-size: 26rpx; font-weight: 500; margin-right: $spacing-md;
  border: 3rpx solid $color-border; background: $color-bg-card; color: $color-text-secondary;
  white-space: nowrap; transition: all 0.15s;
  &.active { background: $color-primary; color: #fff; border-color: $color-primary; box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.2); }
}

/* ===== Recording Card — 继承 product-card 结构 ===== */
.rec-card { cursor: pointer; transition: box-shadow 0.2s; }
.rec-card:active { box-shadow: $shadow-lg; }
.rec-header { display: flex; align-items: center; gap: $spacing-lg; }
.rec-icon {
  width: 88rpx; height: 88rpx; border-radius: $radius-lg;
  background: $color-primary-light; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; border: 2rpx solid $color-border;
}
.rec-info { flex: 1; min-width: 0; }
.rec-name { font-size: 30rpx; font-weight: 600; color: $color-text-primary; line-height: 1.4; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.rec-meta { font-size: $font-xs; color: $color-text-tertiary; margin-top: 4rpx; }
/* rec-status — 继承 order-badge 规范 */
.rec-status {
  display: inline-flex; align-items: center; gap: 6rpx;
  height: 44rpx; padding: 0 16rpx; border-radius: $radius-sm;
  font-size: $font-xs; font-weight: 500;
  &.processing { background: #FFF3E0; color: $color-warning; }
  &.failed { background: #FFEBEE; color: $color-danger; }
  &.completed { background: #E8F5E9; color: $color-success; }
}
.rec-speakers { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 20rpx; }
/* category-tag */
.category-tag {
  display: inline-flex; align-items: center; height: 44rpx; padding: 0 16rpx;
  border-radius: $radius-sm; font-size: 22rpx; font-weight: 500;
  background: #E3F2FD; color: #1677FF;
}
/* speaker-tag — 继承 product-tag + order-badge 规范 */
.speaker-tag {
  display: inline-flex; align-items: center; gap: 8rpx;
  height: 44rpx; padding: 0 16rpx; border-radius: $radius-sm;
  font-size: $font-xs; font-weight: 500;
  background: $color-primary-light; color: $color-primary-dark;
}
.speaker-tag.spk-idx-1 { background: #FFF3E0; color: #E65100; }
.speaker-tag.spk-idx-2 { background: #E8F5E9; color: #00B578; }
.speaker-tag.spk-idx-3 { background: #FCE7F3; color: #DB2777; }

/* ===== Search Results ===== */
.search-result-item {
  padding: $spacing-lg; border-bottom: 2rpx solid $color-border;
  transition: background 0.15s;
}
.search-result-item:active { background: $color-bg-hover; }
.search-highlight { background: #FFF3E0; padding: 2rpx 6rpx; border-radius: 4rpx; font-weight: 500; }
.loading-hint { text-align: center; padding: $spacing-xxl; color: $color-text-tertiary; font-size: $font-sm; }

/* ===== Empty State ===== */
.empty-state { text-align: center; padding: 120rpx $spacing-xxl; }
.empty-icon { font-size: 120rpx; display: block; margin-bottom: $spacing-xl; }
.empty-title { font-size: 36rpx; font-weight: 700; color: $color-text-secondary; display: block; margin-bottom: $spacing-sm; }
.empty-desc { font-size: $font-base; color: $color-text-tertiary; display: block; margin-bottom: $spacing-xxl; }
.empty-features {
  text-align: left; margin-top: $spacing-xxl; font-size: $font-sm; color: $color-text-tertiary; line-height: 2.2;
  text { display: block; }
}
.empty-features-heading { font-size: 26rpx; font-weight: 600; color: $color-text-secondary; margin-bottom: $spacing-md; }

/* ===== FAB Button ===== */
.btn-fab {
  position: fixed; right: 32rpx; bottom: calc(136rpx + env(safe-area-inset-bottom));
  width: 104rpx; height: 104rpx; border-radius: 50%;
  background: $color-primary-gradient; color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 8rpx 32rpx rgba(79,70,229,0.35); z-index: 90;
  .fab-icon { font-size: 44rpx; font-weight: 300; }
}

/* ===== Progress ===== */
.progress-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.progress-container { width: 80%; }
.progress-bar-bg { width: 100%; height: 16rpx; background: #E5E7EB; border-radius: 8rpx; overflow: hidden; margin: $spacing-md 0; }
.progress-bar-fill { height: 100%; background: linear-gradient(90deg, $color-primary, #818CF8); border-radius: 8rpx; transition: width 0.3s ease; }
.progress-text { font-size: 26rpx; color: $color-text-secondary; text-align: center; margin-top: $spacing-md; }
.card-title { font-size: 30rpx; font-weight: 600; margin-bottom: 12rpx; color: $color-text-primary; }
</style>
