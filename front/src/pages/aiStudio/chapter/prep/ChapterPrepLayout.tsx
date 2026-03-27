import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Divider, Layout, Space, Steps, Typography, message } from 'antd'
import { ArrowLeftOutlined, EditOutlined } from '@ant-design/icons'
import { Link, Navigate, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom'
import { StudioChaptersService } from '../../../../services/generated'
import { ChapterRawTextEditorModal } from '../components/ChapterRawTextEditorModal'
import type { PrepFlowContext, StepKey } from './usePrepFlow'

const { Header, Content } = Layout

const STEP_ITEMS: { key: StepKey; title: string }[] = [
  { key: 'divide', title: '分镜提取' },
  { key: 'extract', title: '项目级信息提取' },
]

function getStepKeyFromPathname(pathname: string): StepKey | null {
  const hit = STEP_ITEMS.find((x) => pathname.endsWith(`/prep/${x.key}`))
  return hit?.key ?? null
}

export default function ChapterPrepLayout() {
  const { projectId, chapterId } = useParams<{ projectId?: string; chapterId?: string }>()
  const navigate = useNavigate()
  const location = useLocation()

  const [baseRawText, setBaseRawText] = useState('')
  const [workingScriptText, setWorkingScriptText] = useState('')
  const [chapterTitle, setChapterTitle] = useState<string>('')
  const [chapterIndex, setChapterIndex] = useState<number | null>(null)
  const [loadingChapter, setLoadingChapter] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)

  const [scriptDivision, setScriptDivision] = useState<Record<string, any> | null>(null)
  const [editableShots, setEditableShots] = useState<Array<Record<string, any>>>([])
  const [consistencyResult, setConsistencyResult] = useState<Record<string, any> | null>(null)
  const [consistencyDone, setConsistencyDone] = useState(false)
  const [extractionDraft, setExtractionDraft] = useState<Record<string, any> | null>(null)

  useEffect(() => {
    if (!chapterId) return
    setLoadingChapter(true)
    StudioChaptersService.getChapterApiV1StudioChaptersChapterIdGet({ chapterId })
      .then((res) => {
        const c = res.data
        setChapterTitle(c?.title ?? '')
        setChapterIndex(typeof c?.index === 'number' ? c.index : null)
        const raw = c?.raw_text ?? ''
        setBaseRawText(raw)
        setWorkingScriptText(raw)
        setConsistencyDone(false)
        setConsistencyResult(null)
        setScriptDivision(null)
        setEditableShots([])
        setExtractionDraft(null)
      })
      .catch(() => {
        message.error('章节加载失败')
      })
      .finally(() => {
        setLoadingChapter(false)
      })
  }, [chapterId])

  const currentStepKey = getStepKeyFromPathname(location.pathname) ?? 'divide'
  const currentStepIndex = Math.max(
    0,
    STEP_ITEMS.findIndex((x) => x.key === currentStepKey),
  )

  const ctx = useMemo<PrepFlowContext>(() => {
    if (!projectId || !chapterId) {
      // 这里仅用于类型收敛；实际渲染会被 Guard 拦截
      return {
        projectId: projectId ?? '',
        chapterId: chapterId ?? '',
        baseRawText,
        setBaseRawText,
        workingScriptText,
        setWorkingScriptText,
        openScriptEditor: () => setEditorOpen(true),
        consistencyResult,
        setConsistencyResult,
        consistencyDone,
        setConsistencyDone,
        scriptDivision,
        setScriptDivision,
        editableShots,
        setEditableShots,
        extractionDraft,
        setExtractionDraft,
      }
    }
    return {
      projectId,
      chapterId,
      baseRawText,
      setBaseRawText,
      workingScriptText,
      setWorkingScriptText,
      openScriptEditor: () => setEditorOpen(true),
      consistencyResult,
      setConsistencyResult,
      consistencyDone,
      setConsistencyDone,
      scriptDivision,
      setScriptDivision,
      editableShots,
      setEditableShots,
      extractionDraft,
      setExtractionDraft,
    }
  }, [
    baseRawText,
    chapterId,
    projectId,
    consistencyResult,
    consistencyDone,
    editableShots,
    extractionDraft,
    scriptDivision,
    workingScriptText,
  ])

  if (!projectId || !chapterId) {
    return <Navigate to="/projects" replace />
  }

  const goToStep = (key: StepKey) => navigate(`/projects/${projectId}/chapters/${chapterId}/prep/${key}`)

  const prevStep = currentStepIndex > 0 ? STEP_ITEMS[currentStepIndex - 1] : null
  const nextStep = currentStepIndex < STEP_ITEMS.length - 1 ? STEP_ITEMS[currentStepIndex + 1] : null

  const isStepAllowed = (key: StepKey) => {
    if (key === 'divide') return !!workingScriptText.trim()
    if (key === 'extract') return !!scriptDivision && editableShots.length > 0
    return false
  }

  const isCurrentStepCompleted = () => {
    if (currentStepKey === 'divide') return !!scriptDivision && editableShots.length > 0
    if (currentStepKey === 'extract') return !!extractionDraft
    return false
  }

  const canGoPrev = !!prevStep
  const canGoNext = !!nextStep && isCurrentStepCompleted() && isStepAllowed(nextStep.key)

  return (
    <Layout style={{ height: '100%', minHeight: 0, background: '#eef2f7' }}>
      <Header
        style={{
          padding: '0 16px',
          background: '#fff',
          borderBottom: '1px solid #e2e8f0',
          boxShadow: '0 2px 4px rgba(0,0,0,0.04)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}
      >
        <Link
          to={projectId ? `/projects/${projectId}?tab=chapters` : '/projects'}
          className="text-gray-600 hover:text-blue-600 flex items-center gap-1"
        >
          <ArrowLeftOutlined /> 返回章节列表
        </Link>
        <Divider type="vertical" />

        <div className="min-w-0 flex-1">
          <Typography.Text strong className="truncate block">
            {chapterIndex !== null ? `第${chapterIndex}章 · ${chapterTitle || '未命名'}` : chapterTitle || '章节编辑'}
          </Typography.Text>
          <Typography.Text type="secondary" className="text-xs">
            {loadingChapter ? '加载中…' : '脚本处理工作流'}
          </Typography.Text>
        </div>

        <Button icon={<EditOutlined />} onClick={() => setEditorOpen(true)}>
          编辑原文
        </Button>
      </Header>

      <Content
        style={{
          padding: 16,
          minHeight: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <Card size="small" className="mb-3">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <Steps
              current={currentStepIndex}
              onChange={(idx) => {
                const target = STEP_ITEMS[idx]
                if (!target) return
                if (!isStepAllowed(target.key)) {
                  message.warning('请先完成前置步骤')
                  return
                }
                goToStep(target.key)
              }}
              className="flex-1 min-w-[520px]"
              items={STEP_ITEMS.map((x) => ({ title: x.title }))}
            />
            <Space>
              <Button disabled={!canGoPrev} onClick={() => prevStep && goToStep(prevStep.key)}>
                上一步：{prevStep?.title ?? '-'}
              </Button>
              <Button type="primary" disabled={!canGoNext} onClick={() => nextStep && goToStep(nextStep.key)}>
                下一步：{nextStep?.title ?? '-'}
              </Button>
            </Space>
          </div>
        </Card>

        {!workingScriptText.trim() && (
          <Alert
            type="warning"
            showIcon
            className="mb-3"
            message="当前章节没有原文内容"
            description="请先点击右上角“编辑原文”粘贴/输入剧本，然后从“分镜提取”开始。"
          />
        )}

        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          <Outlet context={ctx} />
        </div>
      </Content>

      <ChapterRawTextEditorModal
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        chapterId={chapterId}
        onSaved={(next) => {
          if (typeof next.rawText === 'string') {
            setBaseRawText(next.rawText)
            setWorkingScriptText(next.rawText)
              setConsistencyDone(false)
              setConsistencyResult(null)
              setScriptDivision(null)
              setEditableShots([])
              setExtractionDraft(null)
          }
        }}
      />
    </Layout>
  )
}

