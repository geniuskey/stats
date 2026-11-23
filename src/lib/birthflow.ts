// 출생 → 입학 흐름: 해마다 태어난 아이 수 막대가 lag년 오른쪽으로 같은 속력으로 미끄러져 입학 연도에 도착한다.
// 가는 동안 높이는 출생아 → 입학자(실측) 또는 입학 수요(추계)로 바뀌고, 도착하면 '지금 입학 규모' 선 아래 모자란 만큼이
// 점선 상자(빈 자리)로 드러난다. 가로축은 하나의 달력 연도: 막대의 위치 = 그 세대가 k살이 되는 해.
import { fmt, tick } from "./format";
import { el, legend, makeTooltip, ttRow, placeTooltip, niceTicks } from "./charts";
import { makePlayer } from "./player";
import { people } from "./profile";

export interface BirthFlowSpec {
  type: "birthflow";
  born: number[]; // 출생연도
  births: number[]; // 출생아 수
  estFrom?: number; // 이 출생연도부터 출생아가 추정치
  landing: number[]; // born[i] + lag 년의 입학자(실측) 또는 입학 수요(추계)
  actualTo: number; // 이 입학 연도까지 landing은 실제 입학자
  lag: number; // 출생 → 입학 (19: Y년 입학 = Y−1년 말 18세 = Y−19년생)
  cap: number; // 지금 입학 규모
  capLabel?: string;
  marks?: number[]; // 이름표를 달고 따라갈 출생연도
  speed?: number; // 1년 이동에 걸리는 ms
  height?: number;
  me?: boolean; // 나·자녀 출생연도 막대를 따로 칠하고 이름표를 단다
}

export function renderBirthFlow(host: HTMLElement, spec: BirthFlowSpec) {
  host.innerHTML = "";
  const { born, births, landing, lag, cap } = spec;
  const n = born.length;
  const W = Math.max(host.clientWidth, 280);
  const H = spec.height ?? 340;
  const narrow = W < 520;
  // 그림 범위 안에 있는 나·자녀
  const ppl = (spec.me ? people() : []).filter((pp) => born.includes(pp.born));
  const colorOf = (b: number) => ppl.find((pp) => pp.born === b)?.color;
  legend(host, [
    { name: "출생아 → 입학자", color: "var(--series-1)", kind: "rect" },
    { name: `${spec.capLabel ?? "지금 입학 규모"} ${tick(cap, "man")}`, color: "var(--text-primary)", kind: "dash" },
    { name: "빈 자리", color: "var(--critical)", kind: "dash" },
    ...ppl.map((pp) => ({ name: pp.kid ? `${pp.who} 아이` : `나 (${pp.born}년생)`, color: pp.color, kind: "rect" as const })),
  ]);
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);

  const m = { t: 14, r: 10, b: 26, l: narrow ? 40 : 48 };
  const pw = W - m.l - m.r,
    ph = H - m.t - m.b;
  const x0 = born[0] - 0.5,
    x1 = born[n - 1] + lag + 0.5;
  const X = (yr: number) => m.l + ((yr - x0) / (x1 - x0)) * pw;
  const slot = pw / (x1 - x0);
  const bw = Math.max(1.5, slot * 0.7);
  const maxV = Math.max(...births, ...landing, cap);
  const yt = niceTicks(0, maxV, 4);
  const top = yt[yt.length - 1];
  const Y = (v: number) => m.t + ph - (v / top) * ph;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.setAttribute("aria-label", `${born[0]}~${born[n - 1]}년 출생아가 ${lag}년 뒤 대학 입학 연도로 옮겨 가는 그림. 지금 입학 규모 ${fmt(cap, "int")}명과 비교.`);
  box.appendChild(svg);
  const tt = makeTooltip(box);

  // 추계 구간 배경 (실제 입학자 이후)
  const pz = X(spec.actualTo + 0.5);
  el("rect", { x: pz, y: m.t, width: Math.max(0, m.l + pw - pz), height: ph, class: "proj-zone" }, svg);
  const pzt = el("text", { x: pz + 4, y: m.t + 12, class: "label" }, svg);
  pzt.textContent = "추계";
  for (const v of yt) {
    el("line", { x1: m.l, x2: m.l + pw, y1: Y(v), y2: Y(v), class: "grid-line" }, svg);
    const t = el("text", { x: m.l - 6, y: Y(v) + 4, "text-anchor": "end" }, svg);
    t.textContent = tick(v, "man");
  }
  const step = narrow ? 10 : 5;
  for (let yr = Math.ceil(x0 / step) * step; yr <= x1; yr += step) {
    const t = el("text", { x: X(yr), y: H - 8, "text-anchor": "middle" }, svg);
    t.textContent = String(yr);
  }
  el("line", { x1: m.l, x2: m.l + pw, y1: Y(0), y2: Y(0), class: "axis-line" }, svg);

  // 큰 단계 표시: 출생 → n년 뒤 → 대학 입학
  const stage = el("text", { x: m.l + pw - 4, y: m.t + 40, "text-anchor": "end", class: "pyr-year" }, svg);

  const gGap = el("g", {}, svg);
  const gBar = el("g", {}, svg);
  const bars = born.map((b) => el("rect", { width: bw, rx: Math.min(2, bw / 3), fill: colorOf(b) ?? "var(--series-1)", "fill-opacity": spec.estFrom != null && b >= spec.estFrom ? 0.5 : 1 }, gBar));
  const gaps = born.map(() => el("rect", { width: bw, fill: "none", stroke: "var(--critical)", "stroke-width": 1, "stroke-dasharray": "3 2" }, gGap));

  // 지금 입학 규모 선: 입학 연도 범위에만
  const capY = Y(cap);
  el("line", { x1: X(born[0] + lag - 0.5), x2: m.l + pw, y1: capY, y2: capY, stroke: "var(--text-primary)", "stroke-width": 1.5, "stroke-dasharray": "5 3" }, svg);

  // 따라가는 이름표
  // 내 출생연도 이름표를 더한다. 가까운(3년 이내) 기본 이름표는 겹치지 않게 뺀다
  const markYears = [...(spec.marks ?? []).filter((b) => ppl.every((pp) => Math.abs(b - pp.born) > 3)), ...ppl.map((pp) => pp.born)];
  const marks = markYears.map((b) => {
    const i = born.indexOf(b);
    const g = el("g", {}, svg);
    const ln = el("line", { stroke: colorOf(b) ?? "var(--text-secondary)", "stroke-width": 1 }, g);
    const t = el("text", { "text-anchor": "middle", class: "coh-gen-name halo" }, g);
    if (colorOf(b)) t.style.fill = colorOf(b)!;
    return { i, g, ln, t };
  }).filter((mk) => mk.i >= 0);

  const emptyTxt = el("text", { "text-anchor": "end", class: "label halo", fill: "var(--critical)" }, svg);
  emptyTxt.style.fill = "var(--critical)";
  // 빈 자리가 가장 큰 해 (도착 장면에서 숫자로)
  let worst = -1;
  for (let i = 0; i < n; i++) if (born[i] + lag > spec.actualTo && (worst < 0 || landing[i] < landing[worst])) worst = i;

  let cur = 0;
  const label = (k: number) => (k <= 0 ? "출생" : k >= lag ? "대학 입학" : `${Math.floor(k)}년 뒤`);
  const draw = (k: number) => {
    cur = k;
    const f = k / lag;
    const show = Math.max(0, (k - (lag - 3)) / 3); // 마지막 3년 동안 빈 자리가 드러난다 (일정한 비율)
    for (let i = 0; i < n; i++) {
      const v = births[i] + (landing[i] - births[i]) * f;
      const cx = X(born[i] + k);
      const y = Y(v);
      bars[i].setAttribute("x", (cx - bw / 2).toFixed(1));
      bars[i].setAttribute("y", y.toFixed(1));
      bars[i].setAttribute("height", Math.max(0, Y(0) - y).toFixed(1));
      const gapH = y - capY;
      const g = gaps[i];
      if (show > 0 && gapH > 0.5 && born[i] + lag > spec.actualTo) {
        g.setAttribute("x", (cx - bw / 2).toFixed(1));
        g.setAttribute("y", capY.toFixed(1));
        g.setAttribute("height", gapH.toFixed(1));
        g.setAttribute("opacity", Math.min(1, show).toFixed(2));
        g.removeAttribute("visibility");
      } else g.setAttribute("visibility", "hidden");
    }
    for (const mk of marks) {
      const v = births[mk.i] + (landing[mk.i] - births[mk.i]) * f;
      const cx = X(born[mk.i] + k);
      const yb = Y(v);
      mk.ln.setAttribute("x1", cx.toFixed(1));
      mk.ln.setAttribute("x2", cx.toFixed(1));
      mk.ln.setAttribute("y1", (yb - 12).toFixed(1));
      mk.ln.setAttribute("y2", (yb - 2).toFixed(1));
      mk.t.setAttribute("x", Math.max(m.l + 40, Math.min(m.l + pw - 60, cx)).toFixed(1));
      mk.t.setAttribute("y", (yb - 16).toFixed(1));
      const yr = born[mk.i] + Math.floor(k);
      const who = ppl.find((pp) => pp.born === born[mk.i]);
      const nm = who && !who.kid ? `나 ${born[mk.i]}` : `${born[mk.i]}년생`;
      mk.t.textContent = k >= lag ? (narrow ? `${born[mk.i]}→${born[mk.i] + lag}` : `${nm} → ${born[mk.i] + lag} 입학`) : nm;
      mk.g.setAttribute("data-year", String(yr));
    }
    if (worst >= 0 && show >= 1) {
      emptyTxt.setAttribute("x", (m.l + pw - 2).toFixed(1)); // 오른쪽 끝에 붙여 잘리지 않게
      emptyTxt.setAttribute("y", (capY - 8).toFixed(1));
      emptyTxt.textContent = `${born[worst] + lag}년 빈 자리 ${tick(cap - landing[worst], "man")}`;
      emptyTxt.removeAttribute("visibility");
    } else emptyTxt.setAttribute("visibility", "hidden");
    stage.textContent = label(k);
    host.dataset.frame = String(Math.round(k));
  };

  // 툴팁: 가장 가까운 막대 (지금 위치 기준)
  const hit = el("rect", { x: m.l, y: m.t, width: pw, height: ph, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = e.clientX - r.left;
    const yr = x0 + ((px - m.l) / pw) * (x1 - x0) - cur;
    const i = Math.round(yr) - born[0];
    if (i < 0 || i >= n) return void (tt.style.opacity = "0");
    const Yr = born[i] + lag;
    tt.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tt-title";
    title.textContent = `${born[i]}년생 → ${Yr}년 입학`;
    tt.appendChild(title);
    ttRow(tt, "var(--series-1)", spec.estFrom != null && born[i] >= spec.estFrom ? "출생아 (추정)" : "출생아", fmt(births[i], "int"));
    ttRow(tt, "var(--series-1)", Yr <= spec.actualTo ? "실제 입학자" : "입학 수요 (추계)", fmt(landing[i], "int"));
    if (Yr > spec.actualTo) ttRow(tt, "var(--critical)", "빈 자리", fmt(Math.max(0, cap - landing[i]), "int"));
    placeTooltip(tt, box, px, e.clientY - r.top);
  });
  hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));

  const ctl = document.createElement("div");
  host.appendChild(ctl);
  const frames = Array.from({ length: lag + 1 }, (_, k) => k);
  const keep = host.dataset.frame != null ? Number(host.dataset.frame) : 0;
  makePlayer(ctl, frames.map((k) => label(k)), (i) => draw(i), { start: keep, speed: spec.speed ?? 650, label: (i) => label(i), smooth: draw });
  draw(keep);
}
