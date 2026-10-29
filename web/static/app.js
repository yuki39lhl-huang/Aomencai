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

const FAIL_LABELS = {
  timeout: "超时",
  route_page: "线路页",
  no_period: "无期号",
  no_list: "没有名单",
  fetch_error: "抓取失败",
};

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

function groupZodiacs(row) {
  if (!row) return [];
  if (Array.isArray(row.zodiacs) && row.zodiacs.length) return row.zodiacs;
  return (asDetail(row).places || []).map((p) => p.zodiac);
}

function fillGroup(prefix, row) {
  const groupEl = document.getElementById("group" + prefix);
  const metaEl = document.getElementById("meta" + prefix);
  const places = row ? asDetail(row).places || [] : [];
  if (!row || !places.length) {
    groupEl.innerHTML = '<p class="place-zodiac">—</p>';
    metaEl.textContent = row ? "" : "下次刷新分析后生成";
    return;
  }
  const reasons = asDetail(row).reasons || [];
  groupEl.innerHTML = places
    .map(
      (place) => `<div class="place">
        <p class="place-label">${escapeHTML(place.place)}</p>
        <p class="place-zodiac">${escapeHTML(place.zodiac || "—")}</p>
        <p class="place-meta">遗漏 ${escapeHTML(place.omit ?? "—")} · 热度 ${escapeHTML(place.hot ?? "—")}</p>
        <p class="place-meta score-quiet">得分 ${escapeHTML(place.score)}</p>
      </div>`
    )
    .join("");
  metaEl.textContent = reasons.length ? reasons[0] : "";
}

function fillPick(prefix, row, quietScore) {
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
  const bits = [];
  if (!quietScore) bits.push(`得分 ${row.score}`);
  if (winner.omit !== undefined) bits.push(`遗漏 ${winner.omit} 期`);
  if (winner.hot !== undefined) bits.push(`热度 ${winner.hot} 次`);
  metaEl.textContent = bits.join(" · ");
  const reasons = quietScore && row.score != null ? [`公式得分 ${row.score}，只作参考`] : [];
  reasons.push(...(detail.reasons || []));
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
  const plays = [
    ["bao_xiao", "单肖", "约 55%"],
    ["lian3", "三连肖", "约 10%"],
    ["lian5", "五连肖", "约 1%"],
    ["te_ma", "特码", "约 8%"],
  ];

  const grouped = new Map();
  (hits.items || []).forEach((item) => {
    const row = grouped.get(item.period) || { period: item.period, special: item.special_zodiac || "—" };
    row[item.play_type] = item;
    if (item.special_zodiac) row.special = item.special_zodiac;
    grouped.set(item.period, row);
  });
  const rows = Array.from(grouped.values());
  summaryEl.innerHTML =
    `<span class="stats-range">最近 ${rows.length} 期</span>` +
    plays
      .map(([key, label, chance]) => {
        const s = by[key] || {};
        const done = (s.hit || 0) + (s.miss || 0);
        const rate = done ? `${Math.round(((s.hit || 0) / done) * 100)}%` : "—";
        return `<span class="stat">
          <b>${label}</b>
          <span>${s.hit || 0} 中 / ${s.miss || 0} 没中</span>
          <span class="stat-rate">${rate}<small> · 运气${chance}</small></span>
        </span>`;
      })
      .join("");

  const cell = (item, many) => {
    if (!item) return '<span class="muted">—</span>';
    const names = many ? (item.zodiacs || [item.zodiac]).join(" ") : item.zodiac;
    return `${escapeHTML(names)} ${hitTag(item.hit)}`;
  };
  body.innerHTML = rows.length
    ? rows
        .map(
          (row) => `<tr>
            <td>${row.period}</td>
            <td>${cell(row.bao_xiao, false)}</td>
            <td>${cell(row.lian3, true)}</td>
            <td>${cell(row.lian5, true)}</td>
            <td>${cell(row.te_ma, false)}</td>
            <td>${escapeHTML(row.special || "—")}</td>
          </tr>`
        )
        .join("")
    : '<tr><td colspan="6">还没有推荐记录</td></tr>';
  syncToggle("hitBody");

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
    `${settle.period}期${state} · 单肖荐 ${bao ? bao.zodiac : "—"} · 特码荐 ${tema ? tema.zodiac : "—"}`;
  setHitRadios("baoHit", bao ? bao.hit : null);
  setHitRadios("temaHit", tema ? tema.hit : null);
}

function selectedHit(name) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  if (!el) return null;
  return el.value === "1";
}

const COLLAPSED_ROWS = 10;

function syncToggle(bodyId) {
  const body = document.getElementById(bodyId);
  const btn = document.querySelector(`[data-toggle="${bodyId}"]`);
  if (!body || !btn) return;
  const total = body.querySelectorAll("tr").length;
  btn.hidden = total <= COLLAPSED_ROWS;
  btn.textContent = body.classList.contains("collapsed") ? `展开全部 ${total} 期` : "收起";
}

document.querySelectorAll("[data-toggle]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const id = btn.dataset.toggle;
    document.getElementById(id).classList.toggle("collapsed");
    syncToggle(id);
  });
});

function clockText(value) {
  const d = value ? new Date(value) : null;
  if (!d || Number.isNaN(d.getTime())) return null;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function todayAt(hour, minute) {
  const d = new Date();
  d.setHours(hour, minute, 0, 0);
  return d;
}

function renderRefreshTip(rec, draw) {
  const el = document.getElementById("refreshTip");
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const created = rec && rec.bao_xiao ? new Date(rec.bao_xiao.created_at) : null;
  let text;
  let tone = "";
  if (draw && String(draw.draw_date).slice(0, 10) === today) {
    text = "今晚已开奖。下一期请在明天 21:00–21:20 刷新定推荐。";
  } else if (now < todayAt(21, 0)) {
    text = "今晚 21:32 开奖。网站资料多在开奖前一小时内更新，建议 21:00–21:20 再刷新一次。";
  } else if (now < todayAt(21, 32)) {
    if (created && created >= todayAt(21, 0)) {
      text = "本期已在开奖前刷新过，按这组推荐即可。";
      tone = "ok";
    } else {
      text = "现在是建议刷新时段，点「刷新分析」更新本期推荐。";
      tone = "warn";
    }
  } else {
    text = "已过 21:32，开奖后点「刷新分析」对账。";
    tone = "warn";
  }
  el.textContent = text;
  el.className = "refresh-tip" + (tone ? ` ${tone}` : "");
}

function renderRecommend(payload) {
  const rec = payload.recommend;
  const draw = payload.latest_draw;
  const metaEl = document.getElementById("periodMeta");
  renderRefreshTip(rec, draw);

  if (!rec) {
    metaEl.textContent = "尚未分析，请点击「刷新分析」";
    fillPick("Bao", null);
    fillPick("Tema", null);
    fillGroup("Lian3", null);
    fillGroup("Lian5", null);
    document.getElementById("yearZodiac").textContent = payload.year_zodiac
      ? `固定当年肖：${payload.year_zodiac}`
      : "";
    renderHits(payload);
    renderBacktest(payload.backtest, payload.backtest_error);
    renderSiteAlerts(payload.site_alerts);
    renderManual(payload);
    return;
  }

  const drawText = draw
    ? `最新开奖 ${draw.period}期 特码 ${String(draw.special).padStart(2, "0")}/${draw.special_zodiac}`
    : "暂无开奖";
  const made = clockText(rec.bao_xiao && rec.bao_xiao.created_at);
  metaEl.textContent = `预测 ${rec.period} 期 · ${drawText}` + (made ? ` · 推荐生成于 ${made}` : "");

  document.getElementById("yearZodiac").textContent = payload.year_zodiac
    ? `固定当年肖：${payload.year_zodiac}`
    : "";
  fillPick("Bao", rec.bao_xiao, true);
  fillPick("Tema", rec.te_ma);
  fillGroup("Lian3", rec.lian3);
  fillGroup("Lian5", rec.lian5);
  renderHits(payload);
  renderBacktest(payload.backtest, payload.backtest_error);
  renderSiteAlerts(payload.site_alerts);
  renderManual(payload);
}

function pct(hits, total) {
  if (hits == null || !total) return "—";
  return `${hits}/${total} = ${(hits / total * 100).toFixed(1)}%`;
}

function expText(expected, total) {
  if (expected == null || !total) return "—";
  const n = Number(expected);
  return `${n.toFixed(1)} 次 (${(n / total * 100).toFixed(1)}%)`;
}

function renderSiteAlerts(alerts) {
  const el = document.getElementById("siteAlerts");
  const rows = alerts || [];
  el.textContent = rows.length
    ? rows
        .map((item) => {
          const name = SITE_NAMES[item.site] || item.name || item.site;
          const reason = item.fail_label || FAIL_LABELS[item.fail_reason] || "抓取失败";
          const reuse =
            item.reuse === "same_period"
              ? "同期间沿用上次名单"
              : "新年号尚无名单可沿用";
          return `${name} 连续 ${item.fail_streak} 期没抓到（${reason}），${reuse}`;
        })
        .join("；")
    : "";
}

function renderBacktest(snapshot, errorText) {
  const meta = document.getElementById("backtestMeta");
  const body = document.getElementById("backtestBody");
  const note = document.getElementById("backtestNote");
  const lianEl = document.getElementById("backtestLian");
  const lianBody = document.getElementById("backtestLianBody");
  const yearMeta = document.getElementById("backtestYearMeta");
  const yearBody = document.getElementById("backtestYearBody");
  if (!snapshot) {
    meta.textContent = errorText
      ? `公式对照这次没算成：${errorText}`
      : "还没有对照。新开奖写入后，点一次「刷新分析」就会算出。";
    body.innerHTML = "";
    lianEl.textContent = "";
    lianBody.innerHTML = "";
    yearMeta.textContent = "";
    yearBody.innerHTML = "";
    note.textContent = "";
    return;
  }
  const baoBase = ((snapshot.bao_baseline || 0) * 100).toFixed(1);
  meta.textContent =
    `${snapshot.from_period}–${snapshot.through_period} 期，共 ${snapshot.n} 期` +
    (snapshot.saved_at ? ` · ${snapshot.saved_at} 更新` : "") +
    ` · 随机基准 特码 8.3% / 单肖 ${baoBase}%。号码先验按所挑生肖占几个号计算。`;
  body.innerHTML = (snapshot.rows || [])
    .map(
      (row) => `<tr>
        <td>${escapeHTML(row.label)}</td>
        <td>${pct(row.tema_hits, row.n)}</td>
        <td>${pct(row.bao_hits, row.n)}</td>
        <td>${expText(row.bao_expected, row.n)}</td>
      </tr>`
    )
    .join("");
  const lian = snapshot.lian || [];
  lianEl.textContent = lian.length
    ? "连肖要整组都出现才算中。线上已把当年肖放在第一位。表里的旧公式是改之前的排名，锁当年肖是对照。"
    : "";
  lianBody.innerHTML = lian
    .map(
      (item) => `<tr>
        <td>${escapeHTML(item.label)}</td>
        <td>${pct(item.hits, item.n)}</td>
        <td>${expText(item.expected, item.n)}</td>
      </tr>`
    )
    .join("");
  const split = (snapshot.year_prior && snapshot.year_prior.by_year) || [];
  yearMeta.textContent = split.length
    ? "按开奖日的生肖年切开，用来看旧公式和当年肖差多少。不拿某一期的中没中改回旧公式。"
    : "";
  yearBody.innerHTML = split
    .map(
      (item) => `<tr>
        <td>${item.year} ${escapeHTML(item.zodiac || "")}</td>
        <td>${item.n}</td>
        <td>${item.current_bao}/${item.n}</td>
        <td>${item.year_bao}/${item.n}</td>
        <td>${item.current_lian3}/${item.n}</td>
        <td>${item.year_lian3}/${item.n}</td>
        <td>${item.current_lian5}/${item.n}</td>
        <td>${item.year_lian5}/${item.n}</td>
      </tr>`
    )
    .join("");
  const tips = snapshot.tema_tips || {};
  const cons = snapshot.consensus;
  const consText = cons
    ? ` 共识行只算包肖：资料只认至少 ${cons.min_sites} 个启用站同推的肖，有名单 ${cons.periods_with_tips} 期，` +
      `有同推 ${cons.periods_agreed} 期；` +
      cons.variants
        .map(
          (v) =>
            `热度 ${v.hot_weight} 时资料改动推荐 ${v.changed} 期（共识中 ${v.changed_hits}，不加资料中 ${v.changed_hits_without_tip}）`
        )
        .join("，") +
      "。"
    : "";
  const yearNote = (snapshot.year_prior && snapshot.year_prior.note) || "";
  const errorNote = errorText ? `这次没重算：${errorText} ` : "";
  note.textContent = `${errorNote}${yearNote}${yearNote ? " " : ""}${tips.note || ""}${consText}`;
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
  syncToggle("drawsBody");
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
    const lian3 = groupZodiacs(result.recommend.lian3).join("");
    const notes = [];
    if (result.backtest_error) notes.push(`公式对照没更新：${result.backtest_error}`);
    if (result.live_error) notes.push("实时开奖暂时无效，已用库里的开奖继续");
    if (result.history_error || result.history_light_error) notes.push("历史页暂时连不上");
    const extra = notes.length ? `（${notes.join("；")}）` : "";
    const lianText = lian3 ? ` / 三连肖「${lian3}」` : "";
    setStatus(`完成：${result.recommend.period}期 单肖「${bao}」${lianText} / 特码「${tema}」${extra}`);
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
    setStatus("请先选择单肖和特码是中还是没中", true);
    return;
  }
  const recorded =
    settleRecorded &&
    (settleRecorded.bao !== null || settleRecorded.tema !== null);
  if (recorded) {
    const replace = await askNotice({
      title: "本期已经录入过",
      text: `${settlePeriod}期已有记录：单肖${hitWord(settleRecorded.bao)}，特码${hitWord(settleRecorded.tema)}。\n是否用这次的结果替换？替换后只保留最新一次。`,
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
    const summary = `${settlePeriod}期：单肖${bao ? "中" : "没中"}，特码${tema ? "中" : "没中"}`;
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
