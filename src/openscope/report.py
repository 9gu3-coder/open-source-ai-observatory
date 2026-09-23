"""Human-readable weekly report generation."""

from __future__ import annotations

from typing import Any


def render_weekly_report(dashboard: dict[str, Any]) -> str:
    """Render a deterministic Markdown report from a dashboard bundle."""

    lines = [
        "# OpenScope AI 周报",
        "",
        f"更新时间：{dashboard.get('generated_at', '未知')}",
        "",
        "> 热度反映关注与活跃变化，不代表项目质量。",
        "",
        "| 项目 | 分类 | 趋势分 | 7 日 Star 变化 | 最新版本 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    for item in dashboard.get("repositories", []):
        score = item.get("trend_score")
        score_text = f"{score:.1f}" if isinstance(score, int | float) else "数据积累中"
        delta = item.get("star_delta_7d")
        delta_text = f"{delta:+d}" if isinstance(delta, int) else "—"
        release = item.get("release")
        release_text = "暂无 Release"
        if isinstance(release, dict):
            tag = release.get("tag_name", "Release")
            url = release.get("url")
            release_text = f"[{tag}]({url})" if isinstance(url, str) else str(tag)
        lines.append(
            f"| [{item['display_name']}]({item['source_url']}) | {item['category']} | "
            f"{score_text} | {delta_text} | {release_text} |"
        )
    lines.extend(["", "数据来源：各项目的 GitHub 公共页面与 GitHub REST API。", ""])
    return "\n".join(lines)

