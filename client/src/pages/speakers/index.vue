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

    <view v-else class="card speaker-card" v-for="s in speakers" :key="s.id" @click="rename(s)">
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
</style>
