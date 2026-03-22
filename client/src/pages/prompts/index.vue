<template>
  <view class="page">
    <view class="section-title">
      <text class="section-title-text">摘要模板</text>
    </view>
    <view class="hint">点击任意类别查看或修改总结方式</view>

    <view class="card menu-item" v-for="c in allCats" :key="c" @click="editPrompt(c)">
      <view class="menu-row">
        <view class="menu-info">
          <text class="menu-name">{{ catLabel(c) }}</text>
          <text class="menu-status" :class="{custom: customMap[c]}">{{ customMap[c] ? '已自定义' : '平台默认' }}</text>
        </view>
        <text class="ti ti-chevron-right menu-arrow"></text>
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
.section-title { padding: $spacing-lg; }
.section-title-text { font-size: $font-lg; font-weight: 700; }
.hint { font-size: $font-xs; color: $color-text-tertiary; padding: 0 $spacing-lg $spacing-md; }

.menu-item { cursor: pointer; }
.menu-row { display: flex; align-items: center; gap: $spacing-lg; }
.menu-info { flex: 1; }
.menu-name { font-size: $font-base; font-weight: 500; display: block; }
.menu-status { font-size: $font-xs; color: $color-text-tertiary; &.custom { color: $color-primary; } }
.menu-arrow { font-size: 28rpx; color: $color-text-disabled; }
</style>
