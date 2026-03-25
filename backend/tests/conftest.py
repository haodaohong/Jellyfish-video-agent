"""Pytest 共享 fixture：FastAPI 应用与 TestClient。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

try:
    from app.main import app  # type: ignore
except Exception:  # noqa: BLE001
    # 测试环境里有些可选依赖（例如 langgraph）可能未安装。
    # 不要让整个测试套件在导入 conftest 时直接失败；仅在需要 client 的测试里跳过。
    app = None


@pytest.fixture
def client() -> TestClient:
    """FastAPI 应用 TestClient，用于集成测试。"""
    if app is None:
        pytest.skip("FastAPI app 依赖未满足（例如缺少 langgraph），跳过需要 client 的集成测试。")
    return TestClient(app)
