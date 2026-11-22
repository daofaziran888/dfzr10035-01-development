import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type {
  ActionResult,
  EntryRow,
  HandoverDistribution,
  HandoverRequestDetail,
  HandoverSummaryItem,
  OverviewResult,
  PageResult,
  RoundView,
  SyncChange,
} from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

/* ---- 批次交接分布视图 ---- */

export async function loadHandoverSummary(): Promise<HandoverSummaryItem[]> {
  const response = await request('/api/request_batch/handover/summary')
  if (!response.ok) throw new Error('批次交接概况读取失败')
  const payload = (await response.json()) as { items: HandoverSummaryItem[] }
  return payload.items
}

export async function loadHandoverDistribution(batchId: number): Promise<HandoverDistribution> {
  const response = await request(`/api/request_batch/${batchId}/handover`)
  if (!response.ok) throw new Error('批次请求结果分布读取失败')
  return await response.json()
}

export async function loadHandoverRequest(requestId: number): Promise<HandoverRequestDetail> {
  const response = await request(`/api/request_batch/requests/${requestId}`)
  if (!response.ok) throw new Error('请求尝试明细读取失败')
  return await response.json()
}

export async function syncHandoverBatch(
  batchId: number,
): Promise<{ ok: boolean; message: string; changes: SyncChange[] }> {
  const response = await request(`/api/request_batch/${batchId}/sync`, { method: 'POST' })
  return await response.json()
}

export async function syncHandoverRequest(
  requestId: number,
): Promise<{ ok: boolean; message: string; changes: SyncChange[] }> {
  const response = await request(`/api/request_batch/requests/${requestId}/sync`, { method: 'POST' })
  return await response.json()
}

export async function dispatchHandoverRequest(
  requestId: number,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/request_batch/requests/${requestId}/dispatch`, { method: 'POST' })
  return await response.json()
}

export async function dispatchHandoverBatch(
  batchId: number,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/request_batch/${batchId}/dispatch`, { method: 'POST' })
  return await response.json()
}

export async function skipHandoverRequest(
  requestId: number,
): Promise<{ ok: boolean; message: string }> {
  const response = await request(`/api/request_batch/requests/${requestId}/skip`, {
    method: 'POST',
    body: JSON.stringify({}),
  })
  return await response.json()
}

export async function loadRetryRound(): Promise<RoundView> {
  const response = await request('/api/retry_queue/round/current')
  if (!response.ok) throw new Error('重放队列本轮取单读取失败')
  return await response.json()
}
