const state = {
  teams: [],
  players: [],
  fixtures: [],
  groups: {},
  manifest: {},
  activeView: "overview",
  search: "",
  group: "All",
  team: "All",
};

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const percent = (value) => `${(Number(value || 0) * 100).toFixed(1)}%`;
const number = (value) => Number(value || 0).toLocaleString("en-US");

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
  const [teams, players, predictions, manifest] = await Promise.all([
    loadJson("data/processed/teams.json"),
    loadJson("data/processed/players.json"),
    loadJson("data/processed/predictions.json"),
    loadJson("data/processed/manifest.json"),
  ]);

  state.teams = teams.teams;
  state.players = players.players;
  state.fixtures = predictions.fixtures;
  state.groups = predictions.groups;
  state.predictionsMeta = predictions;
  state.manifest = manifest;

  hydrateControls();
  bindEvents();
  renderAll();
}

function hydrateControls() {
  const groups = ["All", ...Object.keys(state.groups)];
  $("#groupFilter").innerHTML = groups.map((group) => `<option>${group}</option>`).join("");

  const teams = ["All", ...state.teams.map((team) => team.team).sort()];
  $("#teamFilter").innerHTML = teams.map((team) => `<option>${team}</option>`).join("");
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
    : "Unknown";

  $("#generatedAt").textContent = `Generated ${generated}`;
  $("#teamCount").textContent = number(state.manifest.counts?.teams ?? state.teams.length);
  $("#playerCount").textContent = number(state.manifest.counts?.players ?? state.players.length);
  $("#fixtureCount").textContent = number(state.manifest.counts?.fixtures_predicted ?? state.fixtures.length);
  $("#modelAccuracy").textContent = percent(state.manifest.model?.validation_accuracy ?? 0);
  $("#simulationRuns").textContent = `${number(state.predictionsMeta.simulation_runs)} simulations`;

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
    ? teams.map((team, index) => rankRow(index + 1, team.team, `Group ${team.group} | Elo ${team.elo}`, team.simulation?.champion || 0)).join("")
    : empty("No teams match the current filters.");
}

function renderStrengthList() {
  const teams = state.teams.filter((team) => teamPasses(team.team)).slice(0, 10);
  const maxElo = Math.max(...state.teams.map((team) => team.elo));
  const minElo = Math.min(...state.teams.map((team) => team.elo));

  $("#strengthList").innerHTML = teams.length
    ? teams
        .map((team) => {
          const score = (team.elo - minElo) / Math.max(1, maxElo - minElo);
          return rankRow(team.rank, team.team, `Group ${team.group} | Form ${team.recent_form_points}`, score, `${team.elo}`);
        })
        .join("")
    : empty("No teams match the current filters.");
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
          const topPlayers = squad.top_players || [];
          return `
            <article class="squad">
              <h3>${escapeHtml(team.team)}</h3>
              <div class="subtext">Group ${team.group} | Champion ${percent(team.simulation?.champion || 0)}</div>
              <div class="squad-stats">
                <div><span>Avg Age</span><strong>${squad.avg_age ?? "--"}</strong></div>
                <div><span>Caps</span><strong>${number(squad.total_caps)}</strong></div>
                <div><span>Goals</span><strong>${number(squad.total_goals)}</strong></div>
              </div>
              <div class="mini-list">
                ${topPlayers
                  .map(
                    (player) => `
                      <div class="mini-player">
                        <span class="team-name">${escapeHtml(player.player)}</span>
                        <span>${number(player.goals)} G</span>
                      </div>
                    `,
                  )
                  .join("")}
              </div>
            </article>
          `;
        })
        .join("")
    : empty("No squads match the current filters.");
}

function renderFixtures() {
  const fixtures = state.fixtures.filter(fixturePasses);
  $("#fixtureList").innerHTML = fixtures.length
    ? fixtures.map(fixtureCard).join("")
    : empty("No fixtures match the current filters.");
}

function fixtureCard(fixture) {
  const p = fixture.probabilities;
  return `
    <article class="fixture">
      <div>
        <strong>${escapeHtml(fixture.date)}</strong>
        <div class="subtext">Group ${escapeHtml(fixture.group)} | ${escapeHtml(fixture.city)}</div>
      </div>
      <div>
        <div class="match-title">
          <span>${escapeHtml(fixture.home_team)}</span>
          <span class="versus">vs</span>
          <span>${escapeHtml(fixture.away_team)}</span>
        </div>
        <div class="prob-bars">
          ${probLine(fixture.home_team, p.home_win)}
          ${probLine("Draw", p.draw)}
          ${probLine(fixture.away_team, p.away_win)}
        </div>
      </div>
      <div class="pick">Pick: ${escapeHtml(fixture.pick)}<br />${percent(fixture.confidence)}</div>
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
          <h3>Group ${escapeHtml(group)}</h3>
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Team</th>
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
    .join("") || empty("No groups match the current filters.");
}

function renderPlayers() {
  const players = state.players
    .filter(playerPasses)
    .sort((a, b) => b.goals * 4 + b.caps - (a.goals * 4 + a.caps))
    .slice(0, 250);

  $("#playerResultCount").textContent = `${number(players.length)} shown`;
  $("#playerTable").innerHTML = players.length
    ? players
        .map(
          (player) => `
            <tr>
              <td>
                <strong class="player-name">${escapeHtml(player.player)}</strong>
                ${player.captain ? '<span class="captain">C</span>' : ""}
              </td>
              <td>${escapeHtml(player.team)}</td>
              <td>${escapeHtml(player.position)}</td>
              <td>${player.age ?? "--"}</td>
              <td>${number(player.caps)}</td>
              <td>${number(player.goals)}</td>
              <td>${escapeHtml(player.club)}</td>
            </tr>
          `,
        )
        .join("")
    : `<tr><td colspan="7">${empty("No players match the current filters.")}</td></tr>`;
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
        <h1>Data Load Failed</h1>
        <p>${escapeHtml(error.message)}</p>
      </section>
    </main>
  `;
});
