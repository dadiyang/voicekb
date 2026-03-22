<template>
  <view class="page">
    <!-- Logo + 核心卖点 -->
    <view class="logo-section">
      <view class="logo-circle">
        <text class="ti ti-microphone logo-icon"></text>
      </view>
      <text class="logo-name"><text style="color:#4F46E5">Voice</text>KB</text>
      <text class="logo-tagline">把日常录音变成可搜索、可对话的知识库</text>
      <view class="privacy-badge">
        <text class="ti ti-lock privacy-icon"></text>
        <text class="privacy-text">完全本地部署，数据不出你的服务器</text>
      </view>
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
      <view class="tech-tags">
        <text class="tech-tag">faster-whisper</text>
        <text class="tech-tag">resemblyzer</text>
        <text class="tech-tag">ChromaDB</text>
        <text class="tech-tag">Qwen3</text>
        <text class="tech-tag">FastAPI</text>
        <text class="tech-tag">uni-app</text>
      </view>
    </view>

    <text class="footer">v0.1.0 · Apache-2.0 · Made with AI</text>
  </view>
</template>

<script setup>
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; padding-bottom: $spacing-xxl; }

.logo-section { text-align: center; padding: $spacing-xxl $spacing-lg $spacing-lg; }
.logo-circle {
  width: 128rpx; height: 128rpx; border-radius: 50%;
  background: $color-primary-gradient; margin: 0 auto $spacing-lg;
  display: flex; align-items: center; justify-content: center;
}
.logo-icon { font-size: 56rpx; color: #fff; }
.logo-name { font-size: 48rpx; font-weight: 800; letter-spacing: -2rpx; display: block; margin-bottom: $spacing-sm; }
.logo-tagline { font-size: $font-base; color: $color-text-secondary; display: block; line-height: 1.6; }

.privacy-badge {
  display: inline-flex; align-items: center; gap: 8rpx;
  margin-top: $spacing-lg; padding: 12rpx 28rpx;
  background: #E8F5E9; border-radius: $radius-full;
}
.privacy-icon { font-size: 28rpx; color: $color-success; }
.privacy-text { font-size: $font-xs; color: #2E7D32; font-weight: 500; }

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
.tech-tags { display: flex; flex-wrap: wrap; justify-content: center; gap: 12rpx; }
.tech-tag {
  display: inline-block; padding: 8rpx 20rpx;
  background: $color-bg-page; border-radius: $radius-sm;
  font-size: $font-xs; color: $color-text-secondary; font-family: monospace;
}

.footer { display: block; text-align: center; font-size: $font-xs; color: $color-text-disabled; margin-top: $spacing-xxl; }
</style>
