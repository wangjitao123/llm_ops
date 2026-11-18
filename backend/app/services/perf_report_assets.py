"""压测报告的离线化处理。

**为什么需要这个模块**

EvalScope 生成的 HTML 报告通过外链加载 Plotly：

    <script src="https://resources.modelscope.cn/third-part/js/plotly/plotly-2.35.2.min.js">

这个文件约 3.5MB，且托管在 modelscope 资源站。内网/受限网络下浏览器
会长时间卡住甚至超时 —— 报告只有 200KB 左右，但 12 张图全都画不出来。

做法：服务端把 Plotly 下载一次并缓存到 `{perf_outputs}/.assets/`，
下载报告时把它**内联**进 HTML。这样用户拿到的是自包含文件，
双击即可打开，不依赖任何外部网络。

如果服务端也下载不到（完全离线环境），则原样返回，
并在响应头里标记 `X-Report-Offline: false`，前端可据此提示。
"""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 同一份文件的多来源兜底（按顺序尝试）
PLOTLY_URLS: tuple[str, ...] = (
    "https://resources.modelscope.cn/third-part/js/plotly/plotly-2.35.2.min.js",
    "https://cdn.jsdelivr.net/npm/plotly.js@2.35.2/dist/plotly.min.js",
    "https://unpkg.com/plotly.js@2.35.2/dist/plotly.min.js",
)

PLOTLY_FILENAME = "plotly-2.35.2.min.js"

# 匹配 <script src="...plotly..."></script>（属性顺序、引号风格都兼容）
_PLOTLY_TAG_RE = re.compile(
    r'<script\b[^>]*\bsrc\s*=\s*["\'][^"\']*plotly[^"\']*["\'][^>]*>\s*</script>',
    re.IGNORECASE,
)

# 任意 script 块（用于识别/剔除图表初始化代码）
_SCRIPT_BLOCK_RE = re.compile(r"(?s)<script\b[^>]*>(.*?)</script>")

# Plotly 的图表容器
_CHART_DIV_RE = re.compile(
    r'<div\b[^>]*\bclass\s*=\s*["\'][^"\']*plotly-graph-div[^"\']*["\'][^>]*>\s*</div>',
    re.IGNORECASE,
)

# 最小合理体积，防止把错误页当成库缓存下来
_MIN_PLOTLY_BYTES = 500_000


def _cache_path() -> str:
    return os.path.join(settings.perf_outputs_dir, ".assets", PLOTLY_FILENAME)


def _read_cache() -> Optional[str]:
    path = _cache_path()
    try:
        if os.path.getsize(path) >= _MIN_PLOTLY_BYTES:
            with open(path, encoding="utf-8") as f:
                return f.read()
    except OSError:
        return None
    return None


async def get_plotly_source(force_refresh: bool = False) -> Optional[str]:
    """返回 Plotly 的 JS 源码；本地有缓存则直接读，否则下载一次并缓存。

    下载失败返回 None（调用方应降级为原样返回报告）。
    """
    if not force_refresh:
        cached = _read_cache()
        if cached:
            return cached

    import httpx

    path = _cache_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except OSError:
        logger.warning("无法创建报告资源缓存目录: %s", os.path.dirname(path), exc_info=True)

    # 复用平台共享客户端会带 auth 等无关配置，这里用一次性客户端
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
        for url in PLOTLY_URLS:
            try:
                resp = await client.get(url)
            except Exception as e:  # noqa: BLE001 - 换下一个源
                logger.warning("下载 Plotly 失败 %s: %s", url, e)
                continue
            if resp.status_code != 200 or len(resp.content) < _MIN_PLOTLY_BYTES:
                logger.warning(
                    "Plotly 源不可用 %s: status=%s size=%s",
                    url,
                    resp.status_code,
                    len(resp.content),
                )
                continue
            try:
                with open(path, "wb") as f:
                    f.write(resp.content)
            except OSError:
                logger.warning("缓存 Plotly 失败: %s", path, exc_info=True)
            logger.info("Plotly 已缓存到 %s（%d 字节，来源 %s）", path, len(resp.content), url)
            return resp.text

    logger.warning("所有 Plotly 来源均不可用，报告将保留外链（离线打开会卡/白屏）")
    return None


def inline_plotly(html: str, plotly_source: Optional[str]) -> tuple[str, bool]:
    """把报告里的 Plotly 外链替换成内联脚本。

    Returns:
        (处理后的 html, 是否成功内联)
    """
    if not plotly_source:
        return html, False
    if not _PLOTLY_TAG_RE.search(html):
        # 报告已经不含外链（可能上游改了模板），无需处理
        return html, False

    # 库源码里若出现 </script> 会提前闭合标签，转义掉
    safe_source = plotly_source.replace("</script>", "<\\/script>")
    replacement = f"<script>{safe_source}</script>"
    new_html, count = _PLOTLY_TAG_RE.subn(lambda _m: replacement, html, count=1)
    if count == 0:
        return html, False
    return new_html, True


def prepare_report_html(html: str) -> tuple[str, bool]:
    """同步版本：仅使用已缓存的 Plotly 做内联（下载动作由调用方先 await）。

    Returns:
        (处理后的 html, 是否成功内联)
    """
    return inline_plotly(html, _read_cache())


# ============================================================
# 摘要模式：去掉交互图表，只保留数据表格
# ============================================================

_CHART_PLACEHOLDER = (
    '<div style="padding:10px 12px;margin:8px 0;background:#fafafa;'
    'border:1px dashed #d9d9d9;border-radius:6px;color:#8c8c8c;font-size:12px">'
    "［图表已省略］摘要模式不含交互图表，表格数据完整；"
    "如需图表请下载完整版（mode=full）"
    "</div>"
)


def strip_charts(html: str) -> tuple[str, int]:
    """移除 Plotly 库与全部图表初始化代码，只保留表格。

    EvalScope 报告正文只有约 180KB，但要额外背一个 4.5MB 的 Plotly 并渲染
    12 张 SVG 图 —— 打开慢、滚动卡，而大部分信息其实都在表格里。

    Returns:
        (处理后的 html, 移除的图表数量)
    """
    removed = 0

    # 1) 统计图表数量（以 newPlot 调用为准）
    removed = len(re.findall(r"Plotly\.newPlot", html))

    # 2) 去掉图表初始化脚本（含 PLOTLYENV 的那些）
    def _drop_chart_script(m: re.Match[str]) -> str:
        body = m.group(1)
        if "Plotly.newPlot" in body or "PLOTLYENV" in body:
            return ""
        return m.group(0)

    html = _SCRIPT_BLOCK_RE.sub(_drop_chart_script, html)

    # 3) 去掉 Plotly 库本身（外链或内联）
    html = _PLOTLY_TAG_RE.sub("", html)
    html = _SCRIPT_BLOCK_RE.sub(
        lambda m: "" if "plotly.js v" in m.group(1) else m.group(0), html
    )

    # 4) 把图表容器替换成说明占位，保持版面结构
    html = _CHART_DIV_RE.sub(_CHART_PLACEHOLDER, html)

    return html, removed
