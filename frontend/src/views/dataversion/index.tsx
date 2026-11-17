import { useCallback, useEffect, useMemo, useState } from 'react'

import { request } from '@/api/client'

const ENDPOINT = '/api/dataversion'
const columns = [
  "版本编号",
  "数据源标识",
  "当前代际",
  "依赖版本",
  "部署环境",
  "数据库连接",
  "兼容状态",
  "清单条目数"
]
const actions = [
  "提交版本核对",
  "核对兼容性",
  "发布版本",
  "触发换代",
  "退役版本"
]
const statuses = [
  "草稿",
  "版本核对中",
  "已发布",
  "已退役"
]

type Row = Record<string, string | number | null>
type Manifest = {
  版本编号: string
  数据源标识: string
  当前代际: string
  清单条目数: number
  响应记录: Row[]
  数据快照: Row[]
}

export default function DataversionView() {
  const [rows, setRows] = useState<Row[]>([])
  const [total, setTotal] = useState(0)
  const [errorMessage, setErrorMessage] = useState('')
  const [notice, setNotice] = useState('')
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [manifest, setManifest] = useState<Manifest | null>(null)
  const filterFields = useMemo(() => columns.slice(0, 2), [])

  const stats = useMemo(() => [
    { label: '数据版本总数', value: total },
    { label: '已发布版本', value: rows.filter((row) => row.status === '已发布').length },
    { label: '兼容通过', value: rows.filter((row) => row['兼容状态'] === '兼容').length },
  ], [rows, total])

  const reload = useCallback(async () => {
    setErrorMessage('')
    const query = new URLSearchParams(filters).toString()
    try {
      const response = await request(`${ENDPOINT}?${query}`)
      if (!response.ok) {
        throw new Error('数据版本列表读取失败')
      }
      const payload = await response.json()
      setRows(payload.items ?? [])
      setTotal(payload.total ?? 0)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据版本列表读取失败')
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
        throw new Error(payload.message ?? '数据版本动作未生效，请稍后重试')
      }
      setNotice(payload.message ?? '动作已执行')
      await reload()
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据版本操作失败')
    }
  }

  async function openManifest(row: Row) {
    setErrorMessage('')
    try {
      const response = await request(`${ENDPOINT}/${row.id}/manifest`)
      if (!response.ok) {
        throw new Error('数据版本侧清单读取失败')
      }
      setManifest(await response.json())
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '数据版本侧清单读取失败')
    }
  }

  return (
    <section className="page" data-module="dataversion">
      <header className="page-head">
        <div>
          <h2>数据版本管理</h2>
          <p className="page-desc">维护数据源代际与换代事件，换代只失效受影响缓存，其余数据快照保持可读。</p>
        </div>
        <div className="page-actions">
          <button className="btn" type="button" onClick={() => window.open(`${ENDPOINT}/export`, '_blank')}>
            导出数据版本清单
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
                <button className="link" type="button" onClick={() => void openManifest(row)}>
                  清单
                </button>
              </td>
            </tr>
          ))}
          {rows.length === 0 && (
            <tr>
              <td className="empty-state" colSpan={columns.length + 1}>暂无数据版本数据，可先登记数据版本</td>
            </tr>
          )}
        </tbody>
      </table>

      <footer className="page-foot">
        <span>共 {total} 条数据版本记录</span>
        {notice && <span>{notice}</span>}
        {errorMessage && <span className="error-text">{errorMessage}</span>}
      </footer>

      {manifest && (
        <section className="page" data-module="dataversion-manifest">
          <header className="page-head">
            <div>
              <h2>数据版本侧清单：{manifest.数据源标识}（{manifest.版本编号}，代际 {manifest.当前代际}）</h2>
              <p className="page-desc">API响应结果与数据快照随记录一起保留，共 {manifest.清单条目数} 条响应记录。</p>
            </div>
            <div className="page-actions">
              <button className="btn ghost" type="button" onClick={() => setManifest(null)}>收起清单</button>
            </div>
          </header>

          <h3>API响应结果</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>响应编号</th><th>API编号</th><th>命中来源</th><th>版本结果</th>
                <th>数据代际</th><th>额度扣减</th><th>快照编号</th><th>保留优先级</th><th>创建时间</th>
              </tr>
            </thead>
            <tbody>
              {manifest.响应记录.map((row) => (
                <tr key={String(row.id)}>
                  <td>{row['响应编号']}</td>
                  <td>{row['API编号']}</td>
                  <td>{row['命中来源']}</td>
                  <td>{row['版本结果']}</td>
                  <td>{row['数据代际']}</td>
                  <td>{row['额度扣减']}</td>
                  <td>{row['快照编号']}</td>
                  <td>{row['保留优先级']}</td>
                  <td>{row['创建时间']}</td>
                </tr>
              ))}
              {manifest.响应记录.length === 0 && (
                <tr><td className="empty-state" colSpan={9}>该数据源暂无响应记录</td></tr>
              )}
            </tbody>
          </table>

          <h3>数据快照</h3>
          <table className="data-table">
            <thead>
              <tr>
                <th>快照编号</th><th>API编号</th><th>数据代际</th><th>状态</th>
                <th>保留优先级</th><th>命中次数</th><th>创建时间</th><th>过期时间</th>
              </tr>
            </thead>
            <tbody>
              {manifest.数据快照.map((row) => (
                <tr key={String(row.id)}>
                  <td>{row['快照编号']}</td>
                  <td>{row['API编号']}</td>
                  <td>{row['数据代际']}</td>
                  <td>{row['状态']}</td>
                  <td>{row['保留优先级']}</td>
                  <td>{row['命中次数']}</td>
                  <td>{row['创建时间']}</td>
                  <td>{row['过期时间']}</td>
                </tr>
              ))}
              {manifest.数据快照.length === 0 && (
                <tr><td className="empty-state" colSpan={8}>该数据源暂无数据快照</td></tr>
              )}
            </tbody>
          </table>
        </section>
      )}
    </section>
  )
}
