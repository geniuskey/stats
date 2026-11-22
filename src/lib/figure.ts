// 그림 하단 도구: CSV 내려받기 · 인용 문구 복사 · 그림 링크 복사.
// 자료는 화면에 이미 있는 것(표로 보기 표 → 차트 spec JSON → 지도 설정 JSON 순)에서 꺼내므로 따로 싣지 않는다.

type Row = (string | number | null)[];

const SIDO_ORDER_NOTE = "지역 코드는 행정표준코드(시도 2자리, 시군구 5자리)입니다.";

function tableRows(fig: HTMLElement): Row[] | null {
  const t = fig.querySelector<HTMLTableElement>(".table-view table");
  if (!t) return null;
  return [...t.rows].map((tr) => [...tr.cells].map((c) => c.textContent?.trim() ?? ""));
}

const xLabel = (x: number, xf?: string) => (xf === "ym" ? `${Math.floor(x / 12)}-${String((x % 12) + 1).padStart(2, "0")}` : String(x));

// 보이는 패널의 차트 spec (ChartSwitch는 지금 고른 형태)
function specRows(fig: HTMLElement): Row[] | null {
  const panel = fig.querySelector<HTMLElement>(".cs-panel:not([hidden])") ?? fig;
  const src = panel.querySelector<HTMLScriptElement>("[data-chart] script[type='application/json']");
  if (!src) return null;
  const s = JSON.parse(src.textContent || "{}");
  if (s.type === "line" || s.type === "area") {
    const series = s.series as { name: string; data: [number, number | null][] }[];
    const bands = (s.bands ?? []) as { name: string; lower: [number, number][]; upper: [number, number][] }[];
    const xs = [...new Set(series.flatMap((x) => x.data.map((p) => p[0])))].sort((a, b) => a - b);
    const get = (d: [number, number | null][], x: number) => d.find((p) => p[0] === x)?.[1] ?? null;
    const head: Row = [s.xFormat === "ym" ? "연월" : "연도", ...series.map((x) => x.name), ...bands.flatMap((b) => [`${b.name} 하한`, `${b.name} 상한`])];
    return [head, ...xs.map((x) => [xLabel(x, s.xFormat), ...series.map((se) => get(se.data, x)), ...bands.flatMap((b) => [get(b.lower, x), get(b.upper, x)])])];
  }
  if (s.type === "column") return [["항목", "값"], ...s.categories.map((c: string, i: number) => [c, s.values[i]])];
  if (s.type === "stack") return [["항목", ...s.series.map((x: any) => x.name)], ...s.categories.map((c: string, i: number) => [c, ...s.series.map((x: any) => x.values[i])])];
  if (s.type === "scatter") return [["이름", s.xLabel, s.yLabel, ...(s.rLabel ? [s.rLabel] : [])], ...s.points.map((p: any) => [p.label, p.x, p.y, ...(s.rLabel ? [p.r ?? null] : [])])];
  if (s.type === "race") return [["구분", ...s.names], ...s.frames.map((f: any) => [f.label, ...f.values])];
  if (s.type === "waffle") return [["구분", ...s.groups.map((g: any) => `${g.name}(%)`)], ...s.frames.map((f: any) => [f.label, ...f.values])];
  if (s.type === "pyramid") {
    if (s.frames) {
      const head: Row = ["연도", "연령", s.leftName, s.rightName];
      const rows: Row[] = [];
      s.frames.years.forEach((y: number, i: number) => s.groups.forEach((g: string, j: number) => rows.push([y, g, s.frames.m[i][j], s.frames.f[i][j]])));
      return [head, ...rows];
    }
    return [["연령", s.leftName, s.rightName], ...s.groups.map((g: string, j: number) => [g, s.left[j], s.right[j]])];
  }
  return null;
}

// 지도: 지표마다 열 하나(연도 재생 지표는 연도마다 열)
function mapRows(fig: HTMLElement): Row[] | null {
  const src = fig.querySelector<HTMLScriptElement>(":scope > script[type='application/json']");
  if (!src || !fig.hasAttribute("data-kmap")) return null;
  const c = JSON.parse(src.textContent || "{}");
  const ids = Object.keys(c.centroids ?? {});
  const cols: { name: string; v: Record<string, number | null> }[] = [];
  for (const m of c.metrics) {
    if (m.frames) m.frames.labels.forEach((l: string | number, i: number) => cols.push({ name: `${m.label} ${l}`, v: m.frames.values[i] }));
    else cols.push({ name: m.label, v: m.values ?? {} });
  }
  return [["지역 코드", "지역", ...cols.map((x) => x.name)], ...ids.map((id) => [id, c.names[id] ?? id, ...cols.map((x) => x.v[id] ?? null)])];
}

const cell = (v: string | number | null) => {
  if (v == null) return "";
  const t = typeof v === "number" ? String(+v.toPrecision(10)) : v;
  return /[",\n]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
};

function figTitle(fig: HTMLElement) {
  return fig.querySelector(".card-title")?.textContent?.trim() || document.title.split(" | ")[0];
}

function download(fig: HTMLElement) {
  const rows = tableRows(fig) ?? specRows(fig) ?? mapRows(fig);
  if (!rows) return;
  const foot = fig.querySelector<HTMLElement>(".fig-foot");
  const meta: Row[] = [];
  const title = figTitle(fig);
  meta.push([`# ${title}`]);
  if (foot?.dataset.source) meta.push([`# 자료: ${foot.dataset.source}`]);
  if (foot?.dataset.note) meta.push([`# 주: ${foot.dataset.note}`]);
  if (fig.hasAttribute("data-kmap")) meta.push([`# ${SIDO_ORDER_NOTE}`]);
  meta.push([`# 출처: 숫자 너머 ${location.origin}${location.pathname}#${fig.id} (자료 갱신 ${document.body.dataset.updated ?? ""})`]);
  const csv = "﻿" + [...meta, ...rows].map((r) => r.map(cell).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const page = location.pathname.split("/").filter(Boolean).join("-") || "home";
  a.download = `${page}_${title.replace(/[\\/:*?"<>|\s]+/g, "_").slice(0, 40)}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function citation(fig?: HTMLElement) {
  const b = document.body.dataset;
  const updated = b.updated ?? "";
  const year = updated.slice(0, 4);
  const page = b.pageTitle ?? document.title.split(" | ")[0];
  const url = `${location.origin}${location.pathname}${fig ? `#${fig.id}` : ""}`;
  const src = fig?.querySelector<HTMLElement>(".fig-foot")?.dataset.source;
  const what = fig ? `「${figTitle(fig)}」, ${page}` : `「${page}」`;
  return `Euiyun Lab (${year}). ${what}. 숫자 너머. ${url} (자료 갱신 ${updated}${src ? `; 원자료: ${src}` : ""})`;
}

async function copy(text: string, btn: HTMLElement) {
  try {
    await navigator.clipboard.writeText(text);
    flash(btn, "복사했습니다");
  } catch {
    window.prompt("아래 문구를 복사하세요", text);
  }
}

function flash(btn: HTMLElement, msg: string) {
  const old = btn.dataset.label ?? btn.textContent ?? "";
  btn.dataset.label = old;
  btn.textContent = msg;
  btn.classList.add("is-done");
  setTimeout(() => {
    btn.textContent = old;
    btn.classList.remove("is-done");
  }, 1600);
}

export function initFigures() {
  document.addEventListener("click", (e) => {
    const btn = (e.target as HTMLElement).closest<HTMLElement>("[data-fig-act]");
    if (!btn) return;
    const act = btn.dataset.figAct;
    const fig = btn.closest<HTMLElement>("figure");
    if (act === "cite-page") return void copy(citation(), btn);
    if (!fig) return;
    if (act === "csv") download(fig);
    else if (act === "cite") copy(citation(fig), btn);
    else if (act === "link") copy(`${location.origin}${location.pathname}#${fig.id}`, btn);
  });
}
