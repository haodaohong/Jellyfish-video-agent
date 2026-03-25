"""LangChain / LangGraph 链与图。"""

from app.chains.prompts import example_prompt, STORY_SUMMARY_TEMPLATE

# `langgraph` 属于可选依赖：在纯单元测试/精简环境中可能未安装。
# 这里不要让 `import app.chains.*` 因为 graphs 而直接失败。
try:
    from app.chains.graphs import example_graph, example_graph_builder
except Exception:  # noqa: BLE001
    example_graph = None
    example_graph_builder = None

__all__ = [
    "example_prompt",
    "STORY_SUMMARY_TEMPLATE",
    "example_graph",
    "example_graph_builder",
]
