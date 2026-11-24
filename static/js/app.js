/**
 * ReviewForge — Modern SaaS UI Client
 * Automated Multi-Agent Code Governance & Review System
 */

let activeReviewId = null;
let pollInterval = null;
let currentFindings = [];
let currentPatchProposal = null;
let activeSeverityFilter = "ALL";
let pipelineTimer = null;
let pipelineStartTime = null;

document.addEventListener("DOMContentLoaded", () => {
  initDropZone();
  initUploadForm();
  initFilters();
  initTabs();
  initActionButtons();
  initHeroActions();
  loadProviderStatus();
  loadReviewHistory();

  const refreshBtn = document.getElementById("btn-refresh");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadProviderStatus();
      loadReviewHistory();
      if (activeReviewId) {
        loadReviewDetails(activeReviewId);
      }
      showToast("Dashboard refreshed successfully", "info");
    });
  }
});

/* -------------------------------------------------------------
 * Tab Navigation Controller
 * ------------------------------------------------------------- */
function initTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn");
  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-tab");
      switchTab(targetId);
    });
  });
}

function switchTab(targetId, fromAutoTour = false) {
  if (!fromAutoTour && isAutoDemoRunning) {
    clearAutoDemo();
    showToast("Switched to Manual Mode", "info");
  }
  // Update button classes
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.getAttribute("data-tab") === targetId);
  });
  // Update panel classes
  document.querySelectorAll(".console-tab-panel").forEach(panel => {
    panel.classList.toggle("active", panel.id === targetId);
  });
}

/* -------------------------------------------------------------
 * Toast Notification System
 * ------------------------------------------------------------- */
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  const icon = type === "success" ? "✔" : type === "error" ? "✖" : "ℹ";
  toast.innerHTML = `
    <span style="font-size: 1.1rem; color: ${type === 'success' ? '#bef264' : type === 'error' ? '#e11d48' : '#38bdf8'};">${icon}</span>
    <span>${escapeHtml(message)}</span>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = "fadeOut 0.3s ease forwards";
    setTimeout(() => {
      if (toast.parentElement) toast.parentElement.removeChild(toast);
    }, 300);
  }, 3500);
}

/* -------------------------------------------------------------
 * Action Buttons: Download Report & Copy Patch
 * ------------------------------------------------------------- */
function initActionButtons() {
  // Copy Patch Button
  const copyBtn = document.getElementById("btn-copy-patch");
  if (copyBtn) {
    copyBtn.addEventListener("click", () => {
      const diffText = document.getElementById("fix-diff-code").textContent;
      if (!diffText || diffText.includes("No remediation patch") || diffText.includes("No patch available")) {
        showToast("No active patch to copy for this review.", "info");
        return;
      }
      navigator.clipboard.writeText(diffText).then(() => {
        showToast("Unified diff patch copied to clipboard!", "success");
      }).catch(err => {
        showToast("Failed to copy patch: " + err, "error");
      });
    });
  }

  // Download Report Button
  const downloadReportBtn = document.getElementById("btn-download-report");
  if (downloadReportBtn) {
    downloadReportBtn.addEventListener("click", () => {
      downloadCurrentReport(activeReviewId);
    });
  }
}

/* -------------------------------------------------------------
 * Verification Report Modal & Download Handlers
 * ------------------------------------------------------------- */
async function downloadCurrentReport(reviewId) {
  const targetId = reviewId || activeReviewId;
  if (!targetId) {
    showToast("Select a review to download its report.", "info");
    return;
  }
  try {
    const res = await fetch(`/api/reviews/${targetId}/report`);
    if (!res.ok) {
      showToast("Failed to fetch report from server.", "error");
      return;
    }
    const data = await res.json();
    const markdown = data.markdown_report || "# Review Report\n\nNo content available.";
    
    // Trigger client-side file download
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `ReviewForge-Report-${targetId}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    showToast(`Report downloaded: ReviewForge-Report-${targetId}.md`, "success");
  } catch (err) {
    showToast("Network error downloading report: " + err.message, "error");
  }
}

function formatInlineMarkdown(text) {
  if (!text) return "";
  let s = String(text);
  // Normalize bullets
  s = s.replace(/&bull;|•/g, "•");
  let escaped = escapeHtml(s);
  // Restore bullet symbol as styled dot
  escaped = escaped.replace(/•/g, '<span style="color:#71717a; margin:0 5px; font-weight:bold;">&bull;</span>');
  // Bold: **text**
  escaped = escaped.replace(/\*\*(.*?)\*\*/g, '<strong style="color:#f4f4f5;">$1</strong>');
  // Inline code: `code`
  escaped = escaped.replace(/`([^`]+)`/g, '<code class="inline-code" style="background:rgba(255,255,255,0.08); padding:1px 6px; border-radius:4px; font-family:var(--font-mono); color:#bef264; font-size:0.82rem;">$1</code>');
  // Severity tags
  escaped = escaped.replace(/\[CRITICAL\]/g, '<span class="pill-badge pill-crimson" style="font-size:0.68rem; font-weight:800; padding:2px 7px;">CRITICAL</span>');
  escaped = escaped.replace(/\[HIGH\]/g, '<span class="pill-badge pill-crimson" style="font-size:0.68rem; font-weight:800; padding:2px 7px;">HIGH</span>');
  escaped = escaped.replace(/\[MEDIUM\]/g, '<span class="pill-badge pill-amber" style="font-size:0.68rem; font-weight:800; padding:2px 7px; color:#f59e0b; background:rgba(245,158,11,0.15);">MEDIUM</span>');
  escaped = escaped.replace(/\[LOW\]/g, '<span class="pill-badge pill-zinc" style="font-size:0.68rem; font-weight:700; padding:2px 7px;">LOW</span>');
  escaped = escaped.replace(/\[INFO\]/g, '<span class="pill-badge pill-zinc" style="font-size:0.68rem; font-weight:700; padding:2px 7px;">INFO</span>');
  return escaped;
}

function renderMarkdownReportToHtml(markdownText) {
  if (!markdownText) return "<p>No report content available.</p>";

  const lines = markdownText.split("\n");
  const html = [];
  let inCodeBlock = false;
  let codeBlockLines = [];
  let inTable = false;
  let tableRows = [];

  function flushCodeBlock() {
    if (!inCodeBlock) return;
    html.push(`<div class="report-code-block" style="background:#09090b; border:1px solid #27272a; border-radius:6px; padding:0.75rem 1rem; margin:0.5rem 0; overflow-x:auto;"><pre style="margin:0; font-family:var(--font-mono); font-size:0.8rem; line-height:1.6;">`);
    for (const rawLine of codeBlockLines) {
      let lineClass = "report-code-line";
      if (rawLine.startsWith("- ") || (rawLine.startsWith("-") && !rawLine.startsWith("---"))) {
        lineClass += " line-removed";
      } else if (rawLine.startsWith("+ ") || (rawLine.startsWith("+") && !rawLine.startsWith("+++"))) {
        lineClass += " line-added";
      } else if (rawLine.startsWith("#")) {
        lineClass += " line-comment";
      } else if (rawLine.startsWith("@@")) {
        lineClass += " line-hunk";
      }
      html.push(`<div class="${lineClass}">${escapeHtml(rawLine)}</div>`);
    }
    html.push(`</pre></div>`);
    inCodeBlock = false;
    codeBlockLines = [];
  }

  function flushTable() {
    if (!inTable) return;
    if (tableRows.length > 0) {
      html.push(`<div style="overflow-x:auto; margin:0.6rem 0;"><table class="report-table" style="width:100%; border-collapse:collapse; font-size:0.78rem; font-family:var(--font-mono);">`);
      const headerCells = tableRows[0].map(c => `<th style="background:#141417; color:#bef264; padding:0.5rem 0.75rem; border:1px solid #27272a; text-align:left; font-weight:700;">${formatInlineMarkdown(c.trim())}</th>`).join("");
      html.push(`<thead><tr>${headerCells}</tr></thead><tbody>`);
      for (let i = 1; i < tableRows.length; i++) {
        const rowCells = tableRows[i].map(c => `<td style="padding:0.45rem 0.75rem; border:1px solid #27272a; color:#e4e4e7;">${formatInlineMarkdown(c.trim())}</td>`).join("");
        html.push(`<tr>${rowCells}</tr>`);
      }
      html.push(`</tbody></table></div>`);
    }
    inTable = false;
    tableRows = [];
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.trim().startsWith("```")) {
      if (inCodeBlock) {
        flushCodeBlock();
      } else {
        flushTable();
        inCodeBlock = true;
        codeBlockLines = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeBlockLines.push(line);
      continue;
    }

    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      if (/^\|[\s\-:|]+\|$/.test(line.trim())) {
        continue;
      }
      inTable = true;
      const cells = line.trim().slice(1, -1).split("|");
      tableRows.push(cells);
      continue;
    } else {
      flushTable();
    }

    if (!line.trim()) continue;

    // Header banner
    if (line.startsWith("# AUTOMATED CODE REVIEW REPORT: ")) {
      const proj = line.replace("# AUTOMATED CODE REVIEW REPORT: ", "").trim();
      html.push(`
        <div style="background:#141417; border:1px solid #27272a; border-radius:8px; padding:0.85rem 1.15rem; margin-bottom:0.75rem; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:0.5rem;">
          <div>
            <div style="font-size:0.62rem; font-family:var(--font-mono); color:#a1a1aa; text-transform:uppercase; letter-spacing:0.06em; margin-bottom:2px;">Automated Static Verification Report</div>
            <h2 style="margin:0; font-size:1.15rem; color:#ffffff; font-weight:800; letter-spacing:-0.01em;">${escapeHtml(proj)}</h2>
          </div>
          <span class="pill-badge pill-zinc" style="font-size:0.72rem; font-family:var(--font-mono); font-weight:600;">Multi-Agent Engine</span>
        </div>
      `);
    } else if (line.startsWith("# ")) {
      html.push(`<h2 style="margin:0.85rem 0 0.4rem 0; font-size:1.15rem; color:#ffffff; font-weight:800;">${escapeHtml(line.slice(2))}</h2>`);
    } else if (line.startsWith("## Executive Summary")) {
      html.push(`<h3 style="margin:1rem 0 0.35rem 0; font-size:0.95rem; font-family:var(--font-mono); font-weight:700; color:#bef264; text-transform:uppercase; letter-spacing:0.05em;">🛡️ Executive Summary</h3>`);
    } else if (line.startsWith("## 🚨 Defective Code Highlights")) {
      html.push(`<h3 style="margin:1.25rem 0 0.35rem 0; font-size:1.0rem; font-weight:800; color:#f43f5e; border-bottom:1.5px solid rgba(244,63,94,0.3); padding-bottom:0.35rem;">🚨 Defective Code Highlights &amp; Explanations</h3>`);
    } else if (line.startsWith("## 🛠️ Automated Remediation")) {
      html.push(`<h3 style="margin:1.25rem 0 0.35rem 0; font-size:1.0rem; font-weight:800; color:#bef264; border-bottom:1.5px solid rgba(190,242,100,0.3); padding-bottom:0.35rem;">🛠️ Automated Remediation Unified Diff Patch</h3>`);
    } else if (line.startsWith("## ")) {
      html.push(`<h3 style="margin:1rem 0 0.35rem 0; font-size:0.95rem; font-weight:700; color:#bef264; border-bottom:1px solid #27272a; padding-bottom:0.3rem;">${escapeHtml(line.slice(3))}</h3>`);
    } else if (line.startsWith("### 🔴 ")) {
      html.push(`<div style="margin-top:0.85rem; padding-top:0.5rem; border-top:1px dashed #27272a;"><h4 style="margin:0 0 0.35rem 0; font-size:0.92rem; color:#fda4af; font-weight:700;">${formatInlineMarkdown(line.slice(4))}</h4></div>`);
    } else if (line.startsWith("### ")) {
      html.push(`<h4 style="margin:0.75rem 0 0.25rem 0; font-size:0.9rem; color:#f4f4f5; font-weight:700;">${formatInlineMarkdown(line.slice(4))}</h4>`);
    } else if (line.startsWith("> ")) {
      html.push(`<blockquote style="margin:0.4rem 0; padding:0.65rem 1rem; border-left:3px solid #bef264; background:rgba(190, 242, 100, 0.08); border-radius:0 6px 6px 0; color:#f4f4f5; font-size:0.88rem; line-height:1.5; font-style:italic;">${formatInlineMarkdown(line.slice(2))}</blockquote>`);
    } else if (line.startsWith("- ")) {
      html.push(`<div style="margin:0.25rem 0 0.25rem 0.5rem; display:flex; align-items:flex-start; gap:0.5rem; font-size:0.85rem;"><span style="color:#bef264; font-weight:bold;">&bull;</span> <span style="color:#d4d4d8;">${formatInlineMarkdown(line.slice(2))}</span></div>`);
    } else if (line.startsWith("**❌ Offending / Defective Code Snippet:**")) {
      html.push(`<div style="margin-top:0.5rem; font-weight:700; color:#f43f5e; font-size:0.82rem; letter-spacing:0.02em;">❌ Offending / Defective Code Snippet:</div>`);
    } else if (line.startsWith("**💡 Recommended Fix:**")) {
      html.push(`<div style="margin:0.4rem 0; padding:0.5rem 0.75rem; background:rgba(190,242,100,0.06); border:1px solid rgba(190,242,100,0.2); border-radius:6px; font-size:0.83rem; color:#e4e4e7;"><span style="font-weight:700; color:#bef264;">💡 Recommended Fix:</span> ${formatInlineMarkdown(line.replace("**💡 Recommended Fix:**", "").trim())}</div>`);
    } else {
      html.push(`<p style="margin:0.3rem 0; color:#d4d4d8; font-size:0.85rem; line-height:1.55;">${formatInlineMarkdown(line)}</p>`);
    }
  }

  flushCodeBlock();
  flushTable();

  return html.join("\n");
}

let isRawReportView = false;
function toggleReportView() {
  const richEl = document.getElementById("report-modal-rich-content");
  const rawEl = document.getElementById("report-modal-content");
  const btn = document.getElementById("btn-toggle-report-view");
  if (!richEl || !rawEl || !btn) return;

  isRawReportView = !isRawReportView;
  if (isRawReportView) {
    richEl.style.display = "none";
    rawEl.style.display = "block";
    btn.innerHTML = `<span>✨ Formatted View</span>`;
  } else {
    richEl.style.display = "block";
    rawEl.style.display = "none";
    btn.innerHTML = `<span>📝 Raw Markdown</span>`;
  }
}

function updateModalHeaderAndStats(review) {
  const badge = document.getElementById("modal-verdict-badge");
  const statVerdict = document.getElementById("modal-stat-verdict");
  const statFindings = document.getElementById("modal-stat-findings");
  const statAgents = document.getElementById("modal-stat-agents");
  const statRemediation = document.getElementById("modal-stat-remediation");

  const rec = review.recommendation || "PENDING";
  const findings = review.findings || [];
  const blocking = findings.filter(f => ["CRITICAL", "HIGH", "MEDIUM"].includes(f.severity));
  const patch = review.patch_proposal;

  if (badge) {
    if (rec === "APPROVE") {
      badge.className = "badge-verdict verdict-approved";
      badge.innerHTML = "&#x2714; APPROVE";
      badge.style.background = "#bef264";
      badge.style.color = "#000000";
    } else if (rec === "REQUEST_CHANGES") {
      badge.className = "badge-verdict verdict-changes";
      badge.innerHTML = "&#x26A0; REQUEST_CHANGES";
      badge.style.background = "#f43f5e";
      badge.style.color = "#ffffff";
    } else {
      badge.className = "badge-verdict";
      badge.textContent = rec;
      badge.style.background = "#71717a";
      badge.style.color = "#ffffff";
    }
  }

  if (statVerdict) {
    if (rec === "APPROVE") {
      statVerdict.innerHTML = `<span class="pill-badge pill-lime" style="font-size:0.75rem; font-weight:800; padding:3px 8px;">✔ APPROVE (Clean)</span>`;
    } else if (rec === "REQUEST_CHANGES") {
      statVerdict.innerHTML = `<span class="pill-badge pill-crimson" style="font-size:0.72rem; font-weight:800; padding:3px 7px; letter-spacing:0.02em;">⚠ REQUEST_CHANGES</span>`;
    } else {
      statVerdict.innerHTML = `<span class="pill-badge pill-zinc" style="font-size:0.75rem; font-weight:800; padding:3px 8px;">${escapeHtml(rec)}</span>`;
    }
  }

  if (statFindings) {
    if (blocking.length === 0) {
      statFindings.innerHTML = `<span class="text-lime" style="font-size:1.05rem; font-weight:800;">0</span> <span style="font-size:0.75rem; color:#bef264; font-weight:600; margin-left:4px;">Defects (Clean)</span>`;
    } else {
      statFindings.innerHTML = `<span class="text-crimson" style="font-size:1.05rem; font-weight:800;">${blocking.length}</span> <span style="font-size:0.75rem; font-weight:700; color:#fda4af; margin-left:4px;">${blocking.length === 1 ? 'Defect' : 'Defects'} Blocking</span>`;
    }
  }

  if (statAgents) {
    statAgents.innerHTML = `<span class="text-blue" style="font-size:1.05rem; font-weight:800;">6 / 6</span> <span style="font-size:0.75rem; font-weight:600; color:#93c5fd; margin-left:4px;">Active</span>`;
  }

  if (statRemediation) {
    if (patch) {
      const valPassed = patch.validation === "PASSED";
      statRemediation.innerHTML = `<span class="${valPassed ? 'text-lime' : 'text-amber'}" style="font-size:0.82rem; font-weight:800;">${valPassed ? '✔ Dry-Run Verified' : '⚡ Patch Ready'}</span>`;
    } else if (rec === "APPROVE") {
      statRemediation.innerHTML = `<span class="text-lime" style="font-size:0.82rem; font-weight:800;">✔ Verified Safe</span>`;
    } else {
      statRemediation.innerHTML = `<span class="text-amber" style="font-size:0.82rem; font-weight:800;">Manual Review</span>`;
    }
  }
}

async function openReportModal(reviewId) {
  const targetId = reviewId || activeReviewId;
  if (!targetId) {
    showToast("Select a review to view its report.", "info");
    return;
  }
  activeReviewId = targetId;

  const modal = document.getElementById("report-modal");
  const contentEl = document.getElementById("report-modal-content");
  const richContentEl = document.getElementById("report-modal-rich-content");
  if (!modal) return;

  modal.style.display = "flex";
  if (contentEl) contentEl.textContent = "Loading official multi-agent verification report from server...";
  if (richContentEl) richContentEl.innerHTML = `<div style="padding:1.5rem; text-align:center; color:#a1a1aa;">⏳ Loading official multi-agent verification report from server...</div>`;

  try {
    const [reportRes, revRes] = await Promise.all([
      fetch(`/api/reviews/${targetId}/report`),
      fetch(`/api/reviews/${targetId}`)
    ]);

    if (revRes.ok) {
      const review = await revRes.json();
      updateModalHeaderAndStats(review);
    }

    if (reportRes.ok) {
      const data = await reportRes.json();
      const markdown = data.markdown_report || "# Review Report\n\nNo report content generated.";
      if (contentEl) contentEl.textContent = markdown;
      if (richContentEl) richContentEl.innerHTML = renderMarkdownReportToHtml(markdown);
    } else {
      if (contentEl) contentEl.textContent = "Unable to load report from server.";
      if (richContentEl) richContentEl.innerHTML = `<div style="color:#f43f5e; padding:1rem;">⚠️ Unable to load report from server.</div>`;
    }
  } catch (e) {
    if (contentEl) contentEl.textContent = `Error loading report: ${e.message}`;
    if (richContentEl) richContentEl.innerHTML = `<div style="color:#f43f5e; padding:1rem;">⚠️ Error loading report: ${escapeHtml(e.message)}</div>`;
  }
}

function closeReportModal() {
  const modal = document.getElementById("report-modal");
  if (modal) modal.style.display = "none";
}

// Global modal close handlers
window.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeReportModal();
});
document.addEventListener("DOMContentLoaded", () => {
  const modalEl = document.getElementById("report-modal");
  if (modalEl) {
    modalEl.addEventListener("click", (e) => {
      if (e.target === modalEl) closeReportModal();
    });
  }
});

/* -------------------------------------------------------------
 * Automated Demo Tour & Hero Actions
 * ------------------------------------------------------------- */
let isAutoDemoRunning = false;
let autoDemoTimeouts = [];

function clearAutoDemo() {
  isAutoDemoRunning = false;
  autoDemoTimeouts.forEach(t => {
    clearTimeout(t);
    clearInterval(t);
  });
  autoDemoTimeouts = [];
  const indicator = document.getElementById("demo-mode-indicator");
  if (indicator) {
    indicator.innerHTML = `<span>🛠️ <strong>Manual Mode Active</strong> — Interactive control enabled</span>`;
    setTimeout(() => {
      if (!isAutoDemoRunning && indicator) indicator.style.display = "none";
    }, 4500);
  }
}

function exitAutoDemoToManual() {
  clearAutoDemo();
  showToast("Switched to Manual Mode", "info");
}

async function runAutoShowcaseDemo() {
  clearAutoDemo();
  isAutoDemoRunning = true;

  const consoleEl = document.getElementById("console-section");
  if (consoleEl) consoleEl.scrollIntoView({ behavior: "smooth" });

  let indicator = document.getElementById("demo-mode-indicator");
  if (!indicator) {
    indicator = document.createElement("div");
    indicator.id = "demo-mode-indicator";
    indicator.className = "demo-mode-pill-badge";
    const header = document.querySelector(".section-header");
    if (header) header.appendChild(indicator);
  }
  indicator.innerHTML = `<span>🎬 <span class="pulse-indicator"></span> <strong>Automated Demo Active</strong> — Running pipeline for Scenario 2 (Auth Security)...</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
  indicator.style.display = "inline-flex";

  showToast("🎬 Starting automated hands-free demo tour...", "info");

  await loadSampleScenario("scenario_2");
}

function runAutoTourSteps() {
  const indicator = document.getElementById("demo-mode-indicator");
  let step1Secs = 5;
  if (indicator) {
    indicator.innerHTML = `<span>🎬 <strong>Tour Step 1/3:</strong> ⚠️ Critical Defect Detected in <code>auth.py</code> &bull; Verdict: <strong style="color: #f43f5e;">REQUEST_CHANGES</strong> (Inspecting fix patch in ${step1Secs}s...)</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
  }
  switchTab("tab-findings", true);

  const countdown1 = setInterval(() => {
    if (!isAutoDemoRunning) { clearInterval(countdown1); return; }
    step1Secs--;
    if (step1Secs > 0 && indicator) {
      indicator.innerHTML = `<span>🎬 <strong>Tour Step 1/3:</strong> ⚠️ Critical Defect Detected in <code>auth.py</code> &bull; Verdict: <strong style="color: #f43f5e;">REQUEST_CHANGES</strong> (Inspecting fix patch in ${step1Secs}s...)</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
    } else {
      clearInterval(countdown1);
    }
  }, 1000);
  autoDemoTimeouts.push(countdown1);

  const t1 = setTimeout(() => {
    if (!isAutoDemoRunning) return;
    let step2Secs = 5;
    if (indicator) {
      indicator.innerHTML = `<span>🎬 <strong>Tour Step 2/3:</strong> 🛠️ Fix-Suggestion Agent Synthesized Unified Diff Remediation Patch (Auto-applying in ${step2Secs}s...)</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
    }
    switchTab("tab-patch", true);

    const countdown2 = setInterval(() => {
      if (!isAutoDemoRunning) { clearInterval(countdown2); return; }
      step2Secs--;
      if (step2Secs > 0 && indicator) {
        indicator.innerHTML = `<span>🎬 <strong>Tour Step 2/3:</strong> 🛠️ Fix-Suggestion Agent Synthesized Unified Diff Remediation Patch (Auto-applying in ${step2Secs}s...)</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
      } else {
        clearInterval(countdown2);
      }
    }, 1000);
    autoDemoTimeouts.push(countdown2);

    const t2 = setTimeout(() => {
      if (!isAutoDemoRunning) return;
      if (indicator) {
        indicator.innerHTML = `<span>🎬 <strong>Tour Step 3/3:</strong> ⚡ Auto-Applying Remediation Patch &amp; Running Re-Audit for ALL GREEN Approval...</span> <button type="button" class="btn btn-dark btn-xs" onclick="exitAutoDemoToManual()" style="margin-left: 0.8rem; cursor: pointer; border-radius: 9999px;">Switch to Manual Mode</button>`;
      }
      autoResolveCurrentReview(activeReviewId, true);
    }, 5500);
    autoDemoTimeouts.push(t2);

  }, 5500);
  autoDemoTimeouts.push(t1);
}

function concludeAutoDemoToManual() {
  const indicator = document.getElementById("demo-mode-indicator");
  switchTab("tab-findings", true);
  if (indicator) {
    indicator.innerHTML = `<span>🎉 <strong>All Green Verified!</strong> Consensus Verdict: <strong style="color: #bef264;">✔ APPROVE</strong> &bull; Complete Report Opening...</span>`;
  }
  showToast("🎉 100% Green Approved! All vulnerabilities resolved & verified.", "success");

  const t = setTimeout(() => {
    clearAutoDemo();
    // Automatically open the full official verification report!
    openReportModal(activeReviewId);
    showToast("📋 Official Complete Verification Report opened. Download or close to explore Manual Mode.", "info");
  }, 1200);
  autoDemoTimeouts.push(t);
}

async function autoResolveCurrentReview(reviewId, fromDemo = false) {
  const targetId = reviewId || activeReviewId;
  if (!targetId) {
    showToast("No active review selected to resolve.", "error");
    return;
  }

  const applyBtn = document.getElementById("btn-apply-patch");
  if (applyBtn) {
    applyBtn.disabled = true;
    applyBtn.innerHTML = `<span>⏳ Re-Auditing...</span>`;
  }

  showToast("⚡ Applying automated remediation patch & re-auditing codebase...", "info");
  startPipelineProgress("Automated Remediation & Re-Audit");

  try {
    const res = await fetch(`/api/reviews/${targetId}/auto-resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" }
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.message || "Failed to auto-resolve review.");
    }

    const data = await res.json();
    const newReviewId = data.review_id;
    activeReviewId = newReviewId;

    if (applyBtn) {
      applyBtn.disabled = false;
      applyBtn.innerHTML = `<span>⚡ Auto-Apply Fix &amp; Re-Audit (All Green)</span>`;
    }

    loadReviewHistory();
    startPolling(newReviewId, fromDemo);

  } catch (err) {
    console.error("Auto-resolve error:", err);
    if (applyBtn) {
      applyBtn.disabled = false;
      applyBtn.innerHTML = `<span>⚡ Auto-Apply Fix &amp; Re-Audit (All Green)</span>`;
    }
    stopPipelineProgress("FAILED");
    showToast(`Remediation failed: ${err.message}`, "error");
  }
}

function initHeroActions() {
  const quickDemoBtn = document.getElementById("hero-quick-demo-btn");
  if (quickDemoBtn) {
    quickDemoBtn.addEventListener("click", () => {
      runAutoShowcaseDemo();
    });
  }
}

/* -------------------------------------------------------------
 * Live Pipeline Progress Stepper & Animation
 * ------------------------------------------------------------- */
function startPipelineProgress(scenarioOrProjectName) {
  const progressCard = document.getElementById("live-pipeline-progress");
  const progressFill = document.getElementById("pipeline-progress-fill");
  const statusText = document.getElementById("pipeline-status-text");
  const timeBadge = document.getElementById("pipeline-elapsed-time");

  if (!progressCard) return;

  progressCard.style.display = "block";
  progressFill.style.width = "25%";
  statusText.textContent = `Review pipeline running for '${scenarioOrProjectName}'...`;

  // Reset steps
  document.getElementById("pstep-1").className = "pstep active";
  document.getElementById("pstep-2").className = "pstep active";
  document.getElementById("pstep-3").className = "pstep";
  document.getElementById("pstep-4").className = "pstep";

  pipelineStartTime = Date.now();
  if (pipelineTimer) clearInterval(pipelineTimer);

  pipelineTimer = setInterval(() => {
    const elapsedSec = ((Date.now() - pipelineStartTime) / 1000).toFixed(1);
    timeBadge.textContent = `${elapsedSec}s`;

    const secNum = parseFloat(elapsedSec);
    if (secNum >= 1.5 && secNum < 3.0) {
      progressFill.style.width = "50%";
      document.getElementById("pstep-1").className = "pstep done";
      document.getElementById("pstep-2").className = "pstep active";
      statusText.textContent = "Concurrent specialist agents fan-out running...";
    } else if (secNum >= 3.0 && secNum < 5.0) {
      progressFill.style.width = "75%";
      document.getElementById("pstep-2").className = "pstep done";
      document.getElementById("pstep-3").className = "pstep active";
      statusText.textContent = "Reviewer Manager consolidating findings & decision...";
    } else if (secNum >= 5.0) {
      progressFill.style.width = "90%";
      document.getElementById("pstep-3").className = "pstep done";
      document.getElementById("pstep-4").className = "pstep active";
      statusText.textContent = "Formulating dry-run fix proposal...";
    }
  }, 200);
}

function stopPipelineProgress(verdict) {
  if (pipelineTimer) {
    clearInterval(pipelineTimer);
    pipelineTimer = null;
  }
  const progressFill = document.getElementById("pipeline-progress-fill");
  const statusText = document.getElementById("pipeline-status-text");

  if (progressFill) progressFill.style.width = "100%";
  if (statusText) statusText.textContent = `Review completed! Verdict: ${verdict || 'COMPLETED'}`;

  // Mark all steps done
  ["pstep-1", "pstep-2", "pstep-3", "pstep-4"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.className = "pstep done";
  });

  setTimeout(() => {
    const progressCard = document.getElementById("live-pipeline-progress");
    if (progressCard) progressCard.style.display = "none";
  }, 2500);
}

/* -------------------------------------------------------------
 * 1-Click Scenario Loader (Instant Viva & Demo Execution)
 * ------------------------------------------------------------- */
async function loadSampleScenario(scenarioKey) {
  const submitBtn = document.getElementById("btn-submit-review");
  const errorBox = document.getElementById("upload-error-msg");
  errorBox.style.display = "none";

  submitBtn.disabled = true;
  submitBtn.innerHTML = `<span>Starting ${scenarioKey}...</span>`;

  startPipelineProgress(scenarioKey);
  showToast(`Initiated ${scenarioKey} review pipeline`, "info");

  try {
    const res = await fetch(`/api/reviews/sample/${scenarioKey}`, {
      method: "POST"
    });
    const data = await res.json();

    if (!res.ok) {
      errorBox.textContent = data.message || "Failed to load sample scenario.";
      errorBox.style.display = "block";
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
      stopPipelineProgress("FAILED");
      showToast("Failed to load scenario: " + (data.message || ""), "error");
      return;
    }

    activeReviewId = data.review_id;
    loadReviewHistory();
    startPolling(activeReviewId);
    loadReviewDetails(activeReviewId);

    document.getElementById("active-review-banner").scrollIntoView({ behavior: "smooth" });

    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
  } catch (err) {
    errorBox.textContent = `Network error: ${err.message}`;
    errorBox.style.display = "block";
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
    stopPipelineProgress("FAILED");
    showToast("Network error: " + err.message, "error");
  }
}

/* -------------------------------------------------------------
 * Drag and Drop & Custom ZIP Upload
 * ------------------------------------------------------------- */
function initDropZone() {
  const dropZone = document.getElementById("drop-zone");
  const fileInput = document.getElementById("file-input");

  ["dragenter", "dragover"].forEach(event => {
    dropZone.addEventListener(event, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(event => {
    dropZone.addEventListener(event, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropZone.classList.remove("dragover");
    });
  });

  dropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      fileInput.files = e.dataTransfer.files;
      const file = fileInput.files[0];
      updateFileLabel(file.name, file.size);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files.length > 0) {
      const file = fileInput.files[0];
      updateFileLabel(file.name, file.size);
    }
  });
}

function updateFileLabel(name, size) {
  const fileLabel = document.getElementById("selected-filename");
  const textEl = document.getElementById("selected-filename-text");
  const projInput = document.getElementById("project-name-input");

  const sizeStr = size ? ` (${(size / 1024).toFixed(1)} KB)` : "";
  if (textEl) {
    textEl.textContent = `✔ Selected: ${name}${sizeStr}`;
  } else if (fileLabel) {
    fileLabel.textContent = `✔ Selected: ${name}${sizeStr}`;
  }
  if (fileLabel) fileLabel.style.display = "flex";

  if (projInput && !projInput.value.trim()) {
    projInput.value = name.replace(/\.[^/.]+$/, "");
  }
}

function clearSelectedUploadFile(e) {
  if (e) {
    e.preventDefault();
    e.stopPropagation();
  }
  const fileInput = document.getElementById("file-input");
  const fileLabel = document.getElementById("selected-filename");
  const textEl = document.getElementById("selected-filename-text");
  if (fileInput) fileInput.value = "";
  if (fileLabel) fileLabel.style.display = "none";
  if (textEl) textEl.textContent = "";
}

async function quickFillSampleArchive(sampleKey = "payment_gateway") {
  const fileInput = document.getElementById("file-input");
  const projInput = document.getElementById("project-name-input");
  const errorBox = document.getElementById("upload-error-msg");
  if (errorBox) errorBox.style.display = "none";

  showToast(`Loading '${sampleKey}' archive into custom upload form...`, "info");

  try {
    const res = await fetch(`/api/samples/${sampleKey}/download`);
    if (!res.ok) throw new Error("Failed to load sample ZIP.");
    const blob = await res.blob();
    const filename = sampleKey === "user_auth" ? "RealWorld_UserAuth_SecurityDefect.zip" : "RealWorld_PaymentGateway.zip";
    const file = new File([blob], filename, { type: "application/zip" });

    // Set file input files using DataTransfer
    const dataTransfer = new DataTransfer();
    dataTransfer.items.add(file);
    fileInput.files = dataTransfer.files;

    if (projInput) {
      projInput.value = sampleKey === "user_auth" ? "UserAuthTokenService" : "ECommercePaymentGateway";
    }

    updateFileLabel(file.name, file.size);
    showToast(`Real-world archive '${file.name}' loaded! Click 'Start Multi-Agent Review' to test upload.`, "success");
  } catch (err) {
    showToast("Error loading sample archive: " + err.message, "error");
  }
}

function initUploadForm() {
  const form = document.getElementById("upload-form");
  const fileInput = document.getElementById("file-input");
  const projInput = document.getElementById("project-name-input");
  const errorBox = document.getElementById("upload-error-msg");
  const submitBtn = document.getElementById("btn-submit-review");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.style.display = "none";

    if (!fileInput.files || fileInput.files.length === 0) {
      errorBox.textContent = "Please select or drop a valid snapshot ZIP archive.";
      errorBox.style.display = "block";
      return;
    }

    const file = fileInput.files[0];
    const projectName = projInput.value.trim() || file.name.replace(".zip", "");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("project_name", projectName);

    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>Uploading &amp; Scanning...</span>`;

    startPipelineProgress(projectName);
    showToast(`Uploading '${file.name}' for multi-agent audit...`, "info");

    try {
      const res = await fetch("/api/reviews", {
        method: "POST",
        body: formData
      });

      const data = await res.json();

      if (!res.ok) {
        errorBox.textContent = data.message || "Archive upload or validation failed.";
        errorBox.style.display = "block";
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
        stopPipelineProgress("FAILED");
        showToast("Upload failed: " + (data.message || ""), "error");
        return;
      }

      activeReviewId = data.review_id;
      loadReviewHistory();
      startPolling(activeReviewId);
      loadReviewDetails(activeReviewId);

      form.reset();
      document.getElementById("selected-filename").textContent = "";
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
      document.getElementById("active-review-banner").scrollIntoView({ behavior: "smooth" });

    } catch (err) {
      errorBox.textContent = `Network error: ${err.message}`;
      errorBox.style.display = "block";
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span>Start Multi-Agent Review</span>`;
      stopPipelineProgress("FAILED");
      showToast("Upload network error: " + err.message, "error");
    }
  });
}

/* -------------------------------------------------------------
 * Status & History Loading
 * ------------------------------------------------------------- */
async function loadProviderStatus() {
  try {
    const res = await fetch("/api/providers/status");
    const data = await res.json();
    const badge = document.getElementById("provider-badge");
    const label = document.getElementById("provider-name");

    if (data.ollama && data.ollama.status === "ONLINE") {
      badge.className = "status-pill pill-online";
      label.textContent = `Ollama (${data.ollama.model}) Active`;
    } else if (data.gemini && data.gemini.status === "CONFIGURED") {
      badge.className = "status-pill pill-online";
      label.textContent = `Gemini (${data.gemini.model}) Active`;
    } else {
      badge.className = "status-pill pill-offline";
      label.textContent = "Deterministic Static Engine (Active)";
    }
  } catch (e) {
    console.error("Provider status error:", e);
  }
}

async function loadReviewHistory() {
  try {
    const res = await fetch("/api/reviews");
    const data = await res.json();
    const container = document.getElementById("review-history-container");
    const totalCount = document.getElementById("stat-total-reviews");
    const completedCount = document.getElementById("stat-completed-reviews");

    const reviews = data.reviews || [];
    totalCount.textContent = reviews.length;
    completedCount.textContent = reviews.filter(r => r.status === "COMPLETED" || r.status === "PARTIAL").length;

    if (reviews.length === 0) {
      container.innerHTML = `<div class="empty-state">No reviews executed yet.</div>`;
      return;
    }

    container.innerHTML = reviews.map(r => {
      let recBadge = "pill-zinc";
      if (r.recommendation === "APPROVE") recBadge = "pill-lime";
      else if (r.recommendation === "REQUEST_CHANGES") recBadge = "pill-crimson";
      else if (r.status === "PARTIAL") recBadge = "pill-amber";
      else if (r.status === "FAILED") recBadge = "pill-crimson";

      const isSel = r.review_id === activeReviewId ? "active" : "";
      return `
        <div class="history-item ${isSel}" onclick="selectReview('${r.review_id}')">
          <div class="history-item-top">
            <span class="history-item-title">${escapeHtml(r.project_name || r.review_id)}</span>
            <span class="pill-badge ${recBadge}">${r.recommendation || r.status}</span>
          </div>
          <div class="history-item-meta">ID: ${r.review_id} &bull; ${new Date(r.created_at * 1000).toLocaleTimeString()}</div>
        </div>
      `;
    }).join("");

    // Auto-select latest review if none is selected
    if (!activeReviewId && reviews.length > 0) {
      selectReview(reviews[0].review_id);
    }
  } catch (e) {
    console.error("History load error:", e);
  }
}

function selectReview(reviewId) {
  activeReviewId = reviewId;
  loadReviewHistory();
  loadReviewDetails(reviewId);
}

/* -------------------------------------------------------------
 * Polling Review Progress
 * ------------------------------------------------------------- */
function startPolling(reviewId, fromAutoRemediateDemo = false) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(async () => {
    try {
      const res = await fetch(`/api/reviews/${reviewId}/status`);
      if (res.ok) {
        const data = await res.json();
        loadReviewDetails(reviewId);
        if (data.status === "COMPLETED" || data.status === "FAILED" || data.status === "PARTIAL") {
          clearInterval(pollInterval);
          loadReviewHistory();
          stopPipelineProgress(data.recommendation || data.status);
          
          if (data.status === "COMPLETED") {
            if (data.recommendation === "APPROVE") {
              showToast("✨ Review Complete: All checks passed! Verdict: APPROVE (100% Green)", "success");
            } else {
              showToast("Review Complete: Vulnerabilities detected — REQUEST_CHANGES (Patch Ready)", "info");
            }
          } else if (data.status === "PARTIAL") {
            showToast("Review Complete with partial agent disclosures: REQUEST_CHANGES", "info");
          } else {
            showToast("Review pipeline failed due to critical error", "error");
          }

          if (isAutoDemoRunning) {
            if (fromAutoRemediateDemo) {
              concludeAutoDemoToManual();
            } else {
              runAutoTourSteps();
            }
          } else {
            // IN MANUAL MODE, CUSTOM ZIP UPLOAD, OR MANUAL 1-CLICK AUTO-RESOLVE:
            // Automatically open the full report modal with defect code highlights!
            setTimeout(() => {
              openReportModal(reviewId);
              showToast("📋 Official Complete Verification Report opened. Download or close to explore Manual Mode.", "info");
            }, 1200);
          }
        }
      }
    } catch (e) {
      console.error("Polling error:", e);
    }
  }, 1800);
}

/* -------------------------------------------------------------
 * Review Details Rendering
 * ------------------------------------------------------------- */
async function loadReviewDetails(reviewId) {
  try {
    const [revRes, traceRes] = await Promise.all([
      fetch(`/api/reviews/${reviewId}`),
      fetch(`/api/reviews/${reviewId}/trace`)
    ]);

    if (!revRes.ok) return;

    const review = await revRes.json();
    const traceData = traceRes.ok ? await traceRes.json() : { events: [] };

    // Update Header
    document.getElementById("active-review-badge").textContent = review.review_id;
    const modeBadge = document.getElementById("active-review-mode-badge");
    if (modeBadge) modeBadge.textContent = review.review_mode || "CHANGE REVIEW";

    document.getElementById("active-project-title").textContent = review.project_name || "Submitted Project";
    document.getElementById("active-review-meta").innerHTML = `
      <span>Status: <strong>${review.status}</strong></span>
      <span>Execution Time: <strong>${review.updated_at && review.created_at ? (review.updated_at - review.created_at).toFixed(2) + 's' : '-'}</strong></span>
      <span>Timestamp: <strong>${new Date(review.created_at * 1000).toLocaleString()}</strong></span>
    `;

    // Render Recommendation Banner (High Impact)
    const recBox = document.getElementById("recommendation-badge-container");
    const rationaleBox = document.getElementById("recommendation-rationale-box");
    const rationaleText = document.getElementById("recommendation-rationale-text");

    if (review.recommendation) {
      const isApprove = review.recommendation === "APPROVE";
      recBox.innerHTML = `
        <div class="badge-verdict ${isApprove ? 'verdict-approved' : 'verdict-request-changes'}">
          ${isApprove ? '&#x2714; APPROVE' : '&#x26A0; REQUEST_CHANGES'}
        </div>
      `;
      rationaleBox.style.display = "block";
      let rationaleHtml = `<div>${escapeHtml(review.recommendation_rationale || "No rationale recorded.")}</div>`;
      if (review.patch_proposal) {
        rationaleHtml += `
          <div class="patch-callout-banner" style="margin-top: 0.75rem; padding: 0.65rem 1rem; background: #bef2641a; border: 1.5px solid #bef264; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
            <div style="font-size: 0.85rem; color: #18181b;">
              🛠️ <strong>Automated Remediation Patch Ready:</strong> Fix-Suggestion Agent synthesized a verified dry-run patch for <code>${escapeHtml(review.patch_proposal.target_finding)}</code> in <code>${escapeHtml(review.patch_proposal.file)}</code>.
            </div>
            <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
              <button type="button" class="btn btn-dark btn-xs" onclick="switchTab('tab-patch')" style="white-space: nowrap; cursor: pointer; font-weight: 700;">
                View Fix Patch &rarr;
              </button>
              <button type="button" class="btn btn-lime btn-xs" onclick="autoResolveCurrentReview()" style="white-space: nowrap; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(190, 242, 100, 0.45);" title="1-Click apply fix and re-run all 6 agents for an all-green approval">
                ⚡ 1-Click Auto-Resolve &amp; Re-Audit (All Green)
              </button>
            </div>
          </div>
        `;
      } else if (review.recommendation === "REQUEST_CHANGES" || review.status === "PARTIAL") {
        rationaleHtml += `
          <div class="patch-callout-banner" style="margin-top: 0.75rem; padding: 0.65rem 1rem; background: #bef2641a; border: 1.5px solid #bef264; border-radius: 8px; display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
            <div style="font-size: 0.85rem; color: #18181b;">
              💡 <strong>Automated Resolution Available:</strong> Auto-remediate missing test coverage &amp; PEP 8 issues and re-run all 6 agents.
            </div>
            <button type="button" class="btn btn-lime btn-xs" onclick="autoResolveCurrentReview()" style="white-space: nowrap; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(190, 242, 100, 0.45);" title="1-Click remediate and verify for all-green approval">
              ⚡ 1-Click Auto-Resolve &amp; Re-Audit (All Green)
            </button>
          </div>
        `;
      }
      rationaleText.innerHTML = rationaleHtml;
    } else {
      recBox.innerHTML = `<span class="badge-pending">&#x23F3; REVIEW RUNNING...</span>`;
      rationaleBox.style.display = "none";
    }

    // Render 6 Agent Cards
    renderAgentGrid(review.agent_executions || {});

    // Render Findings
    currentPatchProposal = review.patch_proposal || null;
    currentFindings = review.findings || [];
    filterAndRenderFindings();
    updateSeverityPillsCounts();

    // Update Tab Badges
    const findingsBadge = document.getElementById("tab-findings-count-badge");
    if (findingsBadge) findingsBadge.textContent = currentFindings.length;

    const patchBadge = document.getElementById("tab-patch-status-badge");
    if (patchBadge) {
      if (review.patch_proposal) {
        patchBadge.textContent = "Patch Ready";
        patchBadge.className = "tab-badge tab-badge-lime";
      } else {
        patchBadge.textContent = "None";
        patchBadge.className = "tab-badge";
      }
    }

    // Update Blocking stats
    const blocking = currentFindings.filter(f => ["CRITICAL", "HIGH", "MEDIUM"].includes(f.severity)).length;
    document.getElementById("stat-blocking-findings").textContent = blocking;

    // Render Fix Suggestion (Remediation)
    renderFixSuggestion(review.patch_proposal);

    // Render Diff Summary
    document.getElementById("diff-summary-code").textContent = review.diff_summary || "No diff information recorded.";

    // Render Execution Trace
    renderExecutionTrace(traceData.events || []);

  } catch (e) {
    console.error("Detail load error:", e);
  }
}

/* -------------------------------------------------------------
 * Agent Cards Renderer
 * ------------------------------------------------------------- */
function renderAgentGrid(agentExecutions) {
  const container = document.getElementById("agent-grid-container");
  const agentRoster = [
    { key: "Diff Agent", title: "Diff Agent", role: "Source Comparison & Change Identification", icon: "⚡" },
    { key: "Style Agent", title: "Style Agent", role: "Ruff Linting & PEP 8 Format Verification", icon: "🎨" },
    { key: "Security Agent", title: "Security Agent", role: "Bandit AST Scan & detect-secrets Credentials", icon: "🛡️" },
    { key: "Test-Coverage Agent", title: "Test-Coverage Agent", role: "Test Discovery & Docker Sandbox Execution", icon: "🧪" },
    { key: "Reviewer Manager", title: "Reviewer Manager", role: "Fan-In Consensus, Deduplication & Ranking", icon: "⚖️" },
    { key: "Fix-Suggestion Agent", title: "Fix-Suggestion Agent", role: "Automated Remediation Unified Diff Patch", icon: "🛠️" },
  ];

  container.innerHTML = agentRoster.map(a => {
    const exec = agentExecutions[a.key] || { status: "PENDING", tools_called: [], findings_count: 0 };
    let tagClass = "tag-pending";
    if (exec.status === "COMPLETED") tagClass = "tag-completed";
    else if (exec.status === "RUNNING") tagClass = "tag-running";
    else if (exec.status === "FAILED") tagClass = "tag-failed";

    let dur = "-";
    if (exec.start_time && exec.end_time) {
      const diff = exec.end_time - exec.start_time;
      dur = diff < 0.01 ? "< 0.01s" : `${diff.toFixed(2)}s`;
    }
    const tools = (exec.tools_called && exec.tools_called.length > 0) ? exec.tools_called.join(", ") : "None";

    return `
      <div class="agent-bento-card">
        <div class="agent-card-top">
          <div class="agent-card-title">${a.icon} ${a.title}</div>
          <span class="agent-status-tag ${tagClass}">${exec.status}</span>
        </div>
        <div class="agent-card-role">${a.role}</div>
        <div class="agent-meta-item">
          <span>Findings Produced:</span>
          <strong>${exec.findings_count || 0}</strong>
        </div>
        <div class="agent-meta-item">
          <span>Execution Time:</span>
          <strong>${dur}</strong>
        </div>
        <div class="agent-tools-box" title="Real Python tools invoked">
          tools: ${tools}
        </div>
      </div>
    `;
  }).join("");
}

/* -------------------------------------------------------------
 * Findings Renderer & Clickable Severity Filter Pills
 * ------------------------------------------------------------- */
function initFilters() {
  const searchInput = document.getElementById("findings-search");
  if (searchInput) {
    searchInput.addEventListener("input", filterAndRenderFindings);
  }

  // Clickable Severity Filter Pills
  document.querySelectorAll(".sev-pill").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sev-pill").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      activeSeverityFilter = btn.getAttribute("data-sev");
      filterAndRenderFindings();
    });
  });
}

function updateSeverityPillsCounts() {
  const counts = {
    ALL: currentFindings.length,
    CRITICAL: currentFindings.filter(f => f.severity === "CRITICAL").length,
    HIGH: currentFindings.filter(f => f.severity === "HIGH").length,
    MEDIUM: currentFindings.filter(f => f.severity === "MEDIUM").length,
    LOW: currentFindings.filter(f => f.severity === "LOW").length,
    INFO: currentFindings.filter(f => f.severity === "INFO").length,
  };

  const setEl = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };

  setEl("sev-count-all", counts.ALL);
  setEl("sev-count-critical", counts.CRITICAL);
  setEl("sev-count-high", counts.HIGH);
  setEl("sev-count-medium", counts.MEDIUM);
  setEl("sev-count-low", counts.LOW);
  setEl("sev-count-info", counts.INFO);
}

function filterAndRenderFindings() {
  const searchInput = document.getElementById("findings-search");
  const query = searchInput ? searchInput.value.toLowerCase().trim() : "";

  const filtered = currentFindings.filter(f => {
    const matchesQuery = !query ||
      (f.title && f.title.toLowerCase().includes(query)) ||
      (f.description && f.description.toLowerCase().includes(query)) ||
      (f.file && f.file.toLowerCase().includes(query)) ||
      (f.finding_id && f.finding_id.toLowerCase().includes(query));

    const matchesSev = (activeSeverityFilter === "ALL") || (f.severity === activeSeverityFilter);
    return matchesQuery && matchesSev;
  });

  renderFindings(filtered);
}

function renderFindings(findings) {
  const container = document.getElementById("findings-container");
  if (!findings || findings.length === 0) {
    container.innerHTML = `<div class="empty-state">No findings matching the selected filter.</div>`;
    return;
  }

  container.innerHTML = findings.map(f => {
    let sevClass = "sev-info";
    if (f.severity === "CRITICAL") sevClass = "sev-critical";
    else if (f.severity === "HIGH") sevClass = "sev-high";
    else if (f.severity === "MEDIUM") sevClass = "sev-medium";
    else if (f.severity === "LOW") sevClass = "sev-low";

    const loc = f.file ? `${f.file}${f.line ? `:${f.line}` : ''}` : 'Project Scope';
    const defectiveCodeHtml = renderDefectiveCodeHighlight(f, currentPatchProposal);

    return `
      <div class="finding-card-item">
        <div class="finding-top-row">
          <div>
            <span class="severity-pill ${sevClass}">${f.severity}</span>
            <span style="font-weight: 700; margin-left: 0.5rem; font-family: var(--font-mono);">${f.finding_id}</span>
            <span style="color: var(--text-faint); margin: 0 0.4rem;">&bull;</span>
            <span style="font-size: 0.75rem; color: var(--text-faint);">${escapeHtml(f.agent)}</span>
          </div>
          <div class="finding-location">${loc}</div>
        </div>
        <div class="finding-title-text">${escapeHtml(f.title)}</div>
        <div class="finding-description-text">${escapeHtml(f.description)}</div>

        ${defectiveCodeHtml}

        <div class="finding-evidence-box">
          <strong>Agent Tool Analysis (${f.tool}):</strong> ${escapeHtml(f.evidence)}
        </div>
        <div class="finding-remediation-note">
          &#x1F4A1; <strong>Recommendation:</strong> ${escapeHtml(f.recommendation)}
        </div>
      </div>
    `;
  }).join("");
}

function renderDefectiveCodeHighlight(finding, patchProposal) {
  if (!finding.evidence && !finding.line && !finding.file) return "";

  const lineNum = finding.line || "—";
  const fileStr = finding.file || "source";
  const evText = (finding.evidence || "").trim();

  let codeHtml = "";
  if (evText && !evText.startsWith("http")) {
    codeHtml = `<div class="line-removed">- Line ${lineNum} | ${escapeHtml(evText)}   &larr; [DEFECTIVE CODE DETECTED]</div>`;
  } else {
    codeHtml = `<div class="line-removed">- Line ${lineNum} | ${escapeHtml(finding.description || "Defective code structure detected")}</div>`;
  }

  // If this finding is targeted by the Fix-Suggestion Agent, show the green proposed fix!
  let patchComparisonHtml = "";
  if (patchProposal && patchProposal.target_finding === finding.finding_id && patchProposal.patch) {
    const addedLines = extractAddedLinesFromDiff(patchProposal.patch);
    if (addedLines) {
      patchComparisonHtml = `
        <div style="margin-top: 0.45rem; font-size: 0.72rem; font-weight: 700; color: #4ade80;">
          🟢 PROPOSED CORRECTION (DRY-RUN VALIDATED):
        </div>
        <div class="line-added" style="margin-top: 0.2rem;">
          + Line ${lineNum} | ${escapeHtml(addedLines)}
        </div>
      `;
    }
  }

  return `
    <div class="defective-code-box">
      <div class="defective-code-header">
        <span>🚨 Highlighted Defective Code: <code>${escapeHtml(fileStr)}:${lineNum}</code></span>
        <span class="defective-code-badge">${finding.severity} DEFECT</span>
      </div>
      <div class="defective-code-snippet">
        ${codeHtml}
        ${patchComparisonHtml}
      </div>
    </div>
  `;
}

function extractAddedLinesFromDiff(diffText) {
  if (!diffText) return "";
  const lines = diffText.split("\n");
  const added = lines.filter(l => l.startsWith("+") && !l.startsWith("+++")).map(l => l.substring(1).trim());
  return added.length > 0 ? added.join("\n") : "";
}

/* -------------------------------------------------------------
 * Fix Suggestion Renderer
 * ------------------------------------------------------------- */
function renderFixSuggestion(patch) {
  const validationBadge = document.getElementById("patch-validation-badge");
  const metaContainer = document.getElementById("fix-details-meta");
  const expBox = document.getElementById("fix-explanation-box");
  const diffBox = document.getElementById("fix-diff-code");
  const copyBtn = document.getElementById("btn-copy-patch");
  const applyBtn = document.getElementById("btn-apply-patch");
  const ctaBanner = document.getElementById("fix-apply-cta-banner");

  if (!patch) {
    validationBadge.textContent = "VALIDATION: NOT REQUIRED";
    metaContainer.innerHTML = "";
    expBox.textContent = "No remediation patch was required for this review.";
    diffBox.textContent = "No remediation patch needed.";
    if (copyBtn) copyBtn.style.display = "none";
    if (applyBtn) applyBtn.style.display = "none";
    if (ctaBanner) ctaBanner.style.display = "none";
    return;
  }

  if (copyBtn) copyBtn.style.display = "inline-flex";
  if (applyBtn) applyBtn.style.display = "inline-flex";
  if (ctaBanner) ctaBanner.style.display = "flex";
  validationBadge.textContent = `DRY-RUN VALIDATION: ${patch.validation}`;
  metaContainer.innerHTML = `
    <span>Target Finding: <strong>${patch.target_finding}</strong></span>
    <span>Target File: <strong>${patch.file}</strong></span>
    <span>Severity: <strong>${patch.severity}</strong></span>
    <span>Status: <strong>${patch.patch_status}</strong></span>
  `;

  expBox.textContent = patch.explanation || "No explanation provided.";
  diffBox.textContent = patch.patch || "Empty patch.";
}

/* -------------------------------------------------------------
 * Execution Trace Log Renderer
 * ------------------------------------------------------------- */
function renderExecutionTrace(events) {
  const container = document.getElementById("execution-trace-container");
  if (!events || events.length === 0) {
    container.innerHTML = `<div class="empty-state text-zinc">No execution events recorded in logs/run_log.jsonl yet.</div>`;
    return;
  }

  container.innerHTML = events.slice(-50).map(e => {
    const metaStr = e.metadata ? JSON.stringify(e.metadata) : "";
    return `
      <div class="trace-item-row">
        <span class="trace-time">${e.iso_time ? e.iso_time.split("T")[1].replace("Z", "") : "-"}</span>
        <span class="trace-type">${e.event_type}</span>
        <span class="trace-agent">[${e.agent || 'SYSTEM'}]</span>
        <span class="trace-detail">${e.tool ? `tool=${e.tool}` : ''} ${escapeHtml(metaStr)}</span>
      </div>
    `;
  }).join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return str.toString()
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
