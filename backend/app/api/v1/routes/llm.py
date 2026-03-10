"""LLM 相关基础配置的 CRUD 接口：Provider / Model / ModelSettings。"""

from __future__ import annotations

from typing import Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.llm import Model, ModelCategoryKey, ModelSettings, Provider
from app.schemas.common import ApiResponse, PaginatedData, success_response, paginated_response
from app.schemas.llm import (
    ModelCreate,
    ModelRead,
    ModelSettingsRead,
    ModelSettingsUpdate,
    ModelUpdate,
    ProviderCreate,
    ProviderRead,
    ProviderUpdate,
)

router = APIRouter()

# 列表排序允许的字段（避免注入）
PROVIDER_ORDER_FIELDS = {"name", "created_at", "updated_at"}
MODEL_ORDER_FIELDS = {"name", "category", "created_at", "updated_at"}
DEFAULT_PAGE_SIZE = 10
MAX_PAGE_SIZE = 100


# ---------- Provider ----------


@router.get(
    "/providers",
    response_model=ApiResponse[PaginatedData[ProviderRead]],
    summary="列出模型供应商（分页）",
)
async def list_providers(
    db: AsyncSession = Depends(get_db),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ProviderRead]]:
    stmt = select(Provider)
    count_stmt = select(func.count()).select_from(Provider)
    if q and q.strip():
        q_pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            Provider.name.ilike(q_pattern) | Provider.description.ilike(q_pattern)
        )
        count_stmt = count_stmt.where(
            Provider.name.ilike(q_pattern) | Provider.description.ilike(q_pattern)
        )
    order_col = order if order and order in PROVIDER_ORDER_FIELDS else "created_at"
    order_attr = getattr(Provider, order_col)
    stmt = stmt.order_by(order_attr.desc() if is_desc else order_attr.asc())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    providers: Sequence[Provider] = result.scalars().all()
    items = [ProviderRead.model_validate(p) for p in providers]
    return paginated_response(items, page=page, page_size=page_size, total=total)


@router.post(
    "/providers",
    response_model=ApiResponse[ProviderRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型供应商",
)
async def create_provider(
    body: ProviderCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    exists = await db.get(Provider, body.id)
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider with id={body.id} already exists",
        )
    provider = Provider(
        id=body.id,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        api_secret=body.api_secret,
        description=body.description,
        status=body.status,
        created_by=body.created_by,
    )
    db.add(provider)
    await db.flush()
    await db.refresh(provider)
    return success_response(ProviderRead.model_validate(provider), code=201)


@router.get(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="获取单个模型供应商",
)
async def get_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")
    return success_response(ProviderRead.model_validate(provider))


@router.patch(
    "/providers/{provider_id}",
    response_model=ApiResponse[ProviderRead],
    summary="更新模型供应商",
)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ProviderRead]:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Provider not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(provider, field, value)

    await db.flush()
    await db.refresh(provider)
    return success_response(ProviderRead.model_validate(provider))


@router.delete(
    "/providers/{provider_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型供应商",
)
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        return success_response(None)
    await db.delete(provider)
    await db.flush()
    return success_response(None)


# ---------- Model ----------


@router.get(
    "/models",
    response_model=ApiResponse[PaginatedData[ModelRead]],
    summary="列出模型（分页）",
)
async def list_models(
    db: AsyncSession = Depends(get_db),
    provider_id: str | None = Query(None, description="按供应商过滤"),
    category: ModelCategoryKey | None = Query(None, description="按模型类别过滤"),
    q: str | None = Query(None, description="关键字，过滤 name/description"),
    order: str | None = Query(None, description="排序字段：name, category, created_at, updated_at"),
    is_desc: bool = Query(False, description="是否倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE, description="每页条数"),
) -> ApiResponse[PaginatedData[ModelRead]]:
    stmt = select(Model)
    count_stmt = select(func.count()).select_from(Model)
    if provider_id is not None:
        stmt = stmt.where(Model.provider_id == provider_id)
        count_stmt = count_stmt.where(Model.provider_id == provider_id)
    if category is not None:
        stmt = stmt.where(Model.category == category)
        count_stmt = count_stmt.where(Model.category == category)
    if q and q.strip():
        q_pattern = f"%{q.strip()}%"
        stmt = stmt.where(Model.name.ilike(q_pattern) | Model.description.ilike(q_pattern))
        count_stmt = count_stmt.where(
            Model.name.ilike(q_pattern) | Model.description.ilike(q_pattern)
        )
    order_col = order if order and order in MODEL_ORDER_FIELDS else "created_at"
    order_attr = getattr(Model, order_col)
    stmt = stmt.order_by(order_attr.desc() if is_desc else order_attr.asc())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(stmt)
    models: Sequence[Model] = result.scalars().all()
    items = [ModelRead.model_validate(m) for m in models]
    return paginated_response(items, page=page, page_size=page_size, total=total)


@router.post(
    "/models",
    response_model=ApiResponse[ModelRead],
    status_code=status.HTTP_201_CREATED,
    summary="创建模型",
)
async def create_model(
    body: ModelCreate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    exists = await db.get(Model, body.id)
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Model with id={body.id} already exists",
        )

    # 确保 provider 存在
    provider = await db.get(Provider, body.provider_id)
    if provider is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider not found")

    model = Model(
        id=body.id,
        name=body.name,
        category=body.category,
        provider_id=body.provider_id,
        params=body.params,
        description=body.description,
        is_default=body.is_default,
        created_by=body.created_by,
    )
    db.add(model)
    await db.flush()
    await db.refresh(model)
    return success_response(ModelRead.model_validate(model), code=201)


@router.get(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="获取单个模型",
)
async def get_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return success_response(ModelRead.model_validate(model))


@router.patch(
    "/models/{model_id}",
    response_model=ApiResponse[ModelRead],
    summary="更新模型",
)
async def update_model(
    model_id: str,
    body: ModelUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelRead]:
    model = await db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")

    update_data = body.model_dump(exclude_unset=True)

    # 如果更新 provider_id，需要校验新 provider 是否存在
    new_provider_id = update_data.get("provider_id")
    if new_provider_id is not None:
        provider = await db.get(Provider, new_provider_id)
        if provider is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provider not found")

    for field, value in update_data.items():
        setattr(model, field, value)

    await db.flush()
    await db.refresh(model)
    return success_response(ModelRead.model_validate(model))


@router.delete(
    "/models/{model_id}",
    response_model=ApiResponse[None],
    status_code=status.HTTP_200_OK,
    summary="删除模型",
)
async def delete_model(
    model_id: str,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    model = await db.get(Model, model_id)
    if model is None:
        return success_response(None)
    await db.delete(model)
    await db.flush()
    return success_response(None)


# ---------- ModelSettings（单例） ----------


async def _get_or_create_settings(db: AsyncSession) -> ModelSettings:
    """内部工具：获取或创建单例设置行（id=1）。"""
    settings = await db.get(ModelSettings, 1)
    if settings is None:
        settings = ModelSettings(id=1)
        db.add(settings)
        await db.flush()
        await db.refresh(settings)
    return settings


@router.get(
    "/model-settings",
    response_model=ApiResponse[ModelSettingsRead],
    summary="获取模型全局设置（单例）",
)
async def get_model_settings(
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelSettingsRead]:
    settings = await _get_or_create_settings(db)
    return success_response(ModelSettingsRead.model_validate(settings))


@router.put(
    "/model-settings",
    response_model=ApiResponse[ModelSettingsRead],
    summary="更新模型全局设置（单例）",
)
async def update_model_settings(
    body: ModelSettingsUpdate,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[ModelSettingsRead]:
    settings = await _get_or_create_settings(db)

    update_data = body.model_dump()
    for field, value in update_data.items():
        setattr(settings, field, value)

    await db.flush()
    await db.refresh(settings)
    return success_response(ModelSettingsRead.model_validate(settings))

