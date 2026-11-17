import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/scrapeapi'
const columns = [
  "API编号",
  "API名称",
  "请求路径",
  "数据源绑定",
  "参数模板",
  "缓存策略",
  "速率限制",
  "返回格式"
]
const actions = [
  "提交API评审",
  "上线API",
  "下线API"
]
const statuses = [
  "草稿",
  "API评审中",
  "已上线",
  "已下线"
]

type Row = Record<string, string | number | null>
type ExecuteResult = {
  ok: boolean
  message: string
  record: Row | null
  versions: Row[]
}

export default function ScrapeapiView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [responses, setResponses] = useState<Row[]>([])
  const [cacheRows, setCacheRows] = useState<Row[]>([])
  const [windows, setWindows] = useState<Row[]>([])
  const [errorMessage, setErrorMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [executeTarget, setExecuteTarget] = useState<Row | null>(null)
  const [paramsText, setParamsText] = useState('{}')
  const [idemKey, setIdemKey] = useState('')
  const [executeResult, setExecuteResult] = useState<ExecuteResult | null>(null)
  const filterFields = useMemo(() => columns.slice(0, 3), [])

  const stats = useMemo(() => [
    { label: 'API定义总数', value: total },
    { label: '已上线API', value: rows.filter((row) => row.status === '已上线').length },
    { label: '缓存快照数', value: cacheRows.length },
    { label: '响应记录数', value: responses.length },
  ], [rows, total, cacheRows, responses])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const [listRes, respRes, cacheRes, winRes] = await Promise.all([
        request(`${ENDPOINT}?${query}`),
        request(`${ENDPOINT}/responses?size=50`),
        request(`${ENDPOINT}/cache?size=50`),
        request(`${ENDPOINT}/windows`),
      ])
      if (!listRes.ok) {
        throw new Error('API定义列表读取失败')
      }
      const payload = await listRes.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
      setResponses((await respRes.json()).items ?? [])
      setCacheRows((await cacheRes.json()).items ?? [])
      setWindows((await winRes.json()).items ?? [])
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '采集API列表读取失败')
    }
  }, [filters])

  useEffect(() => {
    void reload()
  }, [reload])

  async function runAction(action: string, row: Row) {
    setErrorMessage('')
    setNotice('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/actions`, {
        method: 'POST',
        body: JSON.stringify({ action }),
      })
      const payload = await response.json()
      if (!response.ok || !payload.ok) {
        throw new Error(payload.message ?? '采集API动作未生效，请稍后重试')
      }
      setNotice(payload.message ?? '动作已执行')
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '采集API操作失败')
    }
  }

  function openExecute(row: Row) {
    setExecuteTarget(row)
    setExecuteResult(null)
    setIdemKey('')
    const template = String(row['参数模板'] ?? '').split(',').map((item) => item.trim()).filter(Boolean)
    const preset: Record<string, string> = {}
    template.forEach((field, index) => { preset[field] = index === 0 ? 'demo' : '1' })
    setParamsText(JSON.stringify(preset, null, 2))
  }

  async function runExecute() {
    if (!executeTarget) {
      return
    }
    setErrorMessage('')
    setNotice('')
    let params: Record<string, unknown>
    try {
      params = JSON.parse(paramsText || '{}')
    } catch {
      setErrorMessage('请求参数不是合法 JSON，请检查后再执行')
      return
    }
    try {
      const response = await request(`${ENDPOINT}/${executeTarget.id}/execute`, {
        method: 'POST',
        body: JSON.stringify({ params, idempotency_key: idemKey || undefined }),
      })
      const payload = await response.json()
      setExecuteResult(payload)
      setNotice(payload.message ?? '')
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '采集API执行失败')
    }
  }

  return (
    <section className="page" data-module="scrapeapi">
      <header className="page-head">
        <div>
          <h2>采集API管理</h2>
          <p className="page-desc">定义对外暴露的数据采集API接口，将采集结果以标准化接口形式输出。</p>
        </div>
        <div className="page-actions">
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出采集API清单
          </button>
        </div>
      </header>

      <div className="stat-row">
        {stats.map((item) => (
          <article key={item.label} className="stat-card">
            <span className="stat-label">{item.label}</span>
            <strong className="stat-value">{item.value}</strong>
          </article>
        ))}
      </div>

      <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void reload() }}>
        {filterFields.map((field) => (
          <label key={field} className="filter-item">
            <span>{field}</span>
            <input
              value={filters[field] ?? ''}
              placeholder={`按${field}检索`}
              onChange={(event) => setFilters((prev) => ({ ...prev, [field]: event.target.value }))}
            />
          </label>
        ))}
        <button className="btn" type="submit">查询</button>
        <button className="btn ghost" type="button" onClick={() => setFilters({})}>重置条件</button>
      </form>

      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
            <th>可执行动作</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={String(row.id)}>
              {columns.map((column) => <td key={column}>{row[column] ?? '—'}</td>)}
              <td className="row-actions">
                {actions.map((action) => (
                  <button key={action} className="link" type="button" onClick={() => void runAction(action, row)}>
                    {action}
                  </button>
                ))}
                <button className="link" type="button" onClick={() => openExecute(row)}>
                  执行API
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无采集API数据，可先登记API定义</td>
            </tr>
          )}
        </tbody>
      </table>

      {executeTarget && (
        <section className="page" data-module="scrapeapi-execute">
          <header className="page-head">
            <div>
              <h3>执行API：{executeTarget['API名称']}（{executeTarget['API编号']}）</h3>
              <p className="page-desc">
                缓存键 = 请求路径 + 参数指纹 + 数据源绑定 + 数据代际；同一幂等键重复提交只保留一次，不重复扣减额度。
              </p>
            </div>
            <div className="page-actions">
              <button className="btn ghost" type="button" onClick={() => setExecuteTarget(null)}>关闭</button>
            </div>
          </header>
          <form className="filter-bar" onSubmit={(event) => { event.preventDefault(); void runExecute() }}>
            <label className="filter-item">
              <span>请求参数（JSON）</span>
              <textarea
                rows={4}
                cols={40}
                value={paramsText}
                onChange={(event) => setParamsText(event.target.value)}
              />
            </label>
            <label className="filter-item">
              <span>幂等键（可空，留空自动生成）</span>
              <input value={idemKey} onChange={(event) => setIdemKey(event.target.value)} placeholder="如 order-20261117-01" />
            </label>
            <button className="btn primary" type="submit">执行取数</button>
          </form>
          {executeResult?.record && (
            <table className="data-table">
              <tbody>
                <tr><th>响应编号</th><td>{executeResult.record['响应编号']}</td><th>命中来源</th><td>{executeResult.record['命中来源']}</td></tr>
                <tr><th>数据代际</th><td>{executeResult.record['数据代际']}</td><th>额度扣减</th><td>{executeResult.record['额度扣减']}（剩余 {executeResult.record['剩余额度']}）</td></tr>
                <tr><th>缓存键</th><td colSpan={3}>{executeResult.record['缓存键']}</td></tr>
                <tr><th>处理范围</th><td colSpan={3}>{executeResult.record['处理范围']}</td></tr>
                {executeResult.versions.length > 1 && (
                  <tr>
                    <th>版本结果</th>
                    <td colSpan={3}>
                      {executeResult.versions.map((item) => `${item['版本结果']}：${item['快照编号']}（代际 ${item['数据代际']}）`).join('；')}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          )}
        </section>
      )}

      <h3>响应记录（命中来源与额度消耗）</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>响应编号</th><th>API编号</th><th>命中来源</th><th>版本结果</th><th>数据代际</th>
            <th>额度扣减</th><th>剩余额度</th><th>窗口编号</th><th>快照编号</th><th>保留优先级</th><th>创建时间</th>
          </tr>
        </thead>
        <tbody>
          {responses.map((row) => (
            <tr key={String(row.id)}>
              <td>{row['响应编号']}</td>
              <td>{row['API编号']}</td>
              <td>{row['命中来源']}</td>
              <td>{row['版本结果']}</td>
              <td>{row['数据代际']}</td>
              <td>{row['额度扣减']}</td>
              <td>{row['剩余额度']}</td>
              <td>{row['窗口编号']}</td>
              <td>{row['快照编号']}</td>
              <td>{row['保留优先级']}</td>
              <td>{row['创建时间']}</td>
            </tr>
          ))}
          {responses.length === 0 && (
            <tr><td className="empty-state" colSpan={11}>暂无响应记录，执行API后在此查看命中来源</td></tr>
          )}
        </tbody>
      </table>

      <h3>缓存快照</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>快照编号</th><th>API编号</th><th>缓存键</th><th>数据代际</th>
            <th>状态</th><th>保留优先级</th><th>命中次数</th><th>过期时间</th>
          </tr>
        </thead>
        <tbody>
          {cacheRows.map((row) => (
            <tr key={String(row.id)}>
              <td>{row['快照编号']}</td>
              <td>{row['API编号']}</td>
              <td>{row['缓存键']}</td>
              <td>{row['数据代际']}</td>
              <td>{row['状态']}</td>
              <td>{row['保留优先级']}</td>
              <td>{row['命中次数']}</td>
              <td>{row['过期时间']}</td>
            </tr>
          ))}
          {cacheRows.length === 0 && (
            <tr><td className="empty-state" colSpan={8}>暂无缓存快照</td></tr>
          )}
        </tbody>
      </table>

      <h3>限流窗口</h3>
      <table className="data-table">
        <thead>
          <tr>
            <th>窗口编号</th><th>API编号</th><th>窗口起始时间</th><th>窗口时长秒</th>
            <th>额度上限</th><th>已用额度</th>
          </tr>
        </thead>
        <tbody>
          {windows.map((row) => (
            <tr key={String(row.id)}>
              <td>{row['窗口编号']}</td>
              <td>{row['API编号']}</td>
              <td>{row['窗口起始时间']}</td>
              <td>{row['窗口时长秒']}</td>
              <td>{row['额度上限']}</td>
              <td>{row['已用额度']}</td>
            </tr>
          ))}
          {windows.length === 0 && (
            <tr><td className="empty-state" colSpan={6}>暂无限流窗口计数</td></tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条采集API记录</span>
        {notice && <span>{notice}</span>}
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>
    </section>
  )
}
