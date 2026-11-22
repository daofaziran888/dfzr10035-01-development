/** 纯前端数据层的公共类型：与全栈版后端返回的结构保持一致，换回后端时页面不用改。 */

export type EntryRow = {
  id: number
  status: string
  pending: boolean
  abnormal: boolean
  [field: string]: string | number | boolean
}

export type ModuleMeta = {
  key: string
  name: string
  entity: string
  desc: string
  fields: string[]
  statuses: string[]
  actions: string[]
  actionTargets: Record<string, string>
  metrics: string[]
}

export type PageResult = {
  items: EntryRow[]
  total: number
  page: number
  size: number
}

export type ActionResult = {
  ok: boolean
  message: string
}

export type OverviewResult = {
  cards: { label: string; value: number }[]
  modules: { name: string; created: number; pending: number; abnormal: number }[]
}

/* ---- 批次交接分布视图 ---- */

export type HandoverEvent = {
  id: number
  请求编号: string
  时间: string
  变化: string
  依据回执: string
  说明: string
}

export type ReceiptItem = {
  id: number
  回执编号: string
  请求编号: string
  批次编号: string
  来源: string
  尝试序号: number
  结果: string
  错误信息: string
  到达时间: string
  关联重放任务: string
  到达状态: string
}

export type HandoverRequest = {
  id: number
  请求编号: string
  批次编号: string
  关联端点: string
  请求参数: string
  当前结果: string
  尝试次数: number
  在途回执数: number
  进入补采: boolean
  处置方式: string
  处置回执: string
  确认回执: string
  重放任务编号: string
}

export type HandoverDistribution = {
  batch: EntryRow
  stats: Record<string, number>
  requests: HandoverRequest[]
  incomplete: HandoverRequest[]
  same_params: string[][]
  recent_events: HandoverEvent[]
  观察时间: string
}

export type HandoverSummaryItem = {
  batch_id: number
  批次编号: string
  关联端点: string
  批次状态: string
  逻辑请求数: number
  成功: number
  未收齐: number
  未收齐请求: string[]
}

export type HandoverRequestDetail = {
  request: HandoverRequest
  receipts: ReceiptItem[]
  events: HandoverEvent[]
}

export type SyncChange = {
  请求编号: string
  旧状态: string
  新状态: string
  新到回执: string[]
}

export type RoundTake = {
  任务编号: string
  失败端点: string
  队列状态: string
  关联请求编号: string
  交接状态: string
}

export type RoundSkip = RoundTake & {
  依据回执: string
  原因: string
}

export type RoundView = {
  取单时间: string
  本轮可取: RoundTake[]
  本轮跳过: RoundSkip[]
  已确认请求: { 请求编号: string; 批次编号: string; 当前结果: string; 确认回执: string }[]
}
