# OpenScope AI 设计说明

OpenScope AI 是一个公开的中文静态网站，每天追踪 15 个代表性 AI 开源仓库，展示仓库基础指标、版本动态、高讨论度 Issue、历史趋势与周报。系统不使用付费 API、不采集访客信息，也不把“热度”描述为项目质量。

## 系统边界

- Python 3.12 采集 GitHub REST API；配置位于 `config/repos.yaml`。
- 历史数据保留 365 天，公开数据生成到 `site/data/dashboard.json`。
- GitHub Actions 每天 06:30（Asia/Shanghai）采集并部署 GitHub Pages，同时支持手动运行和主分支发布。
- 单仓库失败时复用上次成功记录并标记过期；失败数超过仓库总数的 20% 时不写历史、不发布新站点。
- 前端使用原生 HTML、CSS、JavaScript，支持移动端、搜索、分类筛选、趋势榜、仓库详情、版本动态和周报。

## 指标

采集 Stars、Forks、开放 Issue 数、主要语言、许可证、最近推送时间、最新 Release，以及按评论数排序且排除 Pull Request 的 3 个开放 Issue。满 7 个不同日期的快照后显示 7 日 Star 增量；满 30 个快照后显示完整趋势分，否则显示“数据积累中”。趋势分是各仓库横向百分位的加权和：7 日 Star 增量 40%、30 日 Star 增量 20%、推送新鲜度 20%、Release 新鲜度 10%、Issue 讨论度 10%。

## 安全与维护

Actions 只使用仓库内置 `GITHUB_TOKEN`，权限限于读取内容、写入历史数据和发布 Pages。任何生成文件都不得包含令牌。请求最多尝试 3 次并指数退避。README 说明定时任务可能延迟、公开仓库长期无活动可能停用，以及如何手动恢复。

