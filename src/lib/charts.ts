// 경량 SVG 차트 (선·밴드·피라미드·세로막대). 데이터 시각화 원칙:
// 얇은 선(2px), 추계 구간은 점선 + 회색 배경, 크로스헤어 툴팁, 범례 + 선택적 직접 라벨, 표 보기 별도 제공.
import { fmt, tick, type Fmt } from "./format";
import { onVisible, reduced, tween } from "./anim";
import { makePlayer } from "./player";
import { renderArea, renderScatter, renderStack, renderRace, renderWaffle, type AreaSpec, type ScatterSpec, type StackSpec, type RaceSpec, type WaffleSpec } from "./charts-extra";

export type Pt = [number, number | null];
export interface LineSeries {
  name: string;
  color: string; // CSS 색 또는 var(--series-n)
  data: Pt[];
  dash?: boolean;
  width?: number;
  label?: boolean; // 끝점 직접 라벨
  fill?: boolean; // 선 아래 옅은 면
  hideInTooltip?: boolean;
  muted?: boolean;
}
export interface Band {
  name: string;
  color: string;
  lower: Pt[];
  upper: Pt[];
}
export interface LineSpec {
  type: "line";
  series: LineSeries[];
  bands?: Band[];
  projStart?: number;
  yFormat?: Fmt;
  yMin?: number;
  yMax?: number;
  zeroBased?: boolean;
  height?: number;
  xFormat?: "year" | "month";
  markers?: { x: number; label: string }[];
  hLines?: { y: number; label: string }[];
  legend?: boolean;
  xUnit?: string; // 툴팁 x 단위 (기본 "년")
  animate?: boolean;
}
export interface PyramidSpec {
  type: "pyramid";
  groups: string[];
  left: number[];
  right: number[];
  leftOutline?: number[];
  rightOutline?: number[];
  leftName: string;
  rightName: string;
  outlineName?: string;
  height?: number;
  /** 연도별 프레임: 재생 버튼으로 애니메이션 */
  frames?: { years: number[]; m: number[][]; f: number[][]; proj?: number };
  start?: number; // 시작 연도
  refYear?: number; // 외곽선으로 고정해 둘 비교 연도
  autoplay?: boolean;
  speed?: number;
}
export interface ColumnSpec {
  type: "column";
  categories: string[];
  values: (number | null)[];
  colors?: string[];
  yFormat?: Fmt;
  height?: number;
  highlight?: number[];
  animate?: boolean;
}
export type ChartSpec = LineSpec | PyramidSpec | ColumnSpec | AreaSpec | ScatterSpec | StackSpec | RaceSpec | WaffleSpec;
export type { AreaSpec, ScatterSpec, StackSpec, RaceSpec, WaffleSpec };

const NS = "http://www.w3.org/2000/svg";
let clipSeq = 0;
/** 첫 렌더일 때 왼쪽→오른쪽으로 드러나는 클립. 반환된 g 에 데이터 표시를 그린다 */
export function revealGroup(svg: SVGSVGElement, x: number, y: number, w: number, h: number, animate: boolean) {
  const id = `rv${++clipSeq}`;
  const defs = el("defs", {}, svg);
  const cp = el("clipPath", { id }, defs);
  const r = el("rect", { x: x - 6, y: y - 20, width: animate ? 0 : w + 80, height: h + 40 }, cp);
  const g = el("g", { "clip-path": `url(#${id})` }, svg);
  if (animate) onVisible(svg, () => tween(1300, (k) => r.setAttribute("width", String((w + 80) * k))));
  return g;
}
/** 첫 렌더 애니메이션 여부 (mount 가 설정) */
export const firstRender = new WeakSet<HTMLElement>();
export function shouldAnimate(host: HTMLElement, flag?: boolean) {
  return flag !== false && !reduced() && firstRender.has(host);
}
export function el<K extends keyof SVGElementTagNameMap>(tag: K, attrs: Record<string, string | number> = {}, parent?: Element) {
  const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  if (parent) parent.appendChild(e);
  return e;
}

export function niceStep(range: number, count: number) {
  const raw = range / Math.max(count, 1);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const n = raw / mag;
  const s = n < 1.5 ? 1 : n < 3 ? 2 : n < 7 ? 5 : 10;
  return s * mag;
}
export function niceTicks(min: number, max: number, count = 5) {
  if (min === max) {
    max = min + 1;
  }
  const step = niceStep(max - min, count);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const out: number[] = [];
  for (let v = lo; v <= hi + step * 0.5; v += step) out.push(Math.round(v / step) * step);
  return out;
}

export function makeTooltip(host: HTMLElement) {
  const tt = document.createElement("div");
  tt.className = "tooltip";
  tt.setAttribute("role", "status");
  host.appendChild(tt);
  return tt;
}
export function ttRow(tt: HTMLElement, color: string, name: string, value: string, dash = false) {
  const row = document.createElement("div");
  row.className = "tt-row";
  const key = document.createElement("span");
  key.className = "tt-key";
  const i = document.createElement("i");
  i.style.borderTopColor = color;
  if (dash) i.style.borderTopStyle = "dashed";
  key.appendChild(i);
  key.appendChild(document.createTextNode(name));
  const val = document.createElement("span");
  val.className = "tt-val";
  val.textContent = value;
  row.append(key, val);
  tt.appendChild(row);
}
export function placeTooltip(tt: HTMLElement, host: HTMLElement, x: number, y: number) {
  const w = tt.offsetWidth;
  const hw = host.clientWidth;
  let left = x + 14;
  if (left + w > hw) left = x - w - 14;
  if (left < 0) left = Math.max(0, Math.min(hw - w, x - w / 2));
  tt.style.left = left + "px";
  tt.style.top = Math.max(0, y - 10) + "px";
  tt.style.opacity = "1";
}

export function legend(host: HTMLElement, items: { name: string; color: string; kind: "line" | "dash" | "rect" }[]) {
  const lg = document.createElement("div");
  lg.className = "chart-legend";
  for (const it of items) {
    const k = document.createElement("span");
    k.className = "key";
    const sw = document.createElement("span");
    sw.className = it.kind === "rect" ? "swatch-rect" : it.kind === "dash" ? "swatch-dash" : "swatch-line";
    if (it.kind === "rect") sw.style.background = it.color;
    else sw.style.borderTopColor = it.color;
    k.appendChild(sw);
    k.appendChild(document.createTextNode(it.name));
    lg.appendChild(k);
  }
  host.appendChild(lg);
}

export function renderLine(host: HTMLElement, spec: LineSpec) {
  host.innerHTML = "";
  const H = spec.height ?? 300;
  const W = Math.max(host.clientWidth, 280);
  const yf = spec.yFormat ?? "int";
  if (spec.legend !== false) {
    const items: { name: string; color: string; kind: "line" | "dash" | "rect" }[] = [];
    for (const s of spec.series) if (!s.hideInTooltip) items.push({ name: s.name, color: s.color, kind: s.dash ? "dash" : "line" });
    for (const b of spec.bands ?? []) items.push({ name: b.name, color: b.color, kind: "rect" });
    if (items.length > 1) legend(host, items);
  }
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const narrow = W < 520;
  const m = { t: 12, r: narrow ? 12 : 64, b: 28, l: narrow ? 44 : 56 };
  const pw = W - m.l - m.r;
  const ph = H - m.t - m.b;

  const xs = new Set<number>();
  let ymin = Infinity,
    ymax = -Infinity;
  const scan = (pts: Pt[]) => {
    for (const [x, y] of pts) {
      xs.add(x);
      if (y != null) {
        ymin = Math.min(ymin, y);
        ymax = Math.max(ymax, y);
      }
    }
  };
  spec.series.forEach((s) => scan(s.data));
  (spec.bands ?? []).forEach((b) => {
    scan(b.lower);
    scan(b.upper);
  });
  (spec.hLines ?? []).forEach((h) => {
    ymin = Math.min(ymin, h.y);
    ymax = Math.max(ymax, h.y);
  });
  const xsArr = [...xs].sort((a, b) => a - b);
  const x0 = xsArr[0],
    x1 = xsArr[xsArr.length - 1];
  if (spec.zeroBased !== false && ymin > 0 && (spec.zeroBased || ymin / ymax < 0.35)) ymin = 0;
  if (spec.yMin != null) ymin = spec.yMin;
  if (spec.yMax != null) ymax = spec.yMax;
  const pad = (ymax - ymin) * 0.06 || 1;
  let ticks = niceTicks(ymin - (ymin === 0 ? 0 : pad), ymax + pad, ph < 220 ? 4 : 5);
  if (ymin >= 0) ticks = ticks.filter((t) => t >= 0);
  const ylo = ticks[0],
    yhi = ticks[ticks.length - 1];
  const X = (x: number) => m.l + ((x - x0) / (x1 - x0 || 1)) * pw;
  const Y = (y: number) => m.t + ph - ((y - ylo) / (yhi - ylo || 1)) * ph;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  if (spec.projStart != null && spec.projStart < x1) {
    const px = X(spec.projStart);
    el("rect", { x: px, y: m.t, width: m.l + pw - px, height: ph, class: "proj-zone", opacity: 0.6 }, svg);
    const t = el("text", { x: px + 6, y: m.t + 14, class: "label" }, svg);
    t.textContent = "추계";
  }
  for (const t of ticks) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: t === 0 ? "axis-line" : "grid-line" }, svg);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tick(t, yf);
  }
  // x ticks
  const span = x1 - x0;
  const maxTicks = Math.max(2, Math.floor(pw / 64));
  let step = [1, 2, 5, 10, 20, 25, 50].find((s) => span / s <= maxTicks) ?? 50;
  const first = Math.ceil(x0 / step) * step;
  for (let x = first; x <= x1; x += step) {
    const tx = el("text", { x: X(x), y: H - 8, "text-anchor": "middle" }, svg);
    tx.textContent = spec.xFormat === "month" ? `${x}월` : String(x);
  }
  el("line", { x1: m.l, x2: m.l + pw, y1: m.t + ph, y2: m.t + ph, class: "axis-line" }, svg);

  for (const h of spec.hLines ?? []) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(h.y), y2: Y(h.y), stroke: "var(--text-muted)", "stroke-width": 1 }, svg);
    const t = el("text", { x: m.l + 4, y: Y(h.y) - 5 }, svg);
    t.textContent = h.label;
  }

  const anim = shouldAnimate(host, spec.animate);
  const marks = revealGroup(svg, m.l, m.t, pw, ph, anim);
  for (const b of spec.bands ?? []) {
    const up = b.upper.filter((p) => p[1] != null) as [number, number][];
    const lo = (b.lower.filter((p) => p[1] != null) as [number, number][]).slice().reverse();
    if (!up.length) continue;
    const d = "M" + up.map(([x, y]) => `${X(x)},${Y(y)}`).join("L") + "L" + lo.map(([x, y]) => `${X(x)},${Y(y)}`).join("L") + "Z";
    el("path", { d, fill: b.color, opacity: 0.12 }, marks);
  }
  const labelSlots: { y: number; s: LineSeries; v: number }[] = [];
  for (const s of spec.series) {
    if (s.fill) {
      const ps = s.data.filter((p) => p[1] != null) as [number, number][];
      if (ps.length > 1) {
        const base = Y(Math.max(ylo, 0));
        const d = `M${X(ps[0][0])},${base}` + ps.map(([x, y]) => `L${X(x)},${Y(y)}`).join("") + `L${X(ps[ps.length - 1][0])},${base}Z`;
        el("path", { d, fill: s.color, opacity: 0.1 }, marks);
      }
    }
    let d = "";
    let pen = false;
    for (const [x, y] of s.data) {
      if (y == null) {
        pen = false;
        continue;
      }
      d += (pen ? "L" : "M") + X(x).toFixed(1) + "," + Y(y).toFixed(1);
      pen = true;
    }
    el(
      "path",
      {
        d,
        fill: "none",
        stroke: s.color,
        "stroke-width": s.width ?? 2,
        "stroke-linejoin": "round",
        "stroke-linecap": "round",
        "stroke-dasharray": s.dash ? "5 4" : "none",
        opacity: s.muted ? 0.55 : 1,
      },
      marks,
    );
    const last = [...s.data].reverse().find((p) => p[1] != null);
    if (s.label && last) {
      const dot = el("circle", { cx: X(last[0]), cy: Y(last[1]!), r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2, class: anim ? "pop-late" : "" }, svg);
      void dot;
      labelSlots.push({ y: Y(last[1]!), s, v: last[1]! });
    }
  }
  if (!narrow) {
    labelSlots.sort((a, b) => a.y - b.y);
    for (let i = 1; i < labelSlots.length; i++) if (labelSlots[i].y - labelSlots[i - 1].y < 15) labelSlots[i].y = labelSlots[i - 1].y + 15;
    for (const l of labelSlots) {
      const t = el("text", { x: m.l + pw + 8, y: l.y + 4, class: "label-strong" + (anim ? " pop-late" : "") }, svg);
      t.textContent = tick(l.v, yf);
    }
  }
  for (const mk of spec.markers ?? []) {
    const t = el("text", { x: X(mk.x), y: m.t + ph - 6, "text-anchor": "middle", class: "label" }, svg);
    t.textContent = mk.label;
  }

  // hover
  const cross = el("line", { x1: 0, x2: 0, y1: m.t, y2: m.t + ph, class: "crosshair", opacity: 0 }, svg);
  const dots = spec.series.map((s) => el("circle", { r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2, opacity: 0 }, svg));
  const tt = makeTooltip(box);
  const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent", tabindex: 0 }, svg);
  let focusIdx = -1;
  const show = (x: number) => {
    cross.setAttribute("x1", String(X(x)));
    cross.setAttribute("x2", String(X(x)));
    cross.setAttribute("opacity", "1");
    tt.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tt-title";
    title.textContent = `${x}${spec.xUnit ?? "년"}${spec.projStart != null && x > spec.projStart ? " (추계)" : ""}`;
    tt.appendChild(title);
    let ty = m.t;
    spec.series.forEach((s, i) => {
      const p = s.data.find((d) => d[0] === x);
      if (p && p[1] != null) {
        dots[i].setAttribute("cx", String(X(x)));
        dots[i].setAttribute("cy", String(Y(p[1])));
        dots[i].setAttribute("opacity", "1");
        if (!s.hideInTooltip) ttRow(tt, s.color, s.name, fmt(p[1], yf), s.dash);
        ty = Y(p[1]);
      } else dots[i].setAttribute("opacity", "0");
    });
    for (const b of spec.bands ?? []) {
      const lo = b.lower.find((d) => d[0] === x),
        up = b.upper.find((d) => d[0] === x);
      if (lo && up && lo[1] != null && up[1] != null) ttRow(tt, b.color, b.name, `${fmt(lo[1], yf)} ~ ${fmt(up[1], yf)}`);
    }
    placeTooltip(tt, box, X(x), Math.min(ty, ph - 40));
  };
  const hide = () => {
    cross.setAttribute("opacity", "0");
    dots.forEach((d) => d.setAttribute("opacity", "0"));
    tt.style.opacity = "0";
  };
  const nearest = (px: number) => {
    let best = xsArr[0];
    for (const x of xsArr) if (Math.abs(X(x) - px) < Math.abs(X(best) - px)) best = x;
    return best;
  };
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    show(nearest(e.clientX - r.left));
  });
  hit.addEventListener("pointerleave", hide);
  hit.addEventListener("blur", hide);
  hit.addEventListener("keydown", (e) => {
    const ke = e as KeyboardEvent;
    if (ke.key !== "ArrowRight" && ke.key !== "ArrowLeft") return;
    e.preventDefault();
    focusIdx = Math.max(0, Math.min(xsArr.length - 1, focusIdx + (ke.key === "ArrowRight" ? 1 : -1)));
    show(xsArr[focusIdx]);
  });
}

export function renderPyramid(host: HTMLElement, spec: PyramidSpec) {
  host.innerHTML = "";
  const n = spec.groups.length;
  const fr = spec.frames;
  const W = Math.max(host.clientWidth, 280);
  const H = spec.height ?? n * 14 + 40;
  const refIdx = fr && spec.refYear != null ? fr.years.indexOf(spec.refYear) : -1;
  const items: { name: string; color: string; kind: "line" | "dash" | "rect" }[] = [
    { name: spec.leftName, color: "var(--series-1)", kind: "rect" },
    { name: spec.rightName, color: "var(--series-2)", kind: "rect" },
  ];
  const outlineName = fr ? (refIdx >= 0 ? `${spec.refYear}년` : undefined) : spec.outlineName;
  if (outlineName) items.push({ name: outlineName, color: "var(--text-primary)", kind: "line" });
  legend(host, items);
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const mid = W / 2;
  const gap = W < 420 ? 20 : 26;
  const m = { t: 4, b: 22 };
  const ph = H - m.t - m.b;
  const bh = ph / n;
  const all = fr ? [...fr.m.flat(), ...fr.f.flat()] : [...spec.left, ...spec.right, ...(spec.leftOutline ?? [0]), ...(spec.rightOutline ?? [0])];
  const maxV = Math.max(...all, 1);
  const half = mid - gap - 4;
  const S = (v: number) => (v / maxV) * half;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  const tt = makeTooltip(box);
  // 큰 연도 표시 (모션 그래픽 워터마크)
  const yearTxt = fr ? el("text", { x: W - 4, y: m.t + 34, "text-anchor": "end", class: "pyr-year" }, svg) : null;
  const projTxt = fr ? el("text", { x: W - 6, y: m.t + 54, "text-anchor": "end", class: "label" }, svg) : null;
  const L: SVGRectElement[] = [],
    R: SVGRectElement[] = [];
  for (let i = 0; i < n; i++) {
    const gi = n - 1 - i; // 위가 고령
    const y = m.t + i * bh + 1;
    const h = Math.max(bh - 2, 1);
    L[gi] = el("rect", { x: mid - gap, y, width: 0, height: h, rx: 2, fill: "var(--series-1)" }, svg);
    R[gi] = el("rect", { x: mid + gap, y, width: 0, height: h, rx: 2, fill: "var(--series-2)" }, svg);
    if (i % 2 === 0 || bh > 12) {
      const t = el("text", { x: mid, y: y + h / 2 + 4, "text-anchor": "middle" }, svg);
      t.textContent = spec.groups[gi].replace("세", "").replace(" 이상", "+");
    }
  }
  // 외곽선 (비교 연도)
  const outline = (lo: number[] | undefined, ro: number[] | undefined) => {
    if (!lo || !ro) return;
    let dl = "",
      dr = "";
    for (let i = 0; i < n; i++) {
      const gi = n - 1 - i;
      const y0 = m.t + i * bh,
        y1 = y0 + bh;
      const lx = mid - gap - S(lo[gi]);
      const rx = mid + gap + S(ro[gi]);
      dl += (i ? "L" : "M") + `${lx},${y0}L${lx},${y1}`;
      dr += (i ? "L" : "M") + `${rx},${y0}L${rx},${y1}`;
    }
    el("path", { d: dl, fill: "none", stroke: "var(--text-primary)", "stroke-width": 1.5, "stroke-linejoin": "round" }, svg);
    el("path", { d: dr, fill: "none", stroke: "var(--text-primary)", "stroke-width": 1.5, "stroke-linejoin": "round" }, svg);
  };
  if (fr && refIdx >= 0) outline(fr.m[refIdx], fr.f[refIdx]);
  else if (!fr) outline(spec.leftOutline, spec.rightOutline);
  const t1 = el("text", { x: mid - gap, y: H - 6, "text-anchor": "end" }, svg);
  t1.textContent = tick(maxV, "int") + " ←";
  const t2 = el("text", { x: mid + gap, y: H - 6 }, svg);
  t2.textContent = "→ " + tick(maxV, "int");

  // 현재 값
  let curL = new Array(n).fill(0),
    curR = new Array(n).fill(0);
  let dataL = fr ? fr.m[0] : spec.left,
    dataR = fr ? fr.f[0] : spec.right;
  let label = "";
  const setW = (l: number[], r: number[]) => {
    for (let gi = 0; gi < n; gi++) {
      const lw = S(l[gi]),
        rw = S(r[gi]);
      L[gi].setAttribute("x", String(mid - gap - lw));
      L[gi].setAttribute("width", String(Math.max(0, lw)));
      R[gi].setAttribute("width", String(Math.max(0, rw)));
    }
  };
  let cancel = () => {};
  const go = (l: number[], r: number[], ms: number) => {
    cancel();
    const fl = curL.slice(),
      frr = curR.slice();
    dataL = l;
    dataR = r;
    cancel = tween(ms, (k) => {
      curL = fl.map((v, i) => v + (l[i] - v) * k);
      curR = frr.map((v, i) => v + (r[i] - v) * k);
      setW(curL, curR);
    });
  };
  // 툴팁
  for (let i = 0; i < n; i++) {
    const gi = n - 1 - i;
    const y = m.t + i * bh + 1;
    const hit = el("rect", { x: 0, y: y - 1, width: W, height: bh, fill: "transparent" }, svg);
    hit.addEventListener("pointermove", (e) => {
      const r = svg.getBoundingClientRect();
      tt.innerHTML = "";
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = spec.groups[gi] + (label ? ` · ${label}` : "");
      tt.appendChild(title);
      ttRow(tt, "var(--series-1)", spec.leftName, fmt(dataL[gi], "int"));
      ttRow(tt, "var(--series-2)", spec.rightName, fmt(dataR[gi], "int"));
      if (fr && refIdx >= 0) ttRow(tt, "var(--text-primary)", `${spec.refYear}년 합계`, fmt(fr.m[refIdx][gi] + fr.f[refIdx][gi], "int"));
      else if (spec.leftOutline && spec.rightOutline && spec.outlineName) {
        ttRow(tt, "var(--text-primary)", spec.outlineName + " " + spec.leftName, fmt(spec.leftOutline[gi], "int"));
        ttRow(tt, "var(--text-primary)", spec.outlineName + " " + spec.rightName, fmt(spec.rightOutline[gi], "int"));
      }
      placeTooltip(tt, box, e.clientX - r.left, y);
    });
    hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));
  }
  const anim = shouldAnimate(host, true);
  if (!fr) {
    if (anim) onVisible(svg, () => go(spec.left, spec.right, 900));
    else go(spec.left, spec.right, 0);
    return;
  }
  // 프레임 + 재생기 + 요약 수치
  const stats = document.createElement("div");
  stats.className = "pyr-stats";
  const ctl = document.createElement("div");
  host.append(ctl, stats);
  const oldFrom = spec.groups.findIndex((g) => g.startsWith("65"));
  const kidTo = spec.groups.findIndex((g) => g.startsWith("15"));
  const paintStats = (i: number) => {
    const tot = fr.m[i].reduce((a, b) => a + b, 0) + fr.f[i].reduce((a, b) => a + b, 0);
    const sum = (a: number, b: number) => {
      let s = 0;
      for (let g = a; g < b; g++) s += fr.m[i][g] + fr.f[i][g];
      return s;
    };
    const old = sum(oldFrom, n),
      kid = sum(0, kidTo);
    const work = tot - old - kid;
    stats.innerHTML = "";
    for (const [k, v] of [
      ["총인구", fmt(tot, "man")],
      ["0~14세", fmt(kid / tot, "pct1")],
      ["15~64세", fmt(work / tot, "pct1")],
      ["65세 이상", fmt(old / tot, "pct1")],
    ]) {
      const d = document.createElement("div");
      d.innerHTML = `<span class="k"></span><span class="v"></span>`;
      d.querySelector(".k")!.textContent = k;
      d.querySelector(".v")!.textContent = v;
      stats.appendChild(d);
    }
  };
  const frame = (i: number, animate: boolean) => {
    host.dataset.frame = String(fr.years[i]);
    label = `${fr.years[i]}년`;
    yearTxt!.textContent = String(fr.years[i]);
    projTxt!.textContent = fr.proj != null && fr.years[i] >= fr.proj ? "추계" : "실측";
    go(fr.m[i], fr.f[i], animate ? 320 : 0);
    paintStats(i);
  };
  const keep = host.dataset.frame ? fr.years.indexOf(Number(host.dataset.frame)) : -1;
  const startIdx = keep >= 0 ? keep : spec.start != null ? Math.max(0, fr.years.indexOf(spec.start)) : fr.years.length - 1;
  const projIdx = fr.proj != null ? fr.years.findIndex((y) => y >= fr.proj!) : undefined;
  makePlayer(ctl, fr.years, frame, { start: startIdx, speed: spec.speed ?? 260, autoplay: spec.autoplay && keep < 0, projFrom: projIdx, label: (i) => `${fr.years[i]}년` });
  if (anim && !spec.autoplay) {
    // 첫 등장: 0에서 시작 프레임까지 자라기
    const i = startIdx;
    host.dataset.frame = String(fr.years[i]);
    label = `${fr.years[i]}년`;
    yearTxt!.textContent = String(fr.years[i]);
    projTxt!.textContent = fr.proj != null && fr.years[i] >= fr.proj ? "추계" : "실측";
    paintStats(i);
    dataL = fr.m[i];
    dataR = fr.f[i];
    onVisible(svg, () => go(fr.m[i], fr.f[i], 900));
  } else frame(startIdx, false);
}

export function renderColumn(host: HTMLElement, spec: ColumnSpec) {
  host.innerHTML = "";
  const H = spec.height ?? 240;
  const W = Math.max(host.clientWidth, 280);
  const yf = spec.yFormat ?? "int";
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);
  const m = { t: 18, r: 8, b: 30, l: 48 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const vals = spec.values.map((v) => v ?? 0);
  let lo = Math.min(0, ...vals),
    hi = Math.max(0, ...vals);
  const ticks = niceTicks(lo, hi, 4);
  lo = ticks[0];
  hi = ticks[ticks.length - 1];
  const Y = (v: number) => m.t + ph - ((v - lo) / (hi - lo || 1)) * ph;
  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  box.appendChild(svg);
  const anim = shouldAnimate(host, spec.animate);
  if (anim) {
    svg.classList.add("will-grow");
    onVisible(svg, () => svg.classList.add("grown"));
  }
  for (const t of ticks) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(t), y2: Y(t), class: t === 0 ? "axis-line" : "grid-line" }, svg);
    const tx = el("text", { x: m.l - 8, y: Y(t) + 4, "text-anchor": "end" }, svg);
    tx.textContent = tick(t, yf);
  }
  const n = spec.categories.length;
  const slot = pw / n;
  const bw = Math.min(24, slot - 2);
  const tt = makeTooltip(box);
  const every = Math.ceil(n / Math.max(2, Math.floor(pw / 48)));
  spec.categories.forEach((c, i) => {
    const v = spec.values[i];
    const cx = m.l + slot * i + slot / 2;
    if (v != null) {
      const y0 = Y(0),
        y1 = Y(v);
      const top = Math.min(y0, y1),
        h = Math.max(Math.abs(y0 - y1), 1);
      const color = spec.colors?.[i] ?? (spec.highlight && !spec.highlight.includes(i) ? "var(--neutral-series)" : "var(--series-1)");
      const r = Math.min(4, h, bw / 2);
      const x = cx - bw / 2;
      const d =
        v >= 0
          ? `M${x},${top + h}V${top + r}Q${x},${top} ${x + r},${top}H${x + bw - r}Q${x + bw},${top} ${x + bw},${top + r}V${top + h}Z`
          : `M${x},${top}V${top + h - r}Q${x},${top + h} ${x + r},${top + h}H${x + bw - r}Q${x + bw},${top + h} ${x + bw},${top + h - r}V${top}Z`;
      const bar = el("path", { d, fill: color, class: v >= 0 ? "grow-up" : "grow-down" }, svg);
      bar.style.transitionDelay = `${Math.min(i * (600 / n), 600)}ms`;
    }
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
      title.textContent = c;
      tt.appendChild(title);
      ttRow(tt, spec.colors?.[i] ?? "var(--series-1)", "값", fmt(v, yf));
      placeTooltip(tt, box, e.clientX - r.left, Y(v ?? 0) - 20);
    });
    hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));
  });
}

export function render(host: HTMLElement, spec: ChartSpec) {
  if (spec.type === "line") renderLine(host, spec);
  else if (spec.type === "pyramid") renderPyramid(host, spec);
  else if (spec.type === "area") renderArea(host, spec);
  else if (spec.type === "scatter") renderScatter(host, spec);
  else if (spec.type === "stack") renderStack(host, spec);
  else if (spec.type === "race") renderRace(host, spec);
  else if (spec.type === "waffle") renderWaffle(host, spec);
  else renderColumn(host, spec);
}

const registry = new Map<HTMLElement, ChartSpec>();
export function mount(host: HTMLElement, spec: ChartSpec) {
  const fresh = !registry.has(host);
  registry.set(host, spec);
  if (fresh) firstRender.add(host);
  render(host, spec);
  firstRender.delete(host);
}
/** 프레임 재생형 차트는 리사이즈 때 다시 그리지 않는다(재생 상태 보존) */
const NO_RERENDER = new Set(["race", "waffle"]);
let raf = 0;
let lastW = 0;
if (typeof window !== "undefined") {
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastW) return;
    lastW = window.innerWidth;
    cancelAnimationFrame(raf);
    raf = requestAnimationFrame(() => registry.forEach((s, h) => (!h.isConnected ? registry.delete(h) : NO_RERENDER.has(s.type) ? null : render(h, s))));
  });
}

/** 페이지의 [data-chart] 요소를 자동으로 그린다 */
export function autoMount(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>("[data-chart]").forEach((host) => {
    if (host.dataset.mounted || host.closest("[hidden]")) return;
    host.dataset.mounted = "1";
    const src = host.querySelector<HTMLScriptElement>("script[type='application/json']");
    if (!src) return;
    const spec = JSON.parse(src.textContent || "{}") as ChartSpec;
    const target = document.createElement("div");
    host.appendChild(target);
    mount(target, spec);
  });
}
