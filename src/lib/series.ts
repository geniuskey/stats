import type { Pt } from "./charts";

export type YMap = Record<string | number, number | null | undefined>;

export function pts(m: YMap | undefined, from?: number, to?: number): Pt[] {
  if (!m) return [];
  return Object.entries(m)
    .map(([k, v]) => [Number(k), v == null ? null : Number(v)] as Pt)
    .filter(([x]) => (from == null || x >= from) && (to == null || x <= to))
    .sort((a, b) => a[0] - b[0]);
}

/** 실측 마지막 점을 추계 앞에 붙여 선이 끊기지 않게 */
export function joinProj(actual: YMap, proj: YMap): Pt[] {
  const a = pts(actual);
  const last = a[a.length - 1];
  return last ? [last, ...pts(proj)] : pts(proj);
}

export function val(m: YMap | undefined, y: number): number | null {
  if (!m) return null;
  const v = m[y] ?? m[String(y)];
  return v == null ? null : Number(v);
}
