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

function renderRecommend(payload) {
  const rec = payload.recommend;
  const draw = payload.latest_draw;
  const metaEl = document.getElementById("periodMeta");

  if (!rec) {
    metaEl.textContent = "尚未分析，请点击「刷新分析」";
    fillPick("Bao", null);
    fillPick("Tema", null);
    renderHits(payload);
    return;
  }

  const drawText = draw
    ? `最新开奖 ${draw.period}期 特码 ${String(draw.special).padStart(2, "0")}/${draw.special_zodiac}`
    : "暂无开奖";
  metaEl.textContent = `预测 ${rec.period} 期 · ${drawText}`;

  fillPick("Bao", rec.bao_xiao);
  fillPick("Tema", rec.te_ma);
  renderHits(payload);
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
    setStatus(`完成：${result.recommend.period}期 包肖「${bao}」/ 特码「${tema}」`);
    await loadPanel();
  } catch (err) {
    setStatus(String(err.message || err), true);
  } finally {
    btn.disabled = false;
  }
}

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
