import { useMemo, useState } from 'react'
import { Button, Card, Divider, Empty, Input, List, Space, Tag, message } from 'antd'
import { PlusOutlined, SaveOutlined, ThunderboltOutlined, DeleteOutlined } from '@ant-design/icons'
import { ScriptProcessingService, StudioImportService } from '../../../../../services/generated'
import { usePrepFlow } from '../usePrepFlow'
import { useNavigate } from 'react-router-dom'

type StudioShotDraft = Record<string, any>

function csvToList(v: string) {
  return v
    .split(',')
    .map((x) => x.trim())
    .filter(Boolean)
}

export default function ExtractProjectStep() {
  const { projectId, chapterId, workingScriptText, consistencyResult, editableShots, extractionDraft, setExtractionDraft } =
    usePrepFlow()
  const navigate = useNavigate()

  const [extracting, setExtracting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [activeShotIndex, setActiveShotIndex] = useState<number | null>(null)

  const shots = useMemo(() => {
    const list = (extractionDraft?.shots as StudioShotDraft[] | undefined) ?? []
    const sorted = Array.isArray(list) ? [...list].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)) : []
    return sorted
  }, [extractionDraft])

  const selectedShot = useMemo(() => {
    if (activeShotIndex === null) return null
    return shots.find((s) => s.index === activeShotIndex) ?? null
  }, [activeShotIndex, shots])

  const setSelectedShotPatch = (patch: Partial<StudioShotDraft>) => {
    if (activeShotIndex === null) return
    setExtractionDraft((prev) => {
      if (!prev) return prev
      const prevShots = (prev.shots as StudioShotDraft[] | undefined) ?? []
      const nextShots = prevShots.map((s) => (s.index === activeShotIndex ? { ...s, ...patch } : s))
      return { ...prev, shots: nextShots }
    })
  }

  const runExtract = async () => {
    if (!workingScriptText.trim()) {
      message.warning('请先完成前置步骤并确保有剧本文本')
      return
    }
    if (!editableShots || editableShots.length === 0) {
      message.warning('请先完成分镜提取并确认分镜表格')
      return
    }
    setExtracting(true)
    try {
      const scriptDivision = { total_shots: editableShots.length, shots: editableShots }
      const res = await ScriptProcessingService.extractScriptApiV1ScriptProcessingExtractPost({
        requestBody: {
          project_id: projectId,
          chapter_id: chapterId,
          script_text: workingScriptText,
          script_division: scriptDivision as any,
          consistency: consistencyResult ?? undefined,
        } as any,
      })
      const data = res.data
      if (!data) {
        message.error(res.message || '信息提取失败')
        return
      }
      setExtractionDraft(data as any)
      const first = (data as any).shots?.[0]?.index
      if (typeof first === 'number') setActiveShotIndex(first)
      message.success('项目级信息提取完成')
    } catch (e: any) {
      message.error(e?.message || '信息提取失败')
    } finally {
      setExtracting(false)
    }
  }

  const confirmImport = async () => {
    if (!extractionDraft) {
      message.warning('请先完成信息提取')
      return
    }
    setImporting(true)
    try {
      const res = await StudioImportService.importFromExtractionApiV1StudioImportFromExtractionPost({
        requestBody: {
          ...(extractionDraft as any),
          on_conflict: 'error',
        },
      })
      if (!res.data) {
        message.error(res.message || '导入失败')
        return
      }
      message.success('已导入到 Studio')
      navigate(`/projects/${projectId}/chapters/${chapterId}/studio`)
    } catch (e: any) {
      message.error(e?.message || '导入失败')
    } finally {
      setImporting(false)
    }
  }

  const addDialogueLine = () => {
    const lines = (selectedShot?.dialogue_lines as any[] | undefined) ?? []
    const next = [...lines, { index: lines.length + 1, text: '', speaker_name: null, target_name: null }]
    setSelectedShotPatch({ dialogue_lines: next })
  }

  const deleteDialogueLine = (idx: number) => {
    const lines = (selectedShot?.dialogue_lines as any[] | undefined) ?? []
    const next = lines.filter((_, i) => i !== idx).map((l, i) => ({ ...l, index: i + 1 }))
    setSelectedShotPatch({ dialogue_lines: next })
  }

  return (
    <Card
      title="Step 2 / 2：项目级信息提取（最终输出）"
      style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}
      bodyStyle={{ padding: 12, height: '100%', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}
      extra={
        <Space>
          <Button type="primary" icon={<ThunderboltOutlined />} loading={extracting} onClick={() => void runExtract()}>
            开始提取
          </Button>
          <Button icon={<SaveOutlined />} type="primary" loading={importing} disabled={!extractionDraft} onClick={() => void confirmImport()}>
            确认保存
          </Button>
        </Space>
      }
    >
      {!extractionDraft ? (
        <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
          <Empty description="尚未提取。点击右上角“开始提取”生成可导入草稿。" />
        </div>
      ) : (
        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', gap: 12 }}>
          <Card
            size="small"
            title={`镜头（${shots.length}）`}
            style={{ width: 320, minWidth: 260, maxWidth: 420, overflow: 'hidden' }}
            bodyStyle={{ padding: 8, height: '100%', overflow: 'auto' }}
          >
            <List
              size="small"
              dataSource={shots}
              renderItem={(s: any) => (
                <List.Item
                  onClick={() => setActiveShotIndex(s.index)}
                  style={{
                    cursor: 'pointer',
                    borderRadius: 10,
                    padding: '8px 10px',
                    background: activeShotIndex === s.index ? 'rgba(59,130,246,0.10)' : undefined,
                  }}
                >
                  <div className="min-w-0">
                    <div className="font-medium truncate">
                      #{s.index} · {s.title || '未命名镜头'}
                    </div>
                    <div className="text-xs text-gray-500 truncate">{s.scene_name || ''}</div>
                  </div>
                </List.Item>
              )}
            />
          </Card>

          <Card
            size="small"
            title={selectedShot ? `镜头 #${selectedShot.index} 详情` : '镜头详情'}
            style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}
            bodyStyle={{ padding: 12, height: '100%', overflow: 'auto' }}
          >
            {!selectedShot ? (
              <Empty description="请选择左侧一个镜头" />
            ) : (
              <div className="space-y-3">
                <div>
                  <div className="text-xs text-gray-600 mb-1">剧本摘录</div>
                  <Input.TextArea
                    value={selectedShot.script_excerpt ?? ''}
                    onChange={(e) => setSelectedShotPatch({ script_excerpt: e.target.value })}
                    autoSize={{ minRows: 3, maxRows: 10 }}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs text-gray-600 mb-1">分镜名</div>
                    <Input value={selectedShot.title ?? ''} onChange={(e) => setSelectedShotPatch({ title: e.target.value })} />
                  </div>
                  <div>
                    <div className="text-xs text-gray-600 mb-1">场景名</div>
                    <Input value={selectedShot.scene_name ?? ''} onChange={(e) => setSelectedShotPatch({ scene_name: e.target.value })} />
                  </div>
                  <div className="md:col-span-2">
                    <div className="text-xs text-gray-600 mb-1">动作（每行一条）</div>
                    <Input.TextArea
                      value={Array.isArray(selectedShot.actions) ? selectedShot.actions.join('\\n') : ''}
                      onChange={(e) =>
                        setSelectedShotPatch({
                          actions: e.target.value.split('\\n').map((x) => x.trim()).filter(Boolean),
                        })
                      }
                      autoSize={{ minRows: 2, maxRows: 6 }}
                    />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div>
                    <div className="text-xs text-gray-600 mb-1">角色名称（逗号分隔）</div>
                    <Input
                      value={Array.isArray(selectedShot.character_names) ? selectedShot.character_names.join(', ') : ''}
                      onChange={(e) => setSelectedShotPatch({ character_names: csvToList(e.target.value) })}
                    />
                  </div>
                  <div>
                    <div className="text-xs text-gray-600 mb-1">道具名称（逗号分隔）</div>
                    <Input
                      value={Array.isArray(selectedShot.prop_names) ? selectedShot.prop_names.join(', ') : ''}
                      onChange={(e) => setSelectedShotPatch({ prop_names: csvToList(e.target.value) })}
                    />
                  </div>
                  <div>
                    <div className="text-xs text-gray-600 mb-1">服装名称（逗号分隔）</div>
                    <Input
                      value={Array.isArray(selectedShot.costume_names) ? selectedShot.costume_names.join(', ') : ''}
                      onChange={(e) => setSelectedShotPatch({ costume_names: csvToList(e.target.value) })}
                    />
                  </div>
                </div>

                <Divider />

                <div className="flex items-center justify-between">
                  <div className="font-medium">对白（dialogue_lines）</div>
                  <Button icon={<PlusOutlined />} onClick={addDialogueLine}>
                    新增对白
                  </Button>
                </div>
                {(selectedShot.dialogue_lines?.length ?? 0) === 0 ? (
                  <Empty description="暂无对白" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                ) : (
                  <div className="space-y-2">
                    {(selectedShot.dialogue_lines as any[]).map((line, i) => (
                      <Card key={i} size="small">
                        <div className="flex items-center justify-between gap-2">
                          <Space wrap className="min-w-0">
                            <Tag>#{line.index ?? i + 1}</Tag>
                            <Tag color="blue" className="max-w-[260px] truncate">
                              {(line.speaker_name || '未知') + ' → ' + (line.target_name || '未知')}
                            </Tag>
                            <Input
                              placeholder="说话者"
                              value={line.speaker_name ?? ''}
                              onChange={(e) => {
                                const lines = [...(selectedShot.dialogue_lines as any[])]
                                lines[i] = { ...lines[i], speaker_name: e.target.value || null }
                                setSelectedShotPatch({ dialogue_lines: lines })
                              }}
                              style={{ width: 140 }}
                            />
                            <Input
                              placeholder="听者"
                              value={line.target_name ?? ''}
                              onChange={(e) => {
                                const lines = [...(selectedShot.dialogue_lines as any[])]
                                lines[i] = { ...lines[i], target_name: e.target.value || null }
                                setSelectedShotPatch({ dialogue_lines: lines })
                              }}
                              style={{ width: 140 }}
                            />
                          </Space>
                          <Button danger icon={<DeleteOutlined />} onClick={() => deleteDialogueLine(i)} />
                        </div>
                        <div className="mt-2">
                          <Input.TextArea
                            placeholder="台词内容"
                            value={line.text ?? ''}
                            onChange={(e) => {
                              const lines = [...(selectedShot.dialogue_lines as any[])]
                              lines[i] = { ...lines[i], text: e.target.value }
                              setSelectedShotPatch({ dialogue_lines: lines })
                            }}
                            autoSize={{ minRows: 2, maxRows: 6 }}
                          />
                        </div>
                      </Card>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}

    </Card>
  )
}

