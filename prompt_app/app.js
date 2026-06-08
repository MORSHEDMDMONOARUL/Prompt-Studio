const promptInput = document.querySelector("#promptInput");
const optimizeBtn = document.querySelector("#optimizeBtn");
const clearBtn = document.querySelector("#clearBtn");
const copyBtn = document.querySelector("#copyBtn");
const downloadBtn = document.querySelector("#downloadBtn");
const useAsInputBtn = document.querySelector("#useAsInputBtn");
const clearHistoryBtn = document.querySelector("#clearHistoryBtn");
const statusText = document.querySelector("#status");
const optimizedOutput = document.querySelector("#optimizedOutput");
const whyText = document.querySelector("#whyText");
const checklist = document.querySelector("#checklist");
const qualityList = document.querySelector("#qualityList");
const charCount = document.querySelector("#charCount");
const sampleChips = document.querySelectorAll(".sample-chip");
const toast = document.querySelector("#toast");
const historyList = document.querySelector("#historyList");
const historyCount = document.querySelector("#historyCount");
const profileHint = document.querySelector("#profileHint");
const qualityScore = document.querySelector("#qualityScore");
const sectionScore = document.querySelector("#sectionScore");
const tokenSaved = document.querySelector("#tokenSaved");
const tokenCount = document.querySelector("#tokenCount");
const sourceMeta = document.querySelector("#sourceMeta");
const tokenText = document.querySelector("#tokenText");
const profileInputs = document.querySelectorAll("input[name='profile']");
const outputModeInputs = document.querySelectorAll("input[name='outputMode']");

const LEGACY_HISTORY_KEY = "projectPromptStudio.history";
const HISTORY_KEY = "promptStudio.history";
const MAX_HISTORY_ITEMS = 8;
const DEFAULT_REQUIRED_SECTIONS = 23;
const PLACEHOLDER_OUTPUT = "The implementation prompt will appear here after generation.";
const profileDescriptions = {
    project_brief: "Balanced project brief",
    coding_agent: "Execution-ready coding prompt",
    product_spec: "Product spec and success criteria",
};

let lastResult = null;
let historyItems = loadHistory();

function selectedProfile() {
    const checked = document.querySelector("input[name='profile']:checked");
    return checked ? checked.value : "project_brief";
}

function selectedOutputMode() {
    const checked = document.querySelector("input[name='outputMode']:checked");
    return checked ? checked.value : "full";
}

function showToast(message) {
    toast.textContent = message;
    toast.classList.add("show");
    window.clearTimeout(showToast.timeoutId);
    showToast.timeoutId = window.setTimeout(() => {
        toast.classList.remove("show");
    }, 2200);
}

function updateCharCount() {
    const count = promptInput.value.length;
    charCount.textContent = `${count} ${count === 1 ? "character" : "characters"}`;
    charCount.classList.toggle("is-warning", count > 10000);
}

function setWorking(isWorking) {
    optimizeBtn.disabled = isWorking;
    statusText.classList.toggle("is-working", isWorking);
    optimizedOutput.classList.toggle("is-loading", isWorking);
}

function setEmptyResult() {
    lastResult = null;
    optimizedOutput.textContent = PLACEHOLDER_OUTPUT;
    whyText.textContent = "No brief generated yet.";
    checklist.innerHTML = "";
    qualityList.innerHTML = "";
    qualityScore.textContent = "--";
    sectionScore.textContent = `0/${DEFAULT_REQUIRED_SECTIONS}`;
    tokenSaved.textContent = "0%";
    tokenCount.textContent = "0";
    sourceMeta.textContent = "--";
    tokenText.textContent = "Generate a brief to see compact prompt savings.";
}

async function optimizePrompt() {
    const prompt = promptInput.value.trim();
    if (!prompt) {
        statusText.textContent = "Enter a project idea to continue.";
        showToast("Project idea required.");
        promptInput.focus();
        return;
    }

    setWorking(true);
    statusText.textContent = "Generating implementation brief...";
    optimizedOutput.textContent = "Preparing the implementation prompt...";
    whyText.textContent = "";
    checklist.innerHTML = "";
    qualityList.innerHTML = "";

    try {
        const response = await fetch("/api/optimize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prompt, profile: selectedProfile() }),
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || "Optimization failed.");
        }

        renderResult(data);
        saveHistory(prompt, data);
        const source = data.source === "nvidia" ? `NVIDIA: ${data.model}` : "local fallback";
        statusText.textContent = `Brief generated. Source: ${source}`;
        if (data.warning) {
            statusText.textContent += " (fallback used)";
        }
        showToast("Brief generated.");
    } catch (error) {
        optimizedOutput.textContent = "Something went wrong.";
        whyText.textContent = error.message;
        statusText.textContent = "Generation failed.";
        showToast("Generation failed.");
    } finally {
        setWorking(false);
    }
}

function currentOutputText() {
    if (!lastResult) {
        return optimizedOutput.textContent.trim();
    }
    if (selectedOutputMode() === "compact") {
        return lastResult.compact_prompt || lastResult.optimized_prompt || "";
    }
    return lastResult.optimized_prompt || "";
}

function renderOutputText() {
    if (!lastResult) {
        return;
    }
    optimizedOutput.textContent = currentOutputText() || "No implementation prompt was returned.";
    updateTokenCards();
}

function renderResult(data) {
    lastResult = data;
    renderOutputText();
    whyText.textContent = data.why_it_is_better || "The brief was structured with clearer requirements and validation criteria.";
    renderList(checklist, data.checklist || []);
    renderQuality(data.quality);
    const requiredSections = data.stats?.required_sections || 15;
    const missingSections = data.quality?.missing_sections?.length || 0;
    qualityScore.textContent = data.quality ? `${data.quality.score} ${data.quality.grade}` : "--";
    sectionScore.textContent = `${requiredSections - missingSections}/${requiredSections}`;
    sourceMeta.textContent = data.source === "nvidia" ? "NVIDIA" : "Fallback";
    updateTokenCards();
}

function updateTokenCards() {
    if (!lastResult?.token_savings) {
        tokenSaved.textContent = "0%";
        tokenCount.textContent = "0";
        tokenText.textContent = "Generate a brief to see compact prompt savings.";
        return;
    }

    const savings = lastResult.token_savings;
    const mode = selectedOutputMode();
    const shownTokens = mode === "compact" ? savings.compact_tokens : savings.full_tokens;
    tokenSaved.textContent = `${savings.saved_percent}%`;
    tokenCount.textContent = String(shownTokens || 0);
    tokenText.textContent = `Compact mode saves about ${savings.saved_tokens} estimated tokens (${savings.saved_percent}%) versus the full brief.`;
}

function renderList(target, items) {
    target.innerHTML = "";
    if (!items.length) {
        const li = document.createElement("li");
        li.textContent = "No items returned.";
        target.appendChild(li);
        return;
    }

    for (const item of items) {
        const li = document.createElement("li");
        li.textContent = item;
        target.appendChild(li);
    }
}

function renderQuality(quality) {
    qualityList.innerHTML = "";
    if (!quality?.checks?.length) {
        renderList(qualityList, ["Generate a brief to see quality checks."]);
        return;
    }

    for (const check of quality.checks) {
        const li = document.createElement("li");
        li.className = check.passed ? "check-pass" : "check-fail";
        li.textContent = `${check.passed ? "Pass" : "Review"}: ${check.label} - ${check.detail}`;
        qualityList.appendChild(li);
    }
}

async function copyOutput() {
    const text = currentOutputText();
    if (!text || text === PLACEHOLDER_OUTPUT) {
        showToast("Nothing to copy yet.");
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        statusText.textContent = `${selectedOutputMode() === "compact" ? "Compact" : "Full"} prompt copied.`;
        showToast("Brief copied.");
    } catch (error) {
        statusText.textContent = "Clipboard permission was denied.";
        showToast("Copy failed.");
    }
}

function downloadOutput() {
    const text = currentOutputText();
    if (!text || text === PLACEHOLDER_OUTPUT) {
        showToast("Nothing to export yet.");
        return;
    }

    const profile = lastResult?.profile?.label || "Project Brief";
    const source = lastResult?.source === "nvidia" ? `NVIDIA ${lastResult.model}` : "Local fallback";
    const mode = selectedOutputMode();
    const savings = lastResult?.token_savings;
    const payload = `---
title: Prompt Studio Brief
profile: ${profile}
source: ${source}
mode: ${mode}
estimated_tokens: ${mode === "compact" ? savings?.compact_tokens || 0 : savings?.full_tokens || 0}
estimated_tokens_saved_percent: ${savings?.saved_percent || 0}
generated: ${new Date().toISOString()}
---

${text}
`;
    const blob = new Blob([payload], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `prompt-studio-${mode}-${Date.now()}.md`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(link.href);
    showToast("Markdown exported.");
}

function useOutputAsInput() {
    const text = currentOutputText();
    if (!text || text === PLACEHOLDER_OUTPUT) {
        showToast("Generate a brief first.");
        return;
    }
    promptInput.value = text;
    updateCharCount();
    promptInput.focus();
    statusText.textContent = `${selectedOutputMode() === "compact" ? "Compact" : "Full"} brief moved back to input.`;
}

function loadHistory() {
    try {
        const current = window.localStorage.getItem(HISTORY_KEY);
        const legacy = window.localStorage.getItem(LEGACY_HISTORY_KEY);
        const source = current || legacy || "[]";
        const parsed = JSON.parse(source);
        if (!current && legacy && Array.isArray(parsed)) {
            window.localStorage.setItem(HISTORY_KEY, JSON.stringify(parsed));
            window.localStorage.removeItem(LEGACY_HISTORY_KEY);
        }
        return Array.isArray(parsed) ? parsed : [];
    } catch (error) {
        return [];
    }
}

function saveHistory(input, result) {
    const item = {
        id: String(Date.now()),
        createdAt: new Date().toISOString(),
        input,
        output: result.optimized_prompt || "",
        compactOutput: result.compact_prompt || "",
        profile: result.profile?.label || "Project Brief",
        source: result.source || "unknown",
        score: result.quality?.score || 0,
        grade: result.quality?.grade || "Unscored",
        tokenSavings: result.token_savings || null,
        why: result.why_it_is_better || "",
        checklist: result.checklist || [],
        quality: result.quality || null,
        stats: result.stats || null,
        model: result.model || "",
    };
    historyItems = [item, ...historyItems.filter((entry) => entry.output !== item.output)].slice(0, MAX_HISTORY_ITEMS);
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(historyItems));
    renderHistory();
}

function renderHistory() {
    historyList.innerHTML = "";
    historyCount.textContent = historyItems.length;

    if (!historyItems.length) {
        const empty = document.createElement("p");
        empty.className = "empty-history";
        empty.textContent = "No saved briefs yet.";
        historyList.appendChild(empty);
        return;
    }

    for (const item of historyItems) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "history-item";
        const saved = item.tokenSavings ? ` - saved ${item.tokenSavings.saved_percent}%` : "";
        button.innerHTML = `
            <span>${escapeHtml(item.profile)} - ${escapeHtml(item.grade)} ${Number(item.score) || 0}${escapeHtml(saved)}</span>
            <strong>${escapeHtml(item.input.slice(0, 92))}${item.input.length > 92 ? "..." : ""}</strong>
            <small>${new Date(item.createdAt).toLocaleString()} - ${escapeHtml(item.source)}</small>
        `;
        button.addEventListener("click", () => restoreHistoryItem(item));
        historyList.appendChild(button);
    }
}

function restoreHistoryItem(item) {
    promptInput.value = item.input;
    updateCharCount();
    renderResult({
        optimized_prompt: item.output,
        compact_prompt: item.compactOutput || item.output,
        token_savings: item.tokenSavings,
        why_it_is_better: item.why,
        checklist: item.checklist,
        quality: item.quality,
        stats: item.stats,
        source: item.source,
        model: item.model,
        profile: { label: item.profile },
    });
    statusText.textContent = "History item restored.";
    showToast("Brief restored.");
}

function clearHistory() {
    historyItems = [];
    window.localStorage.removeItem(HISTORY_KEY);
    window.localStorage.removeItem(LEGACY_HISTORY_KEY);
    renderHistory();
    showToast("History cleared.");
}

function escapeHtml(text) {
    return String(text)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

optimizeBtn.addEventListener("click", optimizePrompt);

promptInput.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
        optimizePrompt();
    }
});

clearBtn.addEventListener("click", () => {
    promptInput.value = "";
    setEmptyResult();
    statusText.textContent = "Ready.";
    updateCharCount();
    promptInput.focus();
});

copyBtn.addEventListener("click", copyOutput);
downloadBtn.addEventListener("click", downloadOutput);
useAsInputBtn.addEventListener("click", useOutputAsInput);
clearHistoryBtn.addEventListener("click", clearHistory);
promptInput.addEventListener("input", updateCharCount);

for (const chip of sampleChips) {
    chip.addEventListener("click", () => {
        promptInput.value = chip.dataset.prompt || "";
        updateCharCount();
        promptInput.focus();
        showToast("Example inserted.");
    });
}

for (const input of profileInputs) {
    input.addEventListener("change", () => {
        profileHint.textContent = profileDescriptions[selectedProfile()] || "Balanced project brief";
    });
}

for (const input of outputModeInputs) {
    input.addEventListener("change", renderOutputText);
}

window.addEventListener("load", () => {
    updateCharCount();
    renderHistory();
    profileHint.textContent = profileDescriptions[selectedProfile()] || "Balanced project brief";
});
