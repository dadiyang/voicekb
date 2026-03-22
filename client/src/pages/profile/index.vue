<template>
  <view class="page">
    <!-- 用户信息 -->
    <view class="profile-header">
      <view class="avatar">V</view>
      <view class="info">
        <text class="name">VoiceKB 用户</text>
        <text class="sub">个人录音知识库</text>
      </view>
    </view>

    <!-- 统计 -->
    <view class="stats-row">
      <view class="stat-card"><text class="stat-num">{{ stats.recordings }}</text><text class="stat-label">录音</text></view>
      <view class="stat-card"><text class="stat-num">{{ stats.speakers }}</text><text class="stat-label">说话人</text></view>
      <view class="stat-card"><text class="stat-num">{{ stats.minutes }}</text><text class="stat-label">分钟</text></view>
    </view>

    <!-- 菜单 -->
    <view class="menu-item" @click="manageSpeakers">
      <text class="menu-icon">👥</text><text class="menu-text">说话人管理</text><text class="menu-arrow">›</text>
    </view>
    <view class="menu-item" @click="manageVocab">
      <text class="menu-icon">📖</text><text class="menu-text">术语管理</text><text class="menu-arrow">›</text>
    </view>
    <view class="menu-item" @click="managePrompts">
      <text class="menu-icon">📋</text><text class="menu-text">摘要模板</text><text class="menu-arrow">›</text>
    </view>
    <view class="menu-item" @click="showAbout">
      <text class="menu-icon">ℹ️</text><text class="menu-text">关于 VoiceKB</text><text class="menu-arrow">›</text>
    </view>

    <text class="version">VoiceKB v0.1.0 · MIT License</text>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { recordingApi, speakerApi, vocabApi, promptApi, categoryApi } from '@/api'

const stats = ref({ recordings: 0, speakers: 0, minutes: 0 })

async function loadStats() {
  try {
    const recs = await recordingApi.list()
    const spks = await speakerApi.list()
    const totalDur = recs.reduce((s, r) => s + (r.duration || 0), 0)
    stats.value = { recordings: recs.length, speakers: spks.length, minutes: Math.floor(totalDur / 60) }
  } catch (e) { /* ignore */ }
}

function manageSpeakers() {
  uni.showLoading({ title: '加载中' })
  speakerApi.list().then(speakers => {
    uni.hideLoading()
    if (!speakers.length) { uni.showToast({ title: '暂无已注册说话人', icon: 'none' }); return }
    uni.showActionSheet({
      itemList: speakers.map(s => `${s.name} (${s.recording_ids.length}条录音) → 重命名`),
      success: (res) => {
        const spk = speakers[res.tapIndex]
        uni.showModal({
          title: `重命名「${spk.name}」`, editable: true, placeholderText: '输入新名称',
          cancelText: '取消', confirmText: '保存',
          success: async (r) => {
            if (r.confirm && r.content?.trim()) {
              await speakerApi.rename(spk.name, r.content.trim())
              uni.showToast({ title: '已更新', icon: 'success' })
            }
          },
        })
      },
    })
  })
}

function manageVocab() {
  uni.showLoading({ title: '加载中' })
  vocabApi.list().then(vocab => {
    uni.hideLoading()
    const items = vocab.map(v => `${v.term} (${v.category === 'person' ? '人名' : '术语'})`)
    items.push('+ 添加术语')
    uni.showActionSheet({
      itemList: items,
      success: (res) => {
        if (res.tapIndex === vocab.length) {
          // 添加
          uni.showModal({
            title: '添加术语', editable: true, placeholderText: '输入人名或专业术语',
            cancelText: '取消', confirmText: '添加',
            success: async (r) => {
              if (r.confirm && r.content?.trim()) {
                await vocabApi.add(r.content.trim(), 'person')
                uni.showToast({ title: '已添加', icon: 'success' })
              }
            },
          })
        } else {
          // 删除
          uni.showModal({
            title: '删除术语', content: `确定删除「${vocab[res.tapIndex].term}」？`,
            cancelText: '取消', confirmText: '删除',
            success: async (r) => {
              if (r.confirm) {
                await vocabApi.delete(vocab[res.tapIndex].id)
                uni.showToast({ title: '已删除', icon: 'success' })
              }
            },
          })
        }
      },
    })
  })
}

function managePrompts() {
  Promise.all([promptApi.list(), categoryApi.list()]).then(([prompts, cats]) => {
    const allCats = ['_default', ...cats.map(c => c.name)]
    const customMap = {}
    prompts.forEach(p => { customMap[p.category] = p })

    const catLabel = c => c === '_default' ? '通用（默认）' : c
    const items = allCats.map(c => `${catLabel(c)} ${customMap[c] ? '· 已自定义' : '· 平台默认'}`)
    uni.showActionSheet({
      itemList: items,
      success: async (res) => {
        const cat = allCats[res.tapIndex]
        const custom = customMap[cat]
        let builtinText = ''
        try { builtinText = (await promptApi.builtin(cat)).prompt } catch (e) {}
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
              // 取消按钮 = 重置默认
              await promptApi.delete(custom.id)
              uni.showToast({ title: '已恢复默认', icon: 'success' })
            }
          },
        })
      },
    })
  })
}

function showAbout() {
  uni.showModal({
    title: 'VoiceKB v0.1.0',
    content: '个人录音知识库\n\n🎤 自动识别每个人说了什么\n🔍 关键词 + 语义双引擎搜索\n📝 智能生成会议摘要\n💬 AI 问答\n\n完全本地部署，数据不出你的服务器\n\n技术栈：faster-whisper · resemblyzer · ChromaDB · Qwen3\n协议：MIT License',
    showCancel: false,
    confirmText: '知道了',
  })
}

onMounted(loadStats)
onShow(loadStats)
</script>

<style lang="scss" scoped>
.page { min-height: #{"calc(100vh - var(--window-top, 0px))"}; background: $color-bg-page; padding: $spacing-lg; }

.profile-header { display: flex; align-items: center; gap: $spacing-lg; margin-bottom: $spacing-xxl; }
.avatar {
  width: 112rpx; height: 112rpx; border-radius: 50%;
  background: $color-primary-gradient; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 48rpx; font-weight: 700;
}
.name { font-size: $font-xl; font-weight: 600; display: block; }
.sub { font-size: $font-sm; color: $color-text-tertiary; }

.stats-row { display: flex; gap: $spacing-lg; margin-bottom: $spacing-xxl; }
.stat-card {
  flex: 1; background: $color-bg-card; border-radius: $radius-lg;
  padding: $spacing-lg; text-align: center; box-shadow: $shadow-sm;
}
.stat-num { font-size: $font-xxl; font-weight: 700; color: $color-primary; display: block; }
.stat-label { font-size: $font-xs; color: $color-text-tertiary; margin-top: 4rpx; display: block; }

.menu-item {
  display: flex; align-items: center; gap: $spacing-lg;
  padding: $spacing-lg; background: $color-bg-card; border-radius: $radius-lg;
  margin-bottom: $spacing-md; box-shadow: $shadow-sm;
}
.menu-icon { font-size: 36rpx; flex-shrink: 0; }
.menu-text { flex: 1; font-size: $font-base; }
.menu-arrow { color: $color-text-disabled; font-size: $font-lg; }

.version { display: block; text-align: center; margin-top: $spacing-xxl; font-size: $font-xs; color: $color-text-disabled; }
</style>
