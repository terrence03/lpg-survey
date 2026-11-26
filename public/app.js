"use strict";
(() => {
  // Relative by default so the site also works under a sub-path such as /lpg-survey/.
  const API = (window.LPG_API_BASE || ".").replace(/\/$/, "");
  const STORE = "lpg-survey-v1";
  const OUTBOX = "lpg-outbox-v1";
  const $ = (id) => document.getElementById(id);
  const body = $("body"), scroller = $("scroller"), foot = $("foot"), progress = $("progress");
  const topTitle = $("topTitle"), topStep = $("topStep"), toast = $("toast");

  let CFG = null; // questions.json
  let S = null;   // { sid, view: home|survey|checkin-done|survey-done, step, a:{}, t:{}, sending }
  let err = null; // { card, msg }

  // ---------- storage (best effort) ----------
  const load = (k, d) => { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };
  const persist = () => save(STORE, S);
  const uuid = () => (crypto.randomUUID ? crypto.randomUUID()
    : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) => (c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (c / 4)))).toString(16)));
  const fresh = () => ({ sid: uuid(), view: "home", step: 0, a: {}, t: {} });

  // ---------- network ----------
  async function post(path, data, timeoutMs = 10000) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const r = await fetch(API + path, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data), signal: ctl.signal, keepalive: true,
      });
      if (r.status >= 500) throw new Error("server " + r.status);
      return r;
    } finally { clearTimeout(timer); }
  }
  // Failed sends are queued on the phone and retried later.
  function queue(path, data) { const q = load(OUTBOX, []); q.push({ path, data }); save(OUTBOX, q); }
  async function flush() {
    const q = load(OUTBOX, []);
    if (!q.length) return;
    const left = [];
    for (const item of q) { try { await post(item.path, item.data); } catch { left.push(item); } }
    save(OUTBOX, left);
  }
  async function send(path, data) {
    try { await post(path, data); return true; } catch { queue(path, data); return false; }
  }

  // ---------- question logic ----------
  const Q = (k) => CFG.questions[k];
  const childrenOf = (k) => Object.keys(CFG.questions).filter((c) => Q(c).parent === k);
  const has = (k, v) => [].concat(S.a[k] || []).includes(v);
  function visible(k) {
    const d = Q(k);
    if (!d.show) return true;
    if (d.parent && !visible(d.parent)) return false;
    const s = d.show, v = S.a[s.q];
    if (s.eq) return v === s.eq;
    if (s.in) return s.in.includes(v);
    if (s.has) return has(s.q, s.has);
    return true;
  }
  const answered = (k) => { const v = S.a[k]; return Array.isArray(v) ? v.length > 0 : !!v; };
  const otherOn = (k) => { const d = Q(k); return d.other && has(k, d.other); };

  // Same required-answer rules as the original Streamlit app, split by step.
  const RULES = [
    () => null,
    () => ["q1", "q2", "q3"].find((k) => !answered(k)) && miss(["q1", "q2", "q3"].find((k) => !answered(k))),
    () => ["gender", "age"].find((k) => !answered(k)) && miss(["gender", "age"].find((k) => !answered(k))),
    () => {
      if (!answered("lpg_usage")) return miss("lpg_usage");
      if (S.a.lpg_usage === "1") {
        if (!answered("contract")) return miss("contract", "lpg_usage");
        if (S.a.contract === "2" && !answered("contract_no")) return miss("contract_no", "lpg_usage");
      }
      if (!answered("contract_aware")) return miss("contract_aware");
      if (S.a.contract_aware === "4" && !answered("contract_aware_no")) return miss("contract_aware_no", "contract_aware");
      if (!answered("contract_willing")) return miss("contract_willing");
      if (S.a.contract_willing === "2" && !answered("contract_willing_no")) return miss("contract_willing_no", "contract_willing");
      return null;
    },
    () => {
      if (!answered("policy_info")) return miss("policy_info");
      if (has("policy_info", "7")) return answered("policy_info_network") ? null : miss("policy_info_network", "policy_info");
      if (has("policy_info", "8")) return answered("policy_info_advertising") ? null : miss("policy_info_advertising", "policy_info");
      return null;
    },
  ];
  function miss(k, card) { return { card: card || k, msg: `請回答「${Q(k).no}　${Q(k).question.replace(/[（(]可複選[)）]/, "")}」` }; }

  function payload() {
    const answers = {}, texts = {};
    for (const k of Object.keys(CFG.questions)) {
      if (!visible(k) || !answered(k)) continue;
      answers[k] = S.a[k];
      const d = Q(k);
      if (otherOn(k) && (S.t[d.other_key] || "").trim()) texts[d.other_key] = S.t[d.other_key].trim();
    }
    return { sid: S.sid, answers, texts };
  }

  // ---------- rendering ----------
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function optionsHTML(k) {
    const d = Q(k), multi = d.type === "multi", v = S.a[k], quiz = d.answer;
    const kind = d.layout === "chips" ? " chips" : quiz ? " quiz" : multi && Object.keys(d.options).length > 4 ? " multi-list" : "";
    let h = `<div class="opts${kind}" role="${multi ? "group" : "radiogroup"}" aria-labelledby="qt_${k}">`;
    for (const [n, label] of Object.entries(d.options)) {
      const sel = multi ? has(k, n) : v === n;
      let cls = "opt" + (multi ? " multi" : "") + (sel ? " sel" : "");
      if (quiz && v) cls += n === d.answer ? " right" : sel ? " wrong" : "";
      h += `<label class="${cls}"><input type="${multi ? "checkbox" : "radio"}" name="${k}" value="${n}" id="${k}_${n}"${sel ? " checked" : ""}><span class="mk"></span><span>${esc(label)}</span></label>`;
    }
    h += "</div>";
    if (quiz && v) h += v === d.answer ? `<div class="fb ok">正確！</div>` : `<div class="fb no">正確答案為 ${esc(d.options[d.answer])}</div>`;
    if (otherOn(k)) h += `<input class="txt" id="${d.other_key}" data-text="${d.other_key}" placeholder="請輸入" aria-label="${esc(d.other_question || "其他")}" value="${esc(S.t[d.other_key] || "")}">`;
    return h;
  }
  function questionHTML(k, nested) {
    const d = Q(k);
    let h = `<div class="${nested ? "child" : "q" + (err && err.card === k ? " err" : "")}" id="card_${k}">`;
    h += `<div class="no">${esc(d.no)}</div><div class="qt" id="qt_${k}">${esc(d.question.replace(/\s*[（(]可複選[)）]/, ""))}${d.type === "multi" ? ' <span class="hint">（可複選）</span>' : ""}</div>`;
    h += optionsHTML(k);
    for (const c of childrenOf(k)) if (visible(c)) h += questionHTML(c, true);
    if (!nested && err && err.card === k) h += `<div class="em" role="alert">${esc(err.msg)}</div>`;
    return h + "</div>";
  }

  function render() {
    const v = S.view, steps = CFG.steps;
    progress.hidden = v !== "survey";
    topStep.textContent = "";
    if (v === "home") {
      topTitle.textContent = "宣導活動";
      body.innerHTML = `<div class="home"><div class="hero"><img src="img/mascot.webp" width="170" height="166" alt="LPG 宣導吉祥物"></div>
        <div class="home-text"><h1 class="title">家用液化石油氣<br>供氣定型化契約宣導活動</h1>
        <section class="gifts" aria-labelledby="giftsH">
          <h2 class="gifts-h" id="giftsH">活動好禮</h2>
          <ul>
            <li>完成打卡，即可獲得<b>小禮物</b>乙份</li>
            <li>完成活動問卷，即可獲得<b>精美實用禮</b>乙份</li>
          </ul>
          <p class="gifts-note">※ 宣導品數量有限，送完為止！</p>
        </section></div></div>`;
      foot.className = "inner foot-in col";
      foot.innerHTML = `<button class="btn pri" data-act="start">填寫問卷獲得精美實用禮</button><button class="btn sec" data-act="checkin">僅打卡</button>`;
    } else if (v === "survey") {
      const st = steps[S.step];
      topTitle.textContent = "「家用液化石油氣供氣定型化契約」問卷";
      topStep.textContent = `${S.step + 1} / ${steps.length}`;
      progress.innerHTML = steps.map((_, i) => `<i class="${i <= S.step ? "on" : ""}"></i>`).join("");
      let h = `<h1 class="title">${esc(st.title)}</h1>`;
      if (st.hint) h += `<p class="sub">${esc(st.hint)}</p>`;
      if (st.video) {
        const id = videoId(CFG.video);
        h += `<p class="sub">感謝您參與本次宣導活動，請<b>先觀看影片再填寫本問卷</b>，完成後即可獲取精美小禮物。</p>
          <button type="button" class="video" id="video" data-act="play" style="background-image:url('https://i.ytimg.com/vi/${id}/hqdefault.jpg')" aria-label="播放宣導影片"><span class="play"></span></button>
          <p class="sub" style="margin-top:12px">看完影片後，按下方「開始作答」。</p>`;
      }
      h += st.questions.map((k) => questionHTML(k)).join("");
      body.innerHTML = h;
      const last = S.step === steps.length - 1;
      foot.className = "inner foot-in";
      foot.innerHTML = (S.step > 0 ? `<button class="btn sec" data-act="prev">上一步</button>` : "")
        + `<button class="btn pri" data-act="next"${S.sending ? " disabled" : ""}>${S.sending ? "送出中…" : S.step === 0 ? "開始作答" : last ? "送出" : "下一步"}</button>`;
    } else {
      const survey = v === "survey-done";
      topTitle.textContent = survey ? "問卷完成" : "打卡完成";
      body.innerHTML = `<div class="done"><p class="slogan">購買瓦斯簽契約，消費權益有保障</p>
        <img src="img/${survey ? "survey_complete" : "checkin_complete"}.webp" alt="${survey ? "問卷完成，請出示此畫面給工作人員領取精美禮物" : "打卡完成，請出示此畫面給工作人員領取小禮物"}"></div>`;
      foot.className = "inner foot-in";
      foot.innerHTML = `<button class="btn sec wide" data-act="home">返回首頁</button>`;
    }
  }
  const videoId = (url) => (url.match(/(?:youtu\.be\/|v=|embed\/)([\w-]{11})/) || [])[1] || "";

  function showToast(msg) {
    toast.textContent = msg; toast.hidden = false;
    clearTimeout(showToast.t); showToast.t = setTimeout(() => (toast.hidden = true), 3500);
  }

  // ---------- navigation (phone back button moves between steps) ----------
  function go(view, step = 0, push = true) {
    S.view = view; S.step = step; err = null; persist(); render(); scroller.scrollTop = 0;
    if (push) history.pushState({ view, step }, "", view === "survey" ? `#step-${step + 1}` : view === "home" ? location.pathname : `#${view}`);
  }
  window.addEventListener("popstate", (e) => {
    const st = e.state;
    if (S.view !== "survey") return; // done pages: back does nothing special
    if (st && st.view === "survey") go("survey", st.step, false);
    else history.pushState({ view: "survey", step: S.step }, "", `#step-${S.step + 1}`);
  });

  // ---------- events ----------
  body.addEventListener("change", (e) => {
    const t = e.target;
    if (!t.name || !CFG.questions[t.name]) return;
    const k = t.name, d = Q(k);
    if (d.type === "multi") {
      const set = new Set(S.a[k] || []);
      t.checked ? set.add(t.value) : set.delete(t.value);
      S.a[k] = Object.keys(d.options).filter((n) => set.has(n));
    } else S.a[k] = t.value;
    if (err && !RULES[S.step]()) err = null;
    persist();
    const y = scroller.scrollTop; render(); scroller.scrollTop = y;
    const el = document.getElementById(`${k}_${t.value}`); if (el) el.focus({ preventScroll: true });
  });
  body.addEventListener("input", (e) => { const k = e.target.dataset.text; if (k) { S.t[k] = e.target.value; persist(); } });

  document.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-act]");
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === "start") {
      send("/api/checkin", { sid: S.sid });
      go("survey", 0);
    } else if (act === "checkin") {
      btn.disabled = true;
      send("/api/checkin", { sid: S.sid });
      go("checkin-done");
    } else if (act === "home") {
      S = fresh(); persist(); go("home");
    } else if (act === "prev") {
      history.back();
    } else if (act === "play") {
      const id = videoId(CFG.video);
      btn.classList.add("playing");
      btn.innerHTML = `<iframe src="https://www.youtube.com/embed/${id}?autoplay=1&playsinline=1&rel=0" title="宣導影片" allow="autoplay; encrypted-media; picture-in-picture; fullscreen" allowfullscreen></iframe>`;
      btn.removeAttribute("data-act");
    } else if (act === "next") {
      const m = RULES[S.step]();
      if (m) {
        err = m; render();
        const card = document.getElementById("card_" + m.card);
        if (card) card.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      if (S.step < CFG.steps.length - 1) return go("survey", S.step + 1);
      S.sending = true; render();
      const ok = await send("/api/survey", payload());
      S.sending = false;
      go("survey-done");
      if (!ok) showToast("網路不穩，稍後自動重新上傳結果");
    }
  });

  window.addEventListener("online", flush);

  // ---------- boot ----------
  async function boot() {
    try {
      CFG = await (await fetch("questions.json")).json();
    } catch {
      body.innerHTML = `<p>題目載入失敗，請重新整理頁面。</p>`;
      return;
    }
    S = load(STORE, null) || fresh();
    if (!S.sid || !S.a) S = fresh();
    S.sending = false;
    if (S.view === "survey") {
      S.step = Math.min(S.step, CFG.steps.length - 1);
      history.replaceState({ view: "survey", step: 0 }, "", "#step-1");
      for (let i = 1; i <= S.step; i++) history.pushState({ view: "survey", step: i }, "", `#step-${i + 1}`);
    } else history.replaceState({ view: S.view, step: 0 }, "", S.view === "home" ? location.pathname : `#${S.view}`);
    render();
    fetch(API + "/api/health").catch(() => {}); // wake the server early
    flush();
  }
  boot();
})();
