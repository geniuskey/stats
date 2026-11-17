// 서비스별 대표 숫자 — 홈 카드와 공유 이미지(OG)가 같은 값을 쓴다
import korea from "../data/korea.json";
import school from "../data/school.json";
import dongne from "../data/dongne.json";
import wage from "../data/wage.json";
import housing from "../data/housing.json";
import industry from "../data/industry.json";
import commerce from "../data/commerce.json";
import retire from "../data/retire.json";
import me from "../data/me.json";
import { compact, int, pct, won } from "./format";
import { quantile } from "./me";

const k = (korea as any).headline;
const sNat = (school as any).regions.find((r: any) => r.key === "00").summary;
const dn = (dongne as any).regions;
export const shrinkCount: number = dn.filter((r: any) => r.m.ch2045 < 0).length;
const w = (wage as any).headline;
const seoul = (housing as any).regions.find((r: any) => r.id === "11");
const ind = (industry as any).summary;
const cm = (commerce as any).meta.classCounts;
const rt = (retire as any).headline;

const sal = (me as any).salary;

export const HEADLINES: Record<string, { num: string; label: string }> = {
  me: { num: `${int(quantile(sal, 0.5))}만원`, label: `근로소득자 ${compact(sal.n)}명 연봉의 한가운데 (${sal.year}년)` },
  korea: { num: `${k.workPerOld2025} → ${k.workPerOld2050}명`, label: "고령자 1명을 받치는 20~64세 (2025→2050)" },
  dongne: { num: `${shrinkCount}/${dn.length}곳`, label: `2045년 인구가 줄어드는 시군구` },
  school: { num: pct(sNat.change2035, 0, true), label: `초등학생 ${(school as any).meta.lastActual}→2035 (${compact(sNat.current)}→${compact(sNat.y2035)})` },
  wage: { num: `${pct(w.nominalChange2015, 0, true)} → ${pct(w.netRealChange2015, 0, true)}`, label: "2015→2025 명목 월급 vs 세후 실질 구매력" },
  housing: { num: `${seoul.current.burden}%`, label: "서울 84㎡ 구입 시 월소득 대비 상환액" },
  industry: { num: `${compact(ind.retire10y * 1000)}명`, label: `10년 안에 65세가 되는 취업자 (${pct(ind.retire10yShare)})` },
  commerce: { num: `${cm.oversupply}곳`, label: "점포는 늘고 소비인구는 20%+ 줄어드는 시군구" },
  retire: { num: won(rt.gap65Male).replace(" 0만", ""), label: "65세 남성 은퇴 후 연금으로 못 채우는 생활비 총액" },
};
