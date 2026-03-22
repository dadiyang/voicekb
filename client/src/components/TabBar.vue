<template>
  <view class="tab-bar safe-bottom">
    <view class="tab-item" :class="{active: current === 'recordings'}" @click="go('recordings')">
      <text class="ti ti-microphone tab-icon" :class="{active: current === 'recordings'}"></text>
      <text class="tab-label" :class="{active: current === 'recordings'}">录音</text>
    </view>
    <view class="tab-item" :class="{active: current === 'chat'}" @click="go('chat')">
      <text class="ti ti-message-circle tab-icon" :class="{active: current === 'chat'}"></text>
      <text class="tab-label" :class="{active: current === 'chat'}">问答</text>
    </view>
    <view class="tab-item" :class="{active: current === 'profile'}" @click="go('profile')">
      <text class="ti ti-user tab-icon" :class="{active: current === 'profile'}"></text>
      <text class="tab-label" :class="{active: current === 'profile'}">我的</text>
    </view>
  </view>
</template>

<script setup>
defineProps({
  current: { type: String, default: 'recordings' }
})

function go(page) {
  const routes = {
    recordings: '/pages/recordings/index',
    chat: '/pages/chat/index',
    profile: '/pages/profile/index',
  }
  uni.redirectTo({ url: routes[page] })
}
</script>

<style lang="scss" scoped>
.tab-bar {
  position: fixed; bottom: 0; left: 0; right: 0;
  height: 110rpx; background: $color-bg-card;
  display: flex; border-top: 1rpx solid $color-border;
  z-index: 100;
}
.tab-item {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 4rpx;
}
.tab-icon {
  font-size: 44rpx; color: $color-text-tertiary;
  &.active { color: $color-primary; }
}
.tab-label {
  font-size: 20rpx; color: $color-text-tertiary;
  &.active { color: $color-primary; font-weight: 600; }
}
</style>
