import { useMemo, useState } from 'react'
import { Button, Card, Empty, Input, Space, Table, message } from 'antd'
import type { TableColumnsType } from 'antd'
import { DeleteOutlined, PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { ScriptProcessingService } from '../../../../../services/generated'
import { usePrepFlow } from '../usePrepFlow'

type ShotRow = {
  index: number
  start_line: number
  end_line: number
  script_excerpt: string
  scene_name?: string | null
  time_of_day?: string | null
  character_names_in_text?: string[]
}

export default function DivideStep() {
  const { workingScriptText, scriptDivision, setScriptDivision, editableShots, setEditableShots, setExtractionDraft } = usePrepFlow()

  const [loading, setLoading] = useState(false)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Array<string>>([])

  const shots = useMemo(() => {
    const list = (editableShots as ShotRow[] | undefined) ?? (scriptDivision?.shots as ShotRow[] | undefined) ?? []
    return Array.isArray(list) ? list : []
  }, [editableShots, scriptDivision])

  const updateShot = (index: number, patch: Partial<ShotRow>) => {
    setEditableShots((prev) => {
      const next = (prev as ShotRow[]).map((s) => (s.index === index ? { ...s, ...patch } : s))
      return next as any
    })
  }

  const columns: TableColumnsType<ShotRow> = [
    {
      title: '镜头',
      dataIndex: 'index',
      key: 'index',
      width: 80,
      render: (v, r) => (
        <Input
          value={String(v)}
          onChange={(e) => {
            const next = Number(e.target.value)
            if (Number.isNaN(next)) return
            // index 作为 rowKey，变更时用“重建”策略
            setEditableShots((prev) => {
              const list = (prev as ShotRow[]).map((s) => (s.index === r.index ? { ...s, index: next } : s))
              return list as any
            })
          }}
          size="small"
        />
      ),
    },
    {
      title: '起止行',
      key: 'lines',
      width: 180,
      render: (_, r) => (
        <Space size="small">
          <Input
            value={String(r.start_line)}
            onChange={(e) => updateShot(r.index, { start_line: Number(e.target.value) || 0 })}
            size="small"
            style={{ width: 72 }}
          />
          <span className="text-gray-400">–</span>
          <Input
            value={String(r.end_line)}
            onChange={(e) => updateShot(r.index, { end_line: Number(e.target.value) || 0 })}
            size="small"
            style={{ width: 72 }}
          />
        </Space>
      ),
    },
    {
      title: '场景',
      dataIndex: 'scene_name',
      key: 'scene_name',
      width: 180,
      render: (v, r) => (
        <Input
          value={v ?? ''}
          onChange={(e) => updateShot(r.index, { scene_name: e.target.value })}
          size="small"
        />
      ),
    },
    {
      title: '摘录',
      dataIndex: 'script_excerpt',
      key: 'script_excerpt',
      render: (v, r) => (
        <Input.TextArea
          value={v}
          onChange={(e) => updateShot(r.index, { script_excerpt: e.target.value })}
          autoSize={{ minRows: 2, maxRows: 6 }}
        />
      ),
    },
  ]

  const runDivide = async () => {
    if (!workingScriptText.trim()) {
      message.warning('请先填写章节原文')
      return
    }

    setLoading(true)
    try {
      const res = await ScriptProcessingService.divideScriptApiV1ScriptProcessingDividePost({
        requestBody: { script_text: workingScriptText },
      })
      const data = res.data
      if (!data) {
        message.error(res.message || '分镜提取失败')
        return
      }
      setScriptDivision(data as any)
      setEditableShots(((data as any).shots ?? []) as any)
      // 上游变更会导致下游作废：清空后续结果
      setExtractionDraft(null)
      message.success(`分镜提取完成：${data.total_shots} 镜`)
    } catch (e: any) {
      message.error(e?.message || '分镜提取失败')
    } finally {
      setLoading(false)
    }
  }

  const addRow = () => {
    const maxIndex = shots.reduce((m, s) => Math.max(m, s.index), 0)
    const next: ShotRow = {
      index: maxIndex + 1,
      start_line: 1,
      end_line: 1,
      script_excerpt: '',
      scene_name: '',
      time_of_day: null,
      character_names_in_text: [],
    }
    setEditableShots((prev) => ([...(prev as any[]), next] as any))
  }

  const deleteSelected = () => {
    if (selectedRowKeys.length === 0) {
      message.info('请先选择要删除的镜头')
      return
    }
    setEditableShots((prev) => (prev as ShotRow[]).filter((s) => !selectedRowKeys.includes(String(s.index))) as any)
    setSelectedRowKeys([])
    setExtractionDraft(null)
    message.success('已删除所选镜头')
  }

  return (
    <Card
      title="Step 1 / 2：分镜提取（可编辑）"
      style={{ flex: 1, minHeight: 0, overflow: 'auto' }}
      bodyStyle={{ padding: 12 }}
      extra={
        <Space>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={loading} onClick={() => void runDivide()}>
            开始分镜提取
          </Button>
          <Button icon={<PlusOutlined />} disabled={loading || shots.length === 0} onClick={addRow}>
            新增镜头
          </Button>
          <Button danger icon={<DeleteOutlined />} disabled={loading} onClick={deleteSelected}>
            删除所选
          </Button>
        </Space>
      }
    >
      {shots.length === 0 ? (
        <Empty description="暂无分镜结果，点击右上角开始分镜提取" />
      ) : (
        <Table<ShotRow>
          rowKey={(r) => String(r.index)}
          dataSource={shots}
          columns={columns as TableColumnsType<ShotRow>}
          pagination={{ pageSize: 10 }}
          size="small"
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => setSelectedRowKeys(keys.map(String)),
          }}
        />
      )}
    </Card>
  )
}

