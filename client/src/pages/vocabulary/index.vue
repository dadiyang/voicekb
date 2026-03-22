<template>
  <view class="page">
    <!-- Tab 切换：人名 / 术语 -->
    <view class="tab-header">
      <view class="tab-btn" :class="{active: tab === 'person'}" @click="tab = 'person'">人名</view>
      <view class="tab-btn" :class="{active: tab === 'term'}" @click="tab = 'term'">术语</view>
    </view>

    <view class="hint-text">添加后新录音会自动使用，旧录音可点「重新识别」更新</view>

    <!-- 添加输入框 -->
    <view class="add-row">
      <input class="add-input" v-model="newTerm"
             :placeholder="tab === 'person' ? '输入人名（如：周神、张三）' : '输入术语（如：K8s、微服务）'"
             confirm-type="done" @confirm="addTerm" />
      <view class="add-btn" @click="addTerm">
        <text class="ti ti-plus add-icon"></text>
      </view>
    </view>

    <!-- 列表 -->
    <view v-if="filtered.length === 0" class="empty-hint">
      <text>还没有添加{{ tab === 'person' ? '人名' : '术语' }}</text>
    </view>

    <view v-else class="term-list">
      <view class="term-item" v-for="v in filtered" :key="v.id">
        <text class="term-text">{{ v.term }}</text>
        <text class="ti ti-x delete-btn" @click="deleteTerm(v)"></text>
      </view>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { vocabApi } from '@/api'

const tab = ref('person')
const vocab = ref([])
const newTerm = ref('')

const filtered = computed(() => vocab.value.filter(v => v.category === tab.value))

async function load() {
  try { vocab.value = await vocabApi.list() } catch (e) {}
}

async function addTerm() {
  const t = newTerm.value.trim()
  if (!t) return
  await vocabApi.add(t, tab.value)
  newTerm.value = ''
  uni.showToast({ title: `已添加「${t}」`, icon: 'success' })
  load()
}

function deleteTerm(v) {
  uni.showModal({
    title: '删除',
    content: `确定删除「${v.term}」？`,
    cancelText: '取消',
    confirmText: '删除',
    success: async (res) => {
      if (res.confirm) {
        await vocabApi.delete(v.id)
        uni.showToast({ title: '已删除', icon: 'success' })
        load()
      }
    },
  })
}

onMounted(load)
onShow(load)
</script>

<style lang="scss" scoped>
.page { min-height: 100vh; background: $color-bg-page; padding: $spacing-lg; }

.tab-header {
  display: flex; gap: $spacing-md; margin-bottom: $spacing-md;
}
.tab-btn {
  flex: 1; height: 72rpx; line-height: 72rpx; text-align: center;
  border-radius: $radius-lg; font-size: $font-base; font-weight: 500;
  background: $color-bg-card; color: $color-text-secondary;
  box-shadow: $shadow-sm;
  &.active { background: $color-primary; color: #fff; box-shadow: 0 4rpx 16rpx rgba(79,70,229,0.25); }
}

.hint-text { font-size: $font-xs; color: $color-text-tertiary; margin-bottom: $spacing-lg; }

.add-row { display: flex; gap: $spacing-md; margin-bottom: $spacing-xl; }
.add-input {
  flex: 1; height: 80rpx; padding: 0 $spacing-lg;
  background: $color-bg-card; border: 3rpx solid $color-border;
  border-radius: $radius-lg; font-size: $font-base; color: $color-text-primary;
}
.add-btn {
  width: 80rpx; height: 80rpx; border-radius: $radius-lg;
  background: $color-primary; color: #fff;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4rpx 12rpx rgba(79,70,229,0.3);
}
.add-icon { font-size: 36rpx; }

.empty-hint { text-align: center; padding: $spacing-xxl; color: $color-text-tertiary; font-size: $font-sm; }

.term-list { display: flex; flex-direction: column; gap: $spacing-sm; }
.term-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 20rpx $spacing-lg; background: $color-bg-card;
  border-radius: $radius-lg; box-shadow: $shadow-sm;
}
.term-text { font-size: $font-base; font-weight: 500; }
.delete-btn { font-size: 28rpx; color: $color-text-disabled; padding: 8rpx; }
</style>
