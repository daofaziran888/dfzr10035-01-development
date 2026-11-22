<template>
  <section class="page" data-module="batch-handover">
    <header class="page-head">
      <div>
        <h2>批次请求结果分布视图（交接）</h2>
        <p class="page-desc">
          批次调用记录与重放回执已关联到同一条逻辑请求：统计按请求编号去重，每条请求的各次尝试只占一个位置；
          参数相同的独立请求仍分别计入。展开请求可查看尝试明细并同步新到回执。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/request_batch">返回请求批次</RouterLink>
      </div>
    </header>

    <h3 class="section-title">各批次交接概况（按批次列出尚未收齐的请求）</h3>
    <table class="data-table">
      <thead>
        <tr>
          <th>批次编号</th><th>关联端点</th><th>批次状态</th>
          <th>逻辑请求数</th><th>成功</th><th>未收齐</th><th>未收齐请求</th><th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in summary"
          :key="item.batch_id"
          :data-testid="`summary-${item.批次编号}`"
          :class="{ 'active-batch': item.batch_id === selectedBatchId }"
        >
          <td>{{ item.批次编号 }}</td>
          <td>{{ item.关联端点 }}</td>
          <td>{{ item.批次状态 }}</td>
          <td>{{ item.逻辑请求数 }}</td>
          <td>{{ item.成功 }}</td>
          <td>{{ item.未收齐 }}</td>
          <td>{{ item.未收齐请求.join('、') || '—' }}</td>
          <td class="row-actions">
            <button class="link" type="button" :data-testid="`select-${item.批次编号}`" @click="selectBatch(item.batch_id)">
              查看分布
            </button>
          </td>
        </tr>
        <tr v-if="!summary.length">
          <td colspan="8" class="empty-state">暂无批次交接数据</td>
        </tr>
      </tbody>
    </table>

    <template v-if="distribution">
      <h3 class="section-title">
        批次 {{ distribution.batch.批次编号 }} 结果分布
        <span class="observe-time">本次观察：{{ distribution.观察时间 }}</span>
      </h3>

      <div class="stat-row">
        <article v-for="item in statCards" :key="item.label" class="stat-card">
          <span class="stat-label">{{ item.label }}</span>
          <strong class="stat-value">{{ item.value }}</strong>
        </article>
      </div>

      <p v-if="distribution.same_params.length" class="hint-text" data-testid="same-params">
        参数相同的独立请求：
        <span v-for="(group, index) in distribution.same_params" :key="index">
          {{ group.join(' 与 ') }}（参数一致，为独立请求，分别计数）
        </span>
      </p>

      <div class="page-actions toolbar">
        <button class="btn primary" data-testid="sync-batch" type="button" @click="syncBatch">同步本批回执</button>
        <button class="btn" data-testid="dispatch-batch" type="button" @click="dispatchBatch">派发全部未收齐</button>
        <button class="btn ghost" data-testid="reload" type="button" @click="reloadAll">刷新观察</button>
      </div>

      <div v-if="notices.length" class="notice-box" data-testid="change-notices">
        <p v-for="(notice, index) in notices" :key="index" class="notice-item">{{ notice }}</p>
      </div>
      <p v-if="actionMessage" class="hint-text" data-testid="action-message">{{ actionMessage }}</p>

      <h4 class="section-title">请求清单（每条逻辑请求一行，多次尝试只计一次）</h4>
      <table class="data-table">
        <thead>
          <tr>
            <th>请求编号</th><th>请求参数</th><th>当前结果</th><th>尝试次数</th>
            <th>进入补采</th><th>处置方式 / 所用回执</th><th>确认回执</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="row in distribution.requests" :key="row.id">
            <tr :data-testid="`req-${row.请求编号}`" :data-state="row.当前结果">
              <td>{{ row.请求编号 }}</td>
              <td class="param-cell">{{ row.请求参数 }}</td>
              <td>
                {{ row.当前结果 }}
                <span v-if="row.在途回执数" class="inflight-badge">回执在途×{{ row.在途回执数 }}</span>
              </td>
              <td>{{ row.尝试次数 }}</td>
              <td>{{ row.进入补采 ? '是' : '否' }}</td>
              <td>
                <template v-if="row.处置方式">{{ row.处置方式 }} / {{ row.处置回执 || '无回执' }}</template>
                <template v-else>—</template>
              </td>
              <td>{{ row.确认回执 || '—' }}</td>
              <td class="row-actions">
                <button
                  class="link"
                  type="button"
                  :data-testid="`expand-${row.请求编号}`"
                  @click="toggleExpand(row)"
                >
                  {{ expandedId === row.id ? '收起' : '展开' }}
                </button>
                <button
                  class="link"
                  type="button"
                  :data-testid="`dispatch-${row.请求编号}`"
                  @click="dispatchOne(row)"
                >
                  派发补采
                </button>
                <button
                  class="link"
                  type="button"
                  :data-testid="`skip-${row.请求编号}`"
                  @click="skipOne(row)"
                >
                  跳过补采
                </button>
              </td>
            </tr>
            <tr v-if="expandedId === row.id" class="detail-row" :data-testid="`detail-${row.请求编号}`">
              <td colspan="8">
                <div v-if="detailLoading" class="empty-state">尝试明细加载中…</div>
                <template v-else-if="detail">
                  <h5>尝试明细（每份回执一次尝试）</h5>
                  <table class="data-table sub-table">
                    <thead>
                      <tr>
                        <th>回执编号</th><th>来源</th><th>尝试序号</th><th>结果</th>
                        <th>错误信息</th><th>到达时间</th><th>关联重放任务</th><th>到达状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="receipt in detail.receipts" :key="receipt.回执编号">
                        <td>{{ receipt.回执编号 }}</td>
                        <td>{{ receipt.来源 }}</td>
                        <td>{{ receipt.尝试序号 }}</td>
                        <td>{{ receipt.结果 }}</td>
                        <td>{{ receipt.错误信息 || '—' }}</td>
                        <td>{{ receipt.到达时间 || '—' }}</td>
                        <td>{{ receipt.关联重放任务 || '—' }}</td>
                        <td>{{ receipt.到达状态 }}</td>
                      </tr>
                      <tr v-if="!detail.receipts.length">
                        <td colspan="8" class="empty-state">暂无回执</td>
                      </tr>
                    </tbody>
                  </table>
                  <h5>状态变迁（前后两次观察为何不同，看这里）</h5>
                  <table class="data-table sub-table">
                    <thead>
                      <tr><th>时间</th><th>变化</th><th>依据回执</th><th>说明</th></tr>
                    </thead>
                    <tbody>
                      <tr v-for="event in detail.events" :key="event.id">
                        <td>{{ event.时间 }}</td>
                        <td>{{ event.变化 }}</td>
                        <td>{{ event.依据回执 || '—' }}</td>
                        <td>{{ event.说明 }}</td>
                      </tr>
                      <tr v-if="!detail.events.length">
                        <td colspan="4" class="empty-state">暂无变迁记录</td>
                      </tr>
                    </tbody>
                  </table>
                </template>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <h4 class="section-title">尚未收齐（{{ distribution.incomplete.length }} 条）</h4>
      <p v-if="distribution.incomplete.length" class="hint-text" data-testid="incomplete-list">
        {{ distribution.incomplete.map((item) => `${item.请求编号}（${item.当前结果}）`).join('、') }}
      </p>
      <p v-else class="hint-text" data-testid="incomplete-list">本批请求已全部收齐。</p>

      <h4 class="section-title">最近交接变迁</h4>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>请求编号</th><th>变化</th><th>依据回执</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="event in distribution.recent_events" :key="event.id">
            <td>{{ event.时间 }}</td>
            <td>{{ event.请求编号 }}</td>
            <td>{{ event.变化 }}</td>
            <td>{{ event.依据回执 || '—' }}</td>
            <td>{{ event.说明 }}</td>
          </tr>
        </tbody>
      </table>
    </template>

    <h3 class="section-title">
      重放队列 · 本轮取单
      <span v-if="round" class="observe-time">取单时间：{{ round.取单时间 }}</span>
    </h3>
    <template v-if="round">
      <h4 class="section-title">本轮可取（{{ round.本轮可取.length }}）</h4>
      <table class="data-table">
        <thead>
          <tr><th>任务编号</th><th>失败端点</th><th>队列状态</th><th>关联请求</th><th>交接状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in round.本轮可取" :key="task.任务编号">
            <td>{{ task.任务编号 }}</td>
            <td>{{ task.失败端点 }}</td>
            <td>{{ task.队列状态 }}</td>
            <td>{{ task.关联请求编号 }}</td>
            <td>{{ task.交接状态 }}</td>
          </tr>
          <tr v-if="!round.本轮可取.length">
            <td colspan="5" class="empty-state">本轮没有可取单的任务</td>
          </tr>
        </tbody>
      </table>

      <h4 class="section-title">本轮跳过（交接已确认，{{ round.本轮跳过.length }}）</h4>
      <table class="data-table">
        <thead>
          <tr><th>任务编号</th><th>关联请求</th><th>交接状态</th><th>依据回执</th><th>原因</th></tr>
        </thead>
        <tbody>
          <tr v-for="task in round.本轮跳过" :key="task.任务编号" data-testid="round-skip">
            <td>{{ task.任务编号 }}</td>
            <td>{{ task.关联请求编号 }}</td>
            <td>{{ task.交接状态 }}</td>
            <td>{{ task.依据回执 || '—' }}</td>
            <td>{{ task.原因 }}</td>
          </tr>
          <tr v-if="!round.本轮跳过.length">
            <td colspan="5" class="empty-state">本轮没有被交接结果跳过的任务</td>
          </tr>
        </tbody>
      </table>

      <h4 class="section-title">已确认请求（补采中断后续做时在这里核对）</h4>
      <table class="data-table">
        <thead>
          <tr><th>请求编号</th><th>批次编号</th><th>当前结果</th><th>确认回执</th></tr>
        </thead>
        <tbody>
          <tr v-for="req in round.已确认请求" :key="req.请求编号">
            <td>{{ req.请求编号 }}</td>
            <td>{{ req.批次编号 }}</td>
            <td>{{ req.当前结果 }}</td>
            <td>{{ req.确认回执 || '—' }}</td>
          </tr>
          <tr v-if="!round.已确认请求.length">
            <td colspan="4" class="empty-state">暂无已确认请求</td>
          </tr>
        </tbody>
      </table>
    </template>

    <footer class="page-foot">
      <span>交接统计每个逻辑请求只记一次；同一请求在原批次与重放中的多份回执都挂在它名下。</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  dispatchHandoverBatch,
  dispatchHandoverRequest,
  loadHandoverDistribution,
  loadHandoverRequest,
  loadHandoverSummary,
  loadRetryRound,
  skipHandoverRequest,
  syncHandoverBatch,
  syncHandoverRequest,
} from '@/api/backend-service'
import type {
  HandoverDistribution,
  HandoverRequest,
  HandoverRequestDetail,
  HandoverSummaryItem,
  RoundView,
  SyncChange,
} from '@/data/types'

const summary = ref<HandoverSummaryItem[]>([])
const distribution = ref<HandoverDistribution | null>(null)
const round = ref<RoundView | null>(null)
const selectedBatchId = ref(0)
const expandedId = ref<number | null>(null)
const detail = ref<HandoverRequestDetail | null>(null)
const detailLoading = ref(false)
const notices = ref<string[]>([])
const actionMessage = ref('')
const errorMessage = ref('')

const statCards = computed(() => {
  const stats = distribution.value?.stats ?? {}
  return [
    { label: '逻辑请求数', value: stats['逻辑请求数'] ?? 0 },
    { label: '成功', value: stats['成功'] ?? 0 },
    { label: '补采中', value: stats['补采中'] ?? 0 },
    { label: '失败待补采', value: stats['失败待补采'] ?? 0 },
    { label: '待回执', value: stats['待回执'] ?? 0 },
    { label: '已跳过', value: stats['已跳过'] ?? 0 },
    { label: '未收齐', value: stats['未收齐'] ?? 0 },
  ]
})

function pushChanges(changes: SyncChange[]) {
  for (const change of changes) {
    notices.value.unshift(
      `${change.请求编号}：${change.旧状态} → ${change.新状态}（新到回执 ${change.新到回执.join('、')}），` +
        '本次观察与上次不同即由此引起',
    )
  }
}

async function reloadAll() {
  errorMessage.value = ''
  try {
    const tasks: Promise<void>[] = [
      loadHandoverSummary().then((items) => {
        summary.value = items
      }),
      loadRetryRound().then((view) => {
        round.value = view
      }),
    ]
    if (selectedBatchId.value) {
      tasks.push(
        loadHandoverDistribution(selectedBatchId.value).then((view) => {
          distribution.value = view
        }),
      )
    }
    await Promise.all(tasks)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '交接视图读取失败'
  }
}

async function selectBatch(batchId: number) {
  selectedBatchId.value = batchId
  expandedId.value = null
  detail.value = null
  await reloadAll()
}

async function toggleExpand(row: HandoverRequest) {
  if (expandedId.value === row.id) {
    expandedId.value = null
    detail.value = null
    return
  }
  expandedId.value = row.id
  detail.value = null
  detailLoading.value = true
  actionMessage.value = ''
  try {
    // 展开时先同步该请求的在途回执：值班员查看中的一条请求可能此刻才成功
    const syncResult = await syncHandoverRequest(row.id)
    if (syncResult.changes.length) {
      pushChanges(syncResult.changes)
      await reloadAll()
    }
    detail.value = await loadHandoverRequest(row.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '尝试明细读取失败'
  } finally {
    detailLoading.value = false
  }
}

async function syncBatch() {
  if (!selectedBatchId.value) return
  actionMessage.value = ''
  try {
    const result = await syncHandoverBatch(selectedBatchId.value)
    if (result.changes.length) {
      pushChanges(result.changes)
    } else {
      actionMessage.value = '本批没有新到回执，观察结果不变'
    }
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '同步回执失败'
  }
}

async function dispatchOne(row: HandoverRequest) {
  actionMessage.value = ''
  try {
    const result = await dispatchHandoverRequest(row.id)
    actionMessage.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '派发补采失败'
  }
}

async function dispatchBatch() {
  if (!selectedBatchId.value) return
  actionMessage.value = ''
  try {
    const result = await dispatchHandoverBatch(selectedBatchId.value)
    actionMessage.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '批量派发失败'
  }
}

async function skipOne(row: HandoverRequest) {
  actionMessage.value = ''
  try {
    const result = await skipHandoverRequest(row.id)
    actionMessage.value = result.message
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '跳过补采失败'
  }
}

onMounted(async () => {
  await reloadAll()
  // 默认选中还有未收齐请求的批次，交接时先看没办完的那批
  const pending = summary.value.find((item) => item.未收齐 > 0) ?? summary.value[0]
  if (pending) await selectBatch(pending.batch_id)
})
</script>

<style scoped>
.section-title {
  margin: 16px 0 8px;
  font-size: 14px;
}
.observe-time {
  margin-left: 10px;
  font-size: 12px;
  color: var(--muted);
  font-weight: normal;
}
.toolbar {
  margin: 8px 0;
  display: flex;
  gap: 8px;
}
.hint-text {
  color: var(--muted);
  font-size: 13px;
}
.notice-box {
  border: 1px solid #f0c36d;
  background: #fff8e6;
  border-radius: 8px;
  padding: 8px 12px;
  margin: 8px 0;
}
.notice-item {
  margin: 4px 0;
  font-size: 13px;
}
.param-cell {
  font-family: monospace;
  font-size: 12px;
  max-width: 260px;
  word-break: break-all;
}
.inflight-badge {
  margin-left: 6px;
  font-size: 11px;
  color: #b45309;
  border: 1px solid #f0c36d;
  border-radius: 4px;
  padding: 1px 4px;
}
.detail-row > td {
  background: #fafbfc;
}
.sub-table {
  margin: 8px 0 12px;
}
.active-batch td {
  background: #eef4ff;
}
h5 {
  margin: 8px 0 4px;
  font-size: 13px;
}
</style>
