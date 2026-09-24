# OpenScope AI 架构说明

## 数据流

```text
config/repos.yaml
       │
       ▼
GitHubClient ── GitHub REST API
       │  每个仓库独立采集与重试
       ▼
run_pipeline ── 失败比例与旧数据回退
       │
       ├── data/history.json（最多 365 天）
       ├── site/data/dashboard.json（浏览器公开数据）
       └── site/reports/YYYY-Www.md（周报）
                              │
                              ▼
                    原生 HTML/CSS/JavaScript
                              │
                              ▼
                         GitHub Pages
```

浏览器不会调用 GitHub API，也不会看到 `GITHUB_TOKEN`。它只读取同一 Pages 站点下的静态 JSON。

## 模块边界

- `config.py`：把 YAML 转成经过验证且不可变的 `RepoConfig`。
- `github.py`：负责 HTTP、三次尝试、响应验证以及 GitHub 数据标准化。
- `models.py`：定义可序列化的仓库、Release 和 Issue 记录。
- `history.py`：去重每日快照、裁剪 365 天、计算增量和百分位趋势分。
- `report.py`：把公开 dashboard 数据生成中文 Markdown 周报。
- `pipeline.py`：编排采集、失败阈值、旧数据回退和原子文件替换。
- `cli.py`：提供联网 `collect` 和无网络 `build --offline` 两个入口。
- `site/`：无构建工具的静态前端，所有远程文字都通过 `textContent` 写入页面。

## 评分方法

完整趋势分只在积累 30 个不同日期的快照后出现。每项指标先在当前 15 个仓库之间转换为 0～100 的百分位，数值相同者取得平均名次，再按以下比例求和：

- 7 日 Star 增量：40%
- 30 日 Star 增量：20%
- 最近推送时间：20%
- 最近 Release 时间：10%
- 高讨论度 Issue 评论数：10%

单仓库观察时百分位为 100。趋势分只适合比较当前观察清单，不适合跨网站或跨时间直接比较。

## 失败与写入策略

每个 HTTP 请求最多尝试三次，重试等待为 1 秒和 2 秒。429、GitHub 明确的速率限制、5xx、超时和传输错误可以重试；无效 JSON 和缺少必需字段会直接把该仓库判为失败。

如果失败仓库不超过总数的 20%，系统优先复用上一份成功记录并设置 `stale: true`。如果失败比例大于 20%，`run_pipeline` 在写文件之前抛出错误，Actions 因非零退出码停止，后续提交和部署不会运行。

每个输出先写入目标目录中的临时文件，刷新到磁盘后通过 `os.replace` 替换，因此单个 JSON 或报告不会出现半写入内容。更新工作流只有在采集、测试和代码检查都成功后才提交数据并上传 Pages artifact。

## GitHub Actions

- `ci.yml`：每次推送和 Pull Request 运行 pytest、Ruff 和离线构建。
- `update-pages.yml`：主分支推送、手动触发或每天 06:30（Asia/Shanghai）运行；成功后提交数据并部署 Pages。
- `deploy` job 依赖 `update` job，因此采集失败无法发布新 artifact。

