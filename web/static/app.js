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

const SITE_NAMES = {
  yanjiuyuan: "研究院",
  dinggeshui: "定个水",
  s772200: "772200",
  s15043: "15043",
  s590555: "590555",
  s42054: "42054",
  s3497: "3497",
  s2549: "2549",
  s19333: "19333",
};

function escapeHTML(text) {
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function asDetail(row) {
  let detail = row.score_detail || {};
  if (typeof detail === "string") {
    try {
      detail = JSON.parse(detail);
    } catch {
      detail = {};
    }
  }
  return detail;
}

function fillPick(prefix, row) {
  const zodiacEl = document.getElementById("zodiac" + prefix);
  const metaEl = document.getElementById("meta" + prefix);
  const reasonsEl = document.getElementById("reasons" + prefix);

  if (!row) {
    zodiacEl.textContent = "—";
    metaEl.textContent = "";
    reasonsEl.innerHTML = "";
    return;
  }

  zodiacEl.textContent = row.zodiac;
  const detail = asDetail(row);
  const winner = detail.winner_detail || {};
  const bits = [`得分 ${row.score}`];
  if (winner.omit !== undefined) bits.push(`遗漏 ${winner.omit} 期`);
  if (winner.hot !== undefined) bits.push(`热度 ${winner.hot} 次`);
  metaEl.textContent = bits.join(" · ");
  const reasons = detail.reasons || [];
  reasonsEl.innerHTML = reasons.length
    ? reasons.map((r) => `<li>${escapeHTML(r)}</li>`).join("")
    : "<li>无</li>";
}

function hitTag(hit) {
  if (hit === null || hit === undefined) return '<span class="tag wait">待开奖</span>';
  return hit ? '<span class="tag ok">中</span>' : '<span class="tag no">没中</span>';
}

function renderHits(payload) {
  const summaryEl = document.getElementById("hitSummary");
  const body = document.getElementById("hitBody");
  const weightEl = document.getElementById("weightList");
  const hits = payload.hits || {};
  const by = hits.by_play || {};
  const bao = by.bao_xiao || {};
  const tema = by.te_ma || {};
  const pending = (bao.pending || 0) + (tema.pending || 0);
  summaryEl.textContent =
    `包肖 ${bao.hit || 0} 中 / ${bao.miss || 0} 没中 · 特码 ${tema.hit || 0} 中 / ${tema.miss || 0} 没中` +
    (pending ? ` · 待开奖 ${pending}` : "");

  const grouped = new Map();
  (hits.items || []).forEach((item) => {
    const row = grouped.get(item.period) || { period: item.period, special: item.special_zodiac || "—" };
    if (item.play_type === "bao_xiao") {
      row.bao = item.zodiac;
      row.baoHit = item.hit;
    } else if (item.play_type === "te_ma") {
      row.tema = item.zodiac;
      row.temaHit = item.hit;
    }
    if (item.special_zodiac) row.special = item.special_zodiac;
    grouped.set(item.period, row);
  });
  const rows = Array.from(grouped.values());
  body.innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr>
            <td>${row.period}</td>
            <td>${escapeHTML(row.bao || "—")}</td>
            <td>${hitTag(row.baoHit)}</td>
            <td>${escapeHTML(row.tema || "—")}</td>
            <td>${hitTag(row.temaHit)}</td>
            <td>${escapeHTML(row.special || "—")}</td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="6">还没有推荐记录</td></tr>';

  const weights = (payload.site_weights || {}).bao_xiao || {};
  const entries = Object.entries(weights).sort((a, b) => b[1] - a[1]);
  weightEl.innerHTML = entries.length
    ? entries
        .map(([code, weight]) => {
          const name = SITE_NAMES[code] || code;
          return `<span class="weight"><b>${escapeHTML(name)}</b> ${Number(weight).toFixed(2)}</span>`;
        })
        .join("")
    : '<span class="hint">还没有足够的站点记录</span>';
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
        .map((n) => `<span class="ball">${String(n).padStart(2, "0")}</span>`)
        .join("");
      const special = String(d.special).padStart(2, "0");
      return `<tr>
        <td>${d.period}</td>
        <td>${d.draw_date || "—"}</td>
        <td class="nums">${plains}</td>
        <td><span class="ball special">${special}</span></td>
        <td>${escapeHTML(d.special_zodiac || "—")}</td>
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
