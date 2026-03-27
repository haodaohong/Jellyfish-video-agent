import { useEffect, useMemo, useState } from 'react'
import { Button, Card, Collapse, Empty, Input, List, Modal, Space, Spin, Tag, message } from 'antd'
import {
  DiffOutlined,
  FileTextOutlined,
  HistoryOutlined,
  ReloadOutlined,
  SaveOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import { ScriptProcessingService, StudioChaptersService } from '../../../../services/generated'
import type { ScriptConsistencyCheckResult } from '../../../../services/generated'

type EditorMode = 'raw' | 'condensed' | 'compare'

type HistoryItem = {
  id: string
  at: number
  rawText: string
  condensedText: string
}

export function ChapterRawTextEditorModal({
  open,
  onClose,
  chapterId,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  chapterId: string | undefined
  onSaved?: (next: { rawText?: string; condensedText?: string }) => void
}) {
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [extracting, setExtracting] = useState(false)
  const [checkingConsistency, setCheckingConsistency] = useState(false)
  const [optimizingScript, setOptimizingScript] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  const [mode, setMode] = useState<EditorMode>('raw')
  const [rawText, setRawText] = useState('')
  const [condensedText, setCondensedText] = useState('')
  const [savedRawText, setSavedRawText] = useState('')
  const [savedCondensedText, setSavedCondensedText] = useState('')
  const [editorText, setEditorText] = useState('')
  const [compareRaw, setCompareRaw] = useState('')
  const [compareCondensed, setCompareCondensed] = useState('')
  const [consistencyResult, setConsistencyResult] = useState<ScriptConsistencyCheckResult | null>(null)

  const plainWordCount = useMemo(() => editorText.trim().length, [editorText])
  const paragraphCount = useMemo(() => editorText.split(/\n\s*\n/).filter((p) => p.trim()).length, [editorText])
  const actionsLoading = extracting || checkingConsistency || optimizingScript
  const consistencyIssues = useMemo(() => {
    const list = (consistencyResult?.issues as any[] | undefined) ?? []
    return Array.isArray(list) ? list : []
  }, [consistencyResult])

  useEffect(() => {
    if (!open) return
    if (!chapterId) return
    setLoading(true)
    StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      .then((res) => {
        const data = res.data
        const nextRaw = data?.raw_text ?? ''
        const nextCondensed = data?.condensed_text ?? ''
        setRawText(nextRaw)
        setCondensedText(nextCondensed)
        setSavedRawText(nextRaw)
        setSavedCondensedText(nextCondensed)
        setMode('raw')
        setEditorText(nextRaw)
        setCompareRaw(nextRaw)
        setCompareCondensed(nextCondensed)
        setConsistencyResult(null)
      })
      .catch(() => {
        message.error('加载章节失败')
      })
      .finally(() => setLoading(false))
  }, [open, chapterId])

  const handleSmartSimplify = async () => {
    if (!rawText.trim()) {
      message.warning('请先输入原文')
      return
    }
    setExtracting(true)
    try {
      const res = await ScriptProcessingService.simplifyScriptApiV1ScriptProcessingSimplifyScriptPost({
        requestBody: {
          script_text: rawText,
        },
      })
      const simplified = res.data?.simplified_script_text?.trim() ?? ''
      if (!simplified) {
        message.error('智能精简失败：未返回有效内容')
        return
      }
      setCondensedText(simplified)
      if (mode === 'compare') {
        // 对比模式下不切换编辑区：只更新右侧精简内容输入框
        setCompareCondensed(simplified)
      } else {
        setMode('condensed')
        setEditorText(simplified)
      }
      message.success('智能精简完成')
    } catch {
      message.error('智能精简失败')
    } finally {
      setExtracting(false)
    }
  }

  const handleCheckConsistency = async () => {
    const scriptText = rawText.trim()
    if (!scriptText) {
      message.warning('请先输入原文')
      return
    }
    setCheckingConsistency(true)
    try {
      const res = await ScriptProcessingService.checkConsistencyApiV1ScriptProcessingCheckConsistencyPost({
        requestBody: { script_text: scriptText },
      })
      const data = res.data
      if (!data) {
        message.error(res.message || '一致性检查失败')
        return
      }
      setConsistencyResult(data)
      if (data.has_issues) message.warning(`发现 ${data.issues?.length ?? 0} 个角色混淆问题`)
      else message.success('未发现角色混淆问题')
    } catch (e: any) {
      message.error(e?.message || '一致性检查失败')
    } finally {
      setCheckingConsistency(false)
    }
  }

  const handleOneClickOptimize = async () => {
    const scriptText = rawText.trim()
    if (!scriptText) {
      message.warning('请先输入原文')
      return
    }
    if (!consistencyResult) {
      message.info('请先进行角色混淆检查')
      return
    }
    setOptimizingScript(true)
    try {
      const res = await ScriptProcessingService.optimizeScriptApiV1ScriptProcessingOptimizeScriptPost({
        requestBody: {
          script_text: scriptText,
          consistency: consistencyResult as any,
        },
      })
      const optimized = res.data?.optimized_script_text?.trim() ?? ''
      if (!optimized) {
        message.error(res.message || '一键优化失败')
        return
      }
      // 优化后回写到主输入区（以原文视图承载）
      setRawText(optimized)
      setEditorText(optimized)
      setMode('raw')
      setCompareRaw(optimized)
      message.success('一键优化完成')
    } catch (e: any) {
      message.error(e?.message || '一键优化失败')
    } finally {
      setOptimizingScript(false)
    }
  }

  const handleBackToRaw = () => {
    setMode('raw')
    setEditorText(rawText)
  }

  const handleViewCondensed = () => {
    if (!condensedText.trim()) {
      message.info('暂无精简内容')
      return
    }
    setMode('condensed')
    setEditorText(condensedText)
  }

  const handleSave = async (): Promise<boolean> => {
    if (!chapterId) return false
    setSaving(true)
    try {
      if (mode === 'raw') {
        await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
          chapterId,
          requestBody: { raw_text: editorText },
        })
        setRawText(editorText)
        setSavedRawText(editorText)
        onSaved?.({ rawText: editorText })
        message.success('原文已保存')
        return true
      }

      if (mode === 'condensed') {
        await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
          chapterId,
          requestBody: { condensed_text: editorText },
        })
        setCondensedText(editorText)
        setSavedCondensedText(editorText)
        onSaved?.({ condensedText: editorText })
        message.success('精简内容已保存')
        return true
      }

      await StudioChaptersService.updateChapterApiV1StudioChaptersChapterIdPatch({
        chapterId,
        requestBody: { raw_text: compareRaw, condensed_text: compareCondensed },
      })
      setRawText(compareRaw)
      setCondensedText(compareCondensed)
      setSavedRawText(compareRaw)
      setSavedCondensedText(compareCondensed)
      onSaved?.({ rawText: compareRaw, condensedText: compareCondensed })
      message.success('已保存')
      return true
    } catch {
      message.error('保存失败')
      return false
    } finally {
      setSaving(false)
    }
  }

  const hasUnsavedChanges = useMemo(() => {
    if (mode === 'compare') return compareRaw !== savedRawText || compareCondensed !== savedCondensedText
    if (mode === 'raw') return editorText !== savedRawText
    return editorText !== savedCondensedText
  }, [compareCondensed, compareRaw, editorText, mode, savedCondensedText, savedRawText])

  const handleRequestClose = () => {
    if (actionsLoading) return
    if (!hasUnsavedChanges) {
      onClose()
      return
    }
    Modal.confirm({
      title: '检测到未保存变更',
      content: '文本输入区有未保存修改，关闭前请选择操作。',
      okText: '保存',
      cancelText: '忽略',
      onOk: async () => {
        const ok = await handleSave()
        if (ok) onClose()
      },
      onCancel: () => {
        onClose()
      },
    })
  }

  const mockHistory: HistoryItem[] = useMemo(
    () => [
      {
        id: 'h-1',
        at: Date.now() - 1000 * 60 * 60 * 2,
        rawText: '【原文】示例版本 1（预置数据）',
        condensedText: '【精简】示例版本 1（预置数据）',
      },
      {
        id: 'h-2',
        at: Date.now() - 1000 * 60 * 22,
        rawText: '【原文】示例版本 2（预置数据）',
        condensedText: '【精简】示例版本 2（预置数据）',
      },
    ],
    [],
  )

  return (
    <>
      <Modal
        title={
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-2">
              <FileTextOutlined />{' '}
              {mode === 'raw' ? '原文编辑区' : mode === 'condensed' ? '精简内容编辑区' : '对比模式'}
              <Tag color="blue">{plainWordCount} 字</Tag>
              <Tag color="default">{paragraphCount} 段</Tag>
            </div>
            <Space size="small">
              <Button size="small" type="primary" icon={<SaveOutlined />} loading={actionsLoading || saving} disabled={actionsLoading} onClick={() => void handleSave()}>
                保存
              </Button>
              <Button
                size="small"
                icon={<ReloadOutlined />}
                loading={actionsLoading}
                disabled={actionsLoading}
                onClick={() => void handleCheckConsistency()}
              >
                角色混淆检查
              </Button>
              <Button
                size="small"
                icon={<ThunderboltOutlined />}
                loading={actionsLoading}
                disabled={actionsLoading}
                onClick={() => void handleSmartSimplify()}
              >
                智能精简
              </Button>
              {mode === 'condensed' ? (
                <Button size="small" icon={<ReloadOutlined />} loading={actionsLoading} disabled={actionsLoading} onClick={handleBackToRaw}>
                  回到原文
                </Button>
              ) : (
                <Button
                  size="small"
                  icon={<ReloadOutlined />}
                  loading={actionsLoading}
                  disabled={actionsLoading || !condensedText.trim()}
                  onClick={handleViewCondensed}
                >
                  查看精简
                </Button>
              )}
              <Button
                size="small"
                icon={<DiffOutlined />}
                loading={actionsLoading}
                disabled={actionsLoading}
                type={mode === 'compare' ? 'primary' : 'default'}
                onClick={() => {
                  if (mode === 'compare') {
                    setMode('raw')
                    setEditorText(rawText)
                    return
                  }
                  setCompareRaw(rawText)
                  setCompareCondensed(condensedText)
                  setMode('compare')
                }}
              >
                对比模式
              </Button>
              <Button size="small" icon={<HistoryOutlined />} loading={actionsLoading} disabled={actionsLoading} onClick={() => setHistoryOpen(true)}>
                版本历史
              </Button>
            </Space>
          </div>
        }
        open={open}
        onCancel={() => {
          handleRequestClose()
        }}
        width={900}
        footer={
          <Button type="primary" loading={actionsLoading} disabled={actionsLoading} onClick={handleRequestClose}>
            关闭
          </Button>
        }
        styles={{
          header: { paddingRight: 48 },
          body: { maxHeight: '70vh', overflow: 'auto', paddingTop: 12 },
        }}
      >
        {loading ? (
          <div className="flex justify-center items-center py-10">
            <Spin />
          </div>
        ) : mode === 'compare' ? (
          <div className="grid grid-cols-2 gap-4">
            <div className="flex flex-col">
              <div className="text-xs text-gray-500 mb-2">原文</div>
              <Input.TextArea
                value={compareRaw}
                onChange={(e) => setCompareRaw(e.target.value)}
                rows={14}
                disabled={actionsLoading}
                style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
            <div className="flex flex-col">
              <div className="text-xs text-gray-500 mb-2">精简内容</div>
              <Input.TextArea
                value={compareCondensed}
                onChange={(e) => setCompareCondensed(e.target.value)}
                rows={14}
                disabled={actionsLoading}
                style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
              />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <Input.TextArea
              value={editorText}
              onChange={(e) => {
                const v = e.target.value
                setEditorText(v)
                if (mode === 'raw') setRawText(v)
                if (mode === 'condensed') setCondensedText(v)
              }}
            disabled={actionsLoading}
              placeholder={mode === 'raw' ? '编辑章节原文…' : '编辑精简内容…'}
              rows={16}
              style={{ resize: 'none', background: '#fdfdfd' }}
            />
            {consistencyResult ? (
              <Card
                size="small"
                title="角色混淆检查结果"
                extra={
                  <Space wrap>
                    <Tag color={consistencyResult.has_issues ? 'red' : 'green'}>
                      {consistencyResult.has_issues ? '发现问题' : '无问题'}
                    </Tag>
                    <Tag>issues：{consistencyIssues.length}</Tag>
                    <Button
                      size="small"
                      type="primary"
                      icon={<ThunderboltOutlined />}
                      loading={actionsLoading}
                      disabled={actionsLoading}
                      onClick={() => void handleOneClickOptimize()}
                    >
                      一键优化
                    </Button>
                  </Space>
                }
              >
                {consistencyIssues.length === 0 ? (
                  <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未发现角色混淆问题" />
                ) : (
                  <List
                    size="small"
                    dataSource={consistencyIssues}
                    renderItem={(it: any, idx) => (
                      <List.Item>
                        <div className="min-w-0">
                          <div className="font-medium">
                            {it?.issue_type ? `[${it.issue_type}] ` : ''}
                            Issue {idx + 1}
                          </div>
                          <div className="text-sm">{it?.description}</div>
                          {it?.character_candidates?.length ? (
                            <div className="text-xs text-gray-500 mt-1">候选角色：{it.character_candidates.join('、')}</div>
                          ) : null}
                          {it?.suggestion ? (
                            <div className="text-xs text-gray-500 mt-1">建议：{it.suggestion}</div>
                          ) : null}
                          {it?.affected_lines ? (
                            <div className="text-xs text-gray-400 mt-1">
                              影响范围：{it.affected_lines.start_line ?? '-'}–{it.affected_lines.end_line ?? '-'}
                            </div>
                          ) : null}
                        </div>
                      </List.Item>
                    )}
                  />
                )}
                {consistencyResult.summary ? (
                  <div className="text-xs text-gray-500 mt-2">{String(consistencyResult.summary)}</div>
                ) : null}
              </Card>
            ) : null}
          </div>
        )}
      </Modal>

      <Modal
        title={
          <div className="flex items-center gap-2">
            <HistoryOutlined /> 历史版本
          </div>
        }
        open={historyOpen}
        onCancel={() => setHistoryOpen(false)}
        width={920}
        footer={
          <Button type="primary" onClick={() => setHistoryOpen(false)}>
            关闭
          </Button>
        }
        styles={{ body: { maxHeight: '70vh', overflow: 'auto' } }}
      >
        {/* TODO: 历史版本接口未接入，当前为预置数据；后续接入后按时间线渲染即可 */}
        <div className="text-xs text-gray-500 mb-3">内容默认折叠，仅展示时间线节点。</div>
        <div className="space-y-3">
          {mockHistory.map((h) => (
            <div key={h.id} className="border border-gray-200 rounded-lg p-3 bg-white">
              <div className="text-sm font-medium mb-2">{new Date(h.at).toLocaleString()}</div>
              <Collapse
                items={[
                  {
                    key: 'content',
                    label: '展开查看内容',
                    children: (
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <div className="text-xs text-gray-500 mb-2">原文内容</div>
                          <Input.TextArea
                            value={h.rawText}
                            readOnly
                            rows={8}
                            style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
                          />
                        </div>
                        <div>
                          <div className="text-xs text-gray-500 mb-2">精简内容</div>
                          <Input.TextArea
                            value={h.condensedText}
                            readOnly
                            rows={8}
                            style={{ resize: 'none', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace' }}
                          />
                        </div>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          ))}
        </div>
      </Modal>
    </>
  )
}

