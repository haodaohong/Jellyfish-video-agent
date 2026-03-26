from __future__ import annotations

"""Studio 图片任务的数据层能力。"""

import base64
import mimetypes

from fastapi import HTTPException, status
from langchain_core.prompts import PromptTemplate as LcPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.tasks import ProviderConfig
from app.models.llm import Model, ModelCategoryKey
from app.models.studio import AssetViewAngle, FileItem, PromptCategory, PromptTemplate, ShotFrameType
from app.services.llm import get_model_by_category, get_provider_by_id_or_obj


def provider_key_from_db_name(name: str) -> str:
    """将 Provider.name 映射为任务层 ProviderKey（openai | volcengine）。"""
    n = (name or "").strip()
    n_lower = n.lower()
    if n_lower == "openai":
        return "openai"
    if n == "火山引擎" or "volc" in n_lower or "doubao" in n_lower or "bytedance" in n_lower:
        return "volcengine"
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Unsupported provider name: {name!r}. Expected: openai, 火山引擎.",
    )


async def resolve_image_model(db: AsyncSession, model_id: str | None) -> Model:
    """根据显式 model_id 或默认图片模型解析 Model。"""
    try:
        return await get_model_by_category(
            db,
            ModelCategoryKey.image,
            model_or_id=model_id,
            allow_default_fallback=False,
        )
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND and model_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Configured model_id not found in DB: {model_id}",
            ) from e
        if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and not model_id:
            # 保持既有行为：未传 model_id 时，仅允许读取 ModelSettings.default_image_model_id。
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No image model configured in DB (missing explicit model_id and ModelSettings.default_image_model_id)",
            ) from e
        if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and model_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Configured model is not an image model: {model_id}",
            ) from e
        raise


async def load_provider_config(db: AsyncSession, provider_id: str) -> ProviderConfig:
    """根据 provider_id 从 DB 解析 ProviderConfig。"""
    try:
        provider = await get_provider_by_id_or_obj(db, provider_id)
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Provider not found for provider_id={provider_id}",
            ) from e
        raise

    try:
        provider_key = provider_key_from_db_name(provider.name)
    except HTTPException as e:
        if e.status_code == status.HTTP_503_SERVICE_UNAVAILABLE and (provider.name or "").strip() == "阿里百炼":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该供应商仅适用于文本生成，不支持图片生成（name=阿里百炼）",
            ) from e
        raise

    api_key = (provider.api_key or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Provider api_key is empty for provider_id={provider.id}",
        )
    base_url = (provider.base_url or "").strip() or None
    return ProviderConfig(provider=provider_key, api_key=api_key, base_url=base_url)  # type: ignore[arg-type]


def prompt_from_description(description: str, *, not_found_msg: str) -> str:
    prompt = (description or "").strip()
    if not prompt:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=not_found_msg)
    return prompt


def is_front_view(view_angle: AssetViewAngle | str | None) -> bool:
    if view_angle is None:
        return False
    value = view_angle.value if isinstance(view_angle, AssetViewAngle) else str(view_angle)
    return value == AssetViewAngle.front.value


def map_view_angle_for_prompt(view_angle: AssetViewAngle | str | None) -> str:
    if view_angle is None:
        return ""
    raw = view_angle.value if isinstance(view_angle, AssetViewAngle) else str(view_angle)
    view_angle_map = {
        "RIGH": "纯右側面,严格右侧面，90度纯侧面轮廓，耳朵清晰可见",
        "RIGHT": "纯右側面,严格右侧面，90度纯侧面轮廓，耳朵清晰可见",
        "LEFT": "纯左侧面,严格左侧面，90度纯侧面轮廓，耳朵清晰可见",
        "BACK": "正后方,正后方视角，完全背对镜头，只能看到后脑勺和后背",
    }
    return view_angle_map.get(raw, raw)


async def resolve_prompt_template(
    db: AsyncSession,
    *,
    category: PromptCategory,
) -> PromptTemplate | None:
    stmt = (
        select(PromptTemplate)
        .where(PromptTemplate.category == category)
        .order_by(PromptTemplate.is_default.desc(), PromptTemplate.updated_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


def render_prompt_template_content(
    content: str,
    *,
    variables: dict[str, object],
) -> str:
    tmpl = LcPromptTemplate.from_template(content)
    render_vars = {k: str(variables.get(k, "")) for k in tmpl.input_variables}
    return tmpl.format(**render_vars).strip()


async def build_prompt_with_template(
    db: AsyncSession,
    *,
    category: PromptCategory,
    variables: dict[str, object],
    fallback_prompt: str,
    not_found_msg: str,
) -> str:
    template = await resolve_prompt_template(db, category=category)
    if template is not None and template.content:
        rendered = render_prompt_template_content(template.content, variables=variables)
        if rendered:
            return rendered
    return prompt_from_description(fallback_prompt, not_found_msg=not_found_msg)


async def resolve_front_image_ref(
    db: AsyncSession,
    *,
    image_model: type,
    parent_field_name: str,
    parent_id: str,
    preferred_quality_level: object | None,
) -> dict[str, str] | None:
    parent_field = getattr(image_model, parent_field_name)
    stmt = (
        select(image_model)
        .where(
            parent_field == parent_id,
            image_model.view_angle == AssetViewAngle.front,
            image_model.file_id.is_not(None),
        )
        .order_by(image_model.created_at.desc(), image_model.id.desc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return None

    target = rows[0]
    if preferred_quality_level is not None:
        for row in rows:
            if row.quality_level == preferred_quality_level:
                target = row
                break

    if not target.file_id:
        return None

    file_obj = await db.get(FileItem, target.file_id)
    if file_obj is None or not file_obj.storage_key:
        return None

    try:
        content = await storage.download_file(key=file_obj.storage_key)
    except Exception:  # noqa: BLE001
        return None
    if not content:
        return None

    content_type: str | None = None
    try:
        info = await storage.get_file_info(key=file_obj.storage_key)
        content_type = (info.content_type or "").strip().lower() or None
    except Exception:  # noqa: BLE001
        content_type = None

    if not content_type:
        guessed_type, _ = mimetypes.guess_type(file_obj.storage_key)
        content_type = (guessed_type or "").strip().lower() or None

    if not content_type or not content_type.startswith("image/"):
        content_type = "image/png"

    image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
    encoded = base64.b64encode(content).decode("ascii")
    data_url = f"data:image/{image_format};base64,{encoded}"
    return {"image_url": data_url}


async def resolve_ordered_image_refs(
    db: AsyncSession,
    *,
    image_model: type,
    parent_field_name: str,
    parent_id: str,
    view_angles: tuple[AssetViewAngle, ...],
) -> list[dict[str, str]]:
    """按指定 view_angles 顺序，解析参考图（data url）。"""
    parent_field = getattr(image_model, parent_field_name)
    stmt = (
        select(image_model)
        .where(
            parent_field == parent_id,
            image_model.file_id.is_not(None),
        )
        .order_by(image_model.created_at.desc(), image_model.id.desc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    if not rows:
        return []

    best_by_angle: dict[str, object] = {}
    for row in rows:
        angle = getattr(row, "view_angle", None)
        key = angle.value if isinstance(angle, AssetViewAngle) else str(angle)
        if key and key not in best_by_angle:
            best_by_angle[key] = row

    out: list[dict[str, str]] = []
    for angle in view_angles:
        row = best_by_angle.get(angle.value)
        if row is None:
            continue
        file_id = getattr(row, "file_id", None)
        if not file_id:
            continue
        file_obj = await db.get(FileItem, str(file_id))
        if file_obj is None or not file_obj.storage_key:
            continue
        try:
            content = await storage.download_file(key=file_obj.storage_key)
        except Exception:  # noqa: BLE001
            continue
        if not content:
            continue

        content_type: str | None = None
        try:
            info = await storage.get_file_info(key=file_obj.storage_key)
            content_type = (info.content_type or "").strip().lower() or None
        except Exception:  # noqa: BLE001
            content_type = None
        if not content_type:
            guessed_type, _ = mimetypes.guess_type(file_obj.storage_key)
            content_type = (guessed_type or "").strip().lower() or None
        if not content_type or not content_type.startswith("image/"):
            content_type = "image/png"

        image_format = content_type.split("/", 1)[1].split(";", 1)[0].strip().lower() or "png"
        encoded = base64.b64encode(content).decode("ascii")
        data_url = f"data:image/{image_format};base64,{encoded}"
        out.append({"image_url": data_url})
    return out


def asset_prompt_category(
    *,
    relation_type: str,
    is_front_view: bool,
) -> PromptCategory:
    mapping = {
        "actor_image": (PromptCategory.actor_image_front, PromptCategory.actor_image_other),
        "prop_image": (PromptCategory.prop_front, PromptCategory.prop_other),
        "scene_image": (PromptCategory.scene_front, PromptCategory.scene_other),
        "costume_image": (PromptCategory.costume_front, PromptCategory.costume_other),
    }
    front_category, other_category = mapping[relation_type]
    return front_category if is_front_view else other_category


def shot_frame_prompt_category(frame_type: ShotFrameType | str) -> PromptCategory:
    value = frame_type.value if isinstance(frame_type, ShotFrameType) else str(frame_type)
    if value == ShotFrameType.first.value:
        return PromptCategory.frame_head
    if value == ShotFrameType.last.value:
        return PromptCategory.frame_tail
    return PromptCategory.frame_key

