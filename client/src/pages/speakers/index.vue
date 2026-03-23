<template>
  <view class="page">
    <!-- 说明头部 -->
    <view class="header-card">
      <text class="ti ti-users header-icon"></text>
      <text class="header-title">说话人管理</text>
      <text class="header-desc">点击说话人进行管理</text>
    </view>

    <view class="list-section">
    <view v-if="!speakers.length" class="empty-hint">
      <text>暂无已注册说话人</text>
      <text class="empty-sub">上传录音后系统会自动识别说话人</text>
    </view>

    <view v-else class="card speaker-card" v-for="s in speakers" :key="s.id" @click="openPanel(s)">
      <view class="speaker-row">
        <view class="speaker-avatar" :class="'spk-' + (speakers.indexOf(s) % 5)">
          <text class="avatar-letter">{{ s.name.charAt(0) }}</text>
        </view>
        <view class="speaker-info">
          <text class="speaker-name">{{ s.name }}</text>
          <text class="speaker-meta">{{ s.recording_ids.length }} 条录音</text>
        </view>
        <text class="ti ti-chevron-right arrow-icon"></text>
      </view>
    </view>
    </view>

    <!-- 统一操作面板 -->
    <view v-if="panelVisible" class="modal-overlay" @click.self="panelVisible = false">
      <view class="modal-sheet">
        <!-- 说话人头部 -->
        <view class="panel-header">
          <view class="speaker-avatar large" :class="'spk-' + (speakers.indexOf(panelSpeaker) % 5)">
            <text class="avatar-letter large">{{ panelSpeaker?.name?.charAt(0) }}</text>
          </view>
          <text class="panel-name">{{ panelSpeaker?.name }}</text>
          <text class="panel-meta">{{ panelSpeaker?.recording_ids?.length || 0 }} 条录音</text>
        </view>

        <!-- 修改名字 -->
        <view class="rename-section">
          <view class="rename-row">
            <input class="rename-input" v-model="renameText"
                   :placeholder="panelSpeaker?.name?.startsWith('说话人') ? '给 TA 起个名字' : panelSpeaker?.name"
                   confirm-type="done" @confirm="doRename" />
            <view class="rename-btn" :class="{disabled: !renameText.trim()}" @click="doRename">保存</view>
          </view>
        </view>

        <!-- 关联录音 -->
        <view v-if="panelRecordings.length" class="recordings-section">
          <text class="section-label">出现的录音{{ panelRecordings.length > 5 ? `（共 ${panelRecordings.length} 条）` : '' }}</text>
          <view class="rec-link" v-for="r in panelRecordings.slice(0, 5)" :key="r.id" @click="goRecording(r.id, panelSpeaker?.name)">
            <text class="ti ti-microphone rec-link-icon"></text>
            <text class="rec-link-text">{{ r.title || r.filename }}</text>
            <text class="ti ti-chevron-right rec-link-arrow"></text>
          </view>
        </view>

        <view style="margin-top: 24rpx">
          <button class="btn-outline btn-block" @click="panelVisible = false">关闭</button>
        </view>

        <!-- 删除 -->
        <view class="delete-zone" @click="showDeleteConfirm">
          <text class="ti ti-trash delete-icon"></text>
          <text class="delete-text">删除此说话人</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { speakerApi, recordingApi } from '@/api'

const speakers = ref([])
const panelVisible = ref(false)
const panelSpeaker = ref(null)
const panelRecordings = ref([])
const renameText = ref('')

async function load() {
  try {
    speakers.value = await speakerApi.list()
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

async function openPanel(spk) {
  panelSpeaker.value = spk
  renameText.value = ''
  panelRecordings.value = []
  panelVisible.value = true

  // 加载关联录音标题
  if (spk.recording_ids?.length) {
    try {
      const all = await recordingApi.list()
      panelRecordings.value = all.filter(r => spk.recording_ids.includes(r.id))
    } catch (e) { /* ignore */ }
  }
}

function goRecording(recId, speakerName) {
  panelVisible.value = false
  const params = speakerName ? `&speaker=${encodeURIComponent(speakerName)}` : ''
  uni.navigateTo({ url: `/pages/recordings/detail?id=${recId}${params}` })
}

async function doRename() {
  const newName = renameText.value.trim()
  if (!newName) return
  try {
    await speakerApi.rename(panelSpeaker.value.id, newName)
    const found = speakers.value.find(s => s.id === panelSpeaker.value.id)
    if (found) found.name = newName
    panelSpeaker.value = { ...panelSpeaker.value, name: newName }
    renameText.value = ''
    uni.showToast({ title: '已更新', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: '更新失败', icon: 'none' })
  }
}

function showDeleteConfirm() {
  const spk = panelSpeaker.value
  uni.showActionSheet({
    itemList: [
      '仅删除声纹（录音中已有的标注保留）',
      '删除声纹并清除所有标注',
    ],
    success: (res) => {
      const revert = res.tapIndex === 1
      uni.showModal({
        title: `确认删除「${spk.name}」`,
        content: revert
          ? '删除后，录音中所有标注为此人的内容将恢复为"未知"。'
          : '删除后，系统不再自动识别此人，但录音中已有的标注不受影响。',
        cancelText: '取消',
        confirmText: '确认删除',
        success: async (r) => {
          if (r.confirm) {
            try {
              await speakerApi.delete(spk.id, revert)
              speakers.value = speakers.value.filter(s => s.id !== spk.id)
              panelVisible.value = false
              uni.showToast({ title: '已删除', icon: 'success' })
            } catch (e) {
              uni.showToast({ title: '删除失败', icon: 'none' })
            }
          }
        },
      })
    },
  })
}

onMounted(load)
onShow(load)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; }

/* ── 说明头部 ── */
.header-card {
  background: linear-gradient(135deg, #6366F1 0%, #818CF8 100%);
  padding: $spacing-xl $spacing-lg;
  text-align: center;
}
.header-icon { font-size: 64rpx; color: #fff; display: block; margin-bottom: $spacing-md; }
.header-title { font-size: $font-xl; font-weight: 700; color: #fff; display: block; }
.header-desc { font-size: $font-sm; color: rgba(255,255,255,0.85); display: block; margin-top: $spacing-xs; }

.list-section { padding: $spacing-lg; padding-bottom: 120rpx; }

.empty-hint { text-align: center; padding: $spacing-xxl; color: $color-text-tertiary;
  text { display: block; font-size: $font-base; }
}
.empty-sub { font-size: $font-sm; margin-top: $spacing-sm; }

.speaker-card { cursor: pointer; }
.speaker-row { display: flex; align-items: center; gap: $spacing-lg; }
.speaker-avatar {
  width: 80rpx; height: 80rpx; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  &.large { width: 100rpx; height: 100rpx; }
}
.avatar-letter { font-size: $font-sm; font-weight: 600; color: #fff;
  &.large { font-size: $font-lg; }
}
.spk-0 { background: $color-primary; }
.spk-1 { background: $color-warning; }
.spk-2 { background: $color-success; }
.spk-3 { background: #DB2777; }
.spk-4 { background: #7C3AED; }

.speaker-info { flex: 1; }
.speaker-name { font-size: $font-base; font-weight: 600; display: block; }
.speaker-meta { font-size: $font-xs; color: $color-text-tertiary; }
.arrow-icon { font-size: 28rpx; color: $color-text-disabled; }

/* ── Modal Sheet ── */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 999;
  display: flex; align-items: flex-end; justify-content: center;
}
.modal-sheet {
  width: 100%; background: $color-bg-card; border-radius: $radius-xl $radius-xl 0 0;
  padding: $spacing-xl $spacing-lg calc(#{$spacing-xl} + env(safe-area-inset-bottom));
}

/* ── Panel Header ── */
.panel-header { text-align: center; margin-bottom: $spacing-xl; }
.panel-name { font-size: $font-lg; font-weight: 700; display: block; margin-top: $spacing-md; }
.panel-meta { font-size: $font-xs; color: $color-text-tertiary; display: block; margin-top: 4rpx; }

/* ── Rename ── */
.rename-section { margin-bottom: $spacing-xl; }
.section-label { font-size: $font-sm; font-weight: 600; color: $color-text-tertiary; display: block; margin-bottom: $spacing-md; }
.rename-row { display: flex; gap: $spacing-md; }
.rename-input {
  flex: 1; height: 80rpx; padding: 0 $spacing-lg;
  background: $color-bg-page; border: 2rpx solid $color-border;
  border-radius: $radius-lg; font-size: 16px; color: $color-text-primary;
}
.rename-btn {
  height: 80rpx; line-height: 80rpx; padding: 0 32rpx;
  background: $color-primary; color: #fff; font-size: $font-sm; font-weight: 600;
  border-radius: $radius-lg; white-space: nowrap;
  &.disabled { opacity: 0.4; }
}

/* ── Recordings ── */
.recordings-section { margin-bottom: $spacing-lg; }
.rec-link {
  display: flex; align-items: center; gap: $spacing-md;
  padding: 20rpx 0; border-bottom: 1rpx solid $color-border; cursor: pointer;
}
.rec-link-icon { font-size: 32rpx; color: $color-primary; flex-shrink: 0; }
.rec-link-text { flex: 1; font-size: $font-sm; color: $color-text-primary; }
.rec-link-arrow { font-size: 24rpx; color: $color-text-disabled; }

/* ── Delete ── */
.delete-zone {
  display: flex; justify-content: center; align-items: center; gap: 8rpx;
  padding: $spacing-lg 0 0;
}
.delete-icon { font-size: 28rpx; color: $color-text-disabled; }
.delete-text { font-size: $font-xs; color: $color-text-disabled; }
</style>
