import { createRouter, createWebHistory } from 'vue-router'

import BatchHandoverView from '@/views/BatchHandoverView.vue'
import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 批次交接分布视图：固定路径，放在通配模块路由之前
    { path: '/request_batch/handover', name: 'batch-handover', component: BatchHandoverView },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
