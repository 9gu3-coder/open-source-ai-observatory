# OpenScope AI 新手维护指南

这份指南假设你只会最基础的终端操作。每次修改都先在新分支完成，测试通过后再合并到 `main`。

## 每周看一次

1. 打开仓库的 Actions 页面。
2. 查看最近一次 **Update data and deploy Pages** 是否为绿色。
3. 打开公开网页，确认顶部“数据日期”是最近一天。
4. 如果“过期回退”不为 0，打开对应项目的 GitHub 链接检查是否改名或删除。

不需要每天手动操作。定时任务正常时，数据提交和网页发布都会自动完成。

## 添加或替换仓库

1. 编辑 `config/repos.yaml`，保持总数为 15。
2. `full_name` 从 GitHub 地址取得。例如 `https://github.com/owner/repo` 对应 `owner/repo`。
3. 分类优先使用已有的“模型框架”“推理引擎”“智能体框架”“AI 应用”。
4. 运行：

   ```bash
   source .venv/bin/activate
   python -m pytest tests/test_config.py -q
   python -m ruff check .
   ```

5. 提交并推送。主分支工作流会采集新项目；新项目需要逐日积累自己的趋势历史。

不要手工复制另一个仓库的指标作为新项目初始值。

## 仓库改名

GitHub API 可能返回新的规范名称，网页会展示它，但配置仍以 `configured_full_name` 作为历史主键。确认改名稳定后：

1. 更新 `config/repos.yaml` 的 `full_name`。
2. 如需保留旧趋势，在 `data/history.json` 中迁移历史主键前先创建备份和 Pull Request；初学者更安全的做法是让新名称重新积累历史。
3. 运行全量测试。

## 工作流失败

- **pytest 或 Ruff 红色**：代码或数据结构不符合约定。不要绕过测试，查看日志中的第一个失败。
- **Collect GitHub data 红色**：查看失败比例和仓库名称。超过 20% 时网站保持上一版，这是预期保护。
- **git push 红色**：检查仓库 Actions 的 Workflow permissions 是否允许读写，以及分支保护是否允许 GitHub Actions bot 提交数据。
- **Deploy Pages 红色**：确认 Settings → Pages 的 Source 是 GitHub Actions，并检查 `github-pages` environment。
- **定时任务消失**：公开仓库长时间无活动可能停用 schedule。重新启用工作流并手动运行一次。

## 更新依赖

依赖锁在 `uv.lock`，但普通使用可以继续采用 pip。需要升级时：

```bash
UV_CACHE_DIR=/tmp/openscope-uv-cache uv lock --upgrade
UV_CACHE_DIR=/tmp/openscope-uv-cache uv sync --extra dev
python -m pytest -q
python -m ruff check .
```

只在测试全部通过时提交新的 `uv.lock`。

## 恢复上一版

不要删除历史文件，也不要使用强制推送。先在 GitHub Actions 中重新运行上一次失败任务。如果代码提交导致故障，创建一个新的 revert 提交并让 CI 验证；如果只是 GitHub 临时不可用，等待后手动运行即可，上一版 Pages 会继续可用。

## 发布前清单

- [ ] `python -m pytest -q` 全部通过。
- [ ] `python -m ruff check .` 无错误。
- [ ] `python -m openscope.cli build --offline` 成功。
- [ ] `node --check site/app.js` 成功。
- [ ] `git diff --check` 无空白错误。
- [ ] 配置和生成文件中没有令牌、密码或私钥。
- [ ] 页面仍显示“热度反映关注与活跃变化，不代表项目质量”。

