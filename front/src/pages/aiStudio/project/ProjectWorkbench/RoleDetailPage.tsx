import { useNavigate, useParams } from 'react-router-dom'
import { StudioImageTasksService } from '../../../../services/generated'
import { AssetEditPageBase } from '../../assets/components/AssetEditPageBase'
import type { AssetViewAngle } from '../../assets/components/AssetEditPageBase'
import { StudioEntitiesApi } from '../../../../services/studioEntities'

type UpdateImagePayload = {
  file_id: string
  width?: number | null
  height?: number | null
  format?: string | null
}

function normalizeUpdateImagePayload(payload: UpdateImagePayload): UpdateImagePayload {
  return {
    ...payload,
    format: payload.format ?? 'png',
  }
}

export default function RoleDetailPage() {
  const navigate = useNavigate()
  const { projectId, characterId } = useParams<{ projectId: string; characterId: string }>()

  if (!characterId) {
    return null
  }

  return (
    <AssetEditPageBase<any, any>
      assetId={characterId}
      missingAssetIdText="缺少 character_id"
      assetDisplayName="角色"
      backTo={projectId ? `/projects/${projectId}?tab=roles` : '/projects'}
      relationType="character_image"
      getAsset={async (id) => {
        const res = await StudioEntitiesApi.get('character', id)
        return (res.data ?? null) as any | null
      }}
      updateAsset={async (id, payload) => {
        const res = await StudioEntitiesApi.update('character', id, payload as Record<string, unknown>)
        return (res.data ?? null) as any | null
      }}
      listImages={async (id) => {
        const res = await StudioEntitiesApi.listImages('character', id, { page: 1, pageSize: 100 })
        return (res.data?.items ?? []) as any[]
      }}
      createImageSlot={async (id, angle: AssetViewAngle) => {
        await StudioEntitiesApi.createImage('character', id, { view_angle: angle })
      }}
      updateImage={async (id, imageId, payload) => {
        await StudioEntitiesApi.updateImage('character', id, imageId, normalizeUpdateImagePayload(payload))
      }}
      renderPrompt={async (id, imageId) => {
        const res = await StudioImageTasksService.renderCharacterImagePromptApiV1StudioImageTasksCharactersCharacterIdRenderPromptPost({
          characterId: id,
          requestBody: { image_id: imageId, model_id: null },
        })
        const data = res.data
        return {
          prompt: (data?.prompt ?? '') as string,
          images: (data?.images ?? []) as string[],
        }
      }}
      createGenerationTask={async (id, imageId, payload) => {
        const res = await StudioImageTasksService.createCharacterImageGenerationTaskApiV1StudioImageTasksCharactersCharacterIdImageTasksPost({
          characterId: id,
          requestBody: { image_id: imageId, model_id: null, prompt: payload.prompt, images: payload.images } as any,
        })
        return res.data?.task_id ?? null
      }}
      onNavigate={(to, replace) => navigate(to, replace ? { replace: true } : undefined)}
    />
  )
}

