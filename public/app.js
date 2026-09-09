// State Management
let currentDataset = null;
let userApiKey = localStorage.getItem("gemini_api_key") || "";
let chartCounter = 0;

document.addEventListener("DOMContentLoaded", () => {
  initTabs();
  initModals();
  initChat();
  initUpload();
  fetchDatasetInfo();
  
  if (userApiKey) {
    document.getElementById("gemini-key-input").value = userApiKey;
  }
  updateLlmButtonState();
});

// Fetch Dataset Overview & Populate Tabs
async function fetchDatasetInfo() {
  try {
    const res = await fetch("/api/info");
    if (!res.ok) throw new Error("Failed to load dataset info");
    const data = await res.json();
    currentDataset = data;

    // Update Header Badges
    document.getElementById("meta-filename").textContent = data.dataset_name || "dataset.csv";
    document.getElementById("meta-rows").textContent = `${data.rows.toLocaleString()} rows`;
    document.getElementById("meta-cols").textContent = `${data.columns_count} cols`;
    document.getElementById("meta-memory").textContent = `${data.memory_mb} MB`;
    document.getElementById("dataset-badge").classList.remove("hidden");

    // Populate Schema Tab
    document.getElementById("schema-raw").textContent = data.schema || "No schema extracted.";

    // Populate Dynamic Ignored Columns
    const ignoredContainer = document.getElementById("ignored-cols-list");
    if (ignoredContainer) {
      ignoredContainer.innerHTML = "";
      if (data.ignored_columns && data.ignored_columns.length > 0) {
        data.ignored_columns.forEach(col => {
          const badge = document.createElement("span");
          badge.className = "text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-amber-300 font-mono border border-slate-700 flex items-center gap-1.5";
          badge.innerHTML = `<i class="fa-solid fa-filter-circle-xmark text-[10px] text-amber-400"></i> ${escapeHtml(col)}`;
          ignoredContainer.appendChild(badge);
        });
      } else {
        ignoredContainer.innerHTML = `<span class="text-xs text-slate-500 italic">No columns ignored (all columns active)</span>`;
      }
    }

    // Populate Summary Tab
    document.getElementById("summary-raw").textContent = data.summary || "No summary available.";

    // Populate Data Dictionary Tab
    document.getElementById("dict-raw").textContent = data.data_dictionary || "No data dictionary found.";

    // Populate Preview Table
    renderPreviewTable(data.columns, data.sample_rows);

  } catch (err) {
    console.error("Error fetching info:", err);
  }
}

// Render Preview Table
function renderPreviewTable(columns, sampleRows) {
  const thead = document.getElementById("preview-thead");
  const tbody = document.getElementById("preview-tbody");
  
  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!columns || !sampleRows || sampleRows.length === 0) {
    tbody.innerHTML = `<tr><td class="p-4 text-center text-slate-500">No preview records available.</td></tr>`;
    return;
  }

  columns.forEach(col => {
    const th = document.createElement("th");
    th.className = "px-4 py-3 font-semibold text-slate-300";
    th.innerHTML = `${col.name} <span class="text-[9px] text-slate-500 font-mono block">${col.type}</span>`;
    thead.appendChild(th);
  });

  sampleRows.forEach((row, i) => {
    const tr = document.createElement("tr");
    tr.className = i % 2 === 0 ? "bg-slate-900/60" : "bg-slate-950/60";
    columns.forEach(col => {
      const td = document.createElement("td");
      td.className = "px-4 py-2.5 whitespace-nowrap border-t border-slate-800/60";
      const val = row[col.name];
      td.textContent = val !== null && val !== undefined ? val : "null";
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

// Tab Switching
function initTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabPanes = document.querySelectorAll(".tab-pane");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");

      tabBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");

      tabPanes.forEach(p => {
        if (p.id === targetId) {
          p.classList.remove("hidden");
        } else {
          p.classList.add("hidden");
        }
      });
    });
  });
}

// Chat Flow
function initChat() {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const stream = document.getElementById("chat-stream");

  // Query chips
  document.querySelectorAll(".query-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      input.value = chip.textContent.trim();
      form.dispatchEvent(new Event("submit"));
    });
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const query = input.value.trim();
    if (!query) return;

    input.value = "";
    appendUserMessage(query);

    const loadingId = appendLoadingIndicator();
    stream.scrollTop = stream.scrollHeight;

    try {
      const res = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          query: query,
          api_key: userApiKey || null
        })
      });

      removeElement(loadingId);

      if (!res.ok) {
        const errData = await res.json();
        const detail = errData.detail || "Error querying data agent.";
        if (detail.includes("NO_LLM_KEY")) {
          appendApiKeyPrompt();
          document.getElementById("settings-modal").classList.remove("hidden");
        } else {
          appendErrorMessage(detail);
        }
        return;
      }

      const data = await res.json();
      appendAgentResponse(data);
    } catch (err) {
      removeElement(loadingId);
      appendErrorMessage(err.message || "Failed to reach server.");
    }

    stream.scrollTop = stream.scrollHeight;
  });
}

// Append User Message
function appendUserMessage(text) {
  const stream = document.getElementById("chat-stream");
  const msg = document.createElement("div");
  msg.className = "flex justify-end";
  msg.innerHTML = `
    <div class="max-w-2xl bg-indigo-600 text-white rounded-2xl rounded-tr-sm px-4 py-3 text-xs leading-relaxed shadow-sm">
      <p class="font-medium">${escapeHtml(text)}</p>
    </div>
  `;
  stream.appendChild(msg);
}

// Loading Indicator
function appendLoadingIndicator() {
  const id = "loading-" + Date.now();
  const stream = document.getElementById("chat-stream");
  const el = document.createElement("div");
  el.id = id;
  el.className = "flex items-start gap-3";
  el.innerHTML = `
    <div class="h-8 w-8 rounded-lg bg-indigo-600/20 text-indigo-400 flex items-center justify-center shrink-0 border border-indigo-500/20">
      <i class="fa-solid fa-spinner fa-spin text-sm"></i>
    </div>
    <div class="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-sm px-4 py-3 text-xs text-slate-400 flex items-center gap-2">
      <span>Analyzing schema, generating safe code, and executing...</span>
    </div>
  `;
  stream.appendChild(el);
  return id;
}

// Append Agent Response
function appendAgentResponse(data) {
  const stream = document.getElementById("chat-stream");
  const exec = data.execution;
  const chartId = `chart-${++chartCounter}`;

  const container = document.createElement("div");
  container.className = "flex items-start gap-3";

  // Provider label
  let providerBadge = "";
  const prov = (data.provider || "").toLowerCase();
  if (prov.includes("gemini")) {
    providerBadge = `<span class="badge-info text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 font-medium"><i class="fa-solid fa-brain mr-1"></i>Gemini 3.6 Flash</span>`;
  } else if (prov.includes("groq")) {
    providerBadge = `<span class="badge-info text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-purple-500/20 text-purple-300 border border-purple-500/40 font-medium"><i class="fa-solid fa-bolt mr-1"></i>Groq Llama 3.3</span>`;
  } else if (prov.includes("openai")) {
    providerBadge = `<span class="badge-info text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-medium"><i class="fa-solid fa-microchip mr-1"></i>OpenAI GPT-4o</span>`;
  } else if (prov.includes("ollama")) {
    providerBadge = `<span class="badge-info text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-medium"><i class="fa-solid fa-server mr-1"></i>Local Ollama</span>`;
  } else {
    providerBadge = `<span class="bg-slate-800 text-slate-400 border border-slate-700 text-[10px] font-mono px-2 py-0.5 rounded-full font-medium"><i class="fa-solid fa-robot mr-1"></i>${escapeHtml(data.provider || 'Offline')}</span>`;
  }

  // Safety status badge
  let safetyBadge = "";
  if (exec.success) {
    safetyBadge = `<span class="badge-safe text-[10px] font-mono px-2 py-0.5 rounded-full"><i class="fa-solid fa-shield-check mr-1"></i>Code Safety Passed</span>`;
  } else {
    safetyBadge = `<span class="badge-unsafe text-[10px] font-mono px-2 py-0.5 rounded-full"><i class="fa-solid fa-triangle-exclamation mr-1"></i>${escapeHtml(exec.error_type || "Error")}</span>`;
  }

  let resultContent = "";

  if (!exec.success) {
    resultContent = `
      <div class="bg-red-950/30 border border-red-500/30 rounded-xl p-4 text-xs text-red-300">
        <p class="font-semibold mb-1">Execution Failed:</p>
        <p class="font-mono text-[11px]">${escapeHtml(exec.error || "Unknown execution error")}</p>
      </div>
    `;
  } else if (exec.result_type === "scalar") {
    resultContent = `
      <div class="bg-slate-950 p-5 rounded-xl border border-slate-800 text-center my-2">
        <span class="text-xs text-slate-400 uppercase tracking-widest font-semibold block mb-1">Result Metric</span>
        <span class="text-3xl font-bold text-white font-mono tracking-tight">${exec.display}</span>
      </div>
    `;
  } else if (exec.result_type === "dataframe") {
    // Generate Table HTML
    let colsHtml = exec.columns.map(c => `<th class="px-3 py-2 text-slate-300 font-semibold uppercase text-[10px] tracking-wider">${escapeHtml(c)}</th>`).join("");
    let rowsHtml = exec.data.map((row, i) => {
      let cells = exec.columns.map(col => {
        let val = row[col];
        if (typeof val === "number") {
          val = Number.isInteger(val) ? val.toLocaleString() : val.toFixed(2);
        }
        return `<td class="px-3 py-2 whitespace-nowrap text-slate-300 font-mono text-[11px] border-t border-slate-800/80">${escapeHtml(String(val !== null ? val : ""))}</td>`;
      }).join("");
      return `<tr class="${i % 2 === 0 ? 'bg-slate-900/40' : 'bg-slate-950/40'}">${cells}</tr>`;
    }).join("");

    // Build Automated Insights HTML
    let insightsHtml = "";
    if (exec.insights && exec.insights.length > 0) {
      insightsHtml = `
        <div class="bg-gradient-to-r from-indigo-950/30 to-slate-900 border border-indigo-500/30 rounded-xl p-4 space-y-3">
          <div class="flex items-center gap-2 text-xs font-semibold text-indigo-300">
            <i class="fa-solid fa-lightbulb text-amber-400 text-sm"></i>
            <span>Data Observations & Graph Insights</span>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5">
            ${exec.insights.map(ins => `
              <div class="bg-slate-950/70 border border-slate-800/90 p-3 rounded-lg text-xs flex items-start gap-2.5 shadow-sm">
                <div class="h-6 w-6 rounded-md bg-indigo-500/10 text-indigo-400 flex items-center justify-center shrink-0 mt-0.5 border border-indigo-500/20">
                  <i class="fa-solid ${ins.icon} text-xs"></i>
                </div>
                <div>
                  <div class="font-semibold text-slate-200 text-xs mb-0.5">${ins.title}</div>
                  <div class="text-slate-400 text-[11px] leading-relaxed">${ins.text}</div>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    resultContent = `
      <div class="space-y-4">
        <!-- Automated Graph & Observation Insights -->
        ${insightsHtml}

        <!-- Interactive Chart Placeholder -->
        ${exec.chart ? `<div id="${chartId}" class="w-full h-72 rounded-xl bg-slate-950 border border-slate-800 p-2"></div>` : ""}

        <!-- Data Table -->
        <div class="bg-slate-950 rounded-xl border border-slate-800 overflow-hidden">
          <div class="px-4 py-2 bg-slate-800/60 border-b border-slate-800 flex justify-between items-center text-xs">
            <span class="text-slate-400">Showing <strong class="text-white">${exec.displayed_rows}</strong> of <strong class="text-white">${exec.total_rows}</strong> rows</span>
            <button onclick="downloadCSV(${JSON.stringify(exec.columns).replace(/"/g, '&quot;')}, ${JSON.stringify(exec.data).replace(/"/g, '&quot;')})" class="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium">
              <i class="fa-solid fa-download"></i> Export CSV
            </button>
          </div>
          <div class="overflow-x-auto max-h-64">
            <table class="w-full text-left text-xs border-collapse">
              <thead class="bg-slate-800/90 text-left sticky top-0"><tr>${colsHtml}</tr></thead>
              <tbody>${rowsHtml}</tbody>
            </table>
          </div>
        </div>
      </div>
    `;
  } else {
    resultContent = `
      <div class="bg-slate-950 p-4 rounded-xl border border-slate-800 font-mono text-xs text-slate-300">
        ${escapeHtml(JSON.stringify(exec.value, null, 2))}
      </div>
    `;
  }

  container.innerHTML = `
    <div class="h-8 w-8 rounded-lg bg-indigo-600/20 text-indigo-400 flex items-center justify-center shrink-0 border border-indigo-500/20 mt-1">
      <i class="fa-solid fa-wand-magic-sparkles text-sm"></i>
    </div>
    <div class="flex-1 bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-sm p-5 space-y-4 max-w-4xl shadow-sm">
      <div class="flex items-center justify-between gap-2 border-b border-slate-800/80 pb-3 flex-wrap">
        <div class="flex items-center gap-2">
          ${providerBadge}
          ${safetyBadge}
        </div>
        <button class="toggle-code-btn text-[11px] text-slate-400 hover:text-white flex items-center gap-1">
          <i class="fa-solid fa-code text-indigo-400"></i>
          <span>Toggle Generated Code</span>
        </button>
      </div>

      <!-- Collapsible Code Container -->
      <div class="code-container hidden">
        <div class="code-box p-3 text-xs overflow-x-auto text-indigo-300 relative group">
          <pre class="font-mono"><code>${escapeHtml(exec.code || "")}</code></pre>
        </div>
      </div>

      <!-- Execution Result -->
      ${resultContent}
    </div>
  `;

  stream.appendChild(container);

  // Toggle code view listener
  const toggleBtn = container.querySelector(".toggle-code-btn");
  const codeBox = container.querySelector(".code-container");
  if (toggleBtn && codeBox) {
    toggleBtn.addEventListener("click", () => {
      codeBox.classList.toggle("hidden");
    });
  }

  // Render Plotly chart if present
  if (exec.success && exec.chart) {
    renderPlotlyChart(chartId, exec.chart);
  }
}

// Render Plotly Chart
function renderPlotlyChart(elementId, chart) {
  const el = document.getElementById(elementId);
  if (!el || typeof Plotly === "undefined") return;

  const darkLayout = {
    paper_bgcolor: "transparent",
    plot_bgcolor: "transparent",
    margin: { t: 40, r: 20, l: 50, b: 40 },
    font: { family: "inherit", color: "#94a3b8", size: 11 },
    title: { text: chart.title, font: { color: "#f8fafc", size: 13 } },
    xaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" },
    yaxis: { gridcolor: "#1e293b", zerolinecolor: "#334155" }
  };

  const config = { responsive: true, displayModeBar: false };

  if (chart.type === "grouped_bar" || (chart.barmode === "group" && chart.series)) {
    const palette = ["#6366f1", "#06b6d4", "#ec4899", "#10b981", "#f59e0b", "#8b5cf6", "#3b82f6"];
    const traces = chart.series.map((s, idx) => ({
      type: "bar",
      name: s.name,
      x: chart.x,
      y: s.y,
      marker: { color: palette[idx % palette.length] },
      opacity: 0.9
    }));
    Plotly.newPlot(el, traces, {
      ...darkLayout,
      barmode: "group",
      legend: { font: { color: "#cbd5e1" }, orientation: "h", y: -0.2 }
    }, config);
  } else if (chart.type === "bar") {
    Plotly.newPlot(el, [{
      type: "bar",
      x: chart.x,
      y: chart.y,
      marker: { color: "#6366f1", opacity: 0.9 }
    }], darkLayout, config);
  } else if (chart.type === "line") {
    Plotly.newPlot(el, [{
      type: "scatter",
      mode: "lines+markers",
      x: chart.x,
      y: chart.y,
      line: { color: "#818cf8", width: 2.5 },
      marker: { color: "#6366f1", size: 6 }
    }], darkLayout, config);
  } else if (chart.type === "pie") {
    darkLayout.margin = { t: 40, r: 20, l: 20, b: 20 };
    Plotly.newPlot(el, [{
      type: "pie",
      hole: 0.5,
      labels: chart.labels,
      values: chart.values,
      marker: { colors: ["#6366f1", "#8b5cf6", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", "#84cc16"] }
    }], darkLayout, config);
  } else if (chart.type === "scatter") {
    Plotly.newPlot(el, [{
      type: "scatter",
      mode: "markers",
      x: chart.x,
      y: chart.y,
      marker: { color: "#06b6d4", size: 8, opacity: 0.8 }
    }], darkLayout, config);
  }
}

// Append Error Message
function appendErrorMessage(text) {
  const stream = document.getElementById("chat-stream");
  const el = document.createElement("div");
  el.className = "flex items-start gap-3";
  el.innerHTML = `
    <div class="h-8 w-8 rounded-lg bg-red-600/20 text-red-400 flex items-center justify-center shrink-0 border border-red-500/20">
      <i class="fa-solid fa-triangle-exclamation text-sm"></i>
    </div>
    <div class="bg-slate-900 border border-red-500/30 text-red-300 rounded-2xl rounded-tl-sm px-4 py-3 text-xs">
      ${escapeHtml(text)}
    </div>
  `;
  stream.appendChild(el);
}

// Upload & Remote URL Handling
function initUpload() {
  const fileInput = document.getElementById("file-input");
  const dropZone = document.getElementById("drop-zone");
  const uploadStatus = document.getElementById("upload-status");
  const btnLoadUrl = document.getElementById("btn-load-url");
  const urlInput = document.getElementById("url-input");
  const btnReset = document.getElementById("btn-reset-dataset");

  dropZone.addEventListener("click", () => fileInput.click());

  dropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropZone.classList.add("border-indigo-500");
  });

  dropZone.addEventListener("dragleave", () => {
    dropZone.classList.remove("border-indigo-500");
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropZone.classList.remove("border-indigo-500");
    if (e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      handleFileUpload(e.target.files[0]);
    }
  });

  async function handleFileUpload(file) {
    if (file.size > 10 * 1024 * 1024) {
      alert("File exceeds maximum allowed limit of 10MB.");
      return;
    }

    uploadStatus.classList.remove("hidden");
    uploadStatus.textContent = `Uploading and parsing ${file.name}...`;

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Upload failed");

      uploadStatus.textContent = `Successfully loaded ${file.name}!`;
      closeModals();
      fetchDatasetInfo();
    } catch (err) {
      uploadStatus.textContent = `Error: ${err.message}`;
    }
  }

  // Load from URL
  btnLoadUrl.addEventListener("click", async () => {
    const url = urlInput.value.trim();
    if (!url) return;

    btnLoadUrl.disabled = true;
    btnLoadUrl.textContent = "Loading...";

    try {
      const res = await fetch("/api/load-url", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Failed to load URL");

      urlInput.value = "";
      closeModals();
      fetchDatasetInfo();
    } catch (err) {
      alert(`Error loading dataset from URL: ${err.message}`);
    } finally {
      btnLoadUrl.disabled = false;
      btnLoadUrl.textContent = "Load";
    }
  });

  // Reset to default sample
  if (btnReset) {
    btnReset.addEventListener("click", async () => {
      try {
        await fetch("/api/reset", { method: "POST" });
        fetchDatasetInfo();
        alert("Reset to default retail dataset.");
      } catch (err) {
        alert("Failed to reset dataset.");
      }
    });
  }
}

// Modals
function initModals() {
  const uploadModal = document.getElementById("upload-modal");
  const settingsModal = document.getElementById("settings-modal");
  const btnUploadOpen = document.getElementById("btn-upload-modal");
  const btnSettingsOpen = document.getElementById("btn-settings-modal");
  const btnSaveKey = document.getElementById("btn-save-key");

  btnUploadOpen.addEventListener("click", () => uploadModal.classList.remove("hidden"));
  btnSettingsOpen.addEventListener("click", () => settingsModal.classList.remove("hidden"));

  document.querySelectorAll(".btn-close-modal").forEach(btn => {
    btn.addEventListener("click", closeModals);
  });

  btnSaveKey.addEventListener("click", () => {
    const key = document.getElementById("gemini-key-input").value.trim();
    userApiKey = key;
    if (key) {
      localStorage.setItem("gemini_api_key", key);
    } else {
      localStorage.removeItem("gemini_api_key");
    }
    closeModals();
    updateLlmButtonState();
alert("LLM configuration saved! All queries will now route through this LLM.");
  });
}

function closeModals() {
  document.getElementById("upload-modal").classList.add("hidden");
  document.getElementById("settings-modal").classList.add("hidden");
}

// Utilities
function removeElement(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function copyToClipboard(id) {
  const text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(() => {
    alert("Copied to clipboard!");
  });
}

function downloadCSV(columns, data) {
  if (!data || !data.length) return;
  const header = columns.join(",");
  const rows = data.map(row => columns.map(c => `"${String(row[c] || '').replace(/"/g, '""')}"`).join(","));
  const csvContent = "data:text/csv;charset=utf-8," + [header, ...rows].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", "query_result.csv");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

function appendApiKeyPrompt() {
  const stream = document.getElementById("chat-stream");
  const el = document.createElement("div");
  el.className = "flex items-start gap-3";
  el.innerHTML = `
    <div class="h-8 w-8 rounded-lg bg-amber-500/20 text-amber-400 flex items-center justify-center shrink-0 border border-amber-500/30">
      <i class="fa-solid fa-key text-sm"></i>
    </div>
    <div class="bg-slate-900 border border-amber-500/40 text-slate-200 rounded-2xl rounded-tl-sm p-4 text-xs space-y-2 max-w-xl shadow-lg">
      <p class="font-semibold text-amber-300 flex items-center gap-1.5">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>LLM API Key Required</span>
      </p>
      <p class="text-slate-300 leading-relaxed">
        All queries must route through an LLM. Please connect your <strong>Google Gemini API Key</strong> (or OpenAI / Groq key) to generate live Python Pandas code.
      </p>
      <div class="flex items-center gap-2 pt-1">
        <button onclick="document.getElementById('settings-modal').classList.remove('hidden')" class="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-1.5 rounded-lg text-xs font-medium transition shadow-sm">
          <i class="fa-solid fa-key mr-1"></i> Enter API Key
        </button>
        <a href="https://aistudio.google.com/app/apikey" target="_blank" class="text-xs text-indigo-400 hover:text-indigo-300 underline">
          Get free Gemini Key (Google AI Studio) &rarr;
        </a>
      </div>
    </div>
  `;
  stream.appendChild(el);
}

function updateLlmButtonState() {
  const btn = document.getElementById("btn-settings-modal");
  const label = document.getElementById("btn-llm-label");
  if (!btn || !label) return;

  if (userApiKey) {
    let name = "Gemini 2.0";
    if (userApiKey.startsWith("gsk_")) name = "Groq Llama 3.3";
    else if (userApiKey.startsWith("sk-")) name = "OpenAI GPT-4o";
    label.innerHTML = `<span class="h-2 w-2 rounded-full bg-emerald-400 inline-block mr-1"></span>${name}`;
    btn.classList.remove("bg-indigo-600", "hover:bg-indigo-500");
    btn.classList.add("bg-emerald-700", "hover:bg-emerald-600");
  } else {
    label.textContent = "Connect LLM";
    btn.classList.remove("bg-emerald-700", "hover:bg-emerald-600");
    btn.classList.add("bg-indigo-600", "hover:bg-indigo-500");
  }
}
