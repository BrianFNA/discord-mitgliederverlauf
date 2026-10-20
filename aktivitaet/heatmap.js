/* Aktivitäts-Graph im GitHub-Stil: ein Feld pro Tag (UTC), Farbe nach
 * Aktivität. Daten aus daily.json: [Datum, Nachrichten, Voice-Sekunden].
 * Farbstufen sind Quartile der Tage MIT Aktivität, damit einzelne
 * Ausreißer-Tage nicht alle anderen Tage ausbleichen. */
(function () {
  const wrap = document.getElementById("heat-wrap");
  if (!wrap) return;

  const svgEl = document.getElementById("heat-svg");
  const scrollEl = document.getElementById("heat-scroll");
  const yearSel = document.getElementById("heat-year");
  const summaryEl = document.getElementById("heat-summary");
  const noteEl = document.getElementById("heat-note");
  const tipEl = document.getElementById("heat-tooltip");

  const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];
  const WEEKDAY_LABELS = { 0: "Mo", 2: "Mi", 4: "Fr" };
  const CELL = 11, STEP = 14, LEFT = 28, TOP = 18;
  const DAY_MS = 86400000;

  const days = new Map();
  let thMsg = [0, 0, 0];
  let thVoice = [0, 0, 0];
  let metric = "all";
  let range = "last12";
  let today = null;
  let dataUntil = null;

  const iso = (d) => d.toISOString().slice(0, 10);
  const utcDate = (s) => {
    const [y, m, d] = s.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d));
  };
  const weekday = (d) => (d.getUTCDay() + 6) % 7;
  const fmtDay = (s) => utcDate(s).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });

  function thresholds(values) {
    const v = values.filter((x) => x > 0).sort((a, b) => a - b);
    if (!v.length) return [0, 0, 0];
    const q = (p) => v[Math.floor(p * (v.length - 1))];
    return [q(0.25), q(0.5), q(0.75)];
  }

  function level(value, th) {
    if (value <= 0) return 0;
    if (value <= th[0]) return 1;
    if (value <= th[1]) return 2;
    if (value <= th[2]) return 3;
    return 4;
  }

  function cellLevel(rec) {
    if (!rec) return 0;
    const lm = level(rec.m, thMsg);
    const lv = level(rec.v, thVoice);
    if (metric === "messages") return lm;
    if (metric === "voice") return lv;
    return Math.max(lm, lv);
  }

  function bounds() {
    const end0 = utcDate(today);
    if (range === "last12") {
      return { start: new Date(end0.getTime() - 364 * DAY_MS), end: end0 };
    }
    const y = Number(range);
    const yearEnd = new Date(Date.UTC(y, 11, 31));
    return { start: new Date(Date.UTC(y, 0, 1)), end: yearEnd < end0 ? yearEnd : end0 };
  }

  function render() {
    const { start, end } = bounds();
    const gridStart = new Date(start.getTime() - weekday(start) * DAY_MS);
    const totalDays = Math.round((end - gridStart) / DAY_MS) + 1;
    const cols = Math.ceil(totalDays / 7);

    let cells = "";
    const monthLabels = [];
    let totMsg = 0, totVoice = 0, active = 0, shown = 0;

    for (let i = 0; i < totalDays; i++) {
      const d = new Date(gridStart.getTime() + i * DAY_MS);
      if (d < start) continue;
      const col = Math.floor(i / 7);
      const row = i % 7;
      const key = iso(d);
      const rec = days.get(key);
      shown++;
      if (rec) {
        totMsg += rec.m;
        totVoice += rec.v;
        if (rec.m > 0 || rec.v > 0) active++;
      }
      if (d.getUTCDate() === 1) monthLabels.push({ col, text: MONTHS[d.getUTCMonth()] });
      cells += `<rect class="heat-cell l${cellLevel(rec)}" x="${LEFT + col * STEP}" y="${TOP + row * STEP}" width="${CELL}" height="${CELL}" rx="2" data-d="${key}"></rect>`;
    }

    if (!monthLabels.length || monthLabels[0].col >= 3) {
      monthLabels.unshift({ col: 0, text: MONTHS[start.getUTCMonth()] });
    }

    let labels = "";
    monthLabels.forEach((m) => {
      labels += `<text class="heat-label" x="${LEFT + m.col * STEP}" y="${TOP - 6}">${m.text}</text>`;
    });
    Object.keys(WEEKDAY_LABELS).forEach((row) => {
      labels += `<text class="heat-label" x="0" y="${TOP + row * STEP + CELL - 1}">${WEEKDAY_LABELS[row]}</text>`;
    });

    const width = LEFT + cols * STEP;
    const height = TOP + 7 * STEP;
    svgEl.setAttribute("width", width);
    svgEl.setAttribute("height", height);
    svgEl.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svgEl.innerHTML = labels + cells;

    summaryEl.textContent =
      `${totMsg.toLocaleString("de-DE")} Nachrichten · ${formatDuration(totVoice)} Voice · ` +
      `an ${active} von ${shown} Tagen aktiv`;

    scrollEl.scrollLeft = scrollEl.scrollWidth;
  }

  function showTip(key, clientX, clientY) {
    const rec = days.get(key);
    const label = utcDate(key).toLocaleDateString("de-DE", {
      weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC",
    });
    let html = `<div class="jt-name">${label}</div>`;
    if (rec && (rec.m || rec.v)) {
      html += `<div class="jt-row">${rec.m.toLocaleString("de-DE")} Nachrichten</div>`;
      html += `<div class="jt-row">${formatDuration(rec.v)} Voice</div>`;
    } else {
      html += `<div class="jt-row">Keine Aktivität</div>`;
    }
    tipEl.innerHTML = html;
    tipEl.classList.add("show");
    const tw = 220;
    const th = tipEl.offsetHeight || 70;
    let left = clientX + 14;
    let top = clientY - th - 10;
    if (left + tw > window.innerWidth - 8) left = clientX - tw - 14;
    if (top < 8) top = clientY + 18;
    tipEl.style.left = left + "px";
    tipEl.style.top = top + "px";
  }

  function hideTip() {
    tipEl.classList.remove("show");
  }

  svgEl.addEventListener("mouseover", (e) => {
    const cell = e.target.closest("rect[data-d]");
    if (cell) showTip(cell.dataset.d, e.clientX, e.clientY);
    else hideTip();
  });
  svgEl.addEventListener("mousemove", (e) => {
    const cell = e.target.closest("rect[data-d]");
    if (cell) showTip(cell.dataset.d, e.clientX, e.clientY);
  });
  svgEl.addEventListener("mouseleave", hideTip);
  svgEl.addEventListener("click", (e) => {
    const cell = e.target.closest("rect[data-d]");
    if (cell) {
      e.stopPropagation();
      showTip(cell.dataset.d, e.clientX, e.clientY);
    }
  });
  document.body.addEventListener("click", hideTip);
  scrollEl.addEventListener("scroll", hideTip);

  document.querySelectorAll("#heat-metric button").forEach((btn) => {
    btn.addEventListener("click", () => {
      metric = btn.dataset.metric;
      document.querySelectorAll("#heat-metric button").forEach((b) => {
        b.classList.toggle("active", b === btn);
      });
      render();
    });
  });

  yearSel.addEventListener("change", () => {
    range = yearSel.value;
    render();
  });

  fetch("daily.json", { cache: "no-store" })
    .then((res) => {
      if (!res.ok) throw new Error("daily.json " + res.status);
      return res.json();
    })
    .then((data) => {
      const rows = data.days || [];
      if (!rows.length) return;
      rows.forEach(([d, m, v]) => days.set(d, { m, v }));
      thMsg = thresholds(rows.map((r) => r[1]));
      thVoice = thresholds(rows.map((r) => r[2]));

      today = (data.generated_at || new Date().toISOString()).slice(0, 10);
      dataUntil = data.data_until || rows[rows.length - 1][0];

      const firstYear = Number(rows[0][0].slice(0, 4));
      const lastYear = Number(today.slice(0, 4));
      yearSel.innerHTML = '<option value="last12">Letzte 12 Monate</option>';
      for (let y = lastYear; y >= firstYear; y--) {
        yearSel.insertAdjacentHTML("beforeend", `<option value="${y}">${y}</option>`);
      }

      let note = `Tage in UTC · Stand ${fmtDay(today)}`;
      const lagDays = (utcDate(today) - utcDate(dataUntil)) / DAY_MS;
      if (lagDays > 2) {
        note += ` · letzte erfasste Aktivität: ${fmtDay(dataUntil)}`;
        noteEl.classList.add("heat-stale");
      }
      noteEl.textContent = note;

      wrap.hidden = false;
      render();
    })
    .catch((err) => console.error(err));
})();
