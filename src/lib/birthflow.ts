// 출생 세대가 학교를 거쳐 대학 문으로 걸어간다: 가로축은 나이(왼쪽 0살 → 오른쪽 19살 대학 입학)이고 학교 구간은 고정.
// 막대 하나가 한 해에 태어난 아이들(높이 = 출생아 수). 해가 갈수록 막대가 같은 속력으로 오른쪽으로 한 칸씩 걸어가
// 미취학 → 초등 → 중학 → 고등 구간을 지나 맨 오른쪽 '대학 입학' 칸에 들어선다. 그 칸에서만 입학 자리(지금 입학 규모)와
// 그해 입학자(실측)·입학 수요(추계)를 견주어 빈 자리를 그린다. 출생아와 입학자는 단위가 달라(재수생·성인·유학생) 대학 칸에서만 비교한다.
// 학교 단계: 만 6세 다음 해 3월 초등 입학 → 7살 초1 … 12살 초6, 13~15 중학, 16~18 고등, 19 대학 입학(lag).
import { fmt, tick } from "./format";
import { el, legend, makeTooltip, ttRow, placeTooltip, niceTicks } from "./charts";
import { makePlayer } from "./player";
import { people } from "./profile";

export interface BirthFlowSpec {
  type: "birthflow";
  born: number[]; // 출생연도 (이어진 해)
  births: number[]; // 출생아 수
  estFrom?: number; // 이 출생연도부터 출생아가 추정치
  landing: number[]; // born[i] + lag 년의 입학자(실측) 또는 입학 수요(추계)
  actualTo: number; // 이 입학 연도까지 landing은 실제 입학자
  lag: number; // 출생 → 대학 입학 (19)
  cap: number; // 지금 입학 규모
  capLabel?: string;
  start?: number; // 처음 보여 줄 해 (기본: actualTo)
  marks?: number[]; // 이름표를 달 출생연도 (나·자녀가 없을 때)
  speed?: number; // 재생 때 1년에 걸리는 ms
  height?: number;
  me?: boolean; // 나·자녀 출생연도 막대에 이름표
  /** 있으면 그림 아래에 같은 해의 학교 단계 카드(학생 수·학교 수·학급당 학생 수)를 붙여 함께 움직인다 */
  schools?: SchoolStage[];
}
export interface SchoolStage {
  key: "ele" | "mid" | "high";
  students: Record<string, number>; // 실측 + 추계(기준)
  schools: Record<string, number>; // 실측만
  classes: Record<string, number>; // 실측만
  lastActual: number;
}

type Stage = { key: string; name: string; short: string; color: string; from: number; to: number };

export function renderBirthFlow(host: HTMLElement, spec: BirthFlowSpec) {
  host.innerHTML = "";
  const { born, births, landing, lag, cap } = spec;
  const n = born.length;
  const W = Math.max(host.clientWidth, 280);
  const narrow = W < 520;
  const H = spec.height ?? 360;
  const STAGES: Stage[] = [
    { key: "pre", name: "미취학", short: "미취학", color: "var(--text-muted)", from: 0, to: 6 },
    { key: "ele", name: "초등", short: "초", color: "var(--series-1)", from: 7, to: 12 },
    { key: "mid", name: "중학", short: "중", color: "var(--series-2)", from: 13, to: 15 },
    { key: "high", name: "고등", short: "고", color: "var(--series-3)", from: 16, to: lag - 1 },
    { key: "univ", name: "대학 입학", short: "대학", color: "var(--text-primary)", from: lag, to: lag },
  ];
  const stageOf = (age: number) => STAGES.find((s) => age >= s.from && age <= s.to) ?? (age < 0 ? STAGES[0] : null);
  const grade = (age: number) => {
    const s = stageOf(age);
    if (!s) return "입학 이후";
    return s.key === "ele" || s.key === "mid" || s.key === "high" ? `${s.short}${age - s.from + 1}` : s.name;
  };
  const ppl = (spec.me ? people() : []).filter((pp) => born.includes(pp.born));

  legend(host, [
    { name: "막대 = 한 해 출생아 수 (색은 학교)", color: "var(--text-muted)", kind: "rect" },
    { name: "대학 입학자·입학 수요", color: "var(--text-primary)", kind: "line" },
    { name: `${spec.capLabel ?? "입학 자리(지금 규모)"} ${tick(cap, "man")}`, color: "var(--critical)", kind: "dash" },
    { name: "빈 자리", color: "var(--critical)", kind: "rect" },
  ]);
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);

  const m = { t: narrow ? 76 : 62, r: 10, b: 56, l: narrow ? 40 : 48 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const a0 = -0.5,
    a1 = lag + 0.5;
  const X = (age: number) => m.l + ((age - a0) / (a1 - a0)) * pw;
  const slot = pw / (a1 - a0);
  const bw = Math.max(3, slot * 0.72);
  const maxV = Math.max(...births, ...landing, cap);
  const yt = niceTicks(0, maxV, 4);
  const top = yt[yt.length - 1];
  const Y = (v: number) => m.t + ph - (v / top) * ph;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  const tt = makeTooltip(box);
  const clipId = `bf-clip-${Math.random().toString(36).slice(2, 8)}`;
  const defs = el("defs", {}, svg);
  const cp = el("clipPath", { id: clipId }, defs);
  el("rect", { x: m.l, y: 0, width: pw, height: H }, cp);

  // 학교 구간 (고정): 옅은 바탕 + 위쪽 이름
  for (const s of STAGES) {
    const xa = X(s.from - 0.5),
      xb = X(s.to + 0.5);
    const r = el("rect", { x: xa, y: m.t - 22, width: xb - xa, height: ph + 22, fill: s.color }, svg);
    r.setAttribute("fill-opacity", s.key === "univ" ? "0.07" : "0.05");
    if (s.from > 0) el("line", { x1: xa, x2: xa, y1: m.t - 22, y2: m.t + ph, stroke: s.color, "stroke-opacity": 0.35, "stroke-width": 1 }, svg);
    // 맨 오른쪽 좁은 대학 칸은 오른쪽 끝에 붙여 잘리지 않게
    const edge = s.key === "univ" && narrow;
    const t = el("text", { x: edge ? xb : (xa + xb) / 2, y: m.t - 8, "text-anchor": edge ? "end" : "middle", class: "label-strong" }, svg);
    t.style.fill = s.color;
    t.textContent = narrow || s.to - s.from < 2 ? s.short : s.name;
  }
  for (const v of yt) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(v), y2: Y(v), class: "grid-line" }, svg);
    const t = el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, svg);
    t.textContent = tick(v, "man");
  }
  // 나이 눈금: 각 단계 시작 나이
  for (const a of [0, 7, 13, 16, lag]) {
    const t = el("text", { x: X(a), y: m.t + ph + 32, "text-anchor": "middle" }, svg);
    t.textContent = a === 0 ? "0살" : `${a}살`;
  }
  el("line", { x1: m.l, x2: m.l + pw, y1: Y(0), y2: Y(0), class: "axis-line" }, svg);

  // 막대 (나이 = 해 − 출생연도 자리로 걸어감)
  const gBar = el("g", { "clip-path": `url(#${clipId})` }, svg);
  const est = (i: number) => spec.estFrom != null && born[i] >= spec.estFrom;
  const bars = born.map((_, i) => el("rect", { width: bw, y: Y(births[i]), height: Math.max(0, Y(0) - Y(births[i])), rx: Math.min(2, bw / 3) }, gBar));
  // 막대 아래 출생연도 (막대와 함께 움직임)
  const yrs = born.map((b) => {
    const t = el("text", { y: m.t + ph + 14, "text-anchor": "middle", class: "label" }, gBar);
    t.textContent = narrow ? `'${String(b).slice(2)}` : `${b}`;
    return t;
  });
  // 아직 태어나지 않은 칸 (데이터 끝 이후 출생)
  const unbornZ = el("rect", { y: m.t, height: ph, fill: "var(--surface-2)" }, svg);
  const unbornT = el("text", { y: m.t + ph / 2, "text-anchor": "middle", class: "label" }, svg);

  // 대학 칸: 입학 자리 선, 입학자·수요 선, 빈 자리 상자
  const ux0 = X(lag - 0.5),
    ux1 = X(lag + 0.5);
  const capY = Y(cap);
  const gapBox = el("rect", { x: ux0 + 3, width: ux1 - ux0 - 6, fill: "var(--critical)", "fill-opacity": 0.14, stroke: "var(--critical)", "stroke-width": 1, "stroke-dasharray": "3 2" }, svg);
  el("line", { x1: ux0, x2: ux1, y1: capY, y2: capY, stroke: "var(--critical)", "stroke-width": 2, "stroke-dasharray": "5 3" }, svg);
  const landLn = el("line", { x1: ux0 - 2, x2: ux1 + 2, stroke: "var(--text-primary)", "stroke-width": 2.5 }, svg);
  const capT = el("text", { x: ux0 - 4, y: capY + 4, "text-anchor": "end", class: "label halo" }, svg);
  capT.style.fill = "var(--critical)";
  capT.textContent = narrow ? `자리 ${tick(cap, "man")}` : `입학 자리 ${tick(cap, "man")}`;
  const landT = el("text", { x: ux0 - 4, "text-anchor": "end", class: "label-strong halo" }, svg);

  // 오른쪽 위: 고른 해와 그해 입학 요약
  const yrTxt = el("text", { x: m.l, y: 18, class: "label-strong" }, svg);
  yrTxt.style.fontSize = narrow ? "16px" : "18px";
  const sumTxt = el("text", narrow ? { x: m.l, y: 38, class: "label" } : { x: m.l + pw, y: 18, "text-anchor": "end", class: "label" }, svg);

  // 이름표 (나·자녀, 없으면 기본)
  const markYears = ppl.length ? ppl.map((pp) => pp.born) : spec.marks ?? [];
  const marks = markYears
    .map((b) => {
      const i = born.indexOf(b);
      const pp = ppl.find((q) => q.born === b);
      const g = el("g", {}, svg);
      const ln = el("line", { stroke: pp?.color ?? "var(--text-secondary)", "stroke-width": 1 }, g);
      const t = el("text", { "text-anchor": "middle", class: "coh-gen-name halo" }, g);
      if (pp) t.style.fill = pp.color;
      return { i, b, pp, g, ln, t };
    })
    .filter((mk) => mk.i >= 0);

  const y0 = born[0] + lag; // 그림이 0~19살로 꽉 차는 첫 해
  const years = Array.from({ length: n }, (_, i) => y0 + i); // 마지막 해 = 마지막 출생연도가 대학 입학
  let curY = spec.start ?? spec.actualTo;

  // t: 소수 해 (2026.4 = 2026과 2027 사이). 막대는 같은 속력으로 걸어간다
  const draw = (t: number) => {
    curY = t;
    const Yi = Math.floor(t + 1e-9);
    for (let i = 0; i < n; i++) {
      const age = t - born[i];
      const cx = X(age);
      const r = bars[i];
      if (age < -0.6 || age > lag + 0.6) {
        r.setAttribute("visibility", "hidden");
        yrs[i].setAttribute("visibility", "hidden");
        continue;
      }
      r.removeAttribute("visibility");
      r.setAttribute("x", (cx - bw / 2).toFixed(1));
      const s = stageOf(Math.round(age)) ?? STAGES[STAGES.length - 1];
      r.setAttribute("fill", s.color);
      r.setAttribute("fill-opacity", s.key === "pre" ? "0.4" : est(i) ? "0.55" : "1");
      const yt = yrs[i];
      // 좁은 화면은 5년 단위와 대학 칸만 연도를 단다
      const showYr = !narrow || born[i] % 5 === 0 || Math.round(age) === lag;
      yt.setAttribute("x", cx.toFixed(1));
      if (showYr) yt.removeAttribute("visibility");
      else yt.setAttribute("visibility", "hidden");
      yt.style.fill = Math.round(age) === lag ? "var(--text-primary)" : "";
    }
    // 아직 태어나지 않은 칸: 마지막 출생연도보다 어린 나이
    const youngest = t - born[n - 1]; // 마지막 세대의 나이
    if (youngest > 0.5) {
      const xe = X(youngest - 0.5);
      unbornZ.setAttribute("x", m.l.toFixed(1));
      unbornZ.setAttribute("width", Math.max(0, xe - m.l).toFixed(1));
      unbornZ.removeAttribute("visibility");
      unbornT.setAttribute("x", ((m.l + xe) / 2).toFixed(1));
      unbornT.textContent = xe - m.l > 90 ? `${born[n - 1] + 1}년생 이후 (아직)` : "";
      unbornT.removeAttribute("visibility");
    } else {
      unbornZ.setAttribute("visibility", "hidden");
      unbornT.setAttribute("visibility", "hidden");
    }
    // 대학 칸에 선 세대: 칸 가운데로 들어올수록 입학자 선·빈 자리가 또렷해진다
    const ui = born.indexOf(Math.round(t) - lag);
    if (ui >= 0) {
      const near = Math.max(0, 1 - Math.abs(t - lag - born[ui]) * 2); // 칸 가운데 ±0.5년에서 0→1→0
      const land = landing[ui];
      const ly = Y(land);
      landLn.setAttribute("y1", ly.toFixed(1));
      landLn.setAttribute("y2", ly.toFixed(1));
      landLn.setAttribute("opacity", near.toFixed(2));
      const Yu = born[ui] + lag;
      const real = Yu <= spec.actualTo;
      landT.setAttribute("y", (Math.abs(ly - capY) < 14 ? Math.max(ly, capY) + 16 : ly + 4).toFixed(1));
      landT.textContent = `${real ? "입학자" : "수요"} ${tick(land, "man")}`;
      landT.setAttribute("opacity", near.toFixed(2));
      if (ly > capY + 0.5) {
        gapBox.setAttribute("y", capY.toFixed(1));
        gapBox.setAttribute("height", (ly - capY).toFixed(1));
        gapBox.setAttribute("opacity", near.toFixed(2));
        gapBox.removeAttribute("visibility");
      } else gapBox.setAttribute("visibility", "hidden");
      const empty = cap - land;
      sumTxt.textContent = `${born[ui]}년생 입학 · ${real ? "실제 입학자" : "입학 수요"} ${tick(land, "man")}${empty > 0 && !real ? ` · 빈 자리 ${tick(empty, "man")}` : ""}`;
      (sumTxt as SVGElement).style.fill = !real && empty > 0 ? "var(--critical)" : "";
    }
    yrTxt.textContent = `${Yi}년`;
    if (Yi !== panelY) paintPanel(Yi);
    for (const mk of marks) {
      const age = t - mk.b;
      if (age < -0.4 || age > lag + 0.4) {
        mk.g.setAttribute("visibility", "hidden");
        continue;
      }
      mk.g.removeAttribute("visibility");
      const cx = X(age);
      const yb = Math.min(Y(births[mk.i]), Math.round(age) === lag ? Y(Math.max(landing[mk.i], cap)) : Infinity);
      mk.ln.setAttribute("x1", cx.toFixed(1));
      mk.ln.setAttribute("x2", cx.toFixed(1));
      mk.ln.setAttribute("y1", (yb - 12).toFixed(1));
      mk.ln.setAttribute("y2", (yb - 2).toFixed(1));
      mk.t.setAttribute("y", (yb - 16).toFixed(1));
      const nm = mk.pp ? (mk.pp.kid ? "아이" : "나") : `${mk.b}년생`;
      const a = Math.round(age);
      mk.t.textContent = a < 0 ? nm : `${nm} · ${a === lag ? "대학 입학" : a < 7 ? `${a}살` : grade(a)}`;
      let w = 80;
      try { w = mk.t.getComputedTextLength() || w; } catch {}
      mk.t.setAttribute("x", Math.max(m.l + w / 2 + 2, Math.min(m.l + pw - w / 2 - 2, cx)).toFixed(1));
    }
    svg.setAttribute("aria-label", `${Yi}년: ${Yi - lag}년생 대학 입학, ${Yi - 18}~${Yi - 16}년생 고등, ${Yi - 15}~${Yi - 13}년생 중학, ${Yi - 12}~${Yi - 7}년생 초등. 막대는 출생아 수.`);
  };

  // 툴팁: 가장 가까운 막대
  const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = e.clientX - r.left;
    const age = a0 + ((px - m.l) / pw) * (a1 - a0);
    const i = Math.round(curY - age) - born[0];
    if (i < 0 || i >= n) return void (tt.style.opacity = "0");
    const b = born[i],
      Yu = b + lag,
      ag = Math.round(curY - b);
    tt.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tt-title";
    title.textContent = `${b}년생 · ${Math.floor(curY)}년에 ${ag === lag ? "대학 입학" : ag < 7 ? `${ag}살` : grade(ag)}`;
    tt.appendChild(title);
    ttRow(tt, "var(--text-muted)", est(i) ? "출생아 (추정)" : "출생아", fmt(births[i], "int"));
    ttRow(tt, "var(--series-1)", "초등 입학", `${b + 7}년`);
    ttRow(tt, "var(--series-2)", "중학 입학", `${b + 13}년`);
    ttRow(tt, "var(--series-3)", "고등 입학", `${b + 16}년`);
    ttRow(tt, "var(--text-primary)", `대학 ${Yu <= spec.actualTo ? "입학자" : "입학 수요"} (${Yu})`, fmt(landing[i], "int"));
    if (Yu > spec.actualTo) ttRow(tt, "var(--critical)", "빈 자리", fmt(Math.max(0, cap - landing[i]), "int"));
    placeTooltip(tt, box, px, e.clientY - r.top);
  });
  hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));

  const ctl = document.createElement("div");
  host.appendChild(ctl);

  // ---- 학교 단계 카드: 고른 해의 초·중·고 학생 수·학교 수·학급당 학생 수 + 대학 입학
  let panelY = NaN;
  const panel = document.createElement("div");
  panel.className = "bf-panel";
  const foot = document.createElement("p");
  foot.className = "bf-foot";
  if (spec.schools?.length) host.append(panel, foot);
  const cards = new Map<string, HTMLElement>();
  for (const s of STAGES.filter((q) => q.key !== "pre")) {
    if (s.key !== "univ" && !spec.schools?.some((q) => q.key === s.key)) continue;
    const c = document.createElement("div");
    c.className = "bf-card";
    c.style.setProperty("--c", s.color);
    panel.appendChild(c);
    cards.set(s.key, c);
  }
  const ref = spec.actualTo; // 견줄 기준 해 (지금)
  const lastOf = (rec: Record<string, number>, y: number) => {
    let k = y;
    while (k > 1900 && rec[k] == null) k--;
    return { y: k, v: rec[k] };
  };
  const chg = (a: number, b: number) => {
    const r = a / b - 1;
    if (Math.abs(r) < 0.005) return `<span class="bf-chg">${ref}년과 비슷</span>`;
    return `<span class="bf-chg ${r < 0 ? "down" : "up"}">${ref}년보다 ${r > 0 ? "+" : "−"}${Math.round(Math.abs(r) * 100)}%</span>`;
  };
  const paintPanel = (Yr: number) => {
    panelY = Yr;
    if (!spec.schools?.length) return;
    let anyProj = Yr > spec.schools[0].lastActual;
    for (const st of spec.schools) {
      const c = cards.get(st.key)!;
      const s = STAGES.find((q) => q.key === st.key)!;
      const range = `${Yr - s.to}~${Yr - s.from}년생`;
      const v = st.students[Yr];
      if (v == null) {
        c.innerHTML = `<div class="bf-h"><b>${s.name}</b><span>${range}</span></div><div class="bf-v">–</div><div class="bf-r">추계 범위 밖</div>`;
        continue;
      }
      const proj = Yr > st.lastActual;
      anyProj ||= proj;
      const sc = proj ? lastOf(st.schools, st.lastActual) : lastOf(st.schools, Yr);
      const cl = proj ? lastOf(st.classes, st.lastActual) : lastOf(st.classes, Yr);
      const star = proj ? "*" : "";
      c.innerHTML =
        `<div class="bf-h"><b>${s.name}</b><span>${range}</span></div>` +
        `<div class="bf-v">${fmt(v, "man")}<small>명${proj ? " (추계)" : ""}</small></div>` +
        (Yr !== ref && st.students[ref] ? `<div class="bf-r">${chg(v, st.students[ref])}</div>` : `<div class="bf-r"><span class="bf-chg">지금</span></div>`) +
        `<dl><dt>학교</dt><dd>${fmt(sc.v, "int")}개${proj ? `<small> (${sc.y})</small>` : ""}</dd>` +
        `<dt>학교당 학생</dt><dd>${fmt(Math.round(v / sc.v), "int")}명${star}</dd>` +
        `<dt>학급당 학생</dt><dd>${(v / cl.v).toFixed(1)}명${star}</dd></dl>`;
    }
    const cu = cards.get("univ");
    if (cu) {
      const i = born.indexOf(Yr - lag);
      const s = STAGES.find((q) => q.key === "univ")!;
      if (i < 0) cu.innerHTML = `<div class="bf-h"><b>${s.name}</b></div><div class="bf-v">–</div>`;
      else {
        const land = landing[i];
        const real = Yr <= spec.actualTo;
        cu.innerHTML =
          `<div class="bf-h"><b>${s.name}</b><span>${born[i]}년생</span></div>` +
          `<div class="bf-v">${fmt(land, "man")}<small>명${real ? "" : " (수요)"}</small></div>` +
          (Yr !== ref ? `<div class="bf-r">${chg(land, cap)}</div>` : `<div class="bf-r"><span class="bf-chg">지금</span></div>`) +
          `<dl><dt>입학 자리</dt><dd>${fmt(cap, "man")}명</dd>` +
          `<dt>채움률</dt><dd>${fmt(Math.min(1, land / cap), "pct")}</dd>` +
          `<dt>빈 자리</dt><dd${land < cap ? ' class="neg"' : ""}>${land < cap ? `${fmt(cap - land, "man")}명` : "없음"}</dd></dl>`;
      }
    }
    const la = spec.schools[0].lastActual;
    foot.textContent = anyProj
      ? `* ${la + 1}년부터 학생 수는 기준 추계이고, 학교 수·학급 수는 ${la}년 그대로라고 보고 나눈 값입니다. 학교가 문을 닫거나 학급을 줄이면 실제 학급당 학생 수는 이보다 큽니다.`
      : `학생·학교·학급 수는 교육기본통계 실측입니다. 대학 입학 자리는 ${ref}년 입학자 수입니다.`;
  };
  const startIdx = Math.max(0, years.indexOf(spec.start ?? spec.actualTo));
  const keep = host.dataset.frame != null ? Number(host.dataset.frame) : startIdx;
  const projIdx = years.indexOf(spec.actualTo + 1);
  makePlayer(ctl, years, (i) => ((host.dataset.frame = String(i)), draw(years[i])), {
    start: keep,
    speed: spec.speed ?? 900,
    projFrom: projIdx > 0 ? projIdx : undefined,
    label: (i) => `${years[i]}년`,
    bubble: true,
    smooth: (ti) => ((host.dataset.frame = String(Math.floor(ti))), draw(y0 + ti)),
  });
  draw(years[keep]);
}
