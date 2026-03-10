"""API 全局响应结构与分页。"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """无分页时的统一响应结构。"""

    code: int = Field(200, description="与 HTTP 状态码一致")
    message: str = Field("success", description="提示信息")
    data: T | None = Field(None, description="实际数据")


class Pagination(BaseModel):
    """分页信息。"""

    page: int = Field(..., description="当前页，从 1 开始")
    page_size: int = Field(..., description="每页条数")
    total: int = Field(..., description="总条数")
    max_page: int = Field(..., description="最大页码")


class PaginatedData(BaseModel, Generic[T]):
    """有分页时的 data 结构。"""

    items: list[T] = Field(..., description="当前页数据")
    pagination: Pagination = Field(..., description="分页信息")


def success_response(
    data: T,
    *,
    code: int = 200,
    message: str = "success",
) -> ApiResponse[T]:
    """构造无分页的成功响应。"""
    return ApiResponse(code=code, message=message, data=data)


def paginated_response(
    items: list[T],
    *,
    page: int,
    page_size: int,
    total: int,
    code: int = 200,
    message: str = "success",
) -> ApiResponse[PaginatedData[T]]:
    """构造有分页的成功响应。"""
    max_page = max(1, (total + page_size - 1) // page_size) if page_size > 0 else 1
    pagination = Pagination(
        page=page,
        page_size=page_size,
        total=total,
        max_page=max_page,
    )
    payload = PaginatedData(items=items, pagination=pagination)
    return ApiResponse(code=code, message=message, data=payload)


def error_response(
    *,
    code: int = 500,
    message: str = "error",
) -> ApiResponse[None]:
    """构造错误响应（data 为 null）。"""
    return ApiResponse(code=code, message=message, data=None)
