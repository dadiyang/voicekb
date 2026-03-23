<template>
  <view class="page">
    <!-- 说明头部 -->
    <view class="header-card">
      <text class="ti ti-users header-icon"></text>
      <text class="header-title">说话人管理</text>
      <text class="header-desc">点击说话人可标注真实姓名，全局生效</text>
    </view>

    <view class="list-section">
    <view v-if="!speakers.length" class="empty-hint">
      <text>暂无已注册说话人</text>
      <text class="empty-sub">上传录音后系统会自动识别说话人</text>
    </view>

    <view v-else class="card speaker-card" v-for="s in speakers" :key="s.id"
          @click="rename(s)" @longpress.prevent="showDeleteMenu(s)">
      <view class="speaker-row">
        <view class="speaker-avatar" :class="'spk-' + (speakers.indexOf(s) % 5)">
          <text class="avatar-letter">{{ s.name.charAt(0) }}</text>
        </view>
        <view class="speaker-info">
          <text class="speaker-name">{{ s.name }}</text>
          <text class="speaker-meta">{{ s.recording_ids.length }} 条录音</text>
        </view>
        <text class="ti ti-pencil edit-icon"></text>
      </view>
    </view>
    </view>

    <!-- 删除菜单 -->
    <view v-if="menuVisible" class="modal-overlay" @click.self="menuVisible = false">
      <view class="modal-sheet">
        <text class="modal-title">{{ menuSpeaker?.name }}</text>
        <view class="menu-item" @click="doDelete(false)">
          <text class="ti ti-trash menu-item-icon"></text>
          <view class="menu-item-content">
            <text class="menu-item-text">删除声纹档案</text>
            <text class="menu-item-desc">录音中的标注保留不变</text>
          </view>
        </view>
        <view class="menu-item" @click="doDelete(true)">
          <text class="ti ti-trash menu-item-icon" style="color:#FF3B30"></text>
          <view class="menu-item-content">
            <text class="menu-item-text" style="color:#FF3B30">删除并重置标注</text>
            <text class="menu-item-desc">录音中的标注恢复为"未知"</text>
          </view>
        </view>
        <view style="margin-top: 24rpx">
          <button class="btn-outline btn-block" @click="menuVisible = false">取消</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { speakerApi } from '@/api'

const speakers = ref([])

async function load() {
  try {
    speakers.value = await speakerApi.list()
  } catch (e) {
    uni.showToast({ title: '加载失败', icon: 'none' })
  }
}

function rename(spk) {
  uni.showModal({
    title: `标注「${spk.name}」`,
    editable: true,
    placeholderText: '输入真实姓名',
    cancelText: '取消',
    confirmText: '保存',
    success: async (res) => {
      if (res.confirm && res.content?.trim()) {
        const newName = res.content.trim()
        await speakerApi.rename(spk.name, newName)
        // 本地更新，不重新加载（避免滚动位置重置）
        const found = speakers.value.find(s => s.id === spk.id)
        if (found) found.name = newName
        uni.showToast({ title: '已更新', icon: 'success' })
      }
    },
  })
}

const menuVisible = ref(false)
const menuSpeaker = ref(null)

function showDeleteMenu(spk) {
  menuSpeaker.value = spk
  menuVisible.value = true
}

async function doDelete(revert) {
  const spk = menuSpeaker.value
  menuVisible.value = false
  try {
    await speakerApi.delete(spk.id, revert)
    speakers.value = speakers.value.filter(s => s.id !== spk.id)
    uni.showToast({ title: revert ? '已删除并重置标注' : '已删除', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: '删除失败', icon: 'none' })
  }
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
}
.avatar-letter { font-size: $font-sm; font-weight: 600; color: #fff; }
.spk-0 { background: $color-primary; }
.spk-1 { background: $color-warning; }
.spk-2 { background: $color-success; }
.spk-3 { background: #DB2777; }
.spk-4 { background: #7C3AED; }

.speaker-info { flex: 1; }
.speaker-name { font-size: $font-base; font-weight: 600; display: block; }
.speaker-meta { font-size: $font-xs; color: $color-text-tertiary; }
.edit-icon { font-size: 32rpx; color: $color-text-disabled; }

/* ── Modal Sheet ── */
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
.menu-item-content { flex: 1; }
.menu-item-text { font-size: $font-base; display: block; }
.menu-item-desc { font-size: $font-xs; color: $color-text-tertiary; display: block; margin-top: 4rpx; }
</style>
