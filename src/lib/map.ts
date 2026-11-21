// KoreaMap 클라이언트: 색 칠하기, 지표 토글, 연도 재생, 시도 확대, 툴팁, 순위 목록 연동.
import { makeBins, binOf, NO_DATA, type Bin } from "./scale";
import { fmt } from "./format";
import { makePlayer, type Player } from "./player";
import { tween, easeInOut } from "./anim";

interface Metric {
  key: string;
  label: string;
  format: any;
  kind: any;
  breaks: number[];
  mid?: number;
  desc?: string;
  higherIsBetter?: boolean;
  values?: Record<string, number | null>;
  frames?: { labels: (string | number)[]; values: Record<string, number | null>[]; start?: number; projFrom?: number };
}
interface Cfg {
  level: "sgg" | "sido";
  metrics: Metric[];
  names: Record<string, string>;
  links: Record<string, string>;
  notes: Record<string, string>;
  highlight?: string;
  zoom: boolean;
  rank: number | false;
  autoplay: boolean;
  speed?: number;
  only?: string;
  vb: number[];
  sidoBoxes: Record<string, number[]>;
  sidoOf: Record<string, string>;
  centroids: Record<string, [number, number]>;
  sizes: Record<string, [number, number]>;
}
const NS = "http://www.w3.org/2000/svg";
const SIDO_NAMES: Record<string, string> = { "11": "서울", "26": "부산", "27": "대구", "28": "인천", "29": "광주", "30": "대전", "31": "울산", "36": "세종", "41": "경기", "51": "강원", "43": "충북", "44": "충남", "52": "전북", "46": "전남", "47": "경북", "48": "경남", "50": "제주" };

export function mountMap(root: HTMLElement) {
  if (root.dataset.mounted) return;
  root.dataset.mounted = "1";
  const cfg = JSON.parse(root.querySelector<HTMLScriptElement>("script[type='application/json']")!.textContent || "{}") as Cfg;
  const svg = root.querySelector<SVGSVGElement>(".kmap-svg")!;
  const stage = root.querySelector<HTMLElement>(".kmap-stage")!;
  const tt = root.querySelector<HTMLElement>(".kmap-tt")!;
  const legendEl = root.querySelector<HTMLElement>(".kmap-legend")!;
  const rankHead = root.querySelector<HTMLElement>(".kmap-rank-head");
  const rankList = root.querySelector<HTMLOListElement>(".kmap-rank-list");
  const labelsG = root.querySelector<SVGGElement>(".kmap-labels")!;
  const hlG = root.querySelector<SVGGElement>(".kmap-hl")!;
  const back = root.querySelector<HTMLButtonElement>(".kmap-back")!;
  const zoomSel = root.querySelector<HTMLSelectElement>(".kmap-zoom");
  const desc = root.querySelector<HTMLElement>(".kmap-desc")!;
  const paths = new Map<string, SVGPathElement>();
  root.querySelectorAll<SVGPathElement>(".kmap-regions path").forEach((p) => paths.set(p.dataset.id!, p));

  let mi = 0;
  let fi = 0;
  let bins: Bin[] = [];
  let zoomed: string | null = null;
  let player: Player | null = null;
  let hover: string | null = null;
  let targetVB: number[] = svg.getAttribute("viewBox")!.split(" ").map(Number);

  const metric = () => cfg.metrics[mi];
  const valuesAt = (m: Metric, f: number) => (m.frames ? m.frames.values[Math.min(f, m.frames.values.length - 1)] : m.values ?? {});
  const cur = () => valuesAt(metric(), fi);
  const fullName = (id: string) => cfg.names[id] ?? id;

  // ---- 범례
  const drawLegend = () => {
    legendEl.innerHTML = "";
    bins.forEach((b, i) => {
      const k = document.createElement("span");
      k.className = "key";
      k.dataset.bin = String(i);
      const sw = document.createElement("span");
      sw.className = "swatch-rect";
      sw.style.background = b.color;
      k.append(sw, document.createTextNode(b.label));
      k.addEventListener("pointerenter", () => focusBin(i));
      k.addEventListener("pointerleave", () => focusBin(-1));
      legendEl.appendChild(k);
    });
    const nd = document.createElement("span");
    nd.className = "key";
    nd.innerHTML = '<span class="swatch-rect" style="background:var(--surface-2);outline:1px solid var(--border)"></span>자료 없음';
    legendEl.appendChild(nd);
  };
  const focusBin = (bi: number) => {
    const v = cur();
    svg.classList.toggle("bin-focus", bi >= 0);
    paths.forEach((p, id) => p.classList.toggle("in-bin", bi >= 0 && binOf(bins, v[id]) === bi));
  };

  // ---- 칠하기
  const paint = () => {
    const v = cur();
    paths.forEach((p, id) => {
      const i = binOf(bins, v[id]);
      p.style.fill = i < 0 ? NO_DATA : bins[i].color;
    });
    drawRank();
    drawLabels();
    if (hover) showTip(hover);
  };

  // ---- 순위
  const drawRank = () => {
    if (!rankList || cfg.rank === false) return;
    const m = metric();
    const v = cur();
    const pool = [...paths.keys()].filter((id) => v[id] != null && (!zoomed || cfg.sidoOf[id] === zoomed));
    pool.sort((a, b) => (v[b] as number) - (v[a] as number));
    const n = cfg.rank as number;
    const all = cfg.level === "sido" || zoomed || pool.length <= n * 2 + 1;
    const rows: (string | null)[] = all ? pool : [...pool.slice(0, n), null, ...pool.slice(-n)];
    const vals = pool.map((id) => v[id] as number);
    const maxAbs = Math.max(...vals.map(Math.abs), 1e-9);
    const hasNeg = vals.some((x) => x < 0);
    const hasPos = vals.some((x) => x > 0);
    const zero = hasNeg && hasPos ? 50 : hasNeg ? 100 : 0;
    const scale = hasNeg && hasPos ? 50 : 100;
    const lbl = m.frames ? ` · ${m.frames.labels[fi]}` : "";
    rankHead!.textContent = `${m.label}${lbl} · ${zoomed ? SIDO_NAMES[zoomed] + " " : ""}${all ? "전체 순위" : `상위·하위 ${n}곳`}`;
    rankList.innerHTML = "";
    rows.forEach((id) => {
      const li = document.createElement("li");
      if (id == null) {
        li.className = "gap";
        li.textContent = "⋯";
        rankList.appendChild(li);
        return;
      }
      const val = v[id] as number;
      const rank = pool.indexOf(id) + 1;
      const w = (Math.abs(val) / maxAbs) * scale;
      const neg = val < 0;
      const color = bins[binOf(bins, val)]?.color ?? NO_DATA;
      li.dataset.id = id;
      li.innerHTML = `<span class="r">${rank}</span><span class="n"></span><span class="t"><span class="f" style="${neg ? `right:${100 - zero}%` : `left:${zero}%`};width:${w}%;background:${color}"></span>${hasNeg && hasPos ? `<span class="z" style="left:${zero}%"></span>` : ""}</span><span class="v">${fmt(val, m.format)}</span>`;
      const nameEl = li.querySelector(".n")!;
      if (cfg.links[id]) {
        const a = document.createElement("a");
        a.href = cfg.links[id];
        a.textContent = fullName(id);
        nameEl.appendChild(a);
      } else nameEl.textContent = fullName(id);
      if (id === hover) li.classList.add("on");
      li.addEventListener("pointerenter", () => setHover(id, false));
      li.addEventListener("pointerleave", () => setHover(null, false));
      rankList.appendChild(li);
    });
  };

  // ---- 확대 시 시군구 이름 라벨
  const drawLabels = () => {
    labelsG.innerHTML = "";
    const showLabels = cfg.level === "sido" ? false : !!(zoomed || cfg.only);
    if (!showLabels) return;
    const box = zoomed ? cfg.sidoBoxes[zoomed] : cfg.vb.length ? [cfg.vb[0], cfg.vb[1], cfg.vb[0] + cfg.vb[2], cfg.vb[1] + cfg.vb[3]] : null;
    if (!box) return;
    // 화면에서 약 11px 이 되도록: (목표 viewBox 폭 ÷ 렌더 폭) × 11
    const rc = svg.getBoundingClientRect();
    const scale = Math.min((rc.width || 600) / targetVB[2], (rc.height || 600) / targetVB[3]);
    const fs = 11 / scale;
    const v = cur();
    paths.forEach((_, id) => {
      if (zoomed && cfg.sidoOf[id] !== zoomed) return;
      if (cfg.only && cfg.sidoOf[id] !== cfg.only) return;
      const c = cfg.centroids[id];
      const sz = cfg.sizes[id];
      if (!c || !sz) return;
      const nmLen = ((cfg.names[id] ?? "").split(" ").pop() ?? "").length;
      // 이름이 들어갈 만한 크기의 지역만 라벨 (작은 구는 툴팁으로)
      if (sz[0] < fs * nmLen * 0.9 || sz[1] < fs * 1.3) return;
      const withVal = sz[1] > fs * 2.6;
      const t = document.createElementNS(NS, "text");
      t.setAttribute("x", String(c[0]));
      t.setAttribute("y", String(c[1]));
      t.setAttribute("font-size", String(fs));
      t.setAttribute("text-anchor", "middle");
      const nm = (cfg.names[id] ?? "").split(" ").pop() ?? "";
      t.textContent = nm;
      const t2 = document.createElementNS(NS, "tspan");
      t2.setAttribute("x", String(c[0]));
      t2.setAttribute("dy", String(fs * 1.1));
      t2.setAttribute("class", "v");
      t2.textContent = v[id] == null ? "" : fmt(v[id], metric().format);
      if (withVal) t.appendChild(t2);
      labelsG.appendChild(t);
    });
  };

  // ---- 툴팁·호버
  const showTip = (id: string, ev?: PointerEvent | FocusEvent) => {
    const m = metric();
    const v = cur();
    const val = v[id];
    tt.innerHTML = "";
    const h = document.createElement("div");
    h.className = "tt-title";
    h.textContent = fullName(id) + (m.frames ? ` · ${m.frames.labels[fi]}` : "");
    tt.appendChild(h);
    const row = (name: string, value: string, strong = false) => {
      const r = document.createElement("div");
      r.className = "tt-row";
      r.innerHTML = `<span class="tt-key"></span><span class="tt-val"></span>`;
      r.querySelector(".tt-key")!.textContent = name;
      const vv = r.querySelector<HTMLElement>(".tt-val")!;
      vv.textContent = value;
      if (!strong) vv.style.fontWeight = "600";
      tt.appendChild(r);
    };
    row(m.label, val == null ? "자료 없음" : fmt(val, m.format), true);
    // 같은 시점의 다른 지표
    // 지표마다 연도 범위가 달라(예: 2025~ 와 2015~) 순번이 아니라 같은 연도(label)로 찾는다. 그 해가 없으면 뺀다.
    const label = m.frames?.labels[fi];
    cfg.metrics.forEach((o, j) => {
      if (j === mi) return;
      let oi = 0;
      if (o.frames) {
        oi = label != null ? o.frames.labels.indexOf(label) : (o.frames.start ?? o.frames.labels.length - 1);
        if (oi < 0) return;
      }
      const ov = valuesAt(o, oi)[id];
      if (ov != null) row(o.label, fmt(ov, o.format));
    });
    if (val != null) {
      const pool = [...paths.keys()].filter((k) => v[k] != null);
      const rank = pool.filter((k) => (v[k] as number) > (val as number)).length + 1;
      row("순위", `${rank} / ${pool.length}`);
    }
    if (cfg.notes[id]) {
      const n = document.createElement("div");
      n.className = "tt-note";
      n.textContent = cfg.notes[id];
      tt.appendChild(n);
    }
    if (cfg.links[id]) {
      const n = document.createElement("div");
      n.className = "tt-note";
      n.textContent = cfg.zoom && !zoomed ? "클릭: 시도 확대" : "클릭: 상세 보기";
      tt.appendChild(n);
    }
    // 위치
    const sr = stage.getBoundingClientRect();
    let x: number, y: number;
    if (ev && "clientX" in ev) {
      x = ev.clientX - sr.left;
      y = ev.clientY - sr.top;
    } else {
      const p = paths.get(id)!.getBoundingClientRect();
      x = p.left + p.width / 2 - sr.left;
      y = p.top + p.height / 2 - sr.top;
    }
    const w = tt.offsetWidth;
    let left = x + 16;
    if (left + w > sr.width) left = x - w - 16;
    tt.style.left = Math.max(0, left) + "px";
    tt.style.top = Math.max(0, Math.min(sr.height - tt.offsetHeight, y - 20)) + "px";
    tt.style.opacity = "1";
  };
  const setHover = (id: string | null, fromMap: boolean, ev?: PointerEvent | FocusEvent) => {
    hover = id;
    hlG.querySelectorAll(".hov").forEach((n) => n.remove());
    if (id) {
      const p = paths.get(id);
      if (p) {
        const c = document.createElementNS(NS, "path");
        c.setAttribute("d", p.getAttribute("d")!);
        c.setAttribute("class", "hov");
        hlG.appendChild(c);
      }
      showTip(id, ev);
    } else tt.style.opacity = "0";
    rankList?.querySelectorAll("li").forEach((li) => li.classList.toggle("on", li.dataset.id === id));
    if (fromMap && id) rankList?.querySelector(`li[data-id="${id}"]`)?.scrollIntoView({ block: "nearest" });
  };

  paths.forEach((p, id) => {
    p.addEventListener("pointermove", (e) => setHover(id, true, e));
    p.addEventListener("pointerleave", () => setHover(null, true));
    p.addEventListener("focus", (e) => setHover(id, true, e));
    p.addEventListener("blur", () => setHover(null, true));
    const activate = () => {
      if (cfg.zoom && !zoomed && cfg.sidoOf[id]) return zoomTo(cfg.sidoOf[id]);
      if (cfg.links[id]) location.href = cfg.links[id];
    };
    p.addEventListener("click", activate);
    p.addEventListener("keydown", (e) => {
      if (e.key === "Enter") activate();
    });
  });
  svg.addEventListener("pointerleave", () => setHover(null, true));

  // ---- 확대
  let cancelZoom = () => {};
  const curVB = () => svg.getAttribute("viewBox")!.split(" ").map(Number);
  const animateVB = (to: number[]) => {
    targetVB = to;
    cancelZoom();
    const from = curVB();
    cancelZoom = tween(
      700,
      (k) => svg.setAttribute("viewBox", from.map((f, i) => (f + (to[i] - f) * k).toFixed(2)).join(" ")),
      undefined,
      easeInOut,
    );
  };
  const zoomTo = (sd: string | null) => {
    zoomed = sd;
    if (zoomSel) zoomSel.value = sd ?? "";
    back.hidden = !sd;
    root.classList.toggle("is-zoomed", !!sd);
    paths.forEach((p, id) => p.classList.toggle("dim", !!sd && cfg.sidoOf[id] !== sd));
    if (sd) {
      const b = cfg.sidoBoxes[sd];
      const w = b[2] - b[0],
        h = b[3] - b[1];
      const pad = Math.max(w, h) * 0.08;
      // 무대 비율에 맞춘다
      const ar = cfg.vb[2] / cfg.vb[3];
      let vw = w + pad * 2,
        vh = h + pad * 2;
      if (cfg.only) {
        vw = w + pad * 2;
        vh = h + pad * 2;
      } else if (vw / vh > ar) vh = vw / ar;
      else vw = vh * ar;
      animateVB([b[0] + w / 2 - vw / 2, b[1] + h / 2 - vh / 2, vw, vh]);
    } else animateVB(cfg.vb);
    setHover(null, false);
    paint();
  };
  back.addEventListener("click", () => zoomTo(null));
  let rw = 0;
  window.addEventListener("resize", () => {
    if (window.innerWidth === rw) return;
    rw = window.innerWidth;
    drawLabels();
  });
  zoomSel?.addEventListener("change", () => zoomTo(zoomSel.value || null));

  // ---- 지표·재생기
  const playerHost = root.querySelector<HTMLElement>(".kmap-player")!;
  let ready = false;
  const setMetric = (i: number) => {
    const prevLabel = ready ? metric().frames?.labels[fi] : undefined;
    ready = true;
    mi = i;
    const m = metric();
    bins = makeBins(m.breaks, m.kind, m.format, m.mid);
    drawLegend();
    desc.textContent = m.desc ?? "";
    desc.hidden = !m.desc || !!cfg.only;
    root.querySelectorAll<HTMLButtonElement>("[data-metric]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.metric) === i)));
    playerHost.innerHTML = "";
    player = null;
    if (m.frames && m.frames.labels.length > 1) {
      // 같은 연도 유지
      const keep = prevLabel != null ? m.frames.labels.indexOf(prevLabel) : -1;
      fi = keep >= 0 ? keep : (m.frames.start ?? m.frames.labels.length - 1);
      player = makePlayer(
        playerHost,
        m.frames.labels,
        (k) => {
          fi = k;
          paint();
        },
        { start: fi, speed: cfg.speed ?? 420, projFrom: m.frames.projFrom, autoplay: cfg.autoplay && i === 0, label: (k) => String(m.frames!.labels[k]) + (m.frames!.projFrom != null && k >= m.frames!.projFrom ? " 추계" : "") },
      );
    } else fi = 0;
    paint();
  };
  root.querySelectorAll<HTMLButtonElement>("[data-metric]").forEach((b) => b.addEventListener("click", () => setMetric(Number(b.dataset.metric))));
  setMetric(0);
}

export function autoMountMaps(root: ParentNode = document) {
  root.querySelectorAll<HTMLElement>("[data-kmap]").forEach(mountMap);
}
