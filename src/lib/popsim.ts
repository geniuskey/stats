// 브라우저 인구 시뮬레이터 — ETL(pop.py)과 같은 코호트 변화율(CCR)법을 전국 단위로 돌린다.
//   P(a, t+1) = P(a−1, t) × CCR_sex(a) × 사망률 개선 보정
//   0세(t)    = 아동비 × 20~44세 여성(t) × [합계출산율(t) ÷ 기준연도 합계출산율]
//   + 이민 순유입: 연 M명을 20대 후반 중심의 연령 분포로 더한다(남녀 반반)

export interface SimParams {
  baseYear: number;
  male: number[];
  female: number[];
  ccrMale: number[];
  ccrFemale: number[];
  childRatio: number;
  maleBirthShare: number;
  tfrBase: number;
}
export interface SimInput {
  tfr: number; // 목표 합계출산율
  tfrYear: number; // 목표 도달 연도 (선형)
  mig: number; // 연간 추가 순유입 (명)
  mortImp: number; // 60세 이상 사망 확률 연 개선율 (0.01 = 1%)
  end?: number;
}
export interface SimYear {
  year: number;
  total: number;
  kids: number;
  work: number;
  old: number;
  births: number;
  workPerOld: number;
  medianAge: number;
}
export interface SimResult {
  years: SimYear[];
  male: number[]; // 마지막 해 1세별
  female: number[];
  frames: { years: number[]; m: number[][]; f: number[][] };
}

const NAGE = 101;
const W_LO = 20,
  W_HI = 44;

/** 이민자 연령 분포 (합 1): 20대 후반 정점 + 동반 아동 */
const MIG_PROFILE = (() => {
  const w = new Array(NAGE).fill(0).map((_, a) => Math.exp(-0.5 * ((a - 29) / 7.5) ** 2) + 0.18 * Math.exp(-0.5 * ((a - 5) / 4) ** 2));
  const s = w.reduce((x, y) => x + y, 0);
  return w.map((x) => x / s);
})();

function group5(a: number[]) {
  const out: number[] = [];
  for (let lo = 0; lo < 100; lo += 5) out.push(Math.round(a.slice(lo, lo + 5).reduce((x, y) => x + y, 0)));
  out.push(Math.round(a[100]));
  return out;
}
function medianAge(m: number[], f: number[]) {
  const t = m.map((x, i) => x + f[i]);
  const tot = t.reduce((a, b) => a + b, 0);
  let acc = 0;
  for (let a = 0; a < NAGE; a++) {
    if (acc + t[a] >= tot / 2) return a + (tot / 2 - acc) / (t[a] || 1);
    acc += t[a];
  }
  return 100;
}
function summarize(year: number, m: number[], f: number[], births: number): SimYear {
  let tot = 0,
    kids = 0,
    work = 0,
    old = 0,
    w2064 = 0;
  for (let a = 0; a < NAGE; a++) {
    const v = m[a] + f[a];
    tot += v;
    if (a < 15) kids += v;
    else if (a < 65) work += v;
    else old += v;
    if (a >= 20 && a < 65) w2064 += v;
  }
  return { year, total: tot, kids, work, old, births, workPerOld: w2064 / (old || 1), medianAge: medianAge(m, f) };
}

export function simulate(p: SimParams, inp: SimInput): SimResult {
  const end = inp.end ?? 2050;
  let m = p.male.slice(),
    f = p.female.slice();
  const years: SimYear[] = [summarize(p.baseYear, m, f, m[0] + f[0])];
  const frames = { years: [p.baseYear], m: [group5(m)], f: [group5(f)] };
  for (let y = p.baseYear + 1; y <= end; y++) {
    const s = y - p.baseYear;
    const k = Math.min(1, s / Math.max(1, inp.tfrYear - p.baseYear));
    const tfr = p.tfrBase + (inp.tfr - p.tfrBase) * k;
    const imp = Math.pow(1 - inp.mortImp, s);
    const nm = new Array(NAGE).fill(0),
      nf = new Array(NAGE).fill(0);
    for (let a = 1; a < NAGE; a++) {
      let cm = p.ccrMale[a],
        cf = p.ccrFemale[a];
      if (a >= 60) {
        if (cm < 1) cm = 1 - (1 - cm) * imp;
        if (cf < 1) cf = 1 - (1 - cf) * imp;
      }
      const sm = m[a - 1] + (a === NAGE - 1 ? m[a] : 0);
      const sf = f[a - 1] + (a === NAGE - 1 ? f[a] : 0);
      nm[a] = sm * cm;
      nf[a] = sf * cf;
    }
    if (inp.mig) for (let a = 0; a < NAGE; a++) {
      nm[a] += (inp.mig / 2) * MIG_PROFILE[a];
      nf[a] += (inp.mig / 2) * MIG_PROFILE[a];
    }
    let women = 0;
    for (let a = W_LO; a <= W_HI; a++) women += nf[a];
    const births = p.childRatio * women * (tfr / p.tfrBase);
    nm[0] += births * p.maleBirthShare;
    nf[0] += births * (1 - p.maleBirthShare);
    m = nm;
    f = nf;
    years.push(summarize(y, m, f, births));
    frames.years.push(y);
    frames.m.push(group5(m));
    frames.f.push(group5(f));
  }
  return { years, male: m, female: f, frames };
}
