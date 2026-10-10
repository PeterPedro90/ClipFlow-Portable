(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const form = $("analyze-form");
  const input = $("url-input");
  const analyzeButton = $("analyze-button");
  const results = $("results");
  const errorBanner = $("error-banner");
  const setupBanner = $("setup-banner");
  const progressCard = $("progress-card");
  const readyCard = $("ready-card");
  const qualityContainer = $("quality-options");
  const state = { info: null, mode: "mp4", quality: null, jobId: null, busy: false, timer: null };

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.classList.remove("hidden");
  }
  function clearError() {
    errorBanner.textContent = "";
    errorBanner.classList.add("hidden");
  }
  function formatDuration(seconds) {
    if (!Number.isFinite(seconds) || !seconds) return "--:--";
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);
    return (hours ? `${hours}:${String(minutes).padStart(2, "0")}` : String(minutes)) + `:${String(secs).padStart(2, "0")}`;
  }
  function resolutionLabel(height) {
    if (height >= 4320) return "8K";
    if (height >= 2160) return "4K";
    if (height >= 1440) return "QHD";
    if (height >= 1080) return "Full HD";
    if (height >= 720) return "HD";
    return "MP4";
  }
  async function request(path, method = "GET", data = undefined) {
    const response = await fetch(path, {
      method,
      ...(data === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) }),
    });
    let payload;
    try { payload = await response.json(); }
    catch { throw new Error("Resposta inesperada do servidor."); }
    if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Não foi possível completar a solicitação.");
    return payload;
  }
  function setAnalyzeBusy(isBusy) {
    analyzeButton.disabled = isBusy;
    $("analyze-text").textContent = isBusy ? "Analisando..." : "Analisar vídeo";
  }
  function setDownloadBusy(isBusy) {
    state.busy = isBusy;
    $("download-button").disabled = isBusy;
    $("download-button").querySelector("span").textContent = isBusy ? "Processando..." : "Preparar arquivo";
    document.querySelectorAll(".mode-tab,.quality-option").forEach(el => el.disabled = isBusy);
  }
  function renderChoices() {
    qualityContainer.replaceChildren();
    if (!state.info) return;
    const isVideo = state.mode === "mp4";
    const choices = isVideo ? state.info.video_qualities : state.info.audio_qualities;
    if (!choices.includes(state.quality)) state.quality = choices[0] ?? null;
    for (const value of choices) {
      const option = document.createElement("button");
      option.type = "button";
      option.className = "quality-option" + (value === state.quality ? " selected" : "");
      option.setAttribute("aria-pressed", value === state.quality ? "true" : "false");
      const main = document.createElement("span");
      main.className = "main";
      main.textContent = isVideo ? `${value}p` : `${value} kbps`;
      const hint = document.createElement("span");
      hint.className = "hint";
      hint.textContent = isVideo ? resolutionLabel(value) : (value === 128 ? "Padrão" : value === 192 ? "Alta" : value === 256 ? "Muito alta" : "Máxima saída");
      option.append(main, hint);
      option.addEventListener("click", () => {
        if (state.busy) return;
        state.quality = value;
        renderChoices();
      });
      qualityContainer.append(option);
    }
    $("quality-help").textContent = isVideo ? "Resoluções encontradas neste vídeo" : "Taxa de codificação do arquivo final";
    $("quality-explanation").textContent = isVideo
      ? "As resoluções são detectadas no vídeo original. Alguns formatos podem exigir conversão."
      : "A escolha define o bitrate do MP3 convertido. Não aumenta a qualidade do áudio original.";
    $("download-button").disabled = !choices.length || state.busy;
    $("quality-panel").setAttribute("aria-labelledby", isVideo ? "mp4-tab" : "mp3-tab");
    document.querySelectorAll(".mode-tab").forEach(tab => {
      const selected = tab.dataset.mode === state.mode;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-selected", String(selected));
    });
  }
  function resetJob() {
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
    state.jobId = null;
    progressCard.classList.add("hidden");
    readyCard.classList.add("hidden");
    $("progress-fill").style.width = "0%";
    setDownloadBusy(false);
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();
    resetJob();
    results.classList.add("hidden");
    state.info = null;
    if (!input.value.trim()) { showError("Cole primeiro o link de um vídeo do YouTube."); return; }
    setAnalyzeBusy(true);
    try {
      const info = await request("/api/info", "POST", { url: input.value.trim() });
      state.info = info;
      state.mode = "mp4";
      state.quality = info.video_qualities[0] ?? null;
      $("video-thumb").src = info.thumbnail;
      $("video-duration").textContent = formatDuration(info.duration);
      $("video-title").textContent = info.title;
      $("video-channel").textContent = info.channel;
      renderChoices();
      results.classList.remove("hidden");
    } catch (error) {
      showError(error.message || "Erro ao analisar vídeo.");
    } finally { setAnalyzeBusy(false); }
  });
  $("paste-btn").addEventListener("click", async () => {
    clearError();
    try { input.value = await navigator.clipboard.readText(); input.focus(); }
    catch { showError("Não foi possível ler a área de transferência. Cole o link manualmente com Ctrl+V."); }
  });
  document.querySelectorAll(".mode-tab").forEach(button => button.addEventListener("click", () => {
    if (state.busy) return;
    state.mode = button.dataset.mode;
    state.quality = null;
    renderChoices();
  }));
  function progressUpdate(percentage, label) {
    const value = Math.min(100, Math.max(0, Number(percentage) || 0));
    $("progress-fill").style.width = `${value}%`;
    $("progress-percentage").textContent = `${Math.round(value)}%`;
    $("progress-status").textContent = label;
  }
  async function pollJob(jobId) {
    if (state.jobId !== jobId) return;
    try {
      const job = await request(`/api/jobs/${jobId}`);
      if (state.jobId !== jobId) return;
      if (job.status === "ready") {
        progressUpdate(100, "Arquivo pronto!");
        progressCard.classList.add("hidden");
        $("save-button").href = `/api/files/${jobId}`;
        readyCard.classList.remove("hidden");
        setDownloadBusy(false);
        return;
      }
      if (job.status === "error") {
        showError(job.error || "Falha ao processar arquivo.");
        progressCard.classList.add("hidden");
        setDownloadBusy(false);
        return;
      }
      progressUpdate(job.progress || 0, job.phase || "Preparando...");
      state.timer = setTimeout(() => pollJob(jobId), 1100);
    } catch (error) {
      showError(error.message || "Não foi possível consultar o progresso.");
      progressCard.classList.add("hidden");
      setDownloadBusy(false);
    }
  }
  $("download-button").addEventListener("click", async () => {
    if (!state.info || !state.quality || state.busy) return;
    clearError();
    readyCard.classList.add("hidden");
    progressCard.classList.remove("hidden");
    progressUpdate(0, "Entrando na fila...");
    setDownloadBusy(true);
    try {
      const data = await request("/api/jobs", "POST", {
        video_id: state.info.id,
        mode: state.mode,
        quality: state.quality,
      });
      state.jobId = data.job_id;
      pollJob(data.job_id);
    } catch (error) {
      progressCard.classList.add("hidden");
      setDownloadBusy(false);
      showError(error.message || "Não foi possível iniciar o download.");
    }
  });
  $("save-button").addEventListener("click", () => {
    // Cada arquivo pronto é baixado uma vez e removido do servidor.
    $("save-button").textContent = "↓ Download iniciado";
    setTimeout(() => { $("save-button").textContent = "↓ Baixar arquivo agora"; }, 3500);
  });
  request("/api/health").then(health => {
    const missing = [];
    if (!health.ffmpeg) missing.push("FFmpeg");
    if (!health.deno) missing.push("Deno");
    if (missing.length) {
      setupBanner.textContent = `Atenção: ${missing.join(" e ")} não ${missing.length > 1 ? "foram encontrados" : "foi encontrado"} no servidor. Consulte o README para concluir a instalação.`;
      setupBanner.classList.remove("hidden");
    }
  }).catch(() => {
    setupBanner.textContent = "Não foi possível conectar ao servidor. Abra este site pelo endereço http://127.0.0.1:8000, após iniciar o programa.";
    setupBanner.classList.remove("hidden");
  });
})();
