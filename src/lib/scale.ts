// 지도·히트맵용 계급 구분 색 척도 (서버·클라이언트 공용).
// 순차: 파랑 단일 색조(seq-100 → seq-700). 발산: 빨강(감소) ↔ 회색 중립 ↔ 파랑(증가).
// 색은 CSS 변수 + color-mix 로 만들어 라이트/다크 테마가 자동으로 따라간다.
import { tick, type Fmt } from "./format";

export type ScaleKind = "seq" | "div" | "seq-warm";

export interface Bin {
  color: string;
  lo: number | null; // 포함
  hi: number | null; // 미포함
  label: string;
}

const SEQ = ["--seq-100", "--seq-200", "--seq-300", "--seq-400", "--seq-500", "--seq-600", "--seq-700"];

function seqColor(t: number) {
  // t: 0..1 → 파랑 램프 위치
  const p = Math.max(0, Math.min(1, t)) * (SEQ.length - 1);
  const i = Math.min(SEQ.length - 2, Math.floor(p));
  const f = p - i;
  if (f < 0.02) return `var(${SEQ[i]})`;
  if (f > 0.98) return `var(${SEQ[i + 1]})`;
  return `color-mix(in oklab, var(${SEQ[i]}) ${Math.round((1 - f) * 100)}%, var(${SEQ[i + 1]}))`;
}
function warmColor(t: number) {
  // 주황 단일 색조 (두 번째 순차 맥락): 중립 → series-2 → 짙은 주황
  const k = Math.max(0, Math.min(1, t));
  if (k < 0.75) return `color-mix(in oklab, var(--series-2) ${Math.round(18 + (k / 0.75) * 82)}%, var(--div-mid))`;
  return `color-mix(in oklab, var(--series-2) ${Math.round(100 - ((k - 0.75) / 0.25) * 35)}%, #5a1f05)`;
}
function armColor(pole: string, t: number) {
  // 중립 → 극. t: 0..1 (0 근처도 중립보다 약간 진하게)
  const k = 0.16 + 0.84 * Math.max(0, Math.min(1, t));
  return `color-mix(in oklab, var(${pole}) ${Math.round(k * 100)}%, var(--div-mid))`;
}

/** breaks 로 n+1 개 계급을 만든다. div 이면 mid(기본 0)를 경계로 양쪽 팔에 색을 나눈다 */
export function makeBins(breaks: number[], kind: ScaleKind, f: Fmt, mid = 0): Bin[] {
  const n = breaks.length + 1;
  const bins: Bin[] = [];
  for (let i = 0; i < n; i++) {
    const lo = i === 0 ? null : breaks[i - 1];
    const hi = i === n - 1 ? null : breaks[i];
    const label = lo == null ? `${tick(hi!, f)} 미만` : hi == null ? `${tick(lo, f)} 이상` : `${tick(lo, f)} ~ ${tick(hi, f)}`;
    bins.push({ color: "", lo, hi, label });
  }
  if (kind === "div") {
    // 중립 계급: mid를 포함하는 계급
    const negBins = bins.filter((b) => b.hi != null && b.hi <= mid);
    const posBins = bins.filter((b) => b.lo != null && b.lo >= mid);
    negBins.forEach((b, j) => (b.color = armColor("--div-neg", negBins.length === 1 ? 0.6 : 1 - j / (negBins.length - 1 || 1))));
    posBins.forEach((b, j) => (b.color = armColor("--div-pos", posBins.length === 1 ? 0.6 : j / (posBins.length - 1 || 1))));
    for (const b of bins) if (!b.color) b.color = "var(--div-mid)";
  } else {
    bins.forEach((b, i) => (b.color = kind === "seq-warm" ? warmColor(i / (n - 1 || 1)) : seqColor(n === 1 ? 0.5 : 0.04 + (i / (n - 1)) * 0.96)));
  }
  return bins;
}

export function binOf(bins: Bin[], v: number | null | undefined): number {
  if (v == null || !isFinite(v)) return -1;
  for (let i = 0; i < bins.length; i++) {
    const b = bins[i];
    if ((b.lo == null || v >= b.lo) && (b.hi == null || v < b.hi)) return i;
  }
  return bins.length - 1;
}

export const NO_DATA = "var(--surface-2)";

export function colorOf(bins: Bin[], v: number | null | undefined) {
  const i = binOf(bins, v);
  return i < 0 ? NO_DATA : bins[i].color;
}

/** 값 분포에서 보기 좋은 경계값 (분위수 → 반올림) */
export function quantileBreaks(values: (number | null | undefined)[], n = 6, round?: number): number[] {
  const xs = values.filter((v): v is number => v != null && isFinite(v)).sort((a, b) => a - b);
  if (!xs.length) return [];
  const out: number[] = [];
  const span = xs[xs.length - 1] - xs[0] || 1;
  const r = round ?? Math.pow(10, Math.floor(Math.log10(span / n)));
  for (let i = 1; i < n; i++) {
    const q = xs[Math.floor((i / n) * (xs.length - 1))];
    const v = Math.round(q / r) * r;
    if (!out.length || v > out[out.length - 1]) out.push(Number(v.toFixed(6)));
  }
  return out;
}
