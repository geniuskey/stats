// 세대 이동 피라미드: 1세 단위 막대가 해마다 한 칸씩 위로 올라간다.
// 연도 사이를 막대 폭만 바꿔 보간하는 대신, 같은 해 태어난 사람들(코호트)의 줄 자체가 위로 미끄러지며
// 폭이 사망·이동만큼 줄어든다. 맨 아래에서는 그해 태어난 아이들이 들어온다.
// 이름 붙은 세대(베이비붐 등)는 진하게, 나머지는 옅게 칠하고 오른쪽 여백에 세대 이름과 지금 나이를 따라 붙인다.
import { fmt, tick } from "./format";
import { el, legend, makeTooltip, ttRow, placeTooltip } from "./charts";
import { makePlayer } from "./player";
import { getBorn } from "./born";

export interface CohortSpec {
  type: "cohort";
  years: number[];
  /** [연도][나이 0..100] (100 = 100세 이상) */
  m: number[][];
  f: number[][];
  proj?: number; // 첫 추계 연도
  generations?: { name: string; short?: string; from: number; to: number }[]; // 출생연도 구간
  refYear?: number; // 가는 선으로 고정해 둘 비교 연도
  start?: number; // 시작 연도
  speed?: number; // 1년에 걸리는 ms
  height?: number;
  me?: boolean; // 내 출생연도 줄을 따로 칠하고 나이를 따라 붙인다
}

export function renderCohort(host: HTMLElement, spec: CohortSpec) {
  host.innerHTML = "";
  const { years, m: M, f: F } = spec;
  const n = years.length;
  const NA = M[0].length; // 101
  const W = Math.max(host.clientWidth, 280);
  const H = spec.height ?? 420;
  const narrow = W < 480;
  const gens = spec.generations ?? [];
  const gutter = gens.length ? (narrow ? 66 : 112) : 0;
  const refIdx = spec.refYear != null ? years.indexOf(spec.refYear) : -1;

  const items: { name: string; color: string; kind: "line" | "dash" | "rect" }[] = [
    { name: "남자", color: "var(--series-1)", kind: "rect" },
    { name: "여자", color: "var(--series-2)", kind: "rect" },
  ];
  if (refIdx >= 0) items.push({ name: `${spec.refYear}년`, color: "var(--text-primary)", kind: "line" });
  if (spec.me && getBorn() != null) items.push({ name: `나 (${getBorn()}년생)`, color: "var(--me)", kind: "rect" });
  legend(host, items);
  const box = document.createElement("div");
  box.style.position = "relative";
  host.appendChild(box);

  const plotW = W - gutter;
  const mid = plotW / 2;
  const gap = narrow ? 15 : 20; // 가운데 나이 눈금 자리
  const mt = 6,
    mb = 22;
  const ph = H - mt - mb;
  const rh = ph / NA; // 한 살 = 한 줄
  const base = mt + ph; // 0세 줄의 아래 끝
  const Y = (pos: number) => base - pos * rh; // 줄 아래 끝의 y (pos = 나이, 소수 가능)
  const maxV = Math.max(...M.flat(), ...F.flat(), 1);
  const half = mid - gap - 2;
  const S = (v: number) => (v / maxV) * half;

  const svg = el("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" });
  svg.setAttribute("aria-label", `인구 피라미드 ${years[0]}~${years[n - 1]}년, 1세 단위. 재생하면 같은 해 태어난 사람들이 해마다 한 줄씩 위로 올라갑니다.`);
  box.appendChild(svg);
  const tt = makeTooltip(box);

  const yearTxt = el("text", { x: 2, y: mt + 30, class: "pyr-year" }, svg);
  const projTxt = el("text", { x: 4, y: mt + 50, class: "label" }, svg);

  // 줄이 0세 아래·100세 위로 삐져나가지 않게 자른다
  const cid = `coh${Math.random().toString(36).slice(2, 8)}`;
  const cp = el("clipPath", { id: cid }, el("defs", {}, svg));
  el("rect", { x: 0, y: Y(NA), width: plotW, height: NA * rh }, cp);
  const g = el("g", { "clip-path": `url(#${cid})` }, svg);
  const dimL = el("path", { fill: "var(--series-1)", "fill-opacity": gens.length ? 0.42 : 1 }, g);
  const dimR = el("path", { fill: "var(--series-2)", "fill-opacity": gens.length ? 0.42 : 1 }, g);
  const hiL = el("path", { fill: "var(--series-1)" }, g);
  const hiR = el("path", { fill: "var(--series-2)" }, g);
  const born = spec.me ? getBorn() : null;
  const meP = el("path", { fill: "var(--me)" }, g);

  // 나이 눈금 (가운데)
  for (let a = 0; a <= 100; a += narrow ? 20 : 10) {
    const t = el("text", { x: mid, y: Y(a + 0.5) + 4, "text-anchor": "middle" }, svg);
    t.textContent = a === 100 ? "100+" : String(a);
  }
  const t1 = el("text", { x: mid - gap, y: H - 6, "text-anchor": "end" }, svg);
  t1.textContent = tick(maxV, "int") + " ←";
  const t2 = el("text", { x: mid + gap, y: H - 6 }, svg);
  t2.textContent = "→ " + tick(maxV, "int");

  // 비교 연도 외곽선 (고정)
  if (refIdx >= 0) {
    let dl = "",
      dr = "";
    for (let a = 0; a < NA; a++) {
      const y0 = Y(a),
        y1 = Y(a + 1);
      const lx = mid - gap - S(M[refIdx][a]),
        rx = mid + gap + S(F[refIdx][a]);
      dl += (a ? "L" : "M") + `${lx.toFixed(1)},${y0.toFixed(1)}L${lx.toFixed(1)},${y1.toFixed(1)}`;
      dr += (a ? "L" : "M") + `${rx.toFixed(1)},${y0.toFixed(1)}L${rx.toFixed(1)},${y1.toFixed(1)}`;
    }
    for (const d of [dl, dr]) el("path", { d, fill: "none", stroke: "var(--text-primary)", "stroke-width": 1.25, "stroke-opacity": 0.7, "stroke-linejoin": "round" }, svg);
  }

  // 세대 표시: 오른쪽 여백의 가는 괄호 + 이름 + 지금 나이
  const genEls = gens.map((gn) => {
    const gg = el("g", { class: "coh-gen" }, svg);
    const line = el("path", { fill: "none", stroke: "var(--text-secondary)", "stroke-width": 1 }, gg);
    const name = el("text", { x: plotW + 10, class: "coh-gen-name" }, gg);
    name.textContent = narrow ? (gn.short ?? gn.name) : gn.name;
    const age = el("text", { x: plotW + 10, class: "coh-gen-age" }, gg);
    return { gn, gg, line, name, age };
  });

  const meTxt = el("text", { x: 4, class: "label-strong halo" }, svg);
  meTxt.style.fill = "var(--me)";
  const meLine = el("line", { stroke: "var(--me)", "stroke-width": 1, "stroke-dasharray": "2 2" }, svg);
  const inGen = (born: number) => gens.some((gn) => born >= gn.from && born <= gn.to);
  const bar = (x: number, w: number, pos: number) => {
    if (w <= 0.05) return "";
    const y = Y(pos + 1) + 0.35;
    const h = Math.max(rh - 0.7, 0.5); // 해마다 한 줄이 보이도록 아주 얇은 틈
    return `M${x.toFixed(1)},${y.toFixed(2)}h${w.toFixed(1)}v${h.toFixed(2)}h${(-w).toFixed(1)}Z`;
  };

  let cur = 0;
  let shownYear = -1;
  const stats = document.createElement("div");
  stats.className = "pyr-stats";
  const paintStats = (i: number) => {
    const tot = M[i].reduce((a, b) => a + b, 0) + F[i].reduce((a, b) => a + b, 0);
    const sum = (lo: number, hi: number) => {
      let s = 0;
      for (let a = lo; a < hi; a++) s += M[i][a] + F[i][a];
      return s;
    };
    const kid = sum(0, 15),
      old = sum(65, NA);
    stats.innerHTML = "";
    for (const [k, v] of [
      ["총인구", fmt(tot, "man")],
      ["0~14세", fmt(kid / tot, "pct1")],
      ["15~64세", fmt((tot - kid - old) / tot, "pct1")],
      ["65세 이상", fmt(old / tot, "pct1")],
    ]) {
      const d = document.createElement("div");
      d.innerHTML = `<span class="k"></span><span class="v"></span>`;
      d.querySelector(".k")!.textContent = k;
      d.querySelector(".v")!.textContent = v;
      stats.appendChild(d);
    }
  };

  /** t: 소수 프레임. i년 모습에서 k만큼 다음 해로 간 장면 */
  const draw = (t: number) => {
    cur = t;
    let i = Math.floor(t),
      k = t - i;
    if (i >= n - 1) (i = n - 1), (k = 0);
    const nx = Math.min(i + 1, n - 1);
    let dL = "",
      dR = "",
      hL = "",
      hR = "",
      mP = "";
    const put = (b: number | null, pos: number, vm: number, vf: number) => {
      const lw = S(vm),
        rw = S(vf);
      const l = bar(mid - gap - lw, lw, pos),
        r = bar(mid + gap, rw, pos);
      if (b != null && b === born) mP += l + r;
      else if (b != null && inGen(b)) (hL += l), (hR += r);
      else (dL += l), (dR += r);
    };
    // 100세 이상: 제자리에서 폭만 바뀐다
    put(null, NA - 1, M[i][NA - 1] + (M[nx][NA - 1] - M[i][NA - 1]) * k, F[i][NA - 1] + (F[nx][NA - 1] - F[i][NA - 1]) * k);
    for (let a = 0; a < NA - 1; a++) {
      // 같은 코호트: i년 a세 → 다음 해 a+1세 (99세는 100세 이상 묶음으로 들어가므로 줄어드는 정도만 흉내)
      const tm = a + 1 < NA - 1 ? M[nx][a + 1] : Math.min(M[i][a], M[nx][NA - 1]);
      const tf = a + 1 < NA - 1 ? F[nx][a + 1] : Math.min(F[i][a], F[nx][NA - 1]);
      put(years[i] - a, a + k, M[i][a] + (tm - M[i][a]) * k, F[i][a] + (tf - F[i][a]) * k);
    }
    // 새로 태어난 아이들: 0세 줄 아래에서 밀려 올라온다
    if (k > 0) put(years[nx], k - 1, M[nx][0], F[nx][0]);
    dimL.setAttribute("d", dL);
    dimR.setAttribute("d", dR);
    hiL.setAttribute("d", hL);
    hiR.setAttribute("d", hR);
    meP.setAttribute("d", mP);
    // 내 줄: 왼쪽 끝에 나이 라벨, 줄까지 점선
    const myPos = born != null ? years[i] + k - born : -1;
    if (born != null && myPos >= -0.5 && myPos < NA - 1) {
      const yc = Y(Math.max(0, myPos) + 0.5);
      const ag = Math.max(0, years[i] - born);
      meTxt.textContent = narrow ? `나 ${ag}세` : `나 ${ag}세 (${born}년생)`;
      meTxt.setAttribute("y", (yc + 4).toFixed(1));
      meTxt.removeAttribute("visibility");
      const tw = (meTxt as SVGTextElement).getComputedTextLength?.() || 60;
      const lx = mid - gap - S(M[i][Math.min(NA - 1, Math.max(0, Math.round(myPos)))]);
      meLine.setAttribute("x1", (4 + tw + 4).toFixed(1));
      meLine.setAttribute("x2", Math.max(4 + tw + 4, lx - 2).toFixed(1));
      meLine.setAttribute("y1", yc.toFixed(1));
      meLine.setAttribute("y2", yc.toFixed(1));
      meLine.setAttribute("visibility", lx - 2 > 4 + tw + 8 ? "visible" : "hidden");
    } else {
      meTxt.setAttribute("visibility", "hidden");
      meLine.setAttribute("visibility", "hidden");
    }

    const now = years[i] + k; // 연속 시각
    for (const { gn, gg, line, name, age } of genEls) {
      const lo = Math.max(0, now - gn.to), // 가장 어린 쪽 줄 아래 끝
        hi = Math.min(NA, now - gn.from + 1);
      if (hi <= lo) {
        gg.setAttribute("visibility", "hidden");
        continue;
      }
      gg.removeAttribute("visibility");
      const yb = Y(lo),
        yt = Y(hi);
      const x = plotW + 4;
      line.setAttribute("d", `M${x},${yt.toFixed(1)}h3V${yb.toFixed(1)}h-3`);
      const cy = (yb + yt) / 2;
      name.setAttribute("y", (cy - 1).toFixed(1));
      age.setAttribute("y", (cy + 12).toFixed(1));
      const a0 = Math.floor(years[i] - gn.to),
        a1 = Math.floor(years[i] - gn.from);
      age.textContent = `${Math.max(0, a0)}~${a1}세`;
    }

    if (years[i] !== shownYear) {
      shownYear = years[i];
      host.dataset.frame = String(years[i]);
      yearTxt.textContent = String(years[i]);
      projTxt.textContent = spec.proj != null && years[i] >= spec.proj ? "추계" : "실측";
      paintStats(i);
    }
  };

  // 툴팁: 가리킨 줄의 나이·출생연도 (지금 보이는 해 기준)
  const hit = el("rect", { x: 0, y: Y(NA), width: plotW, height: NA * rh, fill: "transparent" }, svg);
  hit.addEventListener("pointermove", (e) => {
    const r = svg.getBoundingClientRect();
    const py = e.clientY - r.top;
    const i = Math.min(Math.floor(cur), n - 1);
    const k = cur - i;
    const a = Math.max(0, Math.min(NA - 1, Math.floor((base - py) / rh - (i < n - 1 ? k : 0))));
    tt.innerHTML = "";
    const title = document.createElement("div");
    title.className = "tt-title";
    title.textContent = `${a === NA - 1 ? "100세 이상" : `${a}세`} · ${years[i]}년` + (a < NA - 1 ? ` (${years[i] - a}년생)` : "");
    tt.appendChild(title);
    ttRow(tt, "var(--series-1)", "남자", fmt(M[i][a], "int"));
    ttRow(tt, "var(--series-2)", "여자", fmt(F[i][a], "int"));
    if (refIdx >= 0 && refIdx !== i) ttRow(tt, "var(--text-primary)", `${spec.refYear}년 같은 나이`, fmt(M[refIdx][a] + F[refIdx][a], "int"));
    placeTooltip(tt, box, e.clientX - r.left, py);
  });
  hit.addEventListener("pointerleave", () => (tt.style.opacity = "0"));

  const ctl = document.createElement("div");
  host.append(ctl, stats);
  const keep = host.dataset.frame ? years.indexOf(Number(host.dataset.frame)) : -1;
  const startIdx = keep >= 0 ? keep : spec.start != null ? Math.max(0, years.indexOf(spec.start)) : 0;
  const projIdx = spec.proj != null ? years.findIndex((y) => y >= spec.proj!) : undefined;
  makePlayer(ctl, years, (i) => draw(i), { start: startIdx, speed: spec.speed ?? 520, projFrom: projIdx, label: (i) => `${years[i]}년`, smooth: draw });
  draw(startIdx);
}
