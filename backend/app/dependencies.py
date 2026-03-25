"""FastAPI 依赖注入。"""

from collections.abc import AsyncGenerator

from fastapi import HTTPException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.runnables import Runnable
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.db import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供异步数据库会话。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_llm() -> BaseChatModel:
    """提供 LLM（ChatOpenAI），用于影视技能抽取。未配置 OPENAI_API_KEY 时抛出 503。"""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured; set it in .env to use film extraction endpoints",
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="Install langchain-openai (e.g. uv sync --group dev) to use film extraction endpoints",
        ) from e
    kwargs: dict = {
        "model": settings.openai_model,
        "temperature": 0,
        "api_key": settings.openai_api_key,
        }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)


class _ImageHttpRunnable:
    """最小图片生成 runnable：从环境变量读取配置，通过 HTTP 调用外部图片生成服务。"""

    def __init__(self, *, base_url: str, api_key: str, timeout_s: float = 60.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    def invoke(self, payload: dict) -> dict:  # noqa: ANN001
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise HTTPException(status_code=503, detail="Install httpx to enable image generation") from e
        with httpx.Client(timeout=self._timeout_s) as client:
            r = client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"images": data}

    async def ainvoke(self, payload: dict) -> dict:  # noqa: ANN001
        try:
            import httpx
        except ImportError as e:  # pragma: no cover
            raise HTTPException(status_code=503, detail="Install httpx to enable image generation") from e
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            r = await client.post(
                self._base_url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {"images": data}


def get_image_runnable() -> Runnable:
    """提供图片生成 runnable（用于生成类任务）。未配置 IMAGE_API_* 时抛出 503。"""
    if not settings.image_api_base_url or not settings.image_api_key:
        raise HTTPException(
            status_code=503,
            detail="IMAGE_API_BASE_URL/IMAGE_API_KEY not configured; set them in .env to use image generation tasks",
        )
    return _ImageHttpRunnable(base_url=settings.image_api_base_url, api_key=settings.image_api_key)  # type: ignore[return-value]
