// 「나는 어디쯤?」 — 분포 속 위치 계산 (브라우저 전용, 입력값은 밖으로 나가지 않는다)

/** 누적분포: pts = [값, 누적비율] 오름차순, 마지막 점 위는 파레토 꼬리 */
export interface Dist {
  pts: [number, number][];
  alpha: number;
}

/** 값 x 이하 비율 (0~1). 첫 점이 0%가 아니면 (0, 0)에서 첫 점까지 직선으로 잇는다. */
export function cdf(d: Dist, x: number): number {
  const p = withOrigin(d.pts);
  if (x <= p[0][0]) return 0;
  for (let i = 1; i < p.length; i++) {
    const [x1, c1] = p[i];
    if (x <= x1) {
      const [x0, c0] = p[i - 1];
      return c0 + ((c1 - c0) * (x - x0)) / (x1 - x0 || 1);
    }
  }
  const [xl, cl] = p[p.length - 1];
  return 1 - (1 - cl) * Math.pow(xl / x, d.alpha);
}

/** 누적비율 q에 해당하는 값 */
export function quantile(d: Dist, q: number): number {
  const p = withOrigin(d.pts);
  for (let i = 1; i < p.length; i++) {
    const [x1, c1] = p[i];
    if (q <= c1) {
      const [x0, c0] = p[i - 1];
      return x0 + ((x1 - x0) * (q - c0)) / (c1 - c0 || 1);
    }
  }
  const [xl, cl] = p[p.length - 1];
  return xl * Math.pow((1 - cl) / Math.max(1 - q, 1e-6), 1 / d.alpha);
}

function withOrigin(pts: [number, number][]): [number, number][] {
  return pts[0][1] > 0 ? [[0, 0], ...pts] : pts;
}

/** 표에 직접 나온 가장 낮은 누적비율 (분위 경계값 자료는 10%) — 그 아래는 세분 정보가 없다 */
export function floorShare(d: Dist): number {
  return d.pts[0][1];
}

/** 평균·중앙값만 있을 때: 로그정규분포 가정 (σ = √(2·ln(평균/중앙값))) */
export function lognormalCdf(x: number, median: number, mean: number): number {
  if (x <= 0) return 0;
  const s = Math.sqrt(2 * Math.log(Math.max(mean / median, 1.0001)));
  return normCdf(Math.log(x / median) / s);
}
function normCdf(z: number): number {
  // Abramowitz–Stegun 7.1.26
  const t = 1 / (1 + 0.3275911 * Math.abs(z) / Math.SQRT2);
  const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-(z * z) / 2);
  return z >= 0 ? (1 + y) / 2 : (1 - y) / 2;
}

/** 5세 구간(또는 1세) 인구에서 '나보다 나이 많은 사람' 비율. bins[i]는 i*step ~ i*step+step-1세 */
export function olderShare(bins: number[], step: number, age: number): number {
  const tot = bins.reduce((a, b) => a + b, 0);
  if (!tot) return NaN;
  let older = 0;
  bins.forEach((v, i) => {
    const lo = i * step, hi = lo + step; // 구간 안은 고르게 분포한다고 본다 (마지막 구간도 같은 폭)
    if (lo > age) older += v;
    else if (hi > age) older += (v * (hi - age - 0.5)) / step; // 같은 나이의 절반은 '나보다 많은' 쪽
  });
  return older / tot;
}

/** 상위 x% 표현 */
export function topLabel(p: number, floor = 0): string {
  if (!isFinite(p)) return "–";
  if (floor > 0 && p < floor) return `하위 ${Math.round(floor * 100)}% 이내`;
  const top = (1 - p) * 100;
  if (top < 0.1) return "상위 0.1% 이내";
  if (top < 1) return `상위 ${top.toFixed(1)}%`;
  if (top > 99) return "하위 1% 이내";
  return `상위 ${Math.round(top)}%`;
}

/** 100명 줄 세우기 */
export function lineLabel(p: number): string {
  if (!isFinite(p)) return "";
  const n = Math.min(100, Math.max(1, Math.round((1 - p) * 100) || 1));
  return `100명 중 앞에서 ${n}번째`;
}

/** 만원 단위 금액 */
export function manwon(v: number): string {
  if (!isFinite(v)) return "–";
  const a = Math.abs(v), s = v < 0 ? "-" : "";
  if (a >= 10000) {
    const eok = a / 10000;
    return s + (eok >= 10 ? Math.round(eok).toLocaleString("ko-KR") : eok.toFixed(1).replace(/\.0$/, "")) + "억원";
  }
  return s + Math.round(a).toLocaleString("ko-KR") + "만원";
}
