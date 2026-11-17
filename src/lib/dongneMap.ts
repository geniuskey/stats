// '우리 동네' 시군구 지도 지표 (서버 전용 헬퍼). 홈·동네 목록·동네 상세가 같이 쓴다.
import data from "../data/dongne.json";
import type { MapMetric } from "../components/KoreaMap.astro";

const d = data as any;
const R = d.regions as any[];
const by: number = d.meta.baseYear;
const end: number = d.meta.end;
const years = Object.keys(R[0].series.mid).map(Number).sort((a, b) => a - b);
const projYears = years.filter((y) => y >= by);
const r4 = (v: number | null | undefined) => (v == null || !isFinite(v) ? null : Math.round(v * 10000) / 10000);

export function dongneMetrics(opts: { regions?: any[]; keys?: string[] } = {}): MapMetric[] {
  const regs = opts.regions ?? R;
  const all: MapMetric[] = [
    {
      key: "ch",
      label: `인구 변화 (${by}년 대비)`,
      format: "pctS",
      kind: "div",
      breaks: [-0.3, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2],
      desc: `${by}년 인구 대비 변화율 (중위 추계). ▶ 를 누르면 ${by}→${end}년을 재생합니다. 시도를 누르면 확대됩니다.`,
      frames: {
        labels: projYears,
        values: projYears.map((y) => Object.fromEntries(regs.map((r) => [r.id, r4(r.series.mid[y] ? r.series.mid[y].total / r.series.mid[by].total - 1 : null)]))),
        start: projYears.length - 1,
      },
    },
    {
      key: "old",
      label: "65세 이상 비중",
      format: "pct",
      kind: "seq",
      breaks: [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5],
      desc: "주민 중 65세 이상 비율. 50% 이상이면 주민 절반이 고령자입니다.",
      frames: {
        labels: years,
        values: years.map((y) => Object.fromEntries(regs.map((r) => [r.id, r4(r.series.mid[y]?.oldShare)]))),
        start: years.length - 1,
        projFrom: years.indexOf(by + 1),
      },
    },
    {
      key: "ext",
      label: "소멸위험지수",
      format: "dec2",
      kind: "div",
      mid: 0.5,
      breaks: [0.2, 0.35, 0.5, 0.75, 1.0, 1.5],
      desc: "20~39세 여성 ÷ 65세 이상. 0.5 미만 소멸위험, 0.2 미만 고위험 (빨간색일수록 위험).",
      higherIsBetter: true,
      frames: {
        labels: years,
        values: years.map((y) => Object.fromEntries(regs.map((r) => [r.id, r4(r.series.mid[y]?.extinction)]))),
        start: years.indexOf(by),
        projFrom: years.indexOf(by + 1),
      },
    },
    {
      key: "idx",
      label: "지속가능성 지수",
      format: "dec1",
      kind: "div",
      mid: 50,
      breaks: [30, 40, 45, 50, 55, 60, 70],
      desc: "인구 전망·청년 이동·소멸위험·일자리·빈집을 합친 합성 지수. 50 = 전국 시군구 평균.",
      values: Object.fromEntries(regs.map((r) => [r.id, r.m.index])),
    },
  ];
  return opts.keys ? all.filter((m) => opts.keys!.includes(m.key)) : all;
}

export function dongneNames(regs: any[] = R) {
  return Object.fromEntries(regs.map((r) => [r.id, `${r.sido} ${r.name}`]));
}
export function dongneNotes(regs: any[] = R) {
  return Object.fromEntries(regs.map((r) => [r.id, `${r.m.outlook} 전망 · ${r.m.risk} · 지수 ${r.m.index}`]));
}
export function dongneLinks(base: string, regs: any[] = R) {
  return Object.fromEntries(regs.map((r) => [r.id, `${base}dongne/${r.id}/`]));
}
