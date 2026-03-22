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

/* ── 旧代码备份（已废弃）── */
function _old_manageSpeakers() {
  speakerApi.list().then(speakers => {
    if (!speakers.length) { return }
    uni.showActionSheet({
      itemList: speakers.map(s => `${s.name} → 重命名`),
      success: (res) => {
        const spk = speakers[res.tapIndex]
        uni.showModal({
          title: `重命名「${spk.name}」`,
          editable: true,
          placeholderText: '输入新名称',
          cancelText: '取消',
          confirmText: '保存',
          success: async (r) => {
            if (r.confirm && r.content?.trim()) {
              await speakerApi.rename(spk.name, r.content.trim())
              uni.showToast({ title: '已更新', icon: 'success' })
              loadStats()
            }
          },
        })
      },
    })
  })
}

/* ── 术语管理（分 tab：人名/术语） ── */
function manageVocab() {
  uni.navigateTo({ url: '/pages/vocabulary/index' })
}

function _old_manageVocab() {
  vocabApi.list().then(vocab => {
    uni.hideLoading()
    // 先选择类别
    uni.showActionSheet({
      itemList: ['人名', '术语'],
      success: (catRes) => {
        const category = catRes.tapIndex === 0 ? 'person' : 'term'
        const catLabel = catRes.tapIndex === 0 ? '人名' : '术语'
        const filtered = vocab.filter(v => v.category === category)
        const placeholder = category === 'person'
          ? '输入人名（如：李明、王芳）'
          : '输入术语（如：K8s、微服务）'

        // 展示该类别下的列表
        const items = filtered.map(v => v.term)
        items.push(`+ 添加${catLabel}`)

        uni.showActionSheet({
          itemList: items,
          success: (res) => {
            if (res.tapIndex === filtered.length) {
              // 添加新术语
              uni.showModal({
                title: `添加${catLabel}`,
                editable: true,
                placeholderText: placeholder,
                cancelText: '取消',
                confirmText: '添加',
                success: async (r) => {
                  if (r.confirm && r.content?.trim()) {
                    await vocabApi.add(r.content.trim(), category)
                    uni.showToast({ title: `已添加"${r.content.trim()}"`, icon: 'success' })
                  }
                },
              })
            } else {
              // 删除已有术语
              const term = filtered[res.tapIndex]
              uni.showModal({
                title: '删除术语',
                content: `确定删除「${term.term}」？\n\n删除后新录音将不再使用该术语。`,
                cancelText: '取消',
                confirmText: '删除',
                success: async (r) => {
                  if (r.confirm) {
                    await vocabApi.delete(term.id)
                    uni.showToast({ title: '已删除', icon: 'success' })
                  }
                },
              })
            }
          },
        })
      },
    })
  })
}

/* ── 摘要模板管理 ── */
function managePrompts() {
  uni.navigateTo({ url: '/pages/prompts/index' })
}

function _old_managePrompts() {
  Promise.all([promptApi.list(), categoryApi.list()]).then(([prompts, cats]) => {
    const allCats = ['_default', ...cats.map(c => c.name || c)]
    const customMap = {}
    prompts.forEach(p => { customMap[p.category] = p })

    const catLabel = c => c === '_default' ? '通用（默认）' : c
    const items = allCats.map(c =>
      `${catLabel(c)} ${customMap[c] ? '· 已自定义' : '· 平台默认'}`
    )

    uni.showActionSheet({
      itemList: items,
      success: async (res) => {
        const cat = allCats[res.tapIndex]
        const custom = customMap[cat]
        let builtinText = ''
        try {
          builtinText = (await promptApi.builtin(cat)).prompt
        } catch (e) { /* ignore */ }
        const currentText = custom?.prompt || builtinText

        uni.showModal({
          title: `${catLabel(cat)} · 总结方式`,
          editable: true,
          placeholderText: '告诉 AI 你希望怎么总结这类录音',
          content: currentText,
          cancelText: custom ? '重置默认' : '取消',
          confirmText: '保存',
          success: async (r) => {
            if (r.confirm && r.content?.trim()) {
              await promptApi.save(cat, r.content.trim())
              uni.showToast({ title: '已保存', icon: 'success' })
            } else if (!r.confirm && custom) {
              // 取消按钮 = 重置默认（仅当有自定义时）
              await promptApi.delete(custom.id)
              uni.showToast({ title: '已恢复默认', icon: 'success' })
            }
          },
        })
      },
    })
  })
}

/* ── 关于 VoiceKB ── */
function showAbout() {
  uni.navigateTo({ url: '/pages/about/index' })
}

function _old_showAbout() {
  uni.showModal({
    title: 'VoiceKB v0.1.0',
    content: '开源个人录音知识库\n\n把日常录音变成可搜索、可对话的个人知识库。\n\n核心能力\n\n• 智能语音识别，自动区分说话人\n• 跨录音声纹识别，同一人自动关联\n• 关键词 + 语义双引擎搜索\n• AI 智能问答，基于录音内容回答问题\n• 完全本地部署，数据不出你的服务器\n\n技术栈：faster-whisper · resemblyzer · ChromaDB · Qwen3\n协议：Apache-2.0',
    showCancel: false,
    confirmText: '知道了',
  })
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
