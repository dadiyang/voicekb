<script setup>
import { onLaunch } from '@dcloudio/uni-app'

onLaunch(() => {
  console.log('App Launch')
})
</script>

<style lang="scss">
@import './static/styles/common.scss';
/* tabler-icons 通过 index.html link 标签引入（避免 SCSS 编译吃掉 unicode） */

/* #ifdef H5 */
/* 防止 iOS Safari 在 input 聚焦时自动缩放页面（小程序无此问题） */
input, textarea {
  font-size: 16px !important;
}
/* #endif */
</style>
