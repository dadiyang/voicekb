<template>
  <view class="page">
    <!-- Logo -->
    <view class="logo-section">
      <view class="logo-circle">
        <text class="ti ti-microphone logo-icon"></text>
      </view>
      <text class="logo-name"><text style="color:#4F46E5">Voice</text>KB</text>
      <text class="logo-version">v0.1.0</text>
      <text class="logo-desc">开源个人录音知识库</text>
    </view>

    <!-- 介绍 -->
    <view class="card intro-card">
      <text class="intro-text">把日常录音变成可搜索、可对话的个人知识库。</text>
    </view>

    <!-- 核心能力 -->
    <view class="section-label">核心能力</view>
    <view class="card">
      <view class="feature-item">
        <text class="ti ti-microphone feature-icon"></text>
        <view class="feature-info">
          <text class="feature-name">智能语音识别</text>
          <text class="feature-desc">自动区分说话人，跨录音声纹关联</text>
        </view>
      </view>
      <view class="feature-item">
        <text class="ti ti-search feature-icon"></text>
        <view class="feature-info">
          <text class="feature-name">双引擎搜索</text>
          <text class="feature-desc">关键词 + 语义搜索，快速定位内容</text>
        </view>
      </view>
      <view class="feature-item">
        <text class="ti ti-file-text feature-icon"></text>
        <view class="feature-info">
          <text class="feature-name">智能摘要</text>
          <text class="feature-desc">自动生成会议纪要，支持自定义模板</text>
        </view>
      </view>
      <view class="feature-item" style="border-bottom:none">
        <text class="ti ti-message-circle feature-icon"></text>
        <view class="feature-info">
          <text class="feature-name">AI 问答</text>
          <text class="feature-desc">直接问录音内容，多轮对话</text>
        </view>
      </view>
    </view>

    <!-- 技术栈 -->
    <view class="section-label">技术栈</view>
    <view class="card tech-card">
      <text class="tech-text">faster-whisper · resemblyzer · ChromaDB · Qwen3</text>
    </view>

    <!-- 安全 -->
    <view class="card safe-card">
      <text class="ti ti-lock safe-icon"></text>
      <text class="safe-text">完全本地部署，数据不出你的服务器</text>
    </view>

    <text class="footer">MIT License · Made with AI</text>
  </view>
</template>

<script setup>
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; padding-bottom: $spacing-xxl; }

.logo-section { text-align: center; padding: $spacing-xxl $spacing-lg; }
.logo-circle {
  width: 128rpx; height: 128rpx; border-radius: 50%;
  background: $color-primary-gradient; margin: 0 auto $spacing-lg;
  display: flex; align-items: center; justify-content: center;
}
.logo-icon { font-size: 56rpx; color: #fff; }
.logo-name { font-size: 48rpx; font-weight: 800; letter-spacing: -2rpx; display: block; }
.logo-version { font-size: $font-xs; color: $color-text-disabled; display: block; margin-top: 4rpx; }
.logo-desc { font-size: $font-sm; color: $color-text-tertiary; display: block; margin-top: $spacing-sm; }

.intro-card { text-align: center; }
.intro-text { font-size: $font-base; color: $color-text-secondary; line-height: 1.8; }

.section-label { font-size: $font-sm; font-weight: 600; color: $color-text-tertiary; padding: $spacing-lg $spacing-xl 0; margin-bottom: -$spacing-xs; }

.feature-item {
  display: flex; align-items: center; gap: $spacing-lg;
  padding: 20rpx 0; border-bottom: 1rpx solid $color-border;
}
.feature-icon { font-size: 40rpx; color: $color-primary; flex-shrink: 0; }
.feature-info { flex: 1; }
.feature-name { font-size: $font-base; font-weight: 500; display: block; }
.feature-desc { font-size: $font-xs; color: $color-text-tertiary; }

.tech-card { text-align: center; }
.tech-text { font-size: $font-sm; color: $color-text-secondary; font-family: monospace; }

.safe-card { display: flex; align-items: center; gap: $spacing-md; }
.safe-icon { font-size: 36rpx; color: $color-success; }
.safe-text { font-size: $font-sm; color: $color-text-secondary; }

.footer { display: block; text-align: center; font-size: $font-xs; color: $color-text-disabled; margin-top: $spacing-xxl; }
</style>
