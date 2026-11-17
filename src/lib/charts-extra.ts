// 확장 차트: 누적 영역, 산점도(버블), 누적 막대, 막대 레이스, 100칸 와플.
import { fmt, tick, type Fmt } from "./format";
import { el, niceTicks, makeTooltip, ttRow, placeTooltip, legend, revealGroup, shouldAnimate, type Pt } from "./charts";
import { onVisible, tween } from "./anim";
import { makePlayer } from "./player";

// ------------------------------------------------------------------ 누적 영역
export interface AreaSpec {
  type: "area";
  series: { name: string; color: string; data: Pt[] }[]; // 첫 계열이 맨 아래
  percent?: boolean; // 100% 누적
  yFormat?: Fmt;
  projStart?: number;
  height?: number;
  xUnit?: string;
}

export function renderArea(host: HTMLElement, spec: AreaSpec) {
  host.innerHTML = "";
  const H = spec.height ?? 300;
  const W = Math.max(host.clientWidth, 280);
  const yf = spec.yFormat ?? (spec.percent ? "pct" : "int");
  legend(host, spec.series.map((s) => ({ name: s.name, color: s.color, kind: "rect" as const })));
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const narrow = W < 520;
  const m = { t: 12, r: narrow ? 12 : 96, b: 28, l: narrow ? 44 : 56 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const xs = [...new Set(spec.series.flatMap((s) => s.data.map((p) => p[0])))].sort((a, b) => a - b);
  const get = (s: AreaSpec["series"][number], x: number) => s.data.find((p) => p[0] === x)?.[1] ?? 0;
  // 누적
  const stacks = xs.map((x) => {
    const vals = spec.series.map((s) => get(s, x) ?? 0);
    const tot = vals.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    return vals.map((v) => {
      const lo = acc;
      acc += spec.percent ? v / tot : v;
      return [lo, acc];
    });
  });
  const ymax = spec.percent ? 1 : Math.max(...stacks.map((s) => s[s.length - 1][1]));
  const ticks = spec.percent ? [0, 0.25, 0.5, 0.75, 1] : niceTicks(0, ymax, 5);
  const yhi = ticks[ticks.length - 1];
  const x0 = xs[0],
    x1 = xs[xs.length - 1];
  const X = (x: number) => m.l + ((x - x0) / (x1 - x0 || 1)) * pw;
  const Y = (y: number) => m.t + ph - (y / (yhi || 1)) * ph;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  for (const t of ticks) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: t === 0 ? "axis-line" : "grid-line" }, svg);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tick(t, yf);
  }
  const maxTicks = Math.max(2, Math.floor(pw / 64));
  const step = [1, 2, 5, 10, 20, 25, 50].find((s) => (x1 - x0) / s <= maxTicks) ?? 50;
  for (let x = Math.ceil(x0 / step) * step; x <= x1; x += step) {
    const tx = el("text", { x: X(x), y: H - 8, "text-anchor": "middle" }, svg);
    tx.textContent = String(x);
  }
  const anim = shouldAnimate(host);
  const g = revealGroup(svg, m.l, m.t, pw, ph, anim);
  spec.series.forEach((s, si) => {
    const top = xs.map((x, i) => `${X(x)},${Y(stacks[i][si][1])}`);
    const bot = xs.map((x, i) => `${X(x)},${Y(stacks[i][si][0])}`).reverse();
    el("path", { d: `M${top.join("L")}L${bot.join("L")}Z`, fill: s.color, opacity: 0.88, stroke: "var(--surface-1)", "stroke-width": 1.5, "stroke-linejoin": "round" }, g);
  });
  if (spec.projStart != null && spec.projStart < x1) {
    const px = X(spec.projStart);
    el("line", { x1: px, x2: px, y1: m.t, y2: m.t + ph, stroke: "var(--surface-1)", "stroke-width": 1.5, "stroke-dasharray": "4 3" }, svg);
    const t = el("text", { x: px + 6, y: m.t + 14, class: "label-strong" }, svg);
    t.textContent = "추계 →";
  }
  // 오른쪽 직접 라벨
  if (!narrow) {
    const last = stacks[stacks.length - 1];
    let prevY = Infinity;
    spec.series.forEach((s, si) => {
      const [lo, hi] = last[si];
      let y = Y((lo + hi) / 2) + 4;
      if (prevY - y < 14) y = prevY - 14;
      prevY = y;
      const t = el("text", { x: m.l + pw + 8, y, class: "label" }, svg);
      t.textContent = s.name.length > 7 ? s.name.slice(0, 7) + "…" : s.name;
    });
  }
  const cross = el("line", { x1: 0, x2: 0, y1: m.t, y2: m.t + ph, class: "crosshair", opacity: 0 }, svg);
  const tt = makeTooltip(box);
  const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = e.clientX - r.left;
    let bi = 0;
    xs.forEach((x, i) => Math.abs(X(x) - px) < Math.abs(X(xs[bi]) - px) && (bi = i));
    const x = xs[bi];
    cross.setAttribute("x1", String(X(x)));
    cross.setAttribute("x2", String(X(x)));
    cross.setAttribute("opacity", "1");
    tt.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tt-title";
    title.textContent = `${x}${spec.xUnit ?? "년"}${spec.projStart != null && x > spec.projStart ? " (추계)" : ""}`;
    tt.appendChild(title);
    const tot = spec.series.reduce((a, s) => a + (get(s, x) ?? 0), 0);
    [...spec.series].reverse().forEach((s) => {
      const v = get(s, x) ?? 0;
      ttRow(tt, s.color, s.name, spec.percent ? `${fmt(v / (tot || 1), "pct1")}` : fmt(v, yf));
    });
    placeTooltip(tt, box, X(x), m.t + 10);
  });
  hit.addEventListener("pointerleave", () => {
    tt.style.opacity = "0";
    cross.setAttribute("opacity", "0");
  });
}

// ------------------------------------------------------------------ 산점도 / 버블
export interface ScatterSpec {
  type: "scatter";
  points: { x: number; y: number; r?: number; label: string; color?: string; href?: string; group?: string; note?: string }[];
  groups?: { name: string; color: string }[];
  xFormat?: Fmt;
  yFormat?: Fmt;
  rFormat?: Fmt;
  xLabel: string;
  yLabel: string;
  rLabel?: string;
  xRef?: number; // 기준선 (예: 0, 전국 평균)
  yRef?: number;
  quadrants?: [string, string, string, string]; // 좌상, 우상, 좌하, 우하
  labelTop?: number; // 큰 점 N개 직접 라벨
  labels?: string[]; // 직접 라벨할 이름
  height?: number;
}

export function renderScatter(host: HTMLElement, spec: ScatterSpec) {
  host.innerHTML = "";
  const H = spec.height ?? 380;
  const W = Math.max(host.clientWidth, 280);
  const xf = spec.xFormat ?? "dec1",
    yf = spec.yFormat ?? "dec1";
  if (spec.groups && spec.groups.length > 1) legend(host, spec.groups.map((g) => ({ name: g.name, color: g.color, kind: "rect" as const })));
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const m = { t: 16, r: 16, b: 44, l: W < 520 ? 48 : 60 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const P = spec.points;
  const xsv = P.map((p) => p.x).concat(spec.xRef != null ? [spec.xRef] : []);
  const ysv = P.map((p) => p.y).concat(spec.yRef != null ? [spec.yRef] : []);
  const padX = (Math.max(...xsv) - Math.min(...xsv)) * 0.06 || 1;
  const padY = (Math.max(...ysv) - Math.min(...ysv)) * 0.06 || 1;
  const xt = niceTicks(Math.min(...xsv) - padX, Math.max(...xsv) + padX, Math.max(3, Math.floor(pw / 90)));
  const yt = niceTicks(Math.min(...ysv) - padY, Math.max(...ysv) + padY, 5);
  const X = (v: number) => m.l + ((v - xt[0]) / (xt[xt.length - 1] - xt[0])) * pw;
  const Y = (v: number) => m.t + ph - ((v - yt[0]) / (yt[yt.length - 1] - yt[0])) * ph;
  const rMax = Math.max(...P.map((p) => p.r ?? 1));
  const R = (r?: number) => (spec.points.some((p) => p.r != null) ? 5 + Math.sqrt((r ?? 0) / rMax) * (W < 520 ? 16 : 24) : 6);
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  for (const t of yt) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: "grid-line" }, svg);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tick(t, yf);
  }
  for (const t of xt) {
    const tx = el("text", { x: X(t), y: m.t + ph + 18, "text-anchor": "middle" }, svg);
    tx.textContent = tick(t, xf);
  }
  el("line", { x1: m.l, x2: m.l + pw, y1: m.t + ph, y2: m.t + ph, class: "axis-line" }, svg);
  if (spec.xRef != null) el("line", { x1: X(spec.xRef), x2: X(spec.xRef), y1: m.t, y2: m.t + ph, stroke: "var(--text-muted)", "stroke-dasharray": "3 3" }, svg);
  if (spec.yRef != null) el("line", { x1: m.l, x2: m.l + pw, y1: Y(spec.yRef), y2: Y(spec.yRef), stroke: "var(--text-muted)", "stroke-dasharray": "3 3" }, svg);
  if (spec.quadrants) {
    const pos: [number, number, string][] = [
      [m.l + 6, m.t + 14, "start"],
      [m.l + pw - 6, m.t + 14, "end"],
      [m.l + 6, m.t + ph - 8, "start"],
      [m.l + pw - 6, m.t + ph - 8, "end"],
    ];
    spec.quadrants.forEach((q, i) => {
      if (!q) return;
      const t = el("text", { x: pos[i][0], y: pos[i][1], "text-anchor": pos[i][2], class: "label quad" }, svg);
      t.textContent = q;
    });
  }
  const xl = el("text", { x: m.l + pw, y: H - 4, "text-anchor": "end", class: "label" }, svg);
  xl.textContent = spec.xLabel + " →";
  const yl = el("text", { x: m.l, y: m.t - 4, class: "label" }, svg);
  yl.textContent = "↑ " + spec.yLabel;
  const tt = makeTooltip(box);
  const anim = shouldAnimate(host);
  const order = [...P.keys()].sort((a, b) => (P[b].r ?? 0) - (P[a].r ?? 0)); // 큰 점 먼저 (작은 점이 위에)
  const labelSet = new Set([...(spec.labels ?? []), ...order.slice(0, spec.labelTop ?? 0).map((i) => P[i].label)]);
  const g = el("g", {}, svg);
  order.forEach((i, k) => {
    const p = P[i];
    const color = p.color ?? spec.groups?.find((gg) => gg.name === p.group)?.color ?? "var(--series-1)";
    const c = el("circle", { cx: X(p.x), cy: Y(p.y), r: R(p.r), fill: color, "fill-opacity": 0.78, stroke: "var(--surface-1)", "stroke-width": 1.5, class: anim ? "pop" : "" }, g);
    if (anim) c.style.transitionDelay = `${Math.min(k * 18, 700)}ms`;
    const enter = (e: PointerEvent | FocusEvent) => {
      c.setAttribute("stroke", "var(--text-primary)");
      tt.innerHTML = "";
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = p.label + (p.group ? ` · ${p.group}` : "");
      tt.appendChild(title);
      ttRow(tt, color, spec.xLabel, fmt(p.x, xf));
      ttRow(tt, color, spec.yLabel, fmt(p.y, yf));
      if (p.r != null && spec.rLabel) ttRow(tt, color, spec.rLabel, fmt(p.r, spec.rFormat ?? "int"));
      if (p.note) {
        const n = document.createElement("div");
        n.className = "tt-note";
        n.textContent = p.note;
        tt.appendChild(n);
      }
      placeTooltip(tt, box, X(p.x), Y(p.y) - 10);
      void e;
    };
    c.addEventListener("pointerenter", enter);
    c.addEventListener("pointerleave", () => {
      c.setAttribute("stroke", "var(--surface-1)");
      tt.style.opacity = "0";
    });
    if (p.href) {
      c.style.cursor = "pointer";
      c.addEventListener("click", () => (location.href = p.href!));
    }
  });
  if (anim) onVisible(svg, () => svg.classList.add("grown"));
  // 직접 라벨 (겹침 간단 회피)
  const placed: [number, number][] = [];
  for (const i of order) {
    const p = P[i];
    if (!labelSet.has(p.label)) continue;
    let x = X(p.x),
      y = Y(p.y) - R(p.r) - 4;
    for (const [px, py] of placed) if (Math.abs(px - x) < 60 && Math.abs(py - y) < 13) y = py - 13;
    placed.push([x, y]);
    const t = el("text", { x, y, "text-anchor": "middle", class: "label-strong halo" }, svg);
    t.textContent = p.label;
  }
}

// ------------------------------------------------------------------ 누적 막대
export interface StackSpec {
  type: "stack";
  categories: string[];
  series: { name: string; color: string; values: number[] }[];
  percent?: boolean;
  yFormat?: Fmt;
  height?: number;
  projFrom?: number; // 이 인덱스부터 옅게(추계)
}

export function renderStack(host: HTMLElement, spec: StackSpec) {
  host.innerHTML = "";
  const H = spec.height ?? 280;
  const W = Math.max(host.clientWidth, 280);
  const yf = spec.yFormat ?? (spec.percent ? "pct" : "int");
  legend(host, spec.series.map((s) => ({ name: s.name, color: s.color, kind: "rect" as const })));
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const m = { t: 12, r: 8, b: 30, l: 52 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const n = spec.categories.length;
  const tots = spec.categories.map((_, i) => spec.series.reduce((a, s) => a + (s.values[i] ?? 0), 0));
  const ymax = spec.percent ? 1 : Math.max(...tots);
  const ticks = spec.percent ? [0, 0.25, 0.5, 0.75, 1] : niceTicks(0, ymax, 4);
  const yhi = ticks[ticks.length - 1];
  const Y = (v: number) => m.t + ph - (v / yhi) * ph;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  for (const t of ticks) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: t === 0 ? "axis-line" : "grid-line" }, svg);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tick(t, yf);
  }
  const slot = pw / n;
  const bw = Math.min(40, slot * 0.7);
  const every = Math.ceil(n / Math.max(2, Math.floor(pw / 48)));
  const anim = shouldAnimate(host);
  if (anim) {
    svg.classList.add("will-grow");
    onVisible(svg, () => svg.classList.add("grown"));
  }
  const tt = makeTooltip(box);
  spec.categories.forEach((c, i) => {
    const cx = m.l + slot * i + slot / 2;
    const g = el("g", { class: "grow-up" }, svg);
    g.style.transitionDelay = `${Math.min(i * (500 / n), 500)}ms`;
    let acc = 0;
    spec.series.forEach((s) => {
      const raw = s.values[i] ?? 0;
      const v = spec.percent ? raw / (tots[i] || 1) : raw;
      const y0 = Y(acc),
        y1 = Y(acc + v);
      acc += v;
      if (y0 - y1 < 0.5) return;
      el("rect", { x: cx - bw / 2, y: y1 + 1, width: bw, height: Math.max(0, y0 - y1 - 2), rx: 2, fill: s.color, opacity: spec.projFrom != null && i >= spec.projFrom ? 0.62 : 1 }, g);
    });
    if (i % every === 0) {
      const tx = el("text", { x: cx, y: H - 10, "text-anchor": "middle" }, svg);
      tx.textContent = c;
    }
    const hit = el("rect", { x: cx - slot / 2, y: m.t, width: slot, height: ph, fill: "transparent" }, svg);
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      tt.innerHTML = "";
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = c + (spec.projFrom != null && i >= spec.projFrom ? " (추계)" : "");
      tt.appendChild(title);
      [...spec.series].reverse().forEach((s) => ttRow(tt, s.color, s.name, spec.percent ? fmt((s.values[i] ?? 0) / (tots[i] || 1), "pct1") : fmt(s.values[i], yf)));
      if (!spec.percent) ttRow(tt, "transparent", "합계", fmt(tots[i], yf));
      placeTooltip(tt, box, e.clientX - r.left, m.t + 10);
    });
    hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));
  });
}

// ------------------------------------------------------------------ 막대 레이스 (HTML)
export interface RaceSpec {
  type: "race";
  names: string[];
  colors?: string[];
  frames: { label: string | number; values: (number | null)[] }[];
  format?: Fmt;
  top?: number;
  start?: number;
  speed?: number;
  autoplay?: boolean;
  projFrom?: number;
  unit?: string;
}

export function renderRace(host: HTMLElement, spec: RaceSpec) {
  host.innerHTML = "";
  const top = Math.min(spec.top ?? 12, spec.names.length);
  const rowH = 30;
  const wrap = document.createElement("div");
  wrap.className = "race";
  wrap.style.height = `${top * rowH}px`;
  const big = document.createElement("div");
  big.className = "race-year";
  wrap.appendChild(big);
  const rows = spec.names.map((name, i) => {
    const r = document.createElement("div");
    r.className = "race-row";
    r.innerHTML = `<span class="race-name"></span><span class="race-track"><span class="race-bar"></span></span><span class="race-val"></span>`;
    r.querySelector(".race-name")!.textContent = name;
    (r.querySelector(".race-bar") as HTMLElement).style.background = spec.colors?.[i] ?? "var(--series-1)";
    wrap.appendChild(r);
    return r;
  });
  host.appendChild(wrap);
  const ctl = document.createElement("div");
  host.appendChild(ctl);
  const maxAll = Math.max(...spec.frames.flatMap((f) => f.values.map((v) => v ?? 0)));
  let prevVals: number[] = spec.frames[0].values.map((v) => v ?? 0);
  let cancel = () => {};
  const show = (fi: number, animate: boolean) => {
    const f = spec.frames[fi];
    big.textContent = String(f.label);
    const vals = f.values.map((v) => v ?? 0);
    const order = [...vals.keys()].sort((a, b) => vals[b] - vals[a]);
    const rank = new Array(vals.length);
    order.forEach((idx, k) => (rank[idx] = k));
    rows.forEach((r, i) => {
      const k = rank[i];
      r.style.transform = `translateY(${k * rowH}px)`;
      r.style.opacity = k < top ? "1" : "0";
      r.style.transitionDuration = animate ? "" : "0s";
    });
    const from = prevVals.slice();
    cancel();
    cancel = tween(animate ? (spec.speed ?? 700) * 0.9 : 0, (t) => {
      rows.forEach((r, i) => {
        const v = from[i] + (vals[i] - from[i]) * t;
        (r.querySelector(".race-bar") as HTMLElement).style.width = `${(v / maxAll) * 100}%`;
        r.querySelector(".race-val")!.textContent = fmt(v, spec.format ?? "int") + (spec.unit ?? "");
      });
    });
    prevVals = vals;
  };
  const start = spec.start ?? 0;
  makePlayer(ctl, spec.frames.map((f) => f.label), show, { start, speed: spec.speed ?? 700, autoplay: spec.autoplay, projFrom: spec.projFrom });
  show(start, false);
}

// ------------------------------------------------------------------ 100칸 와플
export interface WaffleSpec {
  type: "waffle";
  groups: { name: string; color: string }[];
  frames: { label: string | number; values: number[] }[]; // 합 100 (반올림 보정)
  start?: number;
  speed?: number;
  autoplay?: boolean;
  projFrom?: number;
  caption?: string; // 예: "명"
}

export function renderWaffle(host: HTMLElement, spec: WaffleSpec) {
  host.innerHTML = "";
  legend(host, spec.groups.map((g) => ({ name: g.name, color: g.color, kind: "rect" as const })));
  const wrap = document.createElement("div");
  wrap.className = "waffle-wrap";
  const grid = document.createElement("div");
  grid.className = "waffle";
  grid.setAttribute("role", "img");
  const cells: HTMLElement[] = [];
  for (let i = 0; i < 100; i++) {
    const c = document.createElement("span");
    c.style.transitionDelay = `${(i % 10) * 12 + Math.floor(i / 10) * 8}ms`;
    grid.appendChild(c);
    cells.push(c);
  }
  const side = document.createElement("div");
  side.className = "waffle-side";
  wrap.append(grid, side);
  host.appendChild(wrap);
  const ctl = document.createElement("div");
  host.appendChild(ctl);
  const show = (fi: number) => {
    const f = spec.frames[fi];
    // 반올림 합 100 보정
    const v = f.values.map((x) => Math.round(x));
    const diff = 100 - v.reduce((a, b) => a + b, 0);
    if (diff) v[v.indexOf(Math.max(...v))] += diff;
    let k = 0;
    v.forEach((cnt, gi) => {
      for (let j = 0; j < cnt && k < 100; j++, k++) cells[k].style.background = spec.groups[gi].color;
    });
    for (; k < 100; k++) cells[k].style.background = "var(--surface-2)";
    grid.setAttribute("aria-label", `${f.label}: ` + spec.groups.map((g, i) => `${g.name} ${v[i]}${spec.caption ?? ""}`).join(", "));
    side.innerHTML = "";
    const yr = document.createElement("div");
    yr.className = "waffle-year";
    yr.textContent = String(f.label);
    side.appendChild(yr);
    spec.groups.forEach((g, i) => {
      const r = document.createElement("div");
      r.className = "waffle-row";
      r.innerHTML = `<span class="swatch-rect" style="background:${g.color}"></span><span class="n"></span><span class="v"></span>`;
      r.querySelector(".n")!.textContent = g.name;
      r.querySelector(".v")!.textContent = `${v[i]}${spec.caption ?? ""}`;
      side.appendChild(r);
    });
  };
  const start = spec.start ?? 0;
  makePlayer(ctl, spec.frames.map((f) => f.label), (i) => show(i), { start, speed: spec.speed ?? 900, autoplay: spec.autoplay, projFrom: spec.projFrom });
  show(start);
}
