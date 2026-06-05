'use strict';

const DATA_URL = '../data_processing/slavevoyages_dotorg/output.json';
const MIN_YEAR = 1710;
const MAX_YEAR = 1868;
const DEFAULT_CROSSING_DAYS = { atlantic: 60, indian_ocean: 45 };

// ── Map ────────────────────────────────────────────────────────────────────
const map = L.map('map', {
  center: [15, -15],
  zoom: 3,
  minZoom: 2,
  maxZoom: 8,
  zoomControl: true,
  attributionControl: false,
});

// ESRI World Physical Map: physical terrain, no political borders or anachronistic boundaries
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Physical_Map/MapServer/tile/{z}/{y}/{x}', {
  attribution: 'Tiles &copy; <a href="https://www.esri.com/">Esri</a>',
  maxZoom: 8,
}).addTo(map);

L.control.attribution({ position: 'bottomright' }).addTo(map);

// ── Canvas overlay ─────────────────────────────────────────────────────────
const canvas = document.getElementById('ship-canvas');
const ctx = canvas.getContext('2d');

function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}
resizeCanvas();
window.addEventListener('resize', () => { resizeCanvas(); drawFrame(); });

// ── Year histogram chart ───────────────────────────────────────────────────
const CHART_W = 260, CHART_H = 72;
const chartCanvas = document.getElementById('chart-canvas');
chartCanvas.width  = CHART_W;
chartCanvas.height = CHART_H;
const chartCtx = chartCanvas.getContext('2d');

let yearlySlaves     = null;   // filled once voyages are loaded
let maxYearlySlaves  = 1;
let smoothedBusyness = null;   // rolling-average of yearlySlaves, for adaptive speed
let avgBusyness      = 1;

function buildYearlySlaves() {
  yearlySlaves = new Array(MAX_YEAR - MIN_YEAR + 1).fill(0);
  for (const v of voyages) {
    const yi = Math.floor(v.t_start) - MIN_YEAR;
    if (yi >= 0 && yi < yearlySlaves.length) yearlySlaves[yi] += v.slaves;
  }
  maxYearlySlaves = Math.max(...yearlySlaves, 1);

  // Smooth over ±7 years so the adaptive speed changes are gradual
  const R = 7;
  smoothedBusyness = yearlySlaves.map((_, i) => {
    let sum = 0, count = 0;
    for (let j = Math.max(0, i - R); j <= Math.min(yearlySlaves.length - 1, i + R); j++) {
      sum += yearlySlaves[j]; count++;
    }
    return count ? sum / count : 0;
  });
  avgBusyness = smoothedBusyness.reduce((a, b) => a + b, 0) / smoothedBusyness.length;
}

// Linearly interpolated busyness at a fractional year
function getBusyness(year) {
  if (!smoothedBusyness) return avgBusyness;
  const f  = year - MIN_YEAR;
  const i0 = Math.max(0, Math.min(smoothedBusyness.length - 1, Math.floor(f)));
  const i1 = Math.min(smoothedBusyness.length - 1, i0 + 1);
  return smoothedBusyness[i0] + (smoothedBusyness[i1] - smoothedBusyness[i0]) * (f - i0);
}

function drawChart() {
  if (!yearlySlaves) return;
  chartCtx.clearRect(0, 0, CHART_W, CHART_H);

  const years = yearlySlaves.length;
  const barW  = CHART_W / years;

  for (let i = 0; i < years; i++) {
    const barH = (yearlySlaves[i] / maxYearlySlaves) * CHART_H;
    const x    = i * barW;
    const past = MIN_YEAR + i <= currentYear;
    chartCtx.fillStyle = past ? 'rgba(232, 128, 64, 0.82)' : 'rgba(255, 255, 255, 0.13)';
    chartCtx.fillRect(x, CHART_H - barH, Math.max(barW, 1), barH);
  }

  // Cursor line at current year
  const cx = ((currentYear - MIN_YEAR) / (MAX_YEAR - MIN_YEAR)) * CHART_W;
  chartCtx.beginPath();
  chartCtx.strokeStyle = 'rgba(245, 200, 66, 0.9)';
  chartCtx.lineWidth = 1.5;
  chartCtx.moveTo(cx, 0);
  chartCtx.lineTo(cx, CHART_H);
  chartCtx.stroke();
}

// ── Ship glyphs ────────────────────────────────────────────────────────────
// All SVGs share viewBox 240×180, left-facing profile, hull top at y=106 (~59%).
// Drawn at 54×40 on canvas; anchor offset = SHIP_H * 0.59.
const SHIP_W = 54, SHIP_H = 40;

// ship.svg = full-rigged 3-master, ship2.svg = brigantine, ship3.svg = lateen ketch
const shipImages = [new Image(), new Image(), new Image()];
shipImages[0].src = 'ship.svg';
shipImages[1].src = 'ship2.svg';
shipImages[2].src = 'ship3.svg';

// ── Date → decimal year ────────────────────────────────────────────────────
function toDecimalYear(s) {
  if (!s) return null;
  const parts = s.split('-');
  const y = parseInt(parts[0], 10);
  if (isNaN(y)) return null;
  if (parts.length === 1) return y + 0.5;
  const m = parseInt(parts[1], 10);
  if (parts.length === 2) return y + (m - 0.5) / 12;
  const d = parseInt(parts[2], 10);
  return y + ((m - 1) * 30.4375 + d - 1) / 365.25;
}

// ── Great-circle interpolation ─────────────────────────────────────────────
function slerp(lat1, lon1, lat2, lon2, t) {
  const R = Math.PI / 180;
  const φ1 = lat1 * R, λ1 = lon1 * R;
  const φ2 = lat2 * R, λ2 = lon2 * R;
  const x1 = Math.cos(φ1) * Math.cos(λ1);
  const y1 = Math.cos(φ1) * Math.sin(λ1);
  const z1 = Math.sin(φ1);
  const x2 = Math.cos(φ2) * Math.cos(λ2);
  const y2 = Math.cos(φ2) * Math.sin(λ2);
  const z2 = Math.sin(φ2);
  const dot = Math.max(-1, Math.min(1, x1 * x2 + y1 * y2 + z1 * z2));
  const omega = Math.acos(dot);
  if (omega < 1e-6) return [lat1, lon1];
  const s0 = Math.sin((1 - t) * omega) / Math.sin(omega);
  const s1 = Math.sin(t * omega) / Math.sin(omega);
  const x = s0 * x1 + s1 * x2;
  const y = s0 * y1 + s1 * y2;
  const z = s0 * z1 + s1 * z2;
  return [
    Math.atan2(z, Math.sqrt(x * x + y * y)) / R,
    Math.atan2(y, x) / R,
  ];
}

// ── Land-avoidance routing ─────────────────────────────────────────────────
function buildRoutePath(from, to, ocean) {
  const [fLat, fLon] = from;
  const [tLat, tLon] = to;

  // Destination requires northern Caribbean approach (Hispaniola/Cuba band)
  const needsHispApproach    = tLat > 17 && tLat < 24 && tLon > -80 && tLon < -66;
  const needsColombiaApproach = tLat > 8  && tLat < 17 && tLon > -80 && tLon < -67;
  const needsGulfApproach    = tLat > 24 && tLon < -82; // Gulf of Mexico: enter via Florida Straits

  // ── Atlantic ─────────────────────────────────────────────────────────────
  if (ocean === 'atlantic' && tLon < -40) {
    // East African port in Atlantic dataset: coast → Cape → South Atlantic → Americas
    // Use [-3, -30] as Brazil bypass (east of Brazil's northeastern bulge)
    if (fLon > 30) {
      const eaf = fLat > -12
        ? [from, [fLat, fLon + 3], [-20, 43], [-38, 25], [-3, -30]]
        : [from, [-28, 43], [-38, 25], [-3, -30]];
      if (needsHispApproach)    return [...eaf, [21.5, -73.5], to];
      if (needsColombiaApproach) return [...eaf, [14, -76], to];
      if (needsGulfApproach)    return [...eaf, [24.5, -82.5], to];
      return [...eaf, to];
    }
    if (fLon > -6) {
      const via1 = fLat > -10 ? [-5, 5] : [-15, -10];
      if (needsHispApproach)    return [from, via1, [21.5, -73.5], to];
      if (needsColombiaApproach) return [from, via1, [14, -76], to];
      if (needsGulfApproach)    return [from, via1, [24.5, -82.5], to];
      return [from, via1, to];
    }
    if (needsHispApproach)    return [from, [21.5, -73.5], to];
    if (needsColombiaApproach) return [from, [14, -76], to];
    if (needsGulfApproach)    return [from, [24.5, -82.5], to];
  }

  // ── Indian Ocean ─────────────────────────────────────────────────────────
  if (ocean === 'indian_ocean') {
    if (fLon < 0 && tLon > 40) return [from, [-36, 20], to];

    // India / SE Asia ports: go SE into Bay of Bengal to clear peninsula, then SW
    if (fLon > 70 && fLat > 5 && tLon < 70) {
      return [from, [8, fLon + 2], to];
    }

    // East Africa coast (38–44°E): latitude-aware routing
    if (fLon >= 38 && fLon < 44 && fLat > -20) {
      const tz = fLat > -12; // Tanzania (north) vs Mozambique Channel (south)
      if (tLon > 50) {
        // → eastern Indian Ocean: go east then south, add Mozambique Channel via
        return tz
          ? [from, [fLat, fLon + 3], [-20, 43], [-28, 43], [-32, 55], to]
          : [from, [-28, 43], [-32, 55], to];
      }
      if (Math.abs(tLon - fLon) < 8 && Math.abs(tLat - fLat) < 10) {
        return [from, to]; // short nearby route: go direct (no land crossing)
      }
      // → Cape or any western destination: south deep enough to clear Eastern Cape
      return tz
        ? [from, [fLat, fLon + 3], [-20, 43], [-38, 25], to]
        : [from, [-28, 43], [-38, 25], to];
    }

    // SW/west Madagascar → eastern Indian Ocean
    if (fLon < 46 && fLat < -15 && tLon > 50) return [from, [-28, 43], [-32, 50], to];

    // Eastern Indian Ocean → western destinations: south then west
    if (fLon > 52 && tLon < 46) return [from, [-32, 50], [-28, 43], to];

    // East/NE Madagascar → further east: deflect south to clear coast
    if (fLon >= 46 && fLon <= 51 && fLat < -10 && tLon > fLon + 4) {
      return [from, [fLat - 4, fLon + 2], to];
    }

    // Madagascar-area port going significantly westward: route south of island both sides
    if (fLon >= 44 && fLon <= 52 && fLat < -5 && tLon < fLon - 3) {
      return [from, [-28, 50], [-30, 43], to];
    }
  }

  return [from, to];
}

// ── Arc-length-proportional path interpolation ────────────────────────────
function arcLength(p1, p2) {
  const R = Math.PI / 180;
  const x1 = Math.cos(p1[0]*R)*Math.cos(p1[1]*R), y1 = Math.cos(p1[0]*R)*Math.sin(p1[1]*R), z1 = Math.sin(p1[0]*R);
  const x2 = Math.cos(p2[0]*R)*Math.cos(p2[1]*R), y2 = Math.cos(p2[0]*R)*Math.sin(p2[1]*R), z2 = Math.sin(p2[0]*R);
  return Math.acos(Math.max(-1, Math.min(1, x1*x2 + y1*y2 + z1*z2)));
}

function slerpPath(path, t) {
  const n = path.length - 1;
  if (n === 1) return slerp(path[0][0], path[0][1], path[1][0], path[1][1], t);

  // Weight each segment by its arc length so ship speed is geographically uniform
  const lengths = [];
  for (let i = 0; i < n; i++) lengths.push(arcLength(path[i], path[i + 1]));
  const total = lengths.reduce((a, b) => a + b, 0);

  let cum = 0;
  for (let i = 0; i < n; i++) {
    const frac = lengths[i] / total;
    if (t <= cum + frac + 1e-9 || i === n - 1) {
      const localT = Math.max(0, Math.min(1, (t - cum) / frac));
      return slerp(path[i][0], path[i][1], path[i + 1][0], path[i + 1][1], localT);
    }
    cum += frac;
  }
  return slerp(path[n-1][0], path[n-1][1], path[n][0], path[n][1], 1);
}

// ── Voyage preparation ─────────────────────────────────────────────────────
function prepareVoyages(rawVoyages) {
  const result = [];

  for (const v of rawVoyages) {
    const purchase = v.waypoints.find(wp => wp.event === 'purchase');
    const arrival  = v.waypoints.find(wp => wp.event === 'arrival');

    if (!purchase?.coordinates || !arrival?.coordinates) continue;

    const defaultDays = DEFAULT_CROSSING_DAYS[v.ocean] ?? 60;
    const durationYears = (v.crossing_days > 0 ? v.crossing_days : defaultDays) / 365.25;

    let t_start = toDecimalYear(purchase.departed_date ?? purchase.date);
    let t_end   = toDecimalYear(arrival.date);

    if (t_start === null && t_end === null) continue;
    if (t_start === null) t_start = t_end - durationYears;
    if (t_end   === null) t_end   = t_start + durationYears;

    if (t_end <= t_start) t_end = t_start + durationYears;
    if (t_end - t_start > 2) t_end = t_start + durationYears;

    // Enforce a minimum visual duration of 60 days so fast ships stay on screen
    // long enough to see. Intentionally detaches from the historical arrival date
    // for very short crossings.
    const MIN_DISPLAY_YEARS = 60 / 365.25;
    if (t_end - t_start < MIN_DISPLAY_YEARS) t_end = t_start + MIN_DISPLAY_YEARS;

    // Eastward if the shortest longitudinal arc from purchase to arrival goes east
    const dLon = ((arrival.coordinates[1] - purchase.coordinates[1]) + 540) % 360 - 180;

    result.push({
      t_start,
      t_end,
      from: purchase.coordinates,
      to:   arrival.coordinates,
      path: buildRoutePath(purchase.coordinates, arrival.coordinates, v.ocean),
      slaves:      v.slaves_embarked ?? 0,
      counted:     false,
      goingEast:   dLon > 0,
      shipVariant: Math.floor(Math.random() * 3),
      // metadata for tooltip
      vessel:        v.vessel,
      ocean:         v.ocean,
      embarked:      v.slaves_embarked,
      disembarked:   v.slaves_disembarked,
      from_port:     purchase.port,
      to_port:       arrival.port,
      from_date:     purchase.departed_date ?? purchase.date,
      to_date:       arrival.date,
    });
  }

  result.sort((a, b) => a.t_start - b.t_start);
  return result;
}

// ── Animation state ────────────────────────────────────────────────────────
let voyages     = [];
let currentYear = MIN_YEAR;
let slavesCount = 0;
let playing     = false;
let speed       = 0.15;
let lastTs      = null;

// ── Story state ────────────────────────────────────────────────────────────
let stories          = [];
let storyActive      = false;
let storyData        = null;
let storyPanelIdx    = 0;
let storySentences   = [];
let storySentenceIdx = 0;
let storyTypeTimer   = null;   // interval: typewriter character tick
let storyPanelTimer  = null;   // timeout: pause after sentence fully typed
let triggeredStories = new Set();
let prevYear         = MIN_YEAR - 0.01;
const TYPE_SPEED_MS      = 26;   // ms per character
const SENTENCE_PAUSE_MS  = 2800; // pause after full sentence before advancing

// ── DOM refs ───────────────────────────────────────────────────────────────
const yearDisplay   = document.getElementById('year-display');
const slaveNumber   = document.getElementById('slave-number');
const playBtn       = document.getElementById('play-btn');
const yearSlider    = document.getElementById('year-slider');
const speedSlider   = document.getElementById('speed-slider');
const speedLabel    = document.getElementById('speed-label');
const storyOverlay  = document.getElementById('story-overlay');
const storyInner    = document.getElementById('story-inner');
const storyTitleEl  = document.getElementById('story-title');
const storyImg      = document.getElementById('story-img');
const storyTextEl   = document.getElementById('story-text');
const storyProgress = document.getElementById('story-progress');

function syncUI() {
  yearDisplay.textContent = Math.floor(currentYear);
  slaveNumber.textContent = slavesCount.toLocaleString('en-US');
  yearSlider.value = Math.round(((currentYear - MIN_YEAR) / (MAX_YEAR - MIN_YEAR)) * 10000);
}

function jumpToYear(y) {
  currentYear = Math.max(MIN_YEAR, Math.min(MAX_YEAR, y));
  slavesCount = 0;
  for (const v of voyages) {
    v.counted = v.t_start <= currentYear;
    if (v.counted) slavesCount += v.slaves;
  }
  syncUI();
}

// Active ship positions for hover hit-testing — refreshed each drawFrame
let activeShips = [];

// ── Draw ───────────────────────────────────────────────────────────────────
function drawFrame() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  activeShips = [];
  drawChart();

  for (const v of voyages) {
    if (v.t_start > currentYear || v.t_end < currentYear) continue;

    const p = Math.max(0, Math.min(1, (currentYear - v.t_start) / (v.t_end - v.t_start)));

    // Fade in over first 8% of journey, fade out over last 8%
    const FADE = 0.08;
    const shipAlpha = p < FADE ? p / FADE : p > 1 - FADE ? (1 - p) / FADE : 1;

    // Ocean-foam wake trail behind the ship
    const trailStart = Math.max(0, p - 0.25);
    const steps = 12;
    let prevPt = null;
    for (let i = 0; i <= steps; i++) {
      const tp = trailStart + (p - trailStart) * (i / steps);
      const [lat, lon] = slerpPath(v.path, tp);
      const pt = map.latLngToContainerPoint([lat, lon]);
      if (prevPt) {
        const alpha = (0.08 + 0.55 * (i / steps)) * shipAlpha;
        ctx.beginPath();
        ctx.strokeStyle = `rgba(230, 242, 255, ${alpha})`;
        ctx.lineWidth = 1.8;
        ctx.moveTo(prevPt.x, prevPt.y);
        ctx.lineTo(pt.x, pt.y);
        ctx.stroke();
      }
      prevPt = pt;
    }

    // Ship position — drawn upright (no rotation), bow pointing left by default
    const [shipLat, shipLon] = slerpPath(v.path, p);
    const shipPt = map.latLngToContainerPoint([shipLat, shipLon]);
    const img = shipImages[v.shipVariant];
    ctx.globalAlpha = shipAlpha * 0.92;
    if (v.goingEast) {
      // Mirror horizontally so the bow points right
      ctx.save();
      ctx.translate(shipPt.x, 0);
      ctx.scale(-1, 1);
      ctx.drawImage(img, -SHIP_W / 2, shipPt.y - SHIP_H * 0.59, SHIP_W, SHIP_H);
      ctx.restore();
    } else {
      ctx.drawImage(img, shipPt.x - SHIP_W / 2, shipPt.y - SHIP_H * 0.59, SHIP_W, SHIP_H);
    }
    ctx.globalAlpha = 1;

    activeShips.push({ x: shipPt.x, y: shipPt.y, v });
  }
}

// ── Animation loop ─────────────────────────────────────────────────────────
function animate(ts) {
  requestAnimationFrame(animate);

  if (playing) {
    if (lastTs !== null) {
      const dt = Math.min((ts - lastTs) / 1000, 0.1);
      // Slow down in busy periods, speed up in quiet ones.
      // Clamp multiplier to [0.15, 5] so it never crawls or rockets.
      const busy = Math.max(getBusyness(currentYear), avgBusyness * 0.05);
      const adaptiveSpeed = speed * Math.max(0.15, Math.min(5, avgBusyness / busy));
      currentYear = Math.min(MAX_YEAR, currentYear + dt * adaptiveSpeed);

      for (const v of voyages) {
        if (!v.counted && v.t_start <= currentYear) {
          slavesCount += v.slaves;
          v.counted = true;
        }
      }

      if (!storyActive) {
        for (let i = 0; i < stories.length; i++) {
          const s = stories[i];
          if (!triggeredStories.has(i) && prevYear < s.triggerYear && currentYear >= s.triggerYear) {
            triggeredStories.add(i);
            showStory(s);
            break;
          }
        }
      }
      prevYear = currentYear;

      if (currentYear >= MAX_YEAR) {
        playing = false;
        playBtn.textContent = '↺ Replay';
      }

      syncUI();
    }
    lastTs = ts;
  } else {
    lastTs = null;
  }

  drawFrame();
}

// ── Story overlay ──────────────────────────────────────────────────────────
function splitSentences(text) {
  return text.split(/(?<=[.!?])\s+/).map(s => s.trim()).filter(Boolean);
}

function clearStoryTimers() {
  clearInterval(storyTypeTimer);
  storyTypeTimer = null;
  clearTimeout(storyPanelTimer);
  storyPanelTimer = null;
}

function showStory(story) {
  storyActive = true;
  storyData = story;
  storyPanelIdx = 0;
  playing = false;
  playBtn.textContent = '▶ Play';
  storyTitleEl.textContent = story.title;
  storyOverlay.style.opacity = '1';
  storyOverlay.style.pointerEvents = 'auto';
  showPanel(0);
  storyOverlay.addEventListener('click', onStoryClick);
}

function showPanel(idx) {
  const panel = storyData.panels[idx];
  storyInner.style.opacity = '0';
  setTimeout(() => {
    storyImg.src = panel.image;
    storyImg.alt = `${storyData.title} — panel ${idx + 1}`;
    storyProgress.innerHTML = storyData.panels
      .map((_, i) => `<span class="story-dot${i === idx ? ' active' : ''}"></span>`)
      .join('');
    storySentences = splitSentences(panel.text);
    storySentenceIdx = 0;
    storyTextEl.style.opacity = '1';
    storyTextEl.textContent = '';
    storyInner.style.opacity = '1';
    typeSentence(0);
  }, 600);
}

function typeSentence(sentenceIdx) {
  storySentenceIdx = sentenceIdx;
  const sentence = storySentences[sentenceIdx];

  // Pre-render the full sentence so the layout (centering) is fixed from the
  // start. Reveal each character span individually so already-visible text
  // never shifts position.
  storyTextEl.innerHTML = [...sentence].map(ch => {
    const esc = ch.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    return `<span class="story-char">${esc}</span>`;
  }).join('');

  const chars = storyTextEl.querySelectorAll('.story-char');
  let i = 0;
  clearStoryTimers();
  storyTypeTimer = setInterval(() => {
    chars[i].style.opacity = '1';
    i++;
    if (i >= chars.length) {
      clearInterval(storyTypeTimer);
      storyTypeTimer = null;
      storyPanelTimer = setTimeout(nextSentenceOrPanel, SENTENCE_PAUSE_MS);
    }
  }, TYPE_SPEED_MS);
}

function nextSentenceOrPanel() {
  if (storySentenceIdx + 1 < storySentences.length) {
    storyTextEl.style.opacity = '0';
    setTimeout(() => {
      storyTextEl.style.opacity = '1';
      typeSentence(storySentenceIdx + 1);
    }, 500);
  } else {
    advancePanel();
  }
}

function advancePanel() {
  storyPanelIdx++;
  if (storyPanelIdx < storyData.panels.length) {
    showPanel(storyPanelIdx);
  } else {
    hideStory();
  }
}

function onStoryClick() {
  if (storyTypeTimer) {
    // Typewriter still running — reveal all remaining chars immediately
    clearStoryTimers();
    storyTextEl.querySelectorAll('.story-char').forEach(el => { el.style.opacity = '1'; });
    storyPanelTimer = setTimeout(nextSentenceOrPanel, SENTENCE_PAUSE_MS);
  } else {
    // Sentence fully typed — advance immediately
    clearStoryTimers();
    nextSentenceOrPanel();
  }
}

function hideStory() {
  clearStoryTimers();
  storyOverlay.removeEventListener('click', onStoryClick);
  storyOverlay.style.opacity = '0';
  storyOverlay.style.pointerEvents = 'none';
  setTimeout(() => {
    storyActive = false;
    playing = true;
    playBtn.textContent = '⏸ Pause';
  }, 1400);
}

// ── Controls ───────────────────────────────────────────────────────────────
playBtn.addEventListener('click', () => {
  if (currentYear >= MAX_YEAR) {
    jumpToYear(MIN_YEAR);
    triggeredStories.clear();
    prevYear = MIN_YEAR - 0.01;
  }
  playing = !playing;
  playBtn.textContent = playing ? '⏸ Pause' : '▶ Play';
  if (playing) {
    oceanAudio.play().catch(() => {});
    if (ambienceAudio.src) ambienceAudio.play().catch(() => {});
  } else {
    oceanAudio.pause();
    ambienceAudio.pause();
  }
});

yearSlider.addEventListener('input', () => {
  const was_playing = playing;
  playing = false;
  const frac = parseInt(yearSlider.value, 10) / 10000;
  jumpToYear(MIN_YEAR + frac * (MAX_YEAR - MIN_YEAR));
  if (was_playing) {
    playing = true;
    playBtn.textContent = '⏸ Pause';
  }
});

function sliderToSpeed(v) {
  // Midpoint (15) = 0.15 yr/s = 1×. Slow half: 0.02–0.15. Fast half: 0.15–5.
  const BASE = 0.15;
  return v <= 15
    ? 0.02 + (v - 1) / 14 * (BASE - 0.02)
    : BASE  + (v - 15) / 15 * (5 - BASE);
}

speedSlider.addEventListener('input', () => {
  speed = sliderToSpeed(parseInt(speedSlider.value, 10));
  speedLabel.textContent = `Speed · ${(speed / 0.15).toFixed(1)}×`;
});

map.on('move zoom', drawFrame);

// ── Ocean audio ────────────────────────────────────────────────────────────
const oceanAudio    = document.getElementById('ocean-audio');
const ambienceAudio = document.getElementById('ambience-audio');
oceanAudio.volume    = 0.5;
ambienceAudio.volume = 0.4;

const AMBIENCE_TRACKS = [
  'music/ambience1.mp3',
  'music/ambience2.mp3',
  'music/ambience3.mp3',
  'music/ambience4.mp3',
  'music/ambience5.mp3',
];

function playNextAmbience() {
  const track = AMBIENCE_TRACKS[Math.floor(Math.random() * AMBIENCE_TRACKS.length)];
  ambienceAudio.src = track;
  ambienceAudio.play().catch(() => {});
}

ambienceAudio.addEventListener('ended', playNextAmbience);

// ── Start screen ───────────────────────────────────────────────────────────
const startScreen = document.getElementById('start-screen');
const startBtn    = document.getElementById('start-btn');

startBtn.addEventListener('click', () => {
  oceanAudio.play().catch(() => {});
  playNextAmbience();
  startScreen.style.opacity = '0';
  setTimeout(() => { startScreen.style.display = 'none'; }, 800);
  playing = true;
  playBtn.textContent = '⏸ Pause';
});

// ── Spacebar: toggle play/pause ────────────────────────────────────────────
// 'BUTTON' intentionally excluded from the skip list: e.preventDefault() below
// prevents the native space-to-click activation, so we get exactly one toggle
// regardless of whether the play button has focus.
document.addEventListener('keydown', e => {
  if (e.code === 'Space' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) {
    e.preventDefault();
    if (storyActive) {
      clearStoryTimers();
      onStoryClick();
    } else {
      playing = !playing;
      playBtn.textContent = playing ? '⏸ Pause' : '▶ Play';
      if (playing) {
        oceanAudio.play().catch(() => {});
        if (ambienceAudio.src) ambienceAudio.play().catch(() => {});
      } else {
        oceanAudio.pause();
        ambienceAudio.pause();
      }
    }
  }
  if (e.code === 'Escape' && storyActive) {
    hideStory();
  }
});

// ── Hover tooltip ──────────────────────────────────────────────────────────
const tooltip = document.getElementById('tooltip');

function formatDate(s) {
  if (!s) return '—';
  const parts = s.split('-');
  if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
  if (parts.length === 2) return `${parts[1]}/${parts[0]}`;
  return parts[0];
}

document.addEventListener('mousemove', e => {
  const mx = e.clientX, my = e.clientY;
  let hit = null;
  // Test from front (most recently drawn = topmost)
  for (let i = activeShips.length - 1; i >= 0; i--) {
    const { x, y, v } = activeShips[i];
    if (mx >= x - SHIP_W / 2 && mx <= x + SHIP_W / 2 &&
        my >= y - SHIP_H * 0.59 && my <= y + SHIP_H * 0.41) {
      hit = v;
      break;
    }
  }

  if (!hit) {
    tooltip.style.display = 'none';
    document.body.style.cursor = '';
    return;
  }

  document.body.style.cursor = 'crosshair';
  tooltip.innerHTML = `
    <div class="tt-vessel">${hit.vessel || 'Unknown vessel'}</div>
    <div class="tt-row">
      <span class="tt-label">Ocean</span>
      <span class="tt-val">${hit.ocean === 'atlantic' ? 'Atlantic' : 'Indian Ocean'}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Slaves embarked</span>
      <span class="tt-val">${hit.embarked != null ? hit.embarked.toLocaleString() : '—'}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Slaves disembarked</span>
      <span class="tt-val">${hit.disembarked != null ? hit.disembarked.toLocaleString() : '—'}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Departed</span>
      <span class="tt-val">${formatDate(hit.from_date)}</span>
    </div>
    <div class="tt-row">
      <span class="tt-label">Arrived</span>
      <span class="tt-val">${formatDate(hit.to_date)}</span>
    </div>
    <div class="tt-route">${hit.from_port || '?'} → ${hit.to_port || '?'}</div>
  `;

  // Position tooltip: prefer right of cursor, flip left if near edge
  const pad = 14;
  let tx = mx + pad, ty = my + pad;
  if (tx + 290 > window.innerWidth) tx = mx - 290 - pad;
  if (ty + tooltip.offsetHeight > window.innerHeight) ty = my - tooltip.offsetHeight - pad;
  tooltip.style.left = tx + 'px';
  tooltip.style.top  = ty + 'px';
  tooltip.style.display = 'block';
});

document.addEventListener('mouseleave', () => {
  tooltip.style.display = 'none';
});

// ── Boot ───────────────────────────────────────────────────────────────────
Promise.all([
  fetch(DATA_URL).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); }),
  fetch('../illustrations/stories.json').then(r => r.ok ? r.json() : []).catch(() => []),
])
  .then(([data, storyList]) => {
    voyages = prepareVoyages(data.voyages);
    buildYearlySlaves();
    stories = storyList;
    for (const s of stories) {
      for (const p of s.panels) {
        const img = new Image();
        img.src = p.image;
      }
    }
    console.log(`Loaded ${voyages.length} animatable voyages (${data.voyages.length} total)`);
    jumpToYear(MIN_YEAR);
    document.getElementById('loading').style.display = 'none';
    playing = false;
    playBtn.textContent = '▶ Play';
    const ready = shipImages.filter(img => !img.complete).length;
    if (ready === 0) {
      requestAnimationFrame(animate);
    } else {
      let loaded = 0;
      const onLoad = () => { if (++loaded === ready) requestAnimationFrame(animate); };
      shipImages.forEach(img => { if (!img.complete) img.onload = onLoad; });
    }
  })
  .catch(err => {
    document.querySelector('#loading p').textContent = `Error: ${err.message}`;
  });
