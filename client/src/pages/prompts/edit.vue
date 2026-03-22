<template>
  <view class="page">
    <view class="edit-body">
      <text class="edit-hint">告诉 AI 你希望怎么总结「{{ catLabel }}」类录音</text>
      <textarea class="edit-textarea" v-model="promptText"
                placeholder="例如：重点列出行动项和负责人，用表格形式"
                :maxlength="-1" auto-height :adjust-position="true" />
    </view>

    <view class="edit-actions">
      <button class="btn-primary" @click="save">保存</button>
      <button v-if="isCustom" class="btn-link" @click="reset">恢复平台默认</button>
    </view>
  </view>
</template>

<script setup>
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { promptApi } from '@/api'

const category = ref('')
const catLabel = ref('')
const promptText = ref('')
const isCustom = ref(false)
let customId = null

onLoad(async (query) => {
  category.value = query.cat || '_default'
  catLabel.value = category.value === '_default' ? '通用' : category.value
  uni.setNavigationBarTitle({ title: catLabel.value + ' · 总结方式' })

  try {
    const all = await promptApi.list()
    const custom = all.find(p => p.category === category.value)
    if (custom) {
      promptText.value = custom.prompt
      isCustom.value = true
      customId = custom.id
    } else {
      const builtin = await promptApi.builtin(category.value)
      promptText.value = builtin.prompt || ''
    }
  } catch (e) {}
})

async function save() {
  const text = promptText.value.trim()
  if (!text) { uni.showToast({ title: '请输入内容', icon: 'none' }); return }
  await promptApi.save(category.value, text)
  uni.showToast({ title: '已保存', icon: 'success' })
  setTimeout(() => uni.navigateBack(), 800)
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

.edit-body { padding: $spacing-lg; }
.edit-hint { font-size: $font-sm; color: $color-text-tertiary; display: block; margin-bottom: $spacing-lg; }
.edit-textarea {
  width: 100%; min-height: 400rpx; padding: $spacing-lg;
  background: $color-bg-card; border: 2rpx solid $color-border;
  border-radius: $radius-lg; font-size: $font-base; color: $color-text-primary;
  line-height: 1.8;
}

.edit-actions { padding: 0 $spacing-lg; }
.btn-primary {
  width: 100%; background: $color-primary-gradient; color: #fff; border: none;
  border-radius: $radius-full; height: 88rpx; font-size: $font-lg; font-weight: 600;
  box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.3);
}
.btn-link {
  width: 100%; background: none; border: none;
  color: $color-text-tertiary; font-size: $font-sm; margin-top: $spacing-lg;
}
</style>
