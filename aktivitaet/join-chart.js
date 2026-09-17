/* Zoombarer Mitgliederverlauf (kumulierte Beitritte über Zeit) für den
 * "Beigetreten"-Tab. Ersetzt/integriert die frühere eigenständige
 * D3-Grafik (member-dashboard) - hier gespeist aus den live vom Bot
 * getrackten Beitrittsdaten statt einer manuell kopierten Logdatei.
 * Hinweis: Es werden nur Beitritte gezählt, keine Austritte (die trackt
 * der Bot aktuell nicht) - die Linie ist daher monoton steigend. */

const JOIN_MARGIN = { top: 10, right: 14, bottom: 26, left: 38 };
const JOIN_VW = 900, JOIN_VH = 320;
const JOIN_WIDTH = JOIN_VW - JOIN_MARGIN.left - JOIN_MARGIN.right;
const JOIN_HEIGHT = JOIN_VH - JOIN_MARGIN.top - JOIN_MARGIN.bottom;

let joinChartData = [];
let joinCircles = null;
let joinZoom = null;
let joinSvg = null;

const joinTooltipEl = document.getElementById("join-tooltip");

function joinEpoch(isoString) {
  return new Date(isoString.endsWith("Z") ? isoString : isoString + "Z").getTime();
}

function hideJoinTooltip() {
  if (joinTooltipEl) joinTooltipEl.classList.remove("show");
}

function showJoinTooltip(d, clientX, clientY) {
  if (!joinTooltipEl) return;
  joinTooltipEl.innerHTML = `
    <div class="jt-name">${d.username.replace(/#0$/, "")}</div>
    <div class="jt-row">${formatDate(d.joined_at)}</div>
    <div class="jt-row">${d.count}. Beitritt</div>
  `;
  joinTooltipEl.classList.add("show");
  const tw = 220;
  const th = joinTooltipEl.offsetHeight || 70;
  let left = clientX + 14;
  let top = clientY - th / 2;
  if (left + tw > window.innerWidth - 8) left = clientX - tw - 14;
  if (top < 8) top = 8;
  if (top + th > window.innerHeight - 8) top = window.innerHeight - th - 8;
  joinTooltipEl.style.left = left + "px";
  joinTooltipEl.style.top = top + "px";
}

function initJoinChart(users) {
  if (typeof d3 === "undefined") return;

  joinChartData = users
    .filter((u) => u.joined_at)
    .map((u) => ({ ...u, epoch: joinEpoch(u.joined_at) }))
    .sort((a, b) => a.epoch - b.epoch)
    .map((u, i) => ({ ...u, count: i + 1 }));

  const svgEl = document.getElementById("join-chart");
  if (!svgEl || joinChartData.length === 0) return;

  joinSvg = d3.select(svgEl);
  joinSvg.selectAll("*").remove();

  const defs = joinSvg.append("defs");
  defs.append("clipPath").attr("id", "join-clip")
    .append("rect").attr("width", JOIN_WIDTH).attr("height", JOIN_HEIGHT);

  const root = joinSvg.append("g").attr("transform", `translate(${JOIN_MARGIN.left},${JOIN_MARGIN.top})`);

  const minDate = new Date(joinChartData[0].epoch);
  const maxDate = new Date(joinChartData[joinChartData.length - 1].epoch);
  const maxCount = joinChartData.length + 2;

  const xScale = d3.scaleTime().domain([minDate, maxDate]).range([0, JOIN_WIDTH]);
  const yScale = d3.scaleLinear().domain([0, maxCount]).range([JOIN_HEIGHT, 0]);

  const yAxisG = root.append("g").attr("class", "join-axis");
  yAxisG.call(d3.axisLeft(yScale).ticks(5).tickSize(-JOIN_WIDTH));
  yAxisG.selectAll("line").attr("class", "join-gridline");
  yAxisG.select(".domain").remove();

  const xAxisG = root.append("g")
    .attr("class", "join-axis join-x-axis")
    .attr("transform", `translate(0,${JOIN_HEIGHT})`);
  xAxisG.call(d3.axisBottom(xScale).ticks(Math.max(JOIN_WIDTH / 90, 3)));

  const plot = root.append("g").attr("clip-path", "url(#join-clip)");

  const lineGen = d3.line().x((d) => xScale(d.epoch)).y((d) => yScale(d.count));
  const path = plot.append("path")
    .datum(joinChartData)
    .attr("d", lineGen)
    .attr("fill", "none")
    .attr("stroke", "var(--accent)")
    .attr("stroke-width", 1.6)
    .attr("opacity", 0.85);

  joinCircles = plot.selectAll("circle").data(joinChartData).enter().append("circle")
    .attr("cx", (d) => xScale(d.epoch))
    .attr("cy", (d) => yScale(d.count))
    .attr("r", 3.2)
    .attr("fill", "#23a55a")
    .style("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      showJoinTooltip(d, event.clientX, event.clientY);
    });

  document.body.addEventListener("click", hideJoinTooltip);

  const zoomLvlEl = document.getElementById("join-zoom-lvl");
  joinZoom = d3.zoom()
    .scaleExtent([1, 3000])
    .translateExtent([[0, 0], [JOIN_WIDTH, JOIN_HEIGHT]])
    .extent([[0, 0], [JOIN_WIDTH, JOIN_HEIGHT]])
    .on("start", hideJoinTooltip)
    .on("zoom", (event) => {
      const t = event.transform;
      const newX = t.rescaleX(xScale);
      xAxisG.call(d3.axisBottom(newX).ticks(Math.max(JOIN_WIDTH / 90, 3)));
      path.attr("d", d3.line().x((d) => newX(d.epoch)).y((d) => yScale(d.count)));
      joinCircles.attr("cx", (d) => newX(d.epoch));
      if (zoomLvlEl) zoomLvlEl.textContent = `${t.k.toFixed(1)}×`;
    });

  joinSvg.call(joinZoom);
  if (zoomLvlEl) zoomLvlEl.textContent = "1.0×";

  const zoomIn = document.getElementById("join-zoom-in");
  const zoomOut = document.getElementById("join-zoom-out");
  const zoomReset = document.getElementById("join-zoom-reset");
  if (zoomIn) zoomIn.onclick = () => joinSvg.call(joinZoom.scaleBy, 1.8);
  if (zoomOut) zoomOut.onclick = () => joinSvg.call(joinZoom.scaleBy, 1 / 1.8);
  if (zoomReset) zoomReset.onclick = () => joinSvg.call(joinZoom.transform, d3.zoomIdentity);
}

function filterJoinChart(term) {
  if (!joinCircles) return;
  const t = (term || "").trim().toLowerCase();
  joinCircles
    .attr("opacity", (d) => (!t || d.username.toLowerCase().includes(t) ? 1 : 0.15))
    .attr("r", (d) => (!t || d.username.toLowerCase().includes(t) ? 3.6 : 2.4));
}

window.initJoinChart = initJoinChart;
window.filterJoinChart = filterJoinChart;
