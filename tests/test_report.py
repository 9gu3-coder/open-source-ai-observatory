from openscope.report import render_weekly_report


def test_weekly_report_links_sources_and_explains_heat_is_not_quality() -> None:
    dashboard = {
        "generated_at": "2026-09-24T00:00:00Z",
        "status": "ready",
        "repositories": [
            {
                "display_name": "Repo",
                "configured_full_name": "owner/repo",
                "category": "工具",
                "source_url": "https://github.com/owner/repo",
                "trend_score": 88.5,
                "star_delta_7d": 12,
                "release": None,
                "stale": False,
            }
        ],
    }

    report = render_weekly_report(dashboard)

    assert "[Repo](https://github.com/owner/repo)" in report
    assert "热度反映关注与活跃变化，不代表项目质量" in report
    assert "88.5" in report
    assert "暂无 Release" in report

