async function fetchJSON(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.error || res.statusText);
  }
  return data;
}

function setStatus(text, isErr) {
  const el = document.getElementById("status");
  el.textContent = text || "";
  el.className = "status" + (isErr ? " err" : "");
}

function fillPick(prefix, row) {
  const zodiacEl = document.getElementById("zodiac" + prefix);
  const metaEl = document.getElementById("meta" + prefix);
  const reasonsEl = document.getElementById("reasons" + prefix);
  const detailEl = document.getElementById("detail" + prefix);

  if (!row) {
    zodiacEl.textContent = "—";
    metaEl.textContent = "";
    reasonsEl.innerHTML = "";
    detailEl.textContent = "";
    return;
  }

  zodiacEl.textContent = row.zodiac;
  metaEl.textContent = `得分 ${row.score}`;
  const detail = row.score_detail || {};
  const reasons = detail.reasons || [];
  reasonsEl.innerHTML = reasons.map((r) => `<li>${r}</li>`).join("") || "<li>无</li>";
  detailEl.textContent = JSON.stringify(detail, null, 2);
}

function renderHits(payload) {
  const summaryEl = document.getElementById("hitSummary");
  const detailEl = document.getElementById("hitDetail");
  const hits = payload.hits || {};
  const by = hits.by_play || {};
  const bao = by.bao_xiao || {};
  const tema = by.te_ma || {};
  summaryEl.textContent =
    `系统推荐：包肖 ${bao.hit || 0}中/${bao.miss || 0}否 · 特码 ${tema.hit || 0}中/${tema.miss || 0}否` +
    (bao.pending || tema.pending ? `（待开奖 ${ (bao.pending || 0) + (tema.pending || 0) }）` : "");
  detailEl.textContent = JSON.stringify(
    { site_weights: payload.site_weights || {}, recent: hits.items || [] },
    null,
    2
  );
}

let settlePeriod = null;
let settleRecorded = null;

function hitWord(hit) {
  if (hit === null || hit === undefined) return "未录入";
  return hit ? "中" : "没中";
}

function askNotice({ title, text, okText, cancelText }) {
  return new Promise((resolve) => {
    const root = document.getElementById("notice");
    const ok = document.getElementById("noticeOk");
    const cancel = document.getElementById("noticeCancel");
    document.getElementById("noticeTitle").textContent = title;
    document.getElementById("noticeText").textContent = text;
    ok.textContent = okText || "确定";
    cancel.hidden = !cancelText;
    if (cancelText) cancel.textContent = cancelText;
    root.hidden = false;
    const finish = (value) => {
      root.hidden = true;
      ok.onclick = null;
      cancel.onclick = null;
      resolve(value);
    };
    ok.onclick = () => finish(true);
    cancel.onclick = () => finish(false);
  });
}

function setHitRadios(name, hit) {
  const wanted = hit === null || hit === undefined ? null : hit ? "1" : "0";
  document.querySelectorAll(`input[name="${name}"]`).forEach((el) => {
    el.checked = wanted !== null && el.value === wanted;
  });
}

function renderManual(payload) {
  const box = document.getElementById("manualHit");
  const settle = payload.settle;
  if (!settle || (!settle.bao_xiao && !settle.te_ma)) {
    box.hidden = true;
    settlePeriod = null;
    settleRecorded = null;
    return;
  }
  box.hidden = false;
  settlePeriod = settle.period;
  const bao = settle.bao_xiao;
  const tema = settle.te_ma;
  settleRecorded = {
    bao: bao ? bao.hit : null,
    tema: tema ? tema.hit : null,
  };
  const state = settle.drawn ? "已开奖" : "待开奖";
  document.getElementById("manualMeta").textContent =
    `${settle.period}期${state} · 包肖荐 ${bao ? bao.zodiac : "—"} · 特码荐 ${tema ? tema.zodiac : "—"}`;
  setHitRadios("baoHit", bao ? bao.hit : null);
  setHitRadios("temaHit", tema ? tema.hit : null);
}

function selectedHit(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  if (!el) return null;
  return el.value === "1";
}

function renderRecommend(payload) {
  const rec = payload.recommend;
  const draw = payload.latest_draw;
  const metaEl = document.getElementById("periodMeta");

  if (!rec) {
    metaEl.textContent = "尚未分析，请点击「刷新分析」";
    fillPick("Bao", null);
    fillPick("Tema", null);
    renderHits(payload);
    renderManual(payload);
    return;
  }

  const drawText = draw
    ? `最新开奖 ${draw.period}期 特码 ${String(draw.special).padStart(2, "0")}/${draw.special_zodiac}`
    : "暂无开奖";
  metaEl.textContent = `预测 ${rec.period} 期 · ${drawText}`;

  fillPick("Bao", rec.bao_xiao);
  fillPick("Tema", rec.te_ma);
  renderHits(payload);
  renderManual(payload);
}

function renderDraws(items) {
  const body = document.getElementById("drawsBody");
  body.innerHTML = (items || [])
    .map((d) => {
      const plains = [d.n1, d.n2, d.n3, d.n4, d.n5, d.n6]
        .map((n) => String(n).padStart(2, "0"))
        .join(" ");
      return `<tr>
        <td>${d.period}</td>
        <td>${d.draw_date || "-"}</td>
        <td>${plains}</td>
        <td>${String(d.special).padStart(2, "0")}</td>
        <td>${d.special_zodiac}</td>
      </tr>`;
    })
    .join("");
}

async function loadPanel() {
  const data = await fetchJSON("/api/latest-recommend");
  renderRecommend(data);
  const draws = await fetchJSON("/api/draws?limit=20");
  renderDraws(draws.items);
}

async function doRefresh() {
  const btn = document.getElementById("btnRefresh");
  btn.disabled = true;
  setStatus("正在抓取并分析，可能需要 30–90 秒…");
  try {
    const result = await fetchJSON("/api/refresh?full_history=true", { method: "POST" });
    const bao = result.recommend.bao_xiao.zodiac;
    const tema = result.recommend.te_ma.zodiac;
    const notes = [];
    if (result.live_error) notes.push("实时开奖暂时无效，已用库里的开奖继续");
    if (result.history_error || result.history_light_error) notes.push("历史页暂时连不上");
    const extra = notes.length ? `（${notes.join("；")}）` : "";
    setStatus(`完成：${result.recommend.period}期 包肖「${bao}」/ 特码「${tema}」${extra}`);
    await loadPanel();
  } catch (err) {
    setStatus(String(err.message || err), true);
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("btnManualHit").addEventListener("click", async () => {
  const btn = document.getElementById("btnManualHit");
  const bao = selectedHit("baoHit");
  const tema = selectedHit("temaHit");
  if (settlePeriod == null) {
    setStatus("没有可录入的已开奖期", true);
    return;
  }
  if (bao === null || tema === null) {
    setStatus("请先选择包肖和特码是中还是没中", true);
    return;
  }
  const recorded =
    settleRecorded &&
    (settleRecorded.bao !== null || settleRecorded.tema !== null);
  if (recorded) {
    const replace = await askNotice({
      title: "本期已经录入过",
      text: `${settlePeriod}期已有记录：包肖${hitWord(settleRecorded.bao)}，特码${hitWord(settleRecorded.tema)}。\n是否用这次的结果替换？替换后只保留最新一次。`,
      okText: "替换",
      cancelText: "取消",
    });
    if (!replace) {
      setStatus(`${settlePeriod}期未替换，仍保留上次录入`);
      return;
    }
  }
  btn.disabled = true;
  try {
    await fetchJSON("/api/manual-hit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ period: settlePeriod, bao_xiao: bao, te_ma: tema }),
    });
    const summary = `${settlePeriod}期：包肖${bao ? "中" : "没中"}，特码${tema ? "中" : "没中"}`;
    setStatus(recorded ? `已替换 ${summary}` : `写入成功 ${summary}`);
    await loadPanel();
    await askNotice({
      title: "写入成功",
      text: recorded ? `${summary}\n已替换该期之前的录入。` : summary,
      okText: "知道了",
    });
  } catch (err) {
    setStatus(String(err.message || err), true);
  } finally {
    btn.disabled = false;
  }
});

document.getElementById("btnRefresh").addEventListener("click", doRefresh);
document.getElementById("btnReload").addEventListener("click", async () => {
  try {
    await loadPanel();
    setStatus("已从数据库重新加载");
  } catch (err) {
    setStatus(String(err.message || err), true);
  }
});

loadPanel().catch((err) => setStatus(String(err.message || err), true));
