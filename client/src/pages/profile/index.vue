<template>
  <view class="page">
    <!-- 渐变头部 -->
    <view class="profile-banner">
      <view class="profile-header">
        <view class="profile-avatar">V</view>
        <view class="profile-info">
          <text class="profile-name">VoiceKB 用户</text>
          <text class="profile-sub">个人录音知识库</text>
        </view>
      </view>
    </view>

    <!-- 统计卡片（悬浮在渐变上） -->
    <view class="stats-float">
    <view class="profile-stats">
      <view class="stat-card">
        <text class="stat-num">{{ stats.recordings }}</text>
        <text class="stat-label">录音</text>
      </view>
      <view class="stat-card">
        <text class="stat-num">{{ stats.speakers }}</text>
        <text class="stat-label">说话人</text>
      </view>
      <view class="stat-card">
        <text class="stat-num">{{ stats.minutes }}</text>
        <text class="stat-label">分钟</text>
      </view>
    </view>
    </view>

    <!-- 菜单项 -->
    <view class="menu-section">
    <view class="profile-menu-item" @click="manageSpeakers">
      <text class="menu-emoji">👥</text>
      <text class="menu-text">说话人管理</text>
      <text class="ti ti-chevron-right menu-arrow"></text>
    </view>
    <view class="profile-menu-item" @click="manageVocab">
      <text class="menu-emoji">📖</text>
      <text class="menu-text">术语管理</text>
      <text class="ti ti-chevron-right menu-arrow"></text>
    </view>
    <view class="profile-menu-item" @click="managePrompts">
      <text class="menu-emoji">📝</text>
      <text class="menu-text">摘要模板</text>
      <text class="ti ti-chevron-right menu-arrow"></text>
    </view>
    <view class="profile-menu-item" @click="showAbout">
      <text class="menu-emoji">💡</text>
      <text class="menu-text">关于 VoiceKB</text>
      <text class="ti ti-chevron-right menu-arrow"></text>
    </view>
    </view>

    <text class="version">VoiceKB v0.1.0 · Apache-2.0</text>

  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { recordingApi, speakerApi, vocabApi, promptApi, categoryApi } from '@/api'

const stats = ref({ recordings: 0, speakers: 0, minutes: 0 })

/** 加载统计数据 */
async function loadStats() {
  try {
    const recs = await recordingApi.list()
    const spks = await speakerApi.list()
    const totalDur = recs.reduce((s, r) => s + (r.duration || 0), 0)
    stats.value = {
      recordings: recs.length,
      speakers: spks.length,
      minutes: Math.floor(totalDur / 60),
    }
  } catch (e) { /* ignore */ }
}

/* ── 说话人管理 — 跳转独立页面 ── */
function manageSpeakers() {
  uni.navigateTo({ url: '/pages/speakers/index' })
}

/* ── 术语管理（分 tab：人名/术语） ── */
function manageVocab() {
  uni.navigateTo({ url: '/pages/vocabulary/index' })
}

/* ── 摘要模板管理 ── */
function managePrompts() {
  uni.navigateTo({ url: '/pages/prompts/index' })
}

/* ── 关于 VoiceKB ── */
function showAbout() {
  uni.navigateTo({ url: '/pages/about/index' })
}

onMounted(loadStats)
onShow(loadStats)
</script>

<style lang="scss" scoped>
.page {
  min-height: #{"calc(100vh - var(--window-top, 0px))"};
  background: $color-bg-page;
  padding-bottom: 140rpx;
}

/* ── 渐变头部 ── */
.profile-banner {
  background: linear-gradient(135deg, #6366F1 0%, #818CF8 100%);
  padding: $spacing-xl $spacing-lg $spacing-xxl;
  
}
.profile-header {
  display: flex;
  align-items: center;
  gap: 28rpx;
}
.profile-avatar {
  width: 112rpx; height: 112rpx; border-radius: 50%;
  background: rgba(255,255,255,0.2); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 48rpx; font-weight: 700;
  border: 4rpx solid rgba(255,255,255,0.3);
}
.profile-info { display: flex; flex-direction: column; }
.profile-name { font-size: $font-xl; font-weight: 700; color: #fff; display: block; }
.profile-sub { font-size: $font-sm; color: rgba(255,255,255,0.85); }

/* ── 统计卡片（悬浮在渐变上） ── */
.stats-float {
  margin-top: -40rpx;
  padding: 0 $spacing-lg;
}
.profile-stats {
  display: flex;
  gap: $spacing-lg;
  margin-bottom: $spacing-xl;
}
.stat-card {
  flex: 1;
  background: $color-bg-card;
  border-radius: $radius-md;
  padding: 28rpx;
  text-align: center;
  box-shadow: $shadow-sm;
}
.stat-num {
  font-size: 44rpx;
  font-weight: 700;
  color: $color-primary;
  display: block;
}
.stat-label {
  font-size: $font-xs;
  color: $color-text-tertiary;
  margin-top: 4rpx;
  display: block;
}

/* ── 菜单区域 ── */
.menu-section {
  padding: 0 $spacing-lg;
}
.profile-menu-item {
  display: flex;
  align-items: center;
  gap: 24rpx;
  padding: 28rpx 32rpx;
  background: $color-bg-card;
  border-radius: $radius-lg;
  margin-bottom: $spacing-md;
  box-shadow: $shadow-md;
}
.menu-emoji {
  font-size: 36rpx;
  flex-shrink: 0;
}
.menu-text {
  flex: 1;
  font-size: $font-base;
}
.menu-arrow {
  flex: none;
  color: $color-text-tertiary;
  font-size: 32rpx;
}

/* ── 版本号 ── */
.version {
  display: block;
  text-align: center;
  margin-top: $spacing-xxl;
  font-size: $font-xs;
  color: $color-text-disabled;
}
</style>
