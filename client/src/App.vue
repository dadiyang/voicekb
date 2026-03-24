<script setup>
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  console.log('App Launch')
})
</script>

<style lang="scss">
@import './static/styles/common.scss';
/* tabler-icons 通过 index.html link 标签引入（绕过 vite CSS 处理，保留 unicode） */

/* #ifdef H5 */
/* 防止 iOS Safari 在 input 聚焦时自动缩放页面（小程序无此问题） */
input, textarea {
  font-size: 16px !important;
}
/* 禁止 Chrome 下拉刷新（pull-to-refresh），防止滚动列表时误触 */
html, body {
  overscroll-behavior-y: contain;
}
/* #endif */
</style>
