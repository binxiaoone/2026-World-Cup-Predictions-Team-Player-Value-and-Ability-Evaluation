const state = {
  teams: [],
  players: [],
  media: {},
  fixtures: [],
  groups: {},
  manifest: {},
  activeView: "overview",
  search: "",
  group: "All",
  team: "All",
  lang: localStorage.getItem("worldcup-lang") || "zh",
};

const I18N = {
  zh: {
    appTitle: "世界杯 AI 预测仪表盘",
    loadingData: "正在加载数据...",
    generated: "生成时间",
    teams: "球队",
    players: "球员",
    fixtures: "赛程",
    validationAccuracy: "验证准确率",
    search: "搜索",
    searchPlaceholder: "球队、球员、俱乐部...",
    group: "小组",
    groups: "小组",
    team: "球队",
    overview: "总览",
    championProbability: "冠军概率",
    teamStrength: "球队强度",
    eloRecent: "Elo + 近期状态",
    featuredSquads: "重点球队阵容",
    topExperience: "国家队经验最多",
    matchPredictions: "比赛预测",
    winDrawLoss: "主胜 / 平局 / 客胜",
    playerDatabase: "球员数据库",
    photo: "照片",
    player: "球员",
    position: "位置",
    overall: "综合",
    marketValue: "身价",
    squadValue: "总身价",
    valueCoverage: "覆盖率",
    noValue: "暂无",
    age: "年龄",
    caps: "出场",
    goals: "进球",
    club: "俱乐部",
    links: "链接",
    all: "全部",
    simulations: "次模拟",
    champion: "冠军",
    form: "状态",
    avgAge: "平均年龄",
    shown: "条展示",
    noTeams: "没有球队匹配当前筛选。",
    noSquads: "没有阵容匹配当前筛选。",
    noFixtures: "没有赛程匹配当前筛选。",
    noGroups: "没有小组匹配当前筛选。",
    noPlayers: "没有球员匹配当前筛选。",
    source: "百科",
    hupu: "虎扑",
    hupuSearch: "虎扑搜索",
    fallbackImage: "备用头像",
    ratingNote: "6星能力为模型估算，基于出场、进球、年龄、位置、球队 Elo 和近期状态。",
    photoAlt: "照片",
    pick: "预测",
    draw: "平局",
    homeWin: "主胜",
    awayWin: "客胜",
    footerText: "教育演示预测，不构成投注建议。数据来源见",
    dataLoadFailed: "数据加载失败",
    attack: "进攻",
    creativity: "创造",
    defense: "防守",
    experience: "经验",
    physical: "身体",
    impact: "影响",
    atk: "进",
    cre: "创",
    def: "防",
    exp: "经",
    phy: "体",
    imp: "影",
  },
  en: {
    appTitle: "AI Prediction Dashboard",
    loadingData: "Loading data...",
    generated: "Generated",
    teams: "Teams",
    players: "Players",
    fixtures: "Fixtures",
    validationAccuracy: "Validation Accuracy",
    search: "Search",
    searchPlaceholder: "Team, player, club...",
    group: "Group",
    groups: "Groups",
    team: "Team",
    overview: "Overview",
    championProbability: "Champion Probability",
    teamStrength: "Team Strength",
    eloRecent: "Elo + recent form",
    featuredSquads: "Featured Squads",
    topExperience: "Top international experience",
    matchPredictions: "Match Predictions",
    winDrawLoss: "Home win / draw / away win",
    playerDatabase: "Player Database",
    photo: "Photo",
    player: "Player",
    position: "Pos",
    overall: "Overall",
    marketValue: "Market Value",
    squadValue: "Squad Value",
    valueCoverage: "Coverage",
    noValue: "N/A",
    age: "Age",
    caps: "Caps",
    goals: "Goals",
    club: "Club",
    links: "Links",
    all: "All",
    simulations: "simulations",
    champion: "Champion",
    form: "Form",
    avgAge: "Avg Age",
    shown: "shown",
    noTeams: "No teams match the current filters.",
    noSquads: "No squads match the current filters.",
    noFixtures: "No fixtures match the current filters.",
    noGroups: "No groups match the current filters.",
    noPlayers: "No players match the current filters.",
    source: "Wiki",
    hupu: "Hupu",
    hupuSearch: "Hupu search",
    fallbackImage: "Fallback image",
    ratingNote: "6-star model estimate from caps, goals, age, position, team Elo, and recent form.",
    photoAlt: "photo",
    pick: "Pick",
    draw: "Draw",
    homeWin: "Home win",
    awayWin: "Away win",
    footerText: "Educational forecast only. Not betting advice. Data sources are listed in",
    dataLoadFailed: "Data Load Failed",
    attack: "Attack",
    creativity: "Creativity",
    defense: "Defense",
    experience: "Experience",
    physical: "Physical",
    impact: "Impact",
    atk: "ATK",
    cre: "CRE",
    def: "DEF",
    exp: "EXP",
    phy: "PHY",
    imp: "IMP",
  },
};

const HUPU_ALIASES = {
  "Lionel Messi": "梅西",
  "Cristiano Ronaldo": "C罗",
  "Kylian Mbappé": "姆巴佩",
  Neymar: "内马尔",
  "Erling Haaland": "哈兰德",
  "Harry Kane": "凯恩",
  "Mohamed Salah": "萨拉赫",
  "Son Heung-min": "孙兴慜",
  "Luka Modrić": "莫德里奇",
  "Kevin De Bruyne": "德布劳内",
  "Romelu Lukaku": "卢卡库",
  "Sadio Mané": "马内",
  "Memphis Depay": "德佩",
  "Virgil van Dijk": "范戴克",
  "Rodri": "罗德里",
  "Bruno Fernandes": "B费",
  "Vinícius Júnior": "维尼修斯",
  "Jude Bellingham": "贝林厄姆",
  "Lautaro Martínez": "劳塔罗",
  "Antoine Griezmann": "格列兹曼",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const percent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const number = (value) => Number(value || 0).toLocaleString(state.lang === "zh" ? "zh-CN" : "en-US");

function t(key) {
  return I18N[state.lang][key] ?? I18N.en[key] ?? key;
}

function normalize(value) {
  return String(value || "").toLowerCase();
}

function loadJson(path) {
  return fetch(path).then((response) => {
    if (!response.ok) {
      throw new Error(`Unable to load ${path}: ${response.status}`);
    }
    return response.json();
  });
}

async function bootstrap() {
  const [teams, players, predictions, manifest, media] = await Promise.all([
    loadJson("data/processed/teams.json"),
    loadJson("data/processed/players.json"),
    loadJson("data/processed/predictions.json"),
    loadJson("data/processed/manifest.json"),
    loadJson("data/processed/player_media.json").catch(() => ({ media: [] })),
  ]);

  state.teams = teams.teams;
  state.players = players.players;
  state.media = Object.fromEntries((media.media || []).map((item) => [item.key, item]));
  state.fixtures = predictions.fixtures;
  state.groups = predictions.groups;
  state.predictionsMeta = predictions;
  state.manifest = manifest;

  hydrateControls();
  bindEvents();
  applyStaticTranslations();
  renderAll();
}

function hydrateControls() {
  const groups = ["All", ...Object.keys(state.groups)];
  $("#groupFilter").innerHTML = groups
    .map((group) => `<option value="${escapeHtml(group)}">${group === "All" ? t("all") : group}</option>`)
    .join("");
  $("#groupFilter").value = state.group;

  const teams = ["All", ...state.teams.map((team) => team.team).sort()];
  $("#teamFilter").innerHTML = teams
    .map((team) => `<option value="${escapeHtml(team)}">${team === "All" ? t("all") : escapeHtml(team)}</option>`)
    .join("");
  $("#teamFilter").value = state.team;
}

function bindEvents() {
  $("#searchInput").addEventListener("input", (event) => {
    state.search = event.target.value.trim();
    renderFilteredViews();
  });

  $("#groupFilter").addEventListener("change", (event) => {
    state.group = event.target.value;
    renderFilteredViews();
  });

  $("#teamFilter").addEventListener("change", (event) => {
    state.team = event.target.value;
    renderFilteredViews();
  });

  $$(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      state.activeView = button.dataset.view;
      $$(".tab").forEach((tab) => tab.classList.toggle("is-active", tab === button));
      $$(".view").forEach((view) => view.classList.toggle("is-active", view.id === state.activeView));
    });
  });

  $$(".lang-btn").forEach((button) => {
    button.addEventListener("click", () => setLanguage(button.dataset.lang));
  });
}

function applyStaticTranslations() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.title = state.lang === "zh" ? "世界杯 AI 预测仪表盘" : "World Cup AI Predictor";
  $$("[data-i18n]").forEach((element) => {
    element.textContent = t(element.dataset.i18n);
  });
  $$("[data-i18n-placeholder]").forEach((element) => {
    element.setAttribute("placeholder", t(element.dataset.i18nPlaceholder));
  });
  $$(".lang-btn").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.lang === state.lang);
  });
}

function setLanguage(lang) {
  if (!I18N[lang] || state.lang === lang) return;
  state.lang = lang;
  localStorage.setItem("worldcup-lang", lang);
  applyStaticTranslations();
  hydrateControls();
  renderAll();
}

function teamPasses(teamName) {
  const team = state.teams.find((item) => item.team === teamName);
  if (!team) return false;
  if (state.group !== "All" && team.group !== state.group) return false;
  if (state.team !== "All" && team.team !== state.team) return false;
  if (!state.search) return true;
  return normalize(team.team).includes(normalize(state.search));
}

function playerPasses(player) {
  if (state.group !== "All" && player.group !== state.group) return false;
  if (state.team !== "All" && player.team !== state.team) return false;
  if (!state.search) return true;
  const haystack = [player.player, player.team, player.club, player.position].map(normalize).join(" ");
  return haystack.includes(normalize(state.search));
}

function playerKey(player) {
  return `${player.team}::${player.player}`;
}

function mediaFor(player) {
  return state.media[playerKey(player)] || {};
}

function initials(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function hupuQuery(player) {
  return HUPU_ALIASES[player.player] || `${player.player} ${player.team} 足球`;
}

function hupuUrl(player) {
  return `https://bbs.hupu.com/search?q=${encodeURIComponent(hupuQuery(player))}`;
}

function playerLinks(player, compact = false) {
  const media = mediaFor(player);
  const wiki = media.page_url
    ? `<a class="${compact ? "link-chip compact" : "link-chip"}" href="${escapeHtml(media.page_url)}" target="_blank" rel="noreferrer">${t("source")}</a>`
    : "";
  const hupu = `<a class="${compact ? "link-chip compact hupu" : "link-chip hupu"}" href="${escapeHtml(hupuUrl(player))}" target="_blank" rel="noreferrer">${t("hupu")}</a>`;
  return `<div class="external-links">${wiki}${hupu}</div>`;
}

function marketLabel(player) {
  return player.market_value?.label || t("noValue");
}

function teamMarketValue(team) {
  return team.squad?.market_value || {};
}

function fixturePasses(fixture) {
  if (state.group !== "All" && fixture.group !== state.group) return false;
  if (state.team !== "All" && ![fixture.home_team, fixture.away_team].includes(state.team)) return false;
  if (!state.search) return true;
  const haystack = [fixture.home_team, fixture.away_team, fixture.city, fixture.group].map(normalize).join(" ");
  return haystack.includes(normalize(state.search));
}

function renderAll() {
  const generated = state.manifest.generated_at
    ? new Date(state.manifest.generated_at).toLocaleString()
    : "--";

  $("#generatedAt").textContent = `${t("generated")} ${generated}`;
  $("#teamCount").textContent = number(state.manifest.counts?.teams ?? state.teams.length);
  $("#playerCount").textContent = number(state.manifest.counts?.players ?? state.players.length);
  $("#fixtureCount").textContent = number(state.manifest.counts?.fixtures_predicted ?? state.fixtures.length);
  $("#modelAccuracy").textContent = percent(state.manifest.model?.validation_accuracy ?? 0);
  $("#simulationRuns").textContent = `${number(state.predictionsMeta.simulation_runs)} ${t("simulations")}`;

  renderFilteredViews();
}

function renderFilteredViews() {
  renderChampionList();
  renderStrengthList();
  renderFeaturedSquads();
  renderFixtures();
  renderGroups();
  renderPlayers();
}

function renderChampionList() {
  const teams = state.teams
    .filter((team) => teamPasses(team.team))
    .sort((a, b) => (b.simulation?.champion || 0) - (a.simulation?.champion || 0))
    .slice(0, 10);

  $("#championList").innerHTML = teams.length
    ? teams.map((team, index) => rankRow(index + 1, team.team, `${t("group")} ${team.group} | Elo ${team.elo}`, team.simulation?.champion || 0)).join("")
    : empty(t("noTeams"));
}

function renderStrengthList() {
  const teams = state.teams.filter((team) => teamPasses(team.team)).slice(0, 10);
  const maxElo = Math.max(...state.teams.map((team) => team.elo));
  const minElo = Math.min(...state.teams.map((team) => team.elo));

  $("#strengthList").innerHTML = teams.length
    ? teams
        .map((team) => {
          const score = (team.elo - minElo) / Math.max(1, maxElo - minElo);
          return rankRow(team.rank, team.team, `${t("group")} ${team.group} | ${t("form")} ${team.recent_form_points}`, score, `${team.elo}`);
        })
        .join("")
    : empty(t("noTeams"));
}

function rankRow(rank, title, subtitle, value, label = percent(value)) {
  const width = Math.max(2, Math.min(100, Number(value || 0) * 100));
  return `
    <div class="rank-row">
      <div class="rank-no">${rank}</div>
      <div class="rank-main">
        <span class="team-name">${escapeHtml(title)}</span>
        <span class="subtext">${escapeHtml(subtitle)}</span>
        <div class="bar"><span style="width:${width}%"></span></div>
      </div>
      <div class="prob">${escapeHtml(label)}</div>
    </div>
  `;
}

function renderFeaturedSquads() {
  const teams = state.teams
    .filter((team) => teamPasses(team.team))
    .sort((a, b) => (b.squad?.total_caps || 0) - (a.squad?.total_caps || 0))
    .slice(0, 6);

  $("#featuredSquads").innerHTML = teams.length
    ? teams
        .map((team) => {
          const squad = team.squad || {};
          const market = teamMarketValue(team);
          const topPlayers = squad.top_players || [];
          return `
            <article class="squad">
              <h3>${escapeHtml(team.team)}</h3>
              <div class="subtext">${t("group")} ${team.group} | ${t("champion")} ${percent(team.simulation?.champion || 0)}</div>
              <div class="squad-stats">
                <div><span>${t("squadValue")}</span><strong>${market.total_label || t("noValue")}</strong></div>
                <div><span>${t("valueCoverage")}</span><strong>${percent(market.coverage || 0)}</strong></div>
                <div><span>${t("avgAge")}</span><strong>${squad.avg_age ?? "--"}</strong></div>
              </div>
              <div class="subtext">${t("caps")} ${number(squad.total_caps)} | ${t("goals")} ${number(squad.total_goals)}</div>
              <div class="mini-list">
                ${topPlayers
                  .map(
                    (player) => `
                      <div class="mini-player">
                        <span class="team-name">${escapeHtml(player.player)}</span>
                        <span>${number(player.goals)} ${state.lang === "zh" ? "球" : "G"}</span>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            </article>
          `;
        })
        .join("")
    : empty(t("noSquads"));
}

function renderFixtures() {
  const fixtures = state.fixtures.filter(fixturePasses);
  $("#fixtureList").innerHTML = fixtures.length
    ? fixtures.map(fixtureCard).join("")
    : empty(t("noFixtures"));
}

function fixtureCard(fixture) {
  const p = fixture.probabilities;
  return `
    <article class="fixture">
      <div>
        <strong>${escapeHtml(fixture.date)}</strong>
        <div class="subtext">${t("group")} ${escapeHtml(fixture.group)} | ${escapeHtml(fixture.city)}</div>
      </div>
      <div>
        <div class="match-title">
          <span>${escapeHtml(fixture.home_team)}</span>
          <span class="versus">vs</span>
          <span>${escapeHtml(fixture.away_team)}</span>
        </div>
        <div class="prob-bars">
          ${probLine(fixture.home_team, p.home_win)}
          ${probLine(t("draw"), p.draw)}
          ${probLine(fixture.away_team, p.away_win)}
        </div>
      </div>
      <div class="pick">${t("pick")}: ${escapeHtml(fixture.pick)}<br />${percent(fixture.confidence)}</div>
    </article>
  `;
}

function probLine(label, value) {
  return `
    <div class="prob-line">
      <span>${escapeHtml(label)}</span>
      <div class="bar"><span style="width:${Math.max(2, Number(value || 0) * 100)}%"></span></div>
      <strong>${percent(value)}</strong>
    </div>
  `;
}

function renderGroups() {
  const entries = Object.entries(state.groups).filter(([group]) => state.group === "All" || state.group === group);
  $("#groupTables").innerHTML = entries
    .map(([group, rows]) => {
      const filteredRows = rows.filter((row) => teamPasses(row.team));
      if (!filteredRows.length) return "";
      return `
        <section class="group-table">
          <h3>${t("group")} ${escapeHtml(group)}</h3>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>${t("team")}</th>
                <th>xPts</th>
                <th>xW</th>
              </tr>
            </thead>
            <tbody>
              ${filteredRows
                .map(
                  (row) => `
                    <tr>
                      <td>${row.rank}</td>
                      <td><strong>${escapeHtml(row.team)}</strong></td>
                      <td>${row.expected_points.toFixed(2)}</td>
                      <td>${row.expected_wins.toFixed(2)}</td>
                    </tr>
                  `,
                )
                .join("")}
            </tbody>
          </table>
        </section>
      `;
    })
    .join("") || empty(t("noGroups"));
}

function renderPlayers() {
  const players = state.players
    .filter(playerPasses)
    .sort((a, b) => b.goals * 4 + b.caps - (a.goals * 4 + a.caps))
    .slice(0, 250);

  renderPlayerCards(players.slice(0, 6));
  $("#playerResultCount").textContent = `${number(players.length)} ${t("shown")}`;
  $("#playerTable").innerHTML = players.length
    ? players
        .map(
          (player) => `
            <tr>
              <td>${playerAvatar(player, "thumb")}</td>
              <td>
                <a class="player-name table-player-link" href="${escapeHtml(hupuUrl(player))}" target="_blank" rel="noreferrer">${escapeHtml(player.player)}</a>
                ${player.captain ? '<span class="captain">C</span>' : ""}
              </td>
              <td>${escapeHtml(player.team)}</td>
              <td>${escapeHtml(player.position)}</td>
              <td><strong>${player.abilities?.overall ?? "--"}</strong></td>
              <td><strong>${escapeHtml(marketLabel(player))}</strong></td>
              <td>${player.age ?? "--"}</td>
              <td>${number(player.caps)}</td>
              <td>${number(player.goals)}</td>
              <td>${escapeHtml(player.club)}</td>
              <td>${playerLinks(player, true)}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="11">${empty(t("noPlayers"))}</td></tr>`;
}

function renderPlayerCards(players) {
  $("#playerCards").innerHTML = players.length
    ? players.map(playerCard).join("")
    : empty(t("noPlayers"));
}

function playerCard(player) {
  return `
    <article class="player-card">
      <div class="player-card-media">
        ${playerAvatar(player, "large")}
        <div>
          <span class="subtext">${t("group")} ${escapeHtml(player.group)} | ${escapeHtml(player.position)}</span>
          <h3>${escapeHtml(player.player)}${player.captain ? '<span class="captain">C</span>' : ""}</h3>
          <p>${escapeHtml(player.team)} | ${escapeHtml(player.club)}</p>
          <div class="player-facts">
            <div class="overall">${t("overall")} <strong>${player.abilities?.overall ?? "--"}</strong><span>/ 6</span></div>
            <div class="value-pill">${t("marketValue")} <strong>${escapeHtml(marketLabel(player))}</strong></div>
          </div>
          ${playerLinks(player)}
        </div>
      </div>
      ${radarSvg(player.abilities?.scores)}
      <p class="rating-note">${t("ratingNote")}</p>
    </article>
  `;
}

function playerAvatar(player, size) {
  const media = mediaFor(player);
  const label = `${player.player} ${t("photoAlt")}`;
  if (media.image_url) {
    return `<img class="avatar avatar-${size}" src="${escapeHtml(media.image_url)}" alt="${escapeHtml(label)}" loading="lazy" referrerpolicy="no-referrer" />`;
  }
  return `<div class="avatar avatar-${size} avatar-fallback" aria-label="${escapeHtml(label)}">${escapeHtml(initials(player.player))}</div>`;
}

function radarSvg(scores = {}) {
  const labels = [
    ["attack", t("atk"), t("attack")],
    ["creativity", t("cre"), t("creativity")],
    ["defense", t("def"), t("defense")],
    ["experience", t("exp"), t("experience")],
    ["physical", t("phy"), t("physical")],
    ["impact", t("imp"), t("impact")],
  ];
  const cx = 110;
  const cy = 100;
  const maxR = 70;
  const angle = (index) => -Math.PI / 2 + (Math.PI * 2 * index) / labels.length;
  const point = (index, radius) => {
    const a = angle(index);
    return [cx + Math.cos(a) * radius, cy + Math.sin(a) * radius];
  };
  const polygon = labels
    .map(([key], index) => {
      const value = Math.max(1, Math.min(6, Number(scores[key] || 1)));
      return point(index, (value / 6) * maxR).map((v) => v.toFixed(1)).join(",");
    })
    .join(" ");
  const grid = [2, 4, 6]
    .map((level) => {
      const points = labels.map((_, index) => point(index, (level / 6) * maxR).map((v) => v.toFixed(1)).join(",")).join(" ");
      return `<polygon points="${points}" class="radar-grid" />`;
    })
    .join("");
  const axes = labels
    .map(([key, label], index) => {
      const [x, y] = point(index, maxR + 18);
      const [x2, y2] = point(index, maxR);
      return `
        <line x1="${cx}" y1="${cy}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}" class="radar-axis" />
        <text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="middle" dominant-baseline="middle">${label}</text>
      `;
    })
    .join("");
  const dots = labels
    .map(([key], index) => {
      const value = Math.max(1, Math.min(6, Number(scores[key] || 1)));
      const [x, y] = point(index, (value / 6) * maxR);
      const fullLabel = labels[index][2];
      return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3" class="radar-dot"><title>${fullLabel}: ${value.toFixed(1)}/6</title></circle>`;
    })
    .join("");

  return `
    <svg class="radar" viewBox="0 0 220 200" role="img" aria-label="${escapeHtml(t("ratingNote"))}">
      ${grid}
      ${axes}
      <polygon points="${polygon}" class="radar-fill" />
      <polyline points="${polygon} ${polygon.split(" ")[0]}" class="radar-line" />
      ${dots}
    </svg>
  `;
}

function empty(message) {
  return `<div class="empty">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

bootstrap().catch((error) => {
  console.error(error);
  document.body.innerHTML = `
    <main>
      <section class="panel">
        <h1>${escapeHtml(t("dataLoadFailed"))}</h1>
        <p>${escapeHtml(error.message)}</p>
      </section>
    </main>
  `;
});
