const DATA_URL = "data.json";

let allUsers = [];
let currentTab = "messages";
let searchTerm = "";

const leaderboardEl = document.getElementById("leaderboard");
const emptyStateEl = document.getElementById("empty-state");
const searchEl = document.getElementById("search");

function formatDuration(totalSeconds) {
  if (!totalSeconds) return "0m";
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatDate(isoString) {
  if (!isoString) return "unbekannt";
  const d = new Date(isoString.endsWith("Z") ? isoString : isoString + "Z");
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" });
}

function formatRelativeUpdate(isoString) {
  if (!isoString) return "–";
  const d = new Date(isoString);
  const diffMin = Math.round((Date.now() - d.getTime()) / 60000);
  if (diffMin < 1) return "gerade eben";
  if (diffMin < 60) return `vor ${diffMin} Min.`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `vor ${diffH} Std.`;
  const diffD = Math.round(diffH / 24);
  return `vor ${diffD} Tg.`;
}

function initials(name) {
  return (name || "?").replace(/#\d+$/, "").trim().slice(0, 2).toUpperCase();
}

const TAB_CONFIG = {
  messages: {
    sort: (a, b) => b.message_count - a.message_count,
    value: (u) => u.message_count,
    display: (u) => `${u.message_count.toLocaleString("de-DE")} <small>Nachrichten</small>`,
    barMax: (users) => Math.max(1, ...users.map((u) => u.message_count)),
    barValue: (u) => u.message_count,
  },
  voice: {
    sort: (a, b) => b.voice_seconds - a.voice_seconds,
    value: (u) => u.voice_seconds,
    display: (u) => `${formatDuration(u.voice_seconds)}`,
    barMax: (users) => Math.max(1, ...users.map((u) => u.voice_seconds)),
    barValue: (u) => u.voice_seconds,
  },
  joins: {
    sort: (a, b) => {
      if (!a.joined_at) return 1;
      if (!b.joined_at) return -1;
      return new Date(a.joined_at) - new Date(b.joined_at);
    },
    value: () => null,
    display: (u) => `${formatDate(u.joined_at)}`,
    barMax: null,
    barValue: null,
  },
};

function render() {
  const cfg = TAB_CONFIG[currentTab];
  let users = allUsers.filter((u) =>
    u.username.toLowerCase().includes(searchTerm.toLowerCase())
  );
  users = [...users].sort(cfg.sort);

  leaderboardEl.innerHTML = "";
  emptyStateEl.hidden = users.length > 0;

  const barMax = cfg.barMax ? cfg.barMax(users) : null;

  users.forEach((u, i) => {
    const rank = i + 1;
    const li = document.createElement("li");
    li.className = "row";

    const rankEl = document.createElement("span");
    rankEl.className = "rank" + (rank === 1 ? " gold" : rank === 2 ? " silver" : rank === 3 ? " bronze" : "");
    rankEl.textContent = rank <= 3 ? ["🥇", "🥈", "🥉"][rank - 1] : `#${rank}`;

    let avatarEl;
    if (u.avatar_url) {
      avatarEl = document.createElement("img");
      avatarEl.className = "avatar";
      avatarEl.src = u.avatar_url;
      avatarEl.loading = "lazy";
      avatarEl.alt = "";
    } else {
      avatarEl = document.createElement("div");
      avatarEl.className = "avatar-fallback";
      avatarEl.textContent = initials(u.username);
    }

    const nameCell = document.createElement("div");
    nameCell.className = "name-cell";
    const nameEl = document.createElement("span");
    nameEl.className = "username";
    nameEl.textContent = u.username.replace(/#0$/, "");
    nameCell.appendChild(nameEl);

    if (barMax !== null) {
      const track = document.createElement("div");
      track.className = "bar-track";
      const fill = document.createElement("div");
      fill.className = "bar-fill";
      const pct = Math.max(2, Math.round((cfg.barValue(u) / barMax) * 100));
      fill.style.width = pct + "%";
      track.appendChild(fill);
      nameCell.appendChild(track);
    }

    const valueEl = document.createElement("span");
    valueEl.className = "value";
    valueEl.innerHTML = cfg.display(u);

    li.append(rankEl, avatarEl, nameCell, valueEl);
    leaderboardEl.appendChild(li);
  });
}

function setTab(tab) {
  currentTab = tab;
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });
  render();
}

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => setTab(btn.dataset.tab));
});

searchEl.addEventListener("input", (e) => {
  searchTerm = e.target.value;
  render();
});

async function load() {
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    const data = await res.json();
    allUsers = data.users || [];

    document.getElementById("stat-messages").textContent = (data.total_messages || 0).toLocaleString("de-DE");
    document.getElementById("stat-voice").textContent = formatDuration(data.total_voice_seconds || 0);
    document.getElementById("stat-members").textContent = (data.member_count || 0).toLocaleString("de-DE");
    document.getElementById("stat-updated").textContent = formatRelativeUpdate(data.generated_at);

    render();
  } catch (err) {
    emptyStateEl.hidden = false;
    emptyStateEl.textContent = "Daten konnten nicht geladen werden.";
    console.error(err);
  }
}

load();
