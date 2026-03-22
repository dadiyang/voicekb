<template>
  <view class="page">
    <view class="edit-header">
      <text class="edit-cat">{{ catLabel }}</text>
      <text class="edit-status" :class="{custom: isCustom}">{{ isCustom ? '已自定义' : '平台默认' }}</text>
    </view>

    <view class="edit-body">
      <text class="edit-hint">告诉 AI 你希望怎么总结这类录音。对话内容会自动附加。</text>
      <textarea class="edit-textarea" v-model="promptText"
                :placeholder="'例如：重点列出行动项和负责人，用表格形式'"
                :maxlength="-1" auto-height :adjust-position="true" />
    </view>

    <view class="edit-actions">
      <button class="btn-primary" @click="save">保存</button>
      <button v-if="isCustom" class="btn-outline" @click="reset">恢复平台默认</button>
    </view>
  </view>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { promptApi } from '@/api'

const category = ref('')
const catLabel = ref('')
const promptText = ref('')
const isCustom = ref(false)
let customId = null

onLoad(async (query) => {
  category.value = query.cat || '_default'
  catLabel.value = category.value === '_default' ? '通用（默认）' : category.value

  try {
    // 加载自定义 prompt
    const all = await promptApi.list()
    const custom = all.find(p => p.category === category.value)
    if (custom) {
      promptText.value = custom.prompt
      isCustom.value = true
      customId = custom.id
    } else {
      // 加载内置默认
      const builtin = await promptApi.builtin(category.value)
      promptText.value = builtin.prompt || ''
    }
  } catch (e) {}
})

async function save() {
  const text = promptText.value.trim()
  if (!text) { uni.showToast({ title: '请输入内容', icon: 'none' }); return }
  try {
    await promptApi.save(category.value, text)
    isCustom.value = true
    uni.showToast({ title: '已保存', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 800)
  } catch (e) {
    uni.showToast({ title: '保存失败', icon: 'none' })
  }
}

async function reset() {
  if (customId) {
    await promptApi.delete(customId)
    uni.showToast({ title: '已恢复默认', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 800)
  }
}
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; }

.edit-header {
  padding: $spacing-xl $spacing-lg $spacing-md;
}
.edit-cat { font-size: $font-xl; font-weight: 700; display: block; }
.edit-status {
  font-size: $font-xs; color: $color-text-tertiary; margin-top: 4rpx; display: block;
  &.custom { color: $color-primary; }
}

.edit-body { padding: 0 $spacing-lg; }
.edit-hint { font-size: $font-sm; color: $color-text-tertiary; display: block; margin-bottom: $spacing-md; }
.edit-textarea {
  width: 100%; min-height: 300rpx; padding: $spacing-lg;
  background: $color-bg-card; border: 2rpx solid $color-border;
  border-radius: $radius-lg; font-size: $font-base; color: $color-text-primary;
  line-height: 1.8;
}

.edit-actions { padding: $spacing-xl $spacing-lg; display: flex; flex-direction: column; gap: $spacing-md; }
.btn-primary {
  background: $color-primary-gradient; color: #fff; border: none;
  border-radius: $radius-full; height: 88rpx; font-size: $font-lg; font-weight: 600;
  box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.3);
}
.btn-outline {
  background: $color-bg-card; color: $color-text-secondary;
  border: 2rpx solid $color-border; border-radius: $radius-full;
  height: 88rpx; font-size: $font-base;
}
</style>
