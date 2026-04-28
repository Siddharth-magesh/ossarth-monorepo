/**
 * OSSARTH — dashboard/static/dashboard.js
 *
 * Client-side logic for the System Monitor Dashboard.
 * - Connects to SSE /metrics endpoint
 * - Updates all panels on every event
 * - Handles POST /command from the input box
 * - Renders sparklines with Chart.js
 * - Diffs process table rows to avoid full re-renders
 */

'use strict';

// ═══════════════════════════════════════════ STATE ═══
const sparklineHistory = {
  cpu: [],
  ram: [],
  gpu: [],
  threads: [],
};
const SPARKLINE_LEN = 60;

let prevThreadCount = 0;
let knownPids = new Set();
let cpuDonutChart = null;
let sparklineCharts = {};
let logEntries = [];

// ═══════════════════════════════════════ SSE SETUP ═══

function initSSE() {
  const dot = document.getElementById('status-dot');
  const es = new EventSource('/metrics');

  es.onopen = () => {
    dot.className = 'status-dot connected';
    dot.title = 'Connected';
  };

  es.onmessage = (event) => {
    try {
      const state = JSON.parse(event.data);
      updateAll(state);
    } catch (e) {
      console.error('SSE parse error:', e);
    }
  };

  es.onerror = () => {
    dot.className = 'status-dot error';
    dot.title = 'Disconnected — reconnecting...';
    // EventSource auto-reconnects, no manual handling needed
  };
}

// ═══════════════════════════════════ MAIN UPDATE ═══

function updateAll(state) {
  updateHeader(state);
  updateCpuGauge(state.cpu_usage_percent || 0);
  updateRamBar(state.used_ram_mb || 0, state.total_ram_mb || 8192);
  updateGpuBar(state.used_gpu_vram_mb || 0, state.total_gpu_vram_mb || 4096);
  updateThreadCounter(state.active_threads || 0, state.context_switches_per_sec || 0);
  updateCoreGrid(state.cpu_per_core || []);
  updateProcessTable(state.process_table || []);
  updateSchedulerQueue(state.scheduler_queue || [], state.context_switches_per_sec || 0, state.scheduler_algorithm || 'round_robin');
  pushSparklines(state);
}

// ════════════════════════════════════ HEADER ═════════
function updateHeader(state) {
  // Uptime
  const secs = Math.floor(state.uptime_seconds || 0);
  const h = String(Math.floor(secs / 3600)).padStart(2, '0');
  const m = String(Math.floor((secs % 3600) / 60)).padStart(2, '0');
  const s = String(secs % 60).padStart(2, '0');
  setText('uptime', `${h}:${m}:${s}`);

  setText('cmd-count', state.command_count || 0);

  const lat = state.last_command_latency_ms;
  setText('latency', lat ? `${Math.round(lat)}ms` : '—');
}

// ══════════════════════════════════ CPU DONUT ═════════
function initCpuDonut() {
  const canvas = document.getElementById('cpu-donut');
  const ctx = canvas.getContext('2d');

  cpuDonutChart = new Chart(ctx, {
    type: 'doughnut',
    data: {
      datasets: [{
        data: [0, 100],
        backgroundColor: ['#00d4ff', 'rgba(255,255,255,0.04)'],
        borderColor: ['#007aa3', 'transparent'],
        borderWidth: [2, 0],
        hoverOffset: 0,
      }],
    },
    options: {
      cutout: '72%',
      animation: { duration: 500 },
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      events: [],
    },
  });
}

function updateCpuGauge(percent) {
  percent = Math.min(100, Math.max(0, percent));
  if (cpuDonutChart) {
    cpuDonutChart.data.datasets[0].data = [percent, 100 - percent];
    // Color based on load
    const color = percent > 80 ? '#ff4757' : percent > 60 ? '#ffd93d' : '#00d4ff';
    cpuDonutChart.data.datasets[0].backgroundColor[0] = color;
    cpuDonutChart.update('none');
  }
  setText('cpu-value', Math.round(percent));
}

// ══════════════════════════════════ RAM BAR ═══════════
function updateRamBar(used, total) {
  const pct = total > 0 ? (used / total) * 100 : 0;
  setStyle('ram-bar', 'width', `${Math.min(100, pct).toFixed(1)}%`);
  setText('ram-used', used.toLocaleString());
  setText('ram-total', total.toLocaleString());
  setText('ram-pct', `${Math.round(pct)}%`);
}

// ══════════════════════════════════ GPU BAR ═══════════
function updateGpuBar(used, total) {
  const pct = total > 0 ? (used / total) * 100 : 0;
  setStyle('gpu-bar', 'width', `${Math.min(100, pct).toFixed(1)}%`);
  setText('gpu-used', used.toLocaleString());
  setText('gpu-total', total.toLocaleString());
  setText('gpu-pct', `${Math.round(pct)}%`);
}

// ═════════════════════════════ THREAD COUNTER ═════════
function updateThreadCounter(count, ctxSwitches) {
  setText('thread-count', count);
  setText('ctx-switches', Math.round(ctxSwitches).toLocaleString());
  setText('sched-cs', Math.round(ctxSwitches).toLocaleString());

  const delta = count - prevThreadCount;
  const el = document.getElementById('thread-delta');
  if (delta !== 0 && prevThreadCount !== 0) {
    el.textContent = delta > 0 ? `+${delta}` : `${delta}`;
    el.className = `counter-delta ${delta > 0 ? 'up' : 'down'}`;
    setTimeout(() => { el.textContent = ''; el.className = 'counter-delta'; }, 2000);
  }
  prevThreadCount = count;
}

// ════════════════════════════════ CORE GRID ═══════════
function updateCoreGrid(perCore) {
  const grid = document.getElementById('core-grid');
  // Build or update
  if (grid.children.length !== perCore.length) {
    grid.innerHTML = '';
    perCore.forEach((_, i) => {
      const item = document.createElement('div');
      item.className = 'core-item';
      item.innerHTML = `
        <div class="core-bar-track">
          <div class="core-bar-fill" id="core-bar-${i}" style="height:2px"></div>
        </div>
        <div class="core-label">C${i}</div>
        <div class="core-val" id="core-val-${i}">0%</div>
      `;
      grid.appendChild(item);
    });
  }

  perCore.forEach((pct, i) => {
    const fill = document.getElementById(`core-bar-${i}`);
    const val  = document.getElementById(`core-val-${i}`);
    if (fill) {
      const h = Math.max(2, Math.min(48, (pct / 100) * 48));
      fill.style.height = `${h}px`;
      // Color coding
      fill.style.background = pct > 80
        ? 'linear-gradient(180deg,#ff4757,#ff6b35)'
        : pct > 60
          ? 'linear-gradient(180deg,#ffd93d,#f97316)'
          : 'linear-gradient(180deg,#00d4ff,#3b82f6)';
    }
    if (val) val.textContent = `${Math.round(pct)}%`;
  });
}

// ═══════════════════════════ PROCESS TABLE ═══════════
function updateProcessTable(processes) {
  const tbody = document.getElementById('proc-tbody');
  const countEl = document.getElementById('proc-count');
  countEl.textContent = `${processes.length} process${processes.length !== 1 ? 'es' : ''}`;

  const currentPids = new Set(processes.map(p => p.pid));

  // Remove dead rows
  knownPids.forEach(pid => {
    if (!currentPids.has(pid)) {
      const row = document.getElementById(`proc-row-${pid}`);
      if (row) {
        row.className = 'proc-row-dead';
        setTimeout(() => row.remove(), 500);
      }
      knownPids.delete(pid);
    }
  });

  // Add or update rows
  processes.forEach(proc => {
    let row = document.getElementById(`proc-row-${proc.pid}`);
    const started = proc.started ? new Date(proc.started).toLocaleTimeString() : '—';
    const inner = `
      <td class="pid-col">${proc.pid}</td>
      <td class="name-col">${escHtml(proc.name || '—')}</td>
      <td class="cmd-col">${escHtml((proc.cmd || '').slice(0, 40))}</td>
      <td class="cpu-col">${(proc.cpu_percent || 0).toFixed(1)}%</td>
      <td class="mem-col">${(proc.memory_mb || 0).toFixed(0)}</td>
      <td class="stat-col">${escHtml(proc.status || 'running')}</td>
      <td class="time-col">${started}</td>
    `;

    if (!row) {
      row = document.createElement('tr');
      row.id = `proc-row-${proc.pid}`;
      row.className = 'proc-row-new';
      tbody.appendChild(row);
      knownPids.add(proc.pid);
    }
    row.innerHTML = inner;
  });

  // Show/hide empty state
  const emptyRow = tbody.querySelector('.empty-row');
  if (processes.length === 0) {
    if (!emptyRow) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No processes running</td></tr>';
    }
  } else if (emptyRow) {
    emptyRow.remove();
  }
}

// ═══════════════════════════ SCHEDULER QUEUE ═════════
function updateSchedulerQueue(queue, ctxSwitches, algo) {
  const list = document.getElementById('sched-list');
  const algoEl = document.getElementById('sched-algo');
  algoEl.textContent = algo || 'round_robin';

  list.innerHTML = '';
  if (!queue || queue.length === 0) {
    list.innerHTML = '<div class="sched-item placeholder">Awaiting processes...</div>';
    return;
  }
  queue.forEach((name, i) => {
    const item = document.createElement('div');
    item.className = `sched-item${i === 0 ? ' active' : ''}`;
    item.textContent = name;
    list.appendChild(item);
  });
}

// ══════════════════════════════════ SPARKLINES ═══════
function pushSparklines(state) {
  const push = (arr, val) => {
    arr.push(val);
    if (arr.length > SPARKLINE_LEN) arr.shift();
  };
  push(sparklineHistory.cpu,     state.cpu_usage_percent || 0);
  push(sparklineHistory.ram,     ((state.used_ram_mb || 0) / (state.total_ram_mb || 8192)) * 100);
  push(sparklineHistory.gpu,     ((state.used_gpu_vram_mb || 0) / (state.total_gpu_vram_mb || 4096)) * 100);
  push(sparklineHistory.threads, state.active_threads || 0);

  updateSparkline('cpu-sparkline',    sparklineHistory.cpu,     '#00d4ff');
  updateSparkline('ram-sparkline',    sparklineHistory.ram,     '#3b82f6');
  updateSparkline('gpu-sparkline',    sparklineHistory.gpu,     '#a855f7');
  updateSparkline('thread-sparkline', sparklineHistory.threads, '#00ff9f');
}

function initSparkline(id, color) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: Array(SPARKLINE_LEN).fill(''),
      datasets: [{
        data: Array(SPARKLINE_LEN).fill(0),
        borderColor: color,
        borderWidth: 1.5,
        fill: true,
        backgroundColor: `${color}18`,
        tension: 0.4,
        pointRadius: 0,
      }],
    },
    options: {
      animation: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false, min: 0 },
      },
      elements: { line: { borderCapStyle: 'round' } },
      responsive: true,
      maintainAspectRatio: false,
    },
  });
  sparklineCharts[id] = chart;
}

function updateSparkline(id, data, color) {
  const chart = sparklineCharts[id];
  if (!chart) return;
  chart.data.datasets[0].data = [...data];
  chart.update('none');
}

async function loadInitialHistory() {
  try {
    const res = await fetch('/history?seconds=60');
    const snapshots = await res.json();
    snapshots.forEach(state => {
      sparklineHistory.cpu.push(state.cpu_usage_percent || 0);
      sparklineHistory.ram.push(((state.used_ram_mb || 0) / (state.total_ram_mb || 8192)) * 100);
      sparklineHistory.gpu.push(((state.used_gpu_vram_mb || 0) / (state.total_gpu_vram_mb || 4096)) * 100);
      sparklineHistory.threads.push(state.active_threads || 0);
    });
  } catch (e) { /* ignore */ }
}

// ══════════════════════════════ COMMAND INPUT ═════════
async function sendCommand() {
  const input = document.getElementById('cmd-input');
  const btn   = document.getElementById('cmd-btn');
  const status = document.getElementById('cmd-status');

  const text = input.value.trim();
  if (!text) return;

  btn.disabled = true;
  btn.textContent = '...';
  status.textContent = 'Processing...';
  status.style.color = 'var(--text-secondary)';

  try {
    const res = await fetch('/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: text }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    status.textContent = data.all_succeeded
      ? `✓ ${data.results.length} step(s) completed in ${Math.round(data.duration_ms)}ms`
      : `⚠ Completed with errors in ${Math.round(data.duration_ms)}ms`;
    status.style.color = data.all_succeeded ? 'var(--green)' : 'var(--yellow)';

    appendCommandLog(data);
    input.value = '';

  } catch (e) {
    status.textContent = `✗ Error: ${e.message}`;
    status.style.color = 'var(--red)';
  } finally {
    btn.disabled = false;
    btn.textContent = 'RUN';
  }
}

// ═══════════════════════════════ COMMAND LOG ══════════
function appendCommandLog(data) {
  const list = document.getElementById('log-list');
  // Remove placeholder
  const ph = list.querySelector('.log-placeholder');
  if (ph) ph.remove();

  const entry = document.createElement('div');
  const success = data.all_succeeded;
  entry.className = `log-entry ${success ? 'success' : 'failure'}`;

  const ts = new Date().toLocaleTimeString();
  const taskType = data.intent?.task_type || 'unknown';
  const totalMs  = Math.round(data.duration_ms);

  const toolTags = (data.results || []).map(r =>
    `<span class="log-tool-tag${r.success ? '' : ' failed'}">${escHtml(r.tool)}</span>`
  ).join('');

  entry.innerHTML = `
    <div class="log-header">
      <span class="log-ts">${ts}</span>
      <span class="log-type">${escHtml(taskType)}</span>
      <span class="log-input">${escHtml(data.input)}</span>
      <span class="log-time">${totalMs}ms</span>
    </div>
    <div class="log-tools">${toolTags}</div>
  `;

  // Prepend (newest at top due to column-reverse on list)
  list.insertBefore(entry, list.firstChild);

  // Cap at 50 entries
  while (list.children.length > 50) list.removeChild(list.lastChild);
}

// ═══════════════════════════════════ HELPERS ══════════
function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function setStyle(id, prop, val) {
  const el = document.getElementById(id);
  if (el) el.style[prop] = val;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ════════════════════════════════ KEYBOARD ════════════
document.addEventListener('DOMContentLoaded', () => {
  const input = document.getElementById('cmd-input');
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendCommand();
    }
  });
});

// ═════════════════════════════════════ INIT ═══════════
(async function init() {
  // Init charts
  initCpuDonut();
  initSparkline('cpu-sparkline',    '#00d4ff');
  initSparkline('ram-sparkline',    '#3b82f6');
  initSparkline('gpu-sparkline',    '#a855f7');
  initSparkline('thread-sparkline', '#00ff9f');

  // Load history for sparklines
  await loadInitialHistory();

  // Load recent commands
  try {
    const res = await fetch('/history/commands');
    const cmds = await res.json();
    cmds.slice().reverse().forEach(cmd => {
      appendCommandLog({
        input: cmd.input,
        all_succeeded: cmd.success,
        intent: { task_type: cmd.task_type },
        results: (cmd.tools_used || []).map(t => ({ tool: t, success: true })),
        duration_ms: cmd.duration_ms,
      });
    });
  } catch (e) { /* ignore */ }

  // Start SSE
  initSSE();
})();
