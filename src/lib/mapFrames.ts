// 지도(/map/)의 연도별 지표: 실적 + 추계(시나리오별). 페이지는 정의(라벨·색 구간·연도)만, 값은 /map/frames.json 으로 따로 받는다.
import dongne from "../data/dongne.json";
import school from "../data/school.json";
import care from "../data/care.json";
import commerce from "../data/commerce.json";
import housing from "../data/housing.json";
import housingSgg from "../data/housing_sgg.json";
import type { Fmt } from "./format";
import type { ScaleKind } from "./scale";

export interface ScenDim { id: string; label: string; options: { v: string; label: string }[]; def: string }
export interface TimeMetric {
  key: string;
  group: string;
  label: string;
  format: Fmt;
  kind: ScaleKind;
  breaks: number[];
  mid?: number;
  desc: string;
  level: "sgg" | "sido";
  years: number[];
  projFrom: number; // 이 연도부터 추계
  start: number; // 처음 보여 줄 연도
  scen: ScenDim[]; // 비어 있으면 시나리오 없음
  unit?: string;
  yearLabels?: Record<number, string>; // 연도 대신 보여 줄 이름 (예: 최근 12개월)
}

const DN = dongne as any;
const SC = school as any;
const CA = care as any;
const CM = commerce as any;
const HS = housing as any;
const by: number = DN.meta.baseYear;
const POP_SCEN: ScenDim = {
  id: "pop", label: "출산율", def: "mid",
  options: [{ v: "low", label: "저위" }, { v: "mid", label: "중위" }, { v: "high", label: "고위" }],
};
const range = (a: number, b: number, step = 1) => Array.from({ length: Math.floor((b - a) / step) + 1 }, (_, i) => a + i * step);
const r3 = (v: number | null | undefined) => (v == null || !isFinite(v) ? null : Math.round(v * 1000) / 1000);

export const SGG_IDS: string[] = (DN.regions as any[]).map((r) => r.id);
export const SIDO_IDS: string[] = (HS.regions as any[]).filter((r) => r.level === "sido").map((r) => r.id);

const dnYears = range(2015, DN.meta.end);
const scYears = range(2015, SC.meta.projEnd);
const cmYears = range(2015, 2045);
const caYears = Object.keys(CA.regions[0].old75).map(Number);
const hsYears = [...Object.keys(HS.regions.find((r: any) => r.id === "11").hist).map(Number), 2027, 2028, 2029, 2030];
const HY = (housingSgg as any).yearly;
const hyYears: number[] = [...HY.years, HY.years[HY.years.length - 1] + 1];
const hyLabels = { [hyYears[hyYears.length - 1]]: "최근 1년" };
const hyRecent = `${HY.recent[0].slice(0, 4)}.${HY.recent[0].slice(4)}~${HY.recent[1].slice(0, 4)}.${HY.recent[1].slice(4)}`;
const NO_PROJ = 9999;
const hsLast = Math.max(...Object.keys(HS.regions.find((r: any) => r.id === "11").hist).map(Number));

export const TIME_METRICS: TimeMetric[] = [
  { key: "t_pop", group: "인구 전망", label: `인구 (${by}=100)`, format: "int", kind: "div", mid: 100, breaks: [60, 75, 90, 97, 103, 110, 125],
    desc: `${by}년 인구를 100으로 본 그해 인구. ${by + 1}년부터는 추계입니다.`, level: "sgg", years: dnYears, projFrom: by + 1, start: DN.meta.end, scen: [POP_SCEN] },
  { key: "t_old", group: "인구 전망", label: "65세 이상 비중", format: "pct", kind: "seq", breaks: [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5],
    desc: "주민 중 65세 이상 비율.", level: "sgg", years: dnYears, projFrom: by + 1, start: DN.meta.end, scen: [POP_SCEN] },
  { key: "t_kid", group: "인구 전망", label: "0~14세 비중", format: "pct1", kind: "seq-warm", breaks: [0.04, 0.06, 0.08, 0.1, 0.12, 0.14],
    desc: "주민 중 0~14세 비율.", level: "sgg", years: dnYears, projFrom: by + 1, start: DN.meta.end, scen: [POP_SCEN] },
  { key: "t_ext", group: "인구 전망", label: "소멸위험지수", format: "dec2", kind: "div", mid: 0.5, breaks: [0.2, 0.35, 0.5, 0.75, 1.0, 1.5],
    desc: "20~39세 여성 ÷ 65세 이상. 0.5 미만 소멸위험, 0.2 미만 고위험.", level: "sgg", years: dnYears, projFrom: by + 1, start: DN.meta.end, scen: [POP_SCEN] },
  { key: "t_school", group: "학교·돌봄·상권", label: `초등학생 (${by}=100)`, format: "int", kind: "div", mid: 100, breaks: [40, 60, 80, 95, 105, 120, 140],
    desc: `${by}년 초등학생 수를 100으로 본 그해 학생 수. ${SC.meta.lastActual + 1}년부터 추계.`, level: "sgg", years: scYears, projFrom: SC.meta.lastActual + 1, start: 2035, scen: [POP_SCEN] },
  { key: "t_old75", group: "학교·돌봄·상권", label: `75세 이상 (${caYears[0]}=100)`, format: "int", kind: "seq-warm", breaks: [110, 130, 150, 170, 190, 210, 240],
    desc: "돌봄 수요의 중심인 75세 이상 인구. 5년 간격 추계(중위).", level: "sgg", years: caYears, projFrom: caYears[0] + 1, start: caYears[caYears.length - 1], scen: [] },
  { key: "t_cons", group: "학교·돌봄·상권", label: `소비인구 (${by}=100)`, format: "int", kind: "div", mid: 100, breaks: [60, 75, 90, 97, 103, 110, 125],
    desc: "연령별 소비 수준으로 가중한 인구. 동네 상권이 기댈 수요입니다.", level: "sgg", years: cmYears, projFrom: by + 1, start: 2045, scen: [POP_SCEN] },
  { key: "t_hburden", group: "집값", label: "주택구입 부담률", format: "pct", kind: "seq", breaks: [0.05, 0.1, 0.15, 0.2, 0.3, 0.45, 0.6],
    desc: `84㎡ 중위가격의 대출 월 상환액 ÷ 시도 평균 가구 월소득 (그해 금리·소득). 국토부 실거래, 마지막 칸은 최근 1년(${hyRecent}).`, level: "sgg", years: hyYears, projFrom: NO_PROJ, start: hyYears[hyYears.length - 1], scen: [], yearLabels: hyLabels },
  { key: "t_hprice", group: "집값", label: "84㎡ 가격", format: "eok", kind: "seq", breaks: [1, 2, 3, 5, 7, 10, 15],
    desc: `아파트 ㎡당 중위가격 × 84㎡ (억원), 중개거래·전용 40~135㎡. 마지막 칸은 최근 1년(${hyRecent}).`, level: "sgg", years: hyYears, projFrom: NO_PROJ, start: hyYears[hyYears.length - 1], scen: [], yearLabels: hyLabels },
  { key: "t_hjeonse", group: "집값", label: "전세가율", format: "pct", kind: "seq", breaks: [0.5, 0.6, 0.7, 0.75, 0.8, 0.85],
    desc: "같은 단지 안 전세 보증금 ÷ 매매가의 단지별 중앙값. 높을수록 집값이 조금만 내려도 보증금을 돌려받기 어렵습니다.", level: "sgg", years: hyYears, projFrom: NO_PROJ, start: hyYears[hyYears.length - 1], scen: [], yearLabels: hyLabels },
  { key: "t_hrenew", group: "집값", label: "전세 재계약 인상률", format: "pct1S", kind: "div", breaks: [-0.02, -0.001, 0.001, 0.02, 0.04, 0.05],
    desc: "전세 갱신 계약의 보증금 인상률 중앙값. 2023년 역전세 때는 내린 곳이 많았습니다.", level: "sgg", years: hyYears, projFrom: NO_PROJ, start: hyYears[hyYears.length - 1], scen: [], yearLabels: hyLabels },
  { key: "t_burden", group: "집값", label: "부담률 전망 (시도)", format: "pct", kind: "seq", breaks: [0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5],
    desc: "84㎡ 평균가의 대출 월 상환액 ÷ 가구 월소득 (시도 단위). 2027년부터는 집값·금리 조건부 시나리오.", level: "sido", years: hsYears, projFrom: hsLast + 1, start: hsLast,
    scen: [
      { id: "price", label: "집값", def: "trend", options: [{ v: "down", label: "연 −2%" }, { v: "flat", label: "횡보" }, { v: "trend", label: "추세" }] },
      { id: "rate", label: "금리", def: "hold", options: [{ v: "cut", label: "−1%p" }, { v: "hold", label: "유지" }, { v: "hike", label: "+1%p" }] },
    ] },
];

/** 시나리오 조합 키 목록 (예: ["low","mid","high"] 또는 ["down|cut", ...]) */
export function scenKeys(m: TimeMetric): string[] {
  if (!m.scen.length) return ["_"];
  return m.scen.reduce<string[]>((acc, d) => acc.flatMap((a) => d.options.map((o) => (a ? `${a}|${o.v}` : o.v))), [""]);
}

/** 값: actual[yearIdx][regionIdx] (추계 전), proj[scenKey][yearIdx][regionIdx] (추계) */
export function buildFrames() {
  const out: Record<string, any> = {};
  const byId = (arr: any[]) => Object.fromEntries(arr.map((r) => [r.id, r]));
  const dn = byId(DN.regions), sc = byId(SC.regions.filter((r: any) => r.level === "sgg")), ca = byId(CA.regions.filter((r: any) => r.level === "sgg")), cm = byId(CM.regions);
  const hs = byId(HS.regions);
  const series = (m: TimeMetric, f: (id: string, y: number, sk: string) => number | null) => {
    const ids = m.level === "sido" ? SIDO_IDS : SGG_IDS;
    const past = m.years.filter((y) => y < m.projFrom), fut = m.years.filter((y) => y >= m.projFrom);
    const sk0 = scenKeys(m);
    out[m.key] = {
      actual: past.map((y) => ids.map((id) => r3(f(id, y, sk0[0])))),
      proj: Object.fromEntries(sk0.map((k) => [k, fut.map((y) => ids.map((id) => r3(f(id, y, k))))])),
    };
  };
  const dnv = (id: string, y: number, s: string, k: string) => dn[id]?.series[s]?.[y]?.[k] ?? null;
  for (const m of TIME_METRICS) {
    switch (m.key) {
      case "t_pop": series(m, (id, y, s) => { const b = dnv(id, by, s, "total"), v = dnv(id, y, s, "total"); return b && v != null ? (v / b) * 100 : null; }); break;
      case "t_old": series(m, (id, y, s) => dnv(id, y, s, "oldShare")); break;
      case "t_kid": series(m, (id, y, s) => dnv(id, y, s, "kidShare")); break;
      case "t_ext": series(m, (id, y, s) => dnv(id, y, s, "extinction")); break;
      case "t_school": series(m, (id, y, s) => {
        const r = sc[id]; if (!r) return null;
        const val = (yy: number) => r.actual[yy] ?? r.proj[s]?.[yy] ?? null;
        const b = val(by), v = val(y);
        return b && v != null ? (v / b) * 100 : null;
      }); break;
      case "t_old75": series(m, (id, y) => { const r = ca[id]; if (!r) return null; const b = r.old75[caYears[0]], v = r.old75[y]; return b && v != null ? (v / b) * 100 : null; }); break;
      case "t_cons": series(m, (id, y, s) => {
        const c = cm[id]?.series.consumers; if (!c) return null;
        const val = (yy: number) => c.actual[yy] ?? c[s]?.[yy] ?? null;
        const b = val(by), v = val(y);
        return b && v != null ? (v / b) * 100 : null;
      }); break;
      case "t_hburden": case "t_hprice": case "t_hjeonse": case "t_hrenew": {
        const k = { t_hburden: "burden", t_hprice: "price84", t_hjeonse: "jeonseRatio", t_hrenew: "renewUp" }[m.key]!;
        const div = { burden: 100, price84: 1e4, jeonseRatio: 100, renewUp: 1 }[k]!;
        series(m, (id, y) => { const v = HY[k][id]?.[hyYears.indexOf(y)]; return v == null ? null : v / div; });
        break;
      }
      case "t_burden": series(m, (id, y, s) => {
        const r = hs[id]; if (!r) return null;
        if (r.hist[y]) return r.hist[y].burden / 100;
        const [p, rt] = s.split("|");
        const v = r.outlook?.[p]?.[rt]?.[y]?.burden;
        return v == null ? null : v / 100;
      }); break;
    }
  }
  return { sgg: SGG_IDS, sido: SIDO_IDS, metrics: out };
}
