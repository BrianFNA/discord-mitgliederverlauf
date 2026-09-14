/* Verstecktes Voice-Log-Panel.
 * Aufruf: irgendwo auf der Seite (außerhalb der Suche) das Wort unten tippen. */
const VLOG_SECRET = "voicelog";
const VLOG_MONTHS = [
  "Januar", "Februar", "März", "April", "Mai", "Juni",
  "Juli", "August", "September", "Oktober", "November", "Dezember",
];

let vlogKeyBuffer = "";
let vlogData = null;
let vlogLoadPromise = null;
let vlogMode = "user";
let vlogSelectedUser = null;
let vlogSelectedDate = null; // {year, month, day}

const vlogOverlay = document.getElementById("vlog-overlay");
const vlogSidebar = document.getElementById("vlog-sidebar");
const vlogDetail = document.getElementById("vlog-detail");
const vlogCloseBtn = document.getElementById("vlog-close");

document.addEventListener("keydown", (e) => {
  const tag = (e.target && e.target.tagName) || "";
  if (tag === "INPUT" || tag === "TEXTAREA") return;
  if (e.key.length !== 1) return;
  vlogKeyBuffer = (vlogKeyBuffer + e.key.toLowerCase()).slice(-VLOG_SECRET.length);
  if (vlogKeyBuffer === VLOG_SECRET) {
    vlogKeyBuffer = "";
    openVlog();
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !vlogOverlay.hidden) closeVlog();
});

vlogCloseBtn.addEventListener("click", closeVlog);
vlogOverlay.addEventListener("click", (e) => {
  if (e.target === vlogOverlay) closeVlog();
});

document.querySelectorAll(".vlog-tab").forEach((btn) => {
  btn.addEventListener("click", () => setVlogMode(btn.dataset.vtab));
});

function loadVlogData() {
  if (!vlogLoadPromise) {
    vlogLoadPromise = fetch("voicelog.json", { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => {
        vlogData = data;
        return data;
      });
  }
  return vlogLoadPromise;
}

function openVlog() {
  vlogOverlay.hidden = false;
  vlogDetail.innerHTML = '<p class="vlog-hint">Lade Daten…</p>';
  loadVlogData().then(() => renderVlog()).catch(() => {
    vlogDetail.innerHTML = '<p class="vlog-hint">Voice-Log konnte nicht geladen werden.</p>';
  });
}

function closeVlog() {
  vlogOverlay.hidden = true;
}

function setVlogMode(mode) {
  vlogMode = mode;
  document.querySelectorAll(".vlog-tab").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.vtab === mode);
  });
  vlogDetail.innerHTML = '<p class="vlog-hint">Links auswählen, um Details zu sehen.</p>';
  renderVlog();
}

function renderVlog() {
  if (!vlogData) return;
  if (vlogMode === "user") {
    renderUserSidebar();
  } else {
    renderDateSidebar();
  }
}

/* ---------- Datum-Hilfsfunktionen (bewusst ohne Date-Objekt/Timezone) ---------- */

function vlogDateParts(isoString) {
  const [datePart, timePart] = isoString.split("T");
  const [year, month, day] = datePart.split("-");
  return { year, month, day, time: (timePart || "").slice(0, 5) };
}

function vlogBuildTree(sessions) {
  const tree = {};
  for (const s of sessions) {
    const { year, month, day } = vlogDateParts(s.joined_at);
    tree[year] ??= { total: 0, months: {} };
    tree[year].total += s.duration_seconds;
    const y = tree[year];
    y.months[month] ??= { total: 0, days: {} };
    y.months[month].total += s.duration_seconds;
    const m = y.months[month];
    m.days[day] ??= { total: 0, sessions: [] };
    m.days[day].total += s.duration_seconds;
    m.days[day].sessions.push(s);
  }
  return tree;
}

function vlogSortedKeysDesc(obj) {
  return Object.keys(obj).sort().reverse();
}

/* ---------- Pro Nutzer ---------- */

function renderUserSidebar() {
  const totals = {};
  for (const s of vlogData.sessions) {
    totals[s.user_id] = (totals[s.user_id] || 0) + s.duration_seconds;
  }
  const userIds = Object.keys(totals).sort((a, b) => totals[b] - totals[a]);

  vlogSidebar.innerHTML = "";
  const searchInput = document.createElement("input");
  searchInput.className = "vlog-search";
  searchInput.type = "search";
  searchInput.placeholder = "Nutzer suchen…";
  vlogSidebar.appendChild(searchInput);

  const listEl = document.createElement("div");
  vlogSidebar.appendChild(listEl);

  function draw(filter) {
    listEl.innerHTML = "";
    userIds
      .filter((uid) => {
        const u = vlogData.users[uid] || {};
        return (u.username || "").toLowerCase().includes(filter.toLowerCase());
      })
      .forEach((uid) => {
        const u = vlogData.users[uid] || { username: "Unbekannt" };
        const btn = document.createElement("button");
        btn.className = "vlog-list-item" + (uid === vlogSelectedUser ? " active" : "");
        btn.type = "button";

        if (u.avatar_url) {
          const img = document.createElement("img");
          img.src = u.avatar_url;
          img.className = "vlog-avatar";
          img.alt = "";
          btn.appendChild(img);
        } else {
          const span = document.createElement("span");
          span.className = "vlog-avatar";
          span.style.background = "var(--accent)";
          btn.appendChild(span);
        }

        const nameEl = document.createElement("span");
        nameEl.className = "vlog-item-name";
        nameEl.textContent = u.username;
        btn.appendChild(nameEl);

        const totalEl = document.createElement("span");
        totalEl.className = "vlog-item-total";
        totalEl.textContent = formatDuration(totals[uid]);
        btn.appendChild(totalEl);

        btn.addEventListener("click", () => {
          vlogSelectedUser = uid;
          draw(searchInput.value);
          renderUserDetail(uid);
        });
        listEl.appendChild(btn);
      });
  }

  searchInput.addEventListener("input", () => draw(searchInput.value));
  draw("");

  if (vlogSelectedUser && totals[vlogSelectedUser] !== undefined) {
    renderUserDetail(vlogSelectedUser);
  }
}

function renderUserDetail(userId) {
  const u = vlogData.users[userId] || { username: "Unbekannt" };
  const sessions = vlogData.sessions.filter((s) => s.user_id === userId);
  const total = sessions.reduce((sum, s) => sum + s.duration_seconds, 0);
  const tree = vlogBuildTree(sessions);

  vlogDetail.innerHTML = "";
  const h3 = document.createElement("h3");
  h3.textContent = u.username;
  vlogDetail.appendChild(h3);

  const sub = document.createElement("p");
  sub.className = "vlog-subtotal";
  sub.textContent = `${formatDuration(total)} Voice-Zeit gesamt · ${sessions.length} Sessions`;
  vlogDetail.appendChild(sub);

  vlogSortedKeysDesc(tree).forEach((year) => {
    const yearData = tree[year];
    const yearDetails = document.createElement("details");
    yearDetails.className = "vlog-tree";
    const yearSummary = document.createElement("summary");
    yearSummary.innerHTML = `<span>${year}</span><span class="vlog-total">${formatDuration(yearData.total)}</span>`;
    yearDetails.appendChild(yearSummary);

    vlogSortedKeysDesc(yearData.months).forEach((month) => {
      const monthData = yearData.months[month];
      const monthDetails = document.createElement("details");
      monthDetails.className = "vlog-tree";
      const monthSummary = document.createElement("summary");
      monthSummary.innerHTML = `<span>${VLOG_MONTHS[parseInt(month, 10) - 1]}</span><span class="vlog-total">${formatDuration(monthData.total)}</span>`;
      monthDetails.appendChild(monthSummary);

      vlogSortedKeysDesc(monthData.days).forEach((day) => {
        const dayData = monthData.days[day];
        const dayDetails = document.createElement("details");
        dayDetails.className = "vlog-tree";
        const daySummary = document.createElement("summary");
        daySummary.innerHTML = `<span>${day}. ${VLOG_MONTHS[parseInt(month, 10) - 1]}</span><span class="vlog-total">${formatDuration(dayData.total)}</span>`;
        dayDetails.appendChild(daySummary);
        dayDetails.appendChild(vlogRenderSessionList(dayData.sessions));
        monthDetails.appendChild(dayDetails);
      });

      yearDetails.appendChild(monthDetails);
    });

    vlogDetail.appendChild(yearDetails);
  });
}

function vlogRenderSessionList(sessions) {
  const ul = document.createElement("ul");
  ul.className = "vlog-session-list";
  [...sessions]
    .sort((a, b) => (a.joined_at < b.joined_at ? 1 : -1))
    .forEach((s) => {
      const li = document.createElement("li");
      li.className = "vlog-session-row";
      const start = vlogDateParts(s.joined_at).time;
      const end = vlogDateParts(s.left_at).time;
      li.innerHTML = `
        <span class="vlog-channel">${s.channel_name || "unbekannt"}</span>
        <span class="vlog-time">${start}–${end}</span>
        <span class="vlog-duration">${formatDuration(s.duration_seconds)}</span>
      `;
      ul.appendChild(li);
    });
  return ul;
}

/* ---------- Pro Datum ---------- */

function renderDateSidebar() {
  const tree = vlogBuildTree(vlogData.sessions);
  vlogSidebar.innerHTML = "";

  vlogSortedKeysDesc(tree).forEach((year) => {
    const yearData = tree[year];
    const yearDetails = document.createElement("details");
    yearDetails.className = "vlog-tree";
    yearDetails.open = false;
    const yearSummary = document.createElement("summary");
    yearSummary.innerHTML = `<span>${year}</span><span class="vlog-total">${formatDuration(yearData.total)}</span>`;
    yearDetails.appendChild(yearSummary);

    vlogSortedKeysDesc(yearData.months).forEach((month) => {
      const monthData = yearData.months[month];
      const monthDetails = document.createElement("details");
      monthDetails.className = "vlog-tree";
      const monthSummary = document.createElement("summary");
      monthSummary.innerHTML = `<span>${VLOG_MONTHS[parseInt(month, 10) - 1]}</span><span class="vlog-total">${formatDuration(monthData.total)}</span>`;
      monthDetails.appendChild(monthSummary);

      vlogSortedKeysDesc(monthData.days).forEach((day) => {
        const dayData = monthData.days[day];
        const isActive = vlogSelectedDate
          && vlogSelectedDate.year === year
          && vlogSelectedDate.month === month
          && vlogSelectedDate.day === day;
        const dayBtn = document.createElement("button");
        dayBtn.type = "button";
        dayBtn.className = "vlog-daybutton" + (isActive ? " active" : "");
        dayBtn.innerHTML = `<span>${day}. ${VLOG_MONTHS[parseInt(month, 10) - 1]}</span><span class="vlog-total">${formatDuration(dayData.total)}</span>`;
        dayBtn.addEventListener("click", () => {
          vlogSelectedDate = { year, month, day };
          renderDateSidebar();
          renderDateDetail(year, month, day, dayData);
        });
        monthDetails.appendChild(dayBtn);
      });

      yearDetails.appendChild(monthDetails);
    });

    vlogSidebar.appendChild(yearDetails);
  });

  if (vlogSelectedDate) {
    const { year, month, day } = vlogSelectedDate;
    const dayData = tree[year] && tree[year].months[month] && tree[year].months[month].days[day];
    if (dayData) renderDateDetail(year, month, day, dayData);
  }
}

function renderDateDetail(year, month, day, dayData) {
  vlogDetail.innerHTML = "";
  const h3 = document.createElement("h3");
  h3.textContent = `${day}. ${VLOG_MONTHS[parseInt(month, 10) - 1]} ${year}`;
  vlogDetail.appendChild(h3);

  const sub = document.createElement("p");
  sub.className = "vlog-subtotal";
  sub.textContent = `${formatDuration(dayData.total)} Voice-Zeit gesamt · ${dayData.sessions.length} Sessions`;
  vlogDetail.appendChild(sub);

  const byUser = {};
  for (const s of dayData.sessions) {
    byUser[s.user_id] ??= { total: 0, sessions: [] };
    byUser[s.user_id].total += s.duration_seconds;
    byUser[s.user_id].sessions.push(s);
  }

  Object.keys(byUser)
    .sort((a, b) => byUser[b].total - byUser[a].total)
    .forEach((uid) => {
      const u = vlogData.users[uid] || { username: "Unbekannt" };
      const group = document.createElement("div");
      group.className = "vlog-daygroup";
      const h4 = document.createElement("h4");
      if (u.avatar_url) {
        h4.innerHTML = `<img src="${u.avatar_url}" alt=""> <span>${u.username}</span><span class="vlog-total">${formatDuration(byUser[uid].total)}</span>`;
      } else {
        h4.innerHTML = `<span>${u.username}</span><span class="vlog-total">${formatDuration(byUser[uid].total)}</span>`;
      }
      group.appendChild(h4);
      group.appendChild(vlogRenderSessionList(byUser[uid].sessions));
      vlogDetail.appendChild(group);
    });
}
