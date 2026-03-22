<template>
  <view class="page">
    <view class="section-title">
      <text class="section-title-text">说话人管理</text>
      <text class="section-title-hint">{{ speakers.length }} 位</text>
    </view>

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
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { speakerApi } from '@/api'

const speakers = ref([])

async function load() {
  try {
    speakers.value = await speakerApi.list()
  } catch (e) {}
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
        await speakerApi.rename(spk.name, res.content.trim())
        uni.showToast({ title: '已更新', icon: 'success' })
        load()
      }
    },
  })
}

onMounted(load)
onShow(load)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; }
.section-title { display: flex; align-items: baseline; gap: $spacing-md; padding: $spacing-lg; }
.section-title-text { font-size: $font-lg; font-weight: 700; }
.section-title-hint { font-size: $font-sm; color: $color-text-tertiary; }

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
