<template>
  <view class="page">
    <!-- 品牌头部（正常滚动） -->
    <view class="brand-header">
      <view class="brand-row">
        <view>
          <text class="brand-title">VoiceKB</text>
          <text class="brand-sub">{{ recordings.length }} 条录音 · {{ totalMinutes }} 分钟</text>
        </view>
        <view class="brand-fab" @click="chooseFile">
          <text class="ti ti-plus brand-fab-icon"></text>
        </view>
      </view>
    </view>

    <!-- 搜索 + 分类筛选（sticky 固定） -->
    <view class="sticky-top">
      <view class="search-bar">
        <text class="ti ti-search search-icon"></text>
        <input class="search-input" v-model="searchQuery" placeholder="搜索录音内容..."
               @input="debounceSearch" confirm-type="search" />
      </view>
      <scroll-view v-if="usedCategories.length && !searchQuery" scroll-x class="filter-bar">
        <view class="filter-chip" :class="{active: activeCategory === ''}" @click="filterBy('')">全部</view>
        <view class="filter-chip" :class="{active: activeCategory === c}" v-for="c in usedCategories" :key="c" @click="filterBy(c)">{{ c }}</view>
      </scroll-view>
    </view>

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

    <!-- 以下内容仅在非搜索状态显示 -->
    <template v-if="!searchQuery">

    <!-- 上传中顶部吸顶提示 -->
    <view v-if="uploadingFile" class="upload-sticky-bar">
      <text>正在上传 {{ uploadPercent }}% — 请勿刷新或离开</text>
    </view>

    <!-- 上传中卡片（非阻塞） -->
    <view v-if="uploadingFile" class="card rec-card uploading-card">
      <view class="rec-header">
        <view class="rec-icon">
          <text class="ti ti-upload" style="font-size:40rpx;color:#4F46E5"></text>
        </view>
        <view class="rec-info">
          <text class="rec-name">{{ uploadingFile }}</text>
          <text class="rec-meta" style="color:#4F46E5">上传中 {{ uploadPercent }}%</text>
        </view>
      </view>
      <view class="progress-bar-bg" style="margin-top:16rpx"><view class="progress-bar-fill" :style="{width: uploadPercent + '%'}" /></view>
    </view>

    <!-- 录音列表 -->
    <view v-if="filteredRecordings.length || uploadingFile">
      <view class="card rec-card" v-for="r in filteredRecordings" :key="r.id"
            @click="r.status === 'completed' ? goDetail(r.id) : goDetail(r.id)" @longpress="showMenu(r.id)">
        <view class="rec-header">
          <view class="rec-icon">
            <text class="ti ti-microphone" style="font-size:40rpx;color:#4F46E5"></text>
          </view>
          <view class="rec-info">
            <text class="rec-name">{{ r.title || r.filename }}</text>
            <text class="rec-meta" v-if="r.status === 'completed'">{{ relativeTime(r.created_at) }} · {{ friendlyDuration(r.duration) }}</text>
            <text class="rec-meta" v-else-if="r.status === 'processing'" style="color:#4F46E5">{{ processingStep(r.id) }}</text>
            <text class="rec-meta" v-else>
              <text class="rec-status" :class="r.status">{{ statusLabel[r.status] }}</text>
            </text>
          </view>
        </view>
        <!-- 处理中的录音显示进度条 -->
        <view v-if="r.status === 'processing'" class="progress-bar-bg" style="margin-top:16rpx">
          <view class="progress-bar-fill" :style="{width: processingPercent(r.id) + '%'}" />
        </view>
        <view v-else class="rec-speakers">
          <text v-if="r.category && r.category !== '其他'" class="category-tag">{{ r.category }}</text>
          <text v-for="(s, i) in (r.speakers||[])" :key="s" class="speaker-tag" :class="'spk-idx-' + i">{{ s }}</text>
        </view>
      </view>
    </view>

    <!-- 空状态（仅在加载完成后显示） -->
    <view v-else-if="loaded" class="empty-state">
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

    </template>
    <!-- /非搜索状态 -->

    <!-- Tab Bar -->

    <!-- 操作菜单 -->
    <view v-if="menuVisible" class="modal-overlay" @click.self="menuVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">操作</text>
        <view class="menu-item" @click="doAction('category')">
          <text class="ti ti-tag menu-item-icon"></text>
          <text class="menu-item-text">修改分类</text>
        </view>
        <view class="menu-item" @click="doAction('resummarize')">
          <text class="ti ti-file-text menu-item-icon"></text>
          <text class="menu-item-text">重新总结</text>
        </view>
        <view class="menu-item" @click="doAction('reprocess')">
          <text class="ti ti-refresh menu-item-icon"></text>
          <text class="menu-item-text">重新识别</text>
          <text class="menu-item-sub">(较慢)</text>
        </view>
        <view class="menu-item" @click="doAction('delete')">
          <text class="ti ti-trash menu-item-icon" style="color:#FF3B30"></text>
          <text class="menu-item-text" style="color:#FF3B30">删除录音</text>
        </view>
        <view style="margin-top: 24rpx">
          <button class="btn-outline btn-block" @click="menuVisible = false">取消</button>
        </view>
      </view>
    </view>

    <!-- 分类选择 -->
    <view v-if="catPickerVisible" class="modal-overlay" @click.self="catPickerVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">修改分类</text>
        <view class="cat-chips">
          <text v-for="c in categoryNames" :key="c" class="filter-chip" @click="pickCategory(c)">{{ c }}</text>
        </view>
        <view style="margin-top: 24rpx">
          <button class="btn-outline btn-block" @click="catPickerVisible = false">取消</button>
        </view>
      </view>
    </view>

    <!-- (进度已嵌入列表卡片，不再使用全屏遮罩) -->
  </view>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { onShow, onHide } from '@dcloudio/uni-app'
import { recordingApi, searchApi, categoryApi, uploadAudio } from '@/api'
import { relativeTime, friendlyDuration } from '@/utils/format'

const recordings = ref([])
const loaded = ref(false)
const activeCategory = ref('')
const searchQuery = ref('')
const searchResults = ref(null)
const searching = ref(false)

// 上传状态 — 用全局变量，导航到详情页再返回时不丢失
// （uni-app tabBar 页面不会销毁，但 navigateTo 的页面栈恢复时需要同步）
const _g = (typeof getApp === 'function' && getApp()?.globalData) || {}
const uploadingFile = ref(_g._uploadingFile || '')
const uploadPercent = ref(_g._uploadPercent || 0)

// 处理中录音的进度（按 recording_id 存储）
const progressMap = ref({}) // { recId: { step, percent } }

const statusLabel = { pending: '等待中', processing: '处理中', completed: '已完成', failed: '失败' }

function processingStep(recId) {
  const p = progressMap.value[recId]
  return p ? `${p.step} ${p.percent}%` : '处理中...'
}
function processingPercent(recId) {
  return progressMap.value[recId]?.percent || 0
}

const totalMinutes = computed(() =>
  Math.floor(recordings.value.reduce((s, r) => s + (r.duration || 0), 0) / 60)
)

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
let progressPollers = {} // recId -> intervalId

async function loadRecordings() {
  try {
    recordings.value = await recordingApi.list()
    loaded.value = true
    // 自动为所有 processing 录音启动进度轮询
    const processingIds = recordings.value.filter(r => r.status === 'processing').map(r => r.id)
    processingIds.forEach(id => { if (!progressPollers[id]) startProgressPoll(id) })
    // 有 processing 录音时定期刷新列表
    if (processingIds.length) {
      clearTimeout(listRefreshTimer)
      listRefreshTimer = setTimeout(loadRecordings, 5000)
    }
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

function startProgressPoll(recId) {
  if (progressPollers[recId]) return
  progressPollers[recId] = setInterval(async () => {
    try {
      const st = await recordingApi.status(recId)
      progressMap.value[recId] = { step: st.step, percent: Math.max(0, st.percent) }
      if (st.percent >= 100 || st.percent < 0) {
        clearInterval(progressPollers[recId])
        delete progressPollers[recId]
        delete progressMap.value[recId]
        if (st.percent >= 100) {
          uni.showToast({ title: '处理完成', icon: 'success' })
        }
        loadRecordings()
      }
    } catch (e) { /* continue */ }
  }, 2000)
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

// beforeunload 拦截（上传中防止用户离开）
function onBeforeUnload(e) {
  e.preventDefault()
  e.returnValue = '音频正在上传中，离开将中断上传。确定离开？'
}

// #ifdef H5
function doUploadH5(file) {
  uploadingFile.value = file.name; _g._uploadingFile = file.name
  uploadPercent.value = 0; _g._uploadPercent = 0
  window.addEventListener('beforeunload', onBeforeUnload)

  const fd = new FormData()
  fd.append('file', file)

  const xhr = new XMLHttpRequest()
  xhr.open('POST', '/api/upload')

  xhr.upload.onprogress = (e) => {
    if (e.lengthComputable) {
      uploadPercent.value = Math.round((e.loaded / e.total) * 100)
      _g._uploadPercent = uploadPercent.value
    }
  }

  xhr.onload = () => {
    window.removeEventListener('beforeunload', onBeforeUnload)
    uploadingFile.value = ''; _g._uploadingFile = ''
    uploadPercent.value = 0; _g._uploadPercent = 0
    if (xhr.status === 200) {
      const data = JSON.parse(xhr.responseText)
      uni.showToast({ title: '上传成功，后台处理中', icon: 'success' })
      loadRecordings()
    } else {
      uni.showToast({ title: '上传失败', icon: 'none' })
    }
  }

  xhr.onerror = () => {
    window.removeEventListener('beforeunload', onBeforeUnload)
    uploadingFile.value = ''; _g._uploadingFile = ''
    uploadPercent.value = 0; _g._uploadPercent = 0
    uni.showToast({ title: '上传失败', icon: 'none' })
  }

  xhr.send(fd)
}
// #endif

async function doUploadFile(path) {
  uploadingFile.value = path.split('/').pop()
  uploadPercent.value = 0

  try {
    const data = await uploadAudio(path)
    uni.showToast({ title: '上传成功，后台处理中', icon: 'success' })
    loadRecordings()
  } catch (e) {
    uni.showToast({ title: '上传失败', icon: 'none' })
  } finally {
    uploadingFile.value = ''
  }
}

function goDetail(id, seekTime) {
  uni.navigateTo({ url: `/pages/recordings/detail?id=${id}${seekTime ? '&seek=' + seekTime : ''}` })
}

const menuVisible = ref(false)
const menuRecId = ref('')
const catPickerVisible = ref(false)
const categoryNames = ref([])

function showMenu(id) {
  menuRecId.value = id
  menuVisible.value = true
}

async function doAction(action) {
  const id = menuRecId.value
  menuVisible.value = false
  if (action === 'category') {
    try {
      const presets = await categoryApi.list()
      categoryNames.value = presets.map(p => p.name || p)
      catPickerVisible.value = true
    } catch (e) {
      uni.showToast({ title: '获取分类失败', icon: 'none' })
    }
  } else if (action === 'resummarize') {
    uni.showToast({ title: '正在重新总结...', icon: 'none' })
    await recordingApi.resummarize(id)
    uni.showToast({ title: '总结已更新', icon: 'success' })
    loadRecordings()
  } else if (action === 'reprocess') {
    await recordingApi.reprocess(id)
    startProgressPoll(id)
    loadRecordings()
  } else if (action === 'delete') {
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
}

async function pickCategory(name) {
  catPickerVisible.value = false
  await recordingApi.updateCategory(menuRecId.value, name)
  uni.showToast({ title: '分类已更新', icon: 'success' })
  loadRecordings()
}

function cleanupPollers() {
  clearTimeout(listRefreshTimer)
  Object.keys(progressPollers).forEach(id => clearInterval(progressPollers[id]))
  progressPollers = {}
}

onMounted(loadRecordings)
onShow(loadRecordings)
onHide(cleanupPollers)
onUnmounted(cleanupPollers)
</script>

<style lang="scss" scoped>
.page { min-height: #{"calc(100vh - var(--window-top, 0px))"}; background: $color-bg-page; padding-bottom: 140rpx; }

/* ===== 品牌头部（正常滚动） ===== */
.brand-header {
  background: linear-gradient(135deg, #6366F1 0%, #818CF8 100%);
  padding: $spacing-lg;
}
.brand-row { display: flex; justify-content: space-between; align-items: center; }
.brand-title { font-size: 40rpx; font-weight: 800; color: #fff; display: block; letter-spacing: -1rpx; }
.brand-sub { font-size: $font-xs; color: rgba(255,255,255,0.75); display: block; margin-top: 4rpx; }
.brand-fab {
  width: 80rpx; height: 80rpx; border-radius: 50%;
  background: rgba(255,255,255,0.2); display: flex; align-items: center; justify-content: center;
}
.brand-fab-icon { font-size: 36rpx; color: #fff; }

/* ===== Sticky 搜索 + 筛选 ===== */
.sticky-top { position: sticky; top: var(--window-top, 44px); z-index: 50; background: $color-bg-page; }

.search-bar {
  position: relative; padding: $spacing-md $spacing-lg;
  background: $color-bg-page;
}
.search-icon { position: absolute; left: 40rpx; top: 50%; transform: translateY(-50%); font-size: 28rpx; color: $color-text-disabled; z-index: 1; }
.search-input {
  width: 100%; height: 80rpx; padding: 0 28rpx 0 72rpx;
  background: $color-bg-card; border: 2rpx solid $color-border;
  border-radius: $radius-full; font-size: $font-base; color: $color-text-primary;
}
// #ifdef H5
.search-input::placeholder { color: $color-text-disabled !important; }
// #endif

/* ===== Filter Bar — 分类筛选 ===== */
.filter-bar {
  white-space: nowrap; padding: 0 $spacing-lg $spacing-md;
  background: $color-bg-page;
}
.filter-chip {
  display: inline-block; height: 60rpx; line-height: 60rpx;
  padding: 0 28rpx; border-radius: $radius-full;
  font-size: 26rpx; font-weight: 500; margin-right: $spacing-md;
  border: 3rpx solid $color-border; background: $color-bg-card; color: $color-text-secondary;
  white-space: nowrap; transition: all 0.15s;
  &.active { background: $color-primary; color: #fff; border-color: $color-primary; box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.2); }
}

/* ===== Recording Card — 继承 order-card 结构 ===== */
.rec-card {
  cursor: pointer; transition: box-shadow 0.2s;
  border-left: 6rpx solid $color-primary; overflow: hidden;
}
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

/* ===== 内嵌进度条 ===== */
.progress-bar-bg { width: 100%; height: 8rpx; background: #E5E7EB; border-radius: 4rpx; overflow: hidden; }
.progress-bar-fill { height: 100%; background: linear-gradient(90deg, $color-primary, #818CF8); border-radius: 4rpx; transition: width 0.5s ease; }

.upload-sticky-bar {
  position: sticky; top: 0; z-index: 50;
  background: $color-primary; color: #fff;
  font-size: 24rpx; text-align: center;
  padding: 10rpx 0;
}
.uploading-card {
  border-left-color: #818CF8 !important;
  animation: pulse-border 1.5s ease-in-out infinite;
}
@keyframes pulse-border {
  0%, 100% { border-left-color: $color-primary; }
  50% { border-left-color: #818CF8; }
}

/* ===== Modal Sheet ===== */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 999;
  display: flex; align-items: flex-end; justify-content: center;
}
.modal-sheet {
  width: 100%; background: $color-bg-card; border-radius: $radius-xl $radius-xl 0 0;
  padding: $spacing-xl $spacing-lg calc(#{$spacing-xl} + env(safe-area-inset-bottom));
}
.modal-title { font-size: $font-lg; font-weight: 700; display: block; margin-bottom: $spacing-lg; }
.menu-item {
  display: flex; align-items: center; gap: $spacing-lg; padding: 24rpx 0;
  border-bottom: 1rpx solid $color-border;
}
.menu-item-icon { font-size: 36rpx; color: $color-text-secondary; flex-shrink: 0; }
.menu-item-text { flex: 1; font-size: $font-base; }
.menu-item-sub { font-size: 20rpx; color: $color-text-tertiary; }
.cat-chips { display: flex; flex-wrap: wrap; gap: $spacing-md; }
</style>
