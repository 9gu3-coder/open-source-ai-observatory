const state = { data: null, query: "", category: "" };

const byId = (id) => document.getElementById(id);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN", { notation: value > 9999 ? "compact" : "standard" }).format(value ?? 0);
}

function metric(label, value) {
  const box = node("div", "metric");
  box.append(node("strong", "", value), node("span", "", label));
  return box;
}

function link(label, href, className = "") {
  const anchor = node("a", className, label);
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noreferrer";
  return anchor;
}

function showDetails(repo) {
  const dialog = byId("repo-dialog");
  const content = byId("dialog-content");
  content.replaceChildren();
  const title = node("h2", "", repo.display_name);
  title.id = "dialog-title";
  content.append(node("p", "category", repo.category), title, node("p", "repo-name", repo.full_name));
  content.append(node("p", "description", repo.description || "该项目暂未提供简介。"));
  content.append(link("查看 GitHub 原始页面 ↗", repo.source_url, "source-button"));

  const releaseTitle = node("h3", "", "最新 Release");
  const release = repo.release
    ? link(`${repo.release.tag_name} · ${repo.release.name}`, repo.release.url)
    : node("p", "description", "暂无 Release");
  content.append(releaseTitle, release);

  content.append(node("h3", "", "高讨论度 Issue"));
  if (!repo.issues?.length) {
    content.append(node("p", "description", "暂无高讨论度 Issue"));
  } else {
    const list = node("ul", "detail-list");
    repo.issues.forEach((issue) => {
      const item = node("li");
      item.append(link(`#${issue.number} ${issue.title}`, issue.url));
      item.append(node("small", "description", ` · ${issue.comments} 条评论`));
      list.append(item);
    });
    content.append(list);
  }
  dialog.showModal();
}

function card(repo) {
  const article = node("article", "repo-card");
  const top = node("div", "card-top");
  top.append(node("span", "category", repo.category));
  if (repo.stale) top.append(node("span", "stale", "数据可能过期"));
  article.append(top, node("h3", "", repo.display_name), node("p", "repo-name", repo.full_name));
  article.append(node("p", "description", repo.description || repo.reason));

  const metrics = node("div", "metrics");
  const trend = repo.trend_score == null ? "积累中" : repo.trend_score.toFixed(1);
  const delta = repo.star_delta_7d == null ? "—" : `${repo.star_delta_7d >= 0 ? "+" : ""}${repo.star_delta_7d}`;
  metrics.append(metric("Stars", formatNumber(repo.stars)), metric("7 日变化", delta), metric("趋势分", trend));
  article.append(metrics);

  const actions = node("div", "card-actions");
  const button = node("button", "detail-button", "查看详情");
  button.type = "button";
  button.addEventListener("click", () => showDetails(repo));
  actions.append(button, link("GitHub ↗", repo.source_url, "repo-link"));
  article.append(actions);
  return article;
}

function renderRepositories() {
  const repositories = state.data?.repositories || [];
  const query = state.query.toLocaleLowerCase("zh-CN");
  const visible = repositories.filter((repo) => {
    const haystack = [repo.display_name, repo.full_name, repo.language, repo.description].filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
    return (!query || haystack.includes(query)) && (!state.category || repo.category === state.category);
  });
  byId("repo-grid").replaceChildren(...visible.map(card));
  byId("result-count").textContent = `${visible.length} / ${repositories.length} 个项目`;
  byId("empty-state").hidden = visible.length !== 0;
}

function renderSummary(data) {
  const items = [
    [data.repositories.length, "追踪项目"],
    [data.snapshot_days, "历史天数"],
    [data.collection?.stale || 0, "过期回退"],
    [data.latest_date || "待采集", "数据日期"],
  ];
  byId("summary").replaceChildren(...items.map(([value, label]) => {
    const item = node("div", "summary-item");
    item.append(node("span", "summary-value", String(value)), node("span", "summary-label", label));
    return item;
  }));
}

function renderCategories(data) {
  const select = byId("category-filter");
  [...new Set(data.repositories.map((repo) => repo.category))].sort().forEach((category) => {
    const option = node("option", "", category);
    option.value = category;
    select.append(option);
  });
}

function renderReleases(data) {
  const releases = data.repositories.filter((repo) => repo.release).slice(0, 8);
  const feed = byId("release-feed");
  if (!releases.length) {
    feed.append(node("p", "description", "暂无 Release，首次采集后会在这里显示。"));
    return;
  }
  feed.replaceChildren(...releases.map((repo) => {
    const item = node("div", "feed-item");
    const text = node("div");
    text.append(link(repo.display_name, repo.source_url), node("small", "", ` · ${repo.release.tag_name}`));
    item.append(text, link("查看 ↗", repo.release.url, "repo-link"));
    return item;
  }));
}

function renderWeekly(data) {
  const container = byId("weekly-report");
  if (!data.repositories.length) {
    container.append(node("p", "", "等待首次自动采集。数据到达后，这里会生成本周趋势摘要。"));
    return;
  }
  container.append(node("p", "", `当前已积累 ${data.snapshot_days} 天数据。趋势分需要 30 天历史，7 日变化需要 7 天历史。`));
  const list = node("ol");
  data.repositories.slice(0, 5).forEach((repo) => {
    const item = node("li");
    item.append(link(repo.display_name, repo.source_url));
    const score = repo.trend_score == null ? "数据积累中" : `趋势分 ${repo.trend_score.toFixed(1)}`;
    item.append(document.createTextNode(` · ${score}`));
    list.append(item);
  });
  container.append(list);
  if (data.weekly_report?.path) container.append(link("打开完整 Markdown 周报 ↗", data.weekly_report.path));
}

async function start() {
  try {
    const response = await fetch("data/dashboard.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = await response.json();
    renderSummary(state.data);
    renderCategories(state.data);
    renderRepositories();
    renderReleases(state.data);
    renderWeekly(state.data);
  } catch (error) {
    byId("repo-grid").append(node("p", "empty-state", `数据加载失败：${error.message}`));
  }
}

byId("search-input").addEventListener("input", (event) => { state.query = event.target.value; renderRepositories(); });
byId("category-filter").addEventListener("change", (event) => { state.category = event.target.value; renderRepositories(); });
byId("repo-dialog").querySelector(".dialog-close").addEventListener("click", () => byId("repo-dialog").close());
start();

