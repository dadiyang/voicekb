<template>
  <view class="page">
    <!-- 说明头部 -->
    <view class="header-card">
      <text class="ti ti-file-text header-icon"></text>
      <text class="header-title">摘要模板</text>
      <text class="header-desc">为不同类别的录音定制 AI 总结方式</text>
    </view>

    <!-- 分类列表 -->
    <view class="list-section">
      <view class="list-card" v-for="c in allCats" :key="c" @click="editPrompt(c)">
        <view class="list-left">
          <view class="cat-dot" :class="{'custom': customMap[c]}"></view>
          <view class="list-info">
            <text class="list-name">{{ catLabel(c) }}</text>
            <text class="list-status" :class="{custom: customMap[c]}">{{ customMap[c] ? '已自定义' : '使用平台默认' }}</text>
          </view>
        </view>
        <text class="ti ti-chevron-right list-arrow"></text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { promptApi, categoryApi } from '@/api'

const allCats = ref([])
const customMap = ref({})

function catLabel(c) { return c === '_default' ? '通用（默认）' : c }

async function load() {
  try {
    const [prompts, cats] = await Promise.all([promptApi.list(), categoryApi.list()])
    allCats.value = ['_default', ...cats.map(c => c.name || c)]
    const map = {}
    prompts.forEach(p => { map[p.category] = p })
    customMap.value = map
  } catch (e) {}
}

async function editPrompt(cat) {
  const custom = customMap.value[cat]
  let builtinText = ''
  try { builtinText = (await promptApi.builtin(cat)).prompt } catch (e) {}
  const currentText = custom?.prompt || builtinText

  uni.showModal({
    title: catLabel(cat),
    editable: true,
    placeholderText: '告诉 AI 你希望怎么总结这类录音',
    content: currentText,
    cancelText: custom ? '重置默认' : '取消',
    confirmText: '保存',
    success: async (r) => {
      if (r.confirm && r.content?.trim()) {
        await promptApi.save(cat, r.content.trim())
        uni.showToast({ title: '已保存', icon: 'success' })
        load()
      } else if (!r.confirm && custom) {
        await promptApi.delete(custom.id)
        uni.showToast({ title: '已恢复默认', icon: 'success' })
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

/* ── 说明头部 ── */
.header-card {
  background: $color-primary-banner;
  padding: $spacing-xxl $spacing-lg;
  text-align: center;
}
.header-icon { font-size: 64rpx; color: #fff; display: block; margin-bottom: $spacing-md; }
.header-title { font-size: $font-xl; font-weight: 700; color: #fff; display: block; }
.header-desc { font-size: $font-sm; color: rgba(255,255,255,0.85); display: block; margin-top: $spacing-xs; }

/* ── 列表 ── */
.list-section { padding: $spacing-lg; }
.list-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 28rpx 32rpx; background: $color-bg-card;
  border-radius: $radius-lg; margin-bottom: $spacing-md;
  box-shadow: $shadow-md; cursor: pointer;
}
.list-left { display: flex; align-items: center; gap: 24rpx; }
.cat-dot {
  width: 16rpx; height: 16rpx; border-radius: 50%;
  background: $color-text-disabled;
  &.custom { background: $color-primary; box-shadow: 0 0 8rpx rgba(79,70,229,0.4); }
}
.list-info { display: flex; flex-direction: column; }
.list-name { font-size: $font-base; font-weight: 500; }
.list-status { font-size: $font-xs; color: $color-text-tertiary; &.custom { color: $color-primary; } }
.list-arrow { font-size: 28rpx; color: $color-text-disabled; }
</style>
