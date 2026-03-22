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
      <view v-else class="search-results">
        <view class="search-item" v-for="r in searchResults" :key="r.recording_id + r.segment.start"
              @click="goDetail(r.recording_id, r.segment.start)">
          <text class="search-meta">{{ getRecTitle(r.recording_id) }} · {{ r.segment.speaker_id }}</text>
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
            <text class="icon-mic">🎙</text>
          </view>
          <view class="rec-info">
            <text class="rec-name">{{ r.title || r.filename }}</text>
            <text class="rec-meta">{{ relativeTime(r.created_at) }} · {{ friendlyDuration(r.duration) }}
              <text v-if="r.status !== 'completed'" class="rec-status" :class="r.status">{{ statusText[r.status] }}</text>
            </text>
          </view>
        </view>
        <view class="rec-tags">
          <text v-if="r.category && r.category !== '其他'" class="tag tag-blue">{{ r.category }}</text>
          <text v-for="s in (r.speakers||[])" :key="s" class="tag tag-orange">{{ s }}</text>
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
        <text>🎤 自动识别每个人说了什么</text>
        <text>🔍 支持关键词和语义搜索</text>
        <text>📝 智能生成会议摘要</text>
        <text>💬 AI 问答，直接问录音内容</text>
      </view>
    </view>

    <!-- 上传 FAB -->
    <view class="fab" @click="chooseFile">
      <text class="fab-icon">+</text>
    </view>

    <!-- 处理进度 -->
    <view v-if="processingId" class="progress-overlay">
      <view class="card" style="margin: 40rpx">
        <text class="card-title">{{ progressStep }}</text>
        <view class="progress-bg"><view class="progress-fill" :style="{width: progressPercent + '%'}" /></view>
        <text class="progress-text">{{ progressPercent }}%</text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { recordingApi, searchApi, uploadAudio } from '@/api'
import { relativeTime, friendlyDuration } from '@/utils/format'

const recordings = ref([])
const activeCategory = ref('')
const searchQuery = ref('')
const searchResults = ref(null)
const searching = ref(false)
const processingId = ref('')
const progressStep = ref('')
const progressPercent = ref(0)

const statusText = { pending: '等待中', processing: '处理中', failed: '失败' }

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

async function loadRecordings() {
  try {
    recordings.value = await recordingApi.list()
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
  return text.replace(new RegExp(`(${escaped})`, 'gi'), '<span style="background:#FEF08A;padding:0 2px;border-radius:2px;font-weight:500">$1</span>')
}

// 上传
function chooseFile() {
  // #ifdef H5
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'audio/*,.m4a,.mp3,.wav,.flac,.aac'
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
    extension: ['.m4a', '.mp3', '.wav', '.flac', '.aac'],
    success: (res) => {
      if (res.tempFiles[0]) doUploadFile(res.tempFiles[0].path)
    },
  })
  // #endif
}

// #ifdef H5
async function doUploadH5(file) {
  const fd = new FormData()
  fd.append('file', file)
  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: fd })
    const data = await resp.json()
    uni.showToast({ title: '上传成功', icon: 'success' })
    watchProgress(data.recording_id)
  } catch (e) {
    uni.showToast({ title: '上传失败', icon: 'none' })
  }
}
// #endif

async function doUploadFile(path) {
  try {
    const data = await uploadAudio(path)
    uni.showToast({ title: '上传成功', icon: 'success' })
    watchProgress(data.recording_id)
  } catch (e) {
    uni.showToast({ title: '上传失败', icon: 'none' })
  }
}

function watchProgress(recId) {
  processingId.value = recId
  progressStep.value = '准备中'
  progressPercent.value = 0

  const poll = setInterval(async () => {
    try {
      const st = await recordingApi.status(recId)
      progressStep.value = st.step
      progressPercent.value = Math.max(0, st.percent)
      if (st.percent >= 100 || st.percent < 0) {
        clearInterval(poll)
        processingId.value = ''
        if (st.percent >= 100) {
          uni.showToast({ title: '处理完成', icon: 'success' })
          goDetail(recId)
        } else {
          uni.showToast({ title: '处理失败', icon: 'none' })
        }
        loadRecordings()
      }
    } catch (e) { /* continue */ }
  }, 2000)
}

function goDetail(id, seekTime) {
  const query = seekTime ? { id, seek: seekTime } : { id }
  uni.navigateTo({ url: `/pages/recordings/detail?id=${id}${seekTime ? '&seek=' + seekTime : ''}` })
}

function showMenu(id) {
  uni.showActionSheet({
    itemList: ['重新总结', '重新识别（较慢）', '删除录音'],
    success: async (res) => {
      if (res.tapIndex === 0) {
        uni.showToast({ title: '正在重新总结...', icon: 'none' })
        await recordingApi.resummarize(id)
        uni.showToast({ title: '总结已更新', icon: 'success' })
        loadRecordings()
      } else if (res.tapIndex === 1) {
        await recordingApi.reprocess(id)
        watchProgress(id)
      } else if (res.tapIndex === 2) {
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

onMounted(loadRecordings)
onShow(loadRecordings)
</script>

<style lang="scss" scoped>
.page { min-height: #{"calc(100vh - var(--window-top, 0px))"}; background: $color-bg-page; }
.search-bar { padding: $spacing-md $spacing-lg; }
.search-input {
  width: 100%; height: 88rpx; padding: 0 $spacing-lg;
  background: $color-bg-hover; border-radius: $radius-lg;
  font-size: $font-base; color: $color-text-primary;
}

.filter-bar { white-space: nowrap; padding: 0 $spacing-lg $spacing-md; }
.filter-chip {
  display: inline-block; height: 56rpx; line-height: 56rpx;
  padding: 0 $spacing-xl; border-radius: $radius-full;
  font-size: $font-sm; margin-right: $spacing-md;
  border: 2rpx solid $color-border; background: $color-bg-card; color: $color-text-secondary;
  &.active { background: $color-primary; color: #fff; border-color: $color-primary; }
}

.rec-card {
  background: $color-bg-card; border-radius: $radius-lg;
  margin: 0 $spacing-lg $spacing-md; padding: $spacing-lg;
  box-shadow: $shadow-sm;
}
.rec-header { display: flex; align-items: center; gap: $spacing-lg; }
.rec-icon {
  width: 88rpx; height: 88rpx; border-radius: $radius-lg;
  background: $color-primary-light; display: flex; align-items: center; justify-content: center;
  .icon-mic { font-size: 40rpx; }
}
.rec-info { flex: 1; min-width: 0; }
.rec-name { font-size: $font-md; font-weight: 600; color: $color-text-primary; display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
.rec-meta { font-size: $font-xs; color: $color-text-tertiary; margin-top: 4rpx; }
.rec-status { padding: 2rpx 12rpx; border-radius: $radius-sm; font-size: $font-xs; font-weight: 500;
  &.processing { background: #FFF3E0; color: $color-warning; }
  &.failed { background: #FFEBEE; color: $color-danger; }
}
.rec-tags { display: flex; flex-wrap: wrap; gap: $spacing-sm; margin-top: $spacing-md; }
.tag {
  height: 40rpx; line-height: 40rpx; padding: 0 $spacing-md;
  border-radius: $radius-sm; font-size: $font-xs; font-weight: 500;
}
.tag-blue { background: #E3F2FD; color: $color-info; }
.tag-orange { background: $color-primary-light; color: $color-primary-dark; }

.search-item { padding: $spacing-lg; border-bottom: 1rpx solid $color-border; }
.search-meta { font-size: $font-xs; color: $color-text-tertiary; margin-bottom: $spacing-xs; display: block; }
.loading-hint { text-align: center; padding: $spacing-xxl; color: $color-text-tertiary; font-size: $font-sm; }

.empty-state { text-align: center; padding: 120rpx $spacing-xxl; }
.empty-icon { font-size: 120rpx; display: block; margin-bottom: $spacing-xl; }
.empty-title { font-size: $font-xl; font-weight: 700; display: block; margin-bottom: $spacing-sm; }
.empty-desc { font-size: $font-base; color: $color-text-tertiary; display: block; margin-bottom: $spacing-xxl; }
.empty-features { text-align: left; margin-top: $spacing-xxl; font-size: $font-sm; color: $color-text-tertiary; line-height: 2.2;
  text { display: block; }
}

.fab {
  position: fixed; right: 32rpx; bottom: calc(160rpx + env(safe-area-inset-bottom));
  width: 104rpx; height: 104rpx; border-radius: 50%;
  background: $color-primary-gradient; color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: $shadow-md; z-index: 50;
  .fab-icon { font-size: 48rpx; font-weight: 300; }
}

.progress-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.progress-bg { height: 12rpx; background: $color-bg-hover; border-radius: 6rpx; overflow: hidden; margin: $spacing-md 0; }
.progress-fill { height: 100%; background: $color-primary-gradient; border-radius: 6rpx; transition: width 0.3s; }
.progress-text { font-size: $font-xs; color: $color-text-tertiary; text-align: center; }
</style>
