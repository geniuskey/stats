// 용어 사전: 이 사이트의 계산 기준. 정의·식은 docs/modules/*.md, etl/*.py, 각 페이지 방법론 섹션과 맞춘다.
// 숫자 상수는 가능한 한 데이터 JSON의 meta에서 읽는다 (데이터가 갱신되면 사전도 따라간다).
import housing from "./housing.json";
import housingSgg from "./housing_sgg.json";
import school from "./school.json";
import univ from "./univ.json";
import wage from "./wage.json";
import commerce from "./commerce.json";
import dongne from "./dongne.json";
import care from "./care.json";
import korea from "./korea.json";
import track from "./track.json";

const HA = (housing as any).meta.assumptions;
const HS = (housingSgg as any).meta.assumptions;
const SC = (school as any).meta;
const UV = (univ as any).meta;
const WG = (wage as any).meta;
const CM = (commerce as any).meta;
const DN = (dongne as any).meta;
const CR = (care as any).meta;
const KO = (korea as any).meta;
const TR = (track as any).meta;
const pct = (x: number) => `${Math.round(x * 100)}%`;

export interface Term {
  id: string;
  term: string;
  en?: string;
  def: string;
  formula?: string; // 식이 아닌 규칙 나열 (글로 보여 줌)
  tex?: string[]; // 수식 (lib/tex 문법, 한 줄에 식 하나)
  where?: string[]; // 기호 설명
  diff?: string;
  links: { slug: string; hash?: string; label: string }[];
}
export interface Group {
  id: string;
  title: string;
  terms: Term[];
}

export const GLOSSARY: Group[] = [
  {
    id: "g-pop",
    title: "인구와 추계",
    terms: [
      {
        id: "term-reg-pop",
        term: "주민등록인구",
        en: "Resident registration population",
        def: "행정안전부 주민등록에 오른 내국인 수. 이 사이트 인구 추계의 출발점이며 매년 말 1세별 값을 씁니다.",
        diff: "통계청 장래인구추계의 총인구는 3개월 이상 머무는 외국인을 포함합니다. 이 사이트는 내국인만 다뤄 공식 추계보다 총인구가 낮게 나옵니다.",
        links: [{ slug: "korea", hash: "method", label: "인구 장기 전망" }],
      },
      {
        id: "term-sgg229",
        term: "시군구 표준화 (229곳)",
        def: "서로 다른 시점·기관의 지역 코드를 2025년 말 기준 시·군·자치구 229곳으로 맞춘 분석 단위. 일반구와 출장소는 상위 시에 합칩니다.",
        formula: "일반구 → 시 (예: 수원시 장안구 → 수원시)\n2026년 전남광주통합특별시 → 옛 광주·전남 시군구\n인천 제물포·영종·서해·검단구 → 옛 중구·동구·서구 (법정동 기준)\n군위군 47720 → 27720 (대구 편입)",
        links: [{ slug: "methodology", label: "방법론 공통 원칙" }],
      },
      {
        id: "term-ccr",
        term: "코호트 변화율법",
        en: "Hamilton-Perry cohort change ratio (CCR)",
        def: "같은 해 태어난 집단(코호트)이 1년 뒤 몇 % 남는지를 최근 추세로 연장하는 소지역 인구 추계법. 사망과 전입·전출을 따로 나누지 않고 한 비율에 함께 담습니다. 이 사이트의 모든 시군구 추계 엔진입니다.",
        tex: [String.raw`인구(a세,\ t+1) = 인구(a-1세,\ t) \times \mathrm{CCR}(a)`],
        where: [`CCR: 최근 3년(2022→2025) 전환의 합계 비율`, `작은 코호트는 시도 값 쪽으로 수축: w = 분모 ÷ (분모 + 300)`, `전국 대비 초과분(지역 고유 이동)은 연 ±8% 상한, 해마다 15%씩 전국 값으로 감쇠`],
        diff: "통계청 장래인구추계는 출생·사망·국제이동을 따로 가정하는 코호트 요인법(cohort-component method)을 씁니다. 코호트 변화율법은 자료가 적은 시군구에 적합하지만 개발·입주 같은 전환점을 미리 알 수 없습니다.",
        links: [{ slug: "dongne", hash: "method", label: "시군구 인구 추계" }, { slug: "track", label: "과거 검증" }],
      },
      {
        id: "term-scenario",
        term: "저위·중위·고위 시나리오",
        en: "Low / medium / high fertility scenario",
        def: "통계청 장래인구추계(2022년 기준)의 출산율 가정 세 가지. 이 사이트는 시나리오별 '20~44세 여성 1명당 출생아'의 변화율만 가져와 최신 실제 출생 수준에 곱합니다.",
        tex: [String.raw`출산율 지수(t) = \dfrac{출생아(t) \,/\, 20∼44세 여성(t)}{같은 값(${KO.baseYear})}`],
        where: [`시나리오(저위·중위·고위)마다 따로 계산`],
        diff: "공식 추계는 2022년 수준에서 출발하지만, 이 사이트는 최근 실제 출생 수준에서 출발합니다. 하나의 예측이 아니라 가정에 따른 범위입니다.",
        links: [{ slug: "korea", hash: "method", label: "인구 장기 전망" }],
      },
      {
        id: "term-tfr",
        term: "합계출산율",
        en: "Total fertility rate (TFR)",
        def: "여성 1명이 가임기간(15~49세) 동안 낳을 것으로 기대되는 평균 출생아 수. 통계청 인구동향조사 값을 씁니다.",
        tex: [String.raw`올해 합계출산율 = \dfrac{올해 출생아 추정}{D}, \qquad D = \dfrac{출생아}{합계출산율}`],
        where: [`D는 최근 3년 평균 변화율로 올해까지 연장`],
        links: [{ slug: "births", hash: "method", label: "출생아 나우캐스트" }],
      },
      {
        id: "term-netmig",
        term: "순이동률",
        en: "Net migration rate",
        def: "들어온 사람에서 나간 사람을 뺀 값을 인구 1천 명당으로 나타낸 것.",
        tex: [String.raw`순이동률 = \dfrac{다른 시군구에서 전입 - 다른 시군구로 전출}{기준연도 주민등록인구} \times 1{,}000`],
        where: [`최근 12개월`],
        diff: "연령별 순이동률도 분모는 전 연령 인구라, 지역끼리 '사람 수의 무게'로 비교됩니다. 상권·동네 지수의 청년 순이동은 20~39세(국내인구이동통계), 이사 페이지의 청년은 20~34세(행안부 전입신고)입니다.",
        links: [{ slug: "move", hash: "method", label: "연령별 인구이동" }],
      },
      {
        id: "term-extinction",
        term: "소멸위험지수",
        def: "20~39세 여성 인구를 65세 이상 인구로 나눈 값. 0.5 미만이면 소멸위험, 0.2 미만이면 고위험으로 봅니다.",
        tex: [String.raw`소멸위험지수 = \dfrac{20∼39세 여성}{65세 이상}`],
        links: [{ slug: "dongne", hash: "method", label: "시군구 인구 추계" }],
      },
      {
        id: "term-sustain",
        term: "지속가능성 지수",
        def: "시군구의 인구 전망·청년 이동·고용·빈집을 한 숫자로 묶은 상대 비교용 합성 지표. 50이 전국 평균 수준입니다.",
        tex: [String.raw`지수 = 50 + 15 \times \sum_i w_i\, z_i`],
        where: [`z: 시군구 분포에서 표준화한 값(±3에서 절단)`, `w: 인구 변화 2025→2035 ${pct(DN.weights.ch2035)} · 청년 순이동률 ${pct(DN.weights.youngMig)} · 소멸위험지수 ${pct(DN.weights.ext2025)} · 종사자 증감률 ${pct(DN.weights.empGrowth)} · 빈집률(역) ${pct(DN.weights.vacancy)}`],
        links: [{ slug: "dongne", hash: "method", label: "시군구 인구 추계" }],
      },
      {
        id: "term-support",
        term: "부양 구조 (고령자 1명당 20~64세)",
        en: "Workers per elderly",
        def: "65세 이상 1명을 20~64세 인구 몇 명이 받치는지. 이 사이트의 '고령자 1명을 일하는 나이 ○명이 받칩니다'가 이 값입니다.",
        tex: [String.raw`부양 구조 = \dfrac{20∼64세 인구}{65세 이상 인구}`],
        diff: "공식 노년부양비는 65세 이상 ÷ 15~64세 × 100(생산가능인구 100명당 고령자 수)입니다. 분자·분모가 뒤집혀 있고 연령 기준도 다릅니다.",
        links: [{ slug: "korea", label: "인구 장기 전망" }, { slug: "retire", hash: "method", label: "노후 소득과 은퇴 자금" }],
      },
    ],
  },
  {
    id: "g-births",
    title: "출생 예측",
    terms: [
      {
        id: "term-nowcast",
        term: "나우캐스트",
        en: "Nowcast",
        def: "공식 연간 발표 전에, 이미 나온 월별 자료로 올해 값을 추정하는 것. 올해 출생아를 1~M월 누계와 남은 달 추정으로 구합니다.",
        tex: [String.raw`계절 비중법:\quad 연간 = \dfrac{1{∼}M월 누계}{최근 5년 1{∼}M월이 연간에서 차지한 비중 평균}`, String.raw`추세법:\quad 연간 = 1{∼}M월 누계 + 작년 남은 달 \times 최근 3개월 전년 동월 대비 비율`],
        where: [`1995년 이후 과거 오차가 작은 방법을 기준 월마다 선택`, `범위는 최근 20년 오차의 10~90% 구간`],
        links: [{ slug: "births", hash: "method", label: "출생아 나우캐스트" }],
      },
      {
        id: "term-marriage-lag",
        term: "혼인 시차 모형",
        def: "혼인이 늘거나 줄면 1~2년 뒤 출생이 따라 움직이는 관계로 내년 출생아를 예측하는 회귀 모형.",
        tex: [String.raw`출생 증가율(t) = a + b_1 \times 혼인 증가율(t-1) + b_2 \times 혼인 증가율(t-2)`],
        where: [`1996년부터 적합`],
        diff: "혼인만 반영합니다. 30대 초반 여성 인구, 정책, 경기 변화는 들어 있지 않습니다.",
        links: [{ slug: "births", hash: "method", label: "출생아 나우캐스트" }],
      },
      {
        id: "term-provisional",
        term: "잠정치 · 확정치",
        en: "Provisional / final",
        def: "먼저 발표된 뒤 나중에 수정될 수 있는 값이 잠정치, 수정이 끝난 값이 확정치입니다. 월별 출생, 최근 소멸 기업, 신고 기한(계약 후 30일)이 지나지 않은 실거래가 잠정치입니다.",
        diff: `이 사이트의 ${WG.lastYear}년 임금도 1~${WG.estimate2026.wageMonths}월 임금, 1~${WG.estimate2026.cpiMonths}월 물가의 전년 동기 대비 증가율을 적용한 잠정치입니다.`,
        links: [{ slug: "births", label: "출생아 나우캐스트" }, { slug: "wage", hash: "method", label: "실질임금과 구매력" }],
      },
    ],
  },
  {
    id: "g-edu",
    title: "교육·의료",
    terms: [
      {
        id: "term-school-age",
        term: "학령인구 (초등)",
        def: "초등학교에 다닐 나이(6~11세)의 주민. 이 사이트의 초등학생 전망은 전년 말 6~11세 주민에 취학 보정계수를 곱해 구합니다.",
        diff: "공식 학령인구는 6~21세(초·중·고·대학) 전체를 가리킵니다. 이 사이트의 학교 전망은 초등 6~11세만 봅니다.",
        links: [{ slug: "school", hash: "method", label: "초등학교 학령인구 전망" }],
      },
      {
        id: "term-enroll-ratio",
        term: "취학 보정계수",
        def: "실제 초등학생 수를 학령 주민 수로 나눈 비율. 다른 지역 통학, 대안교육, 해외 체류를 보정합니다.",
        tex: [String.raw`초등학생(Y) = r \times 6∼11세 주민(Y-1년 말)`, String.raw`입학생(Y) = r \times 6세 주민(Y-1년 말)`],
        where: [`r: ${SC.calYears[0]}~${SC.calYears.at(-1)}년 (실제 학생 ÷ 학령 주민)의 평균`],
        diff: "입학생 수는 모든 연도가 실측이 아닌 이 식의 추정값입니다.",
        links: [{ slug: "school", hash: "method", label: "초등학교 학령인구 전망" }],
      },
      {
        id: "term-fill",
        term: "입학 자리 채움률",
        def: "지금의 대학 입학 규모 가운데 미래 입학 수요로 채워지는 비율. 1보다 작으면 그만큼 자리가 빕니다.",
        tex: [String.raw`입학 수요(Y) = r \times 18세 인구(Y-1년 말)`, String.raw`채움률 = \dfrac{입학 수요}{지금 입학 규모}`],
        where: [`r: ${UV.ratioYears[0]}~${UV.ratioYears.at(-1)}년 입학자 ÷ 18세 인구 평균 (${UV.ratio.toFixed(2)}, 범위 ${UV.ratioLow.toFixed(1)}~${UV.ratioHigh.toFixed(1)})`, `지금 입학 규모: ${UV.last}년 실제 입학자`],
        diff: "KOSIS에 입학정원 표가 없어 실제 입학자를 '지금 입학 규모'로 씁니다. 이미 미충원이 있는 대학은 빈 자리가 적게 잡힙니다. r이 1을 넘는 것은 재수생·만학도·유학생 때문입니다.",
        links: [{ slug: "univ", hash: "method", label: "대학 충원 전망" }],
      },
      {
        id: "term-med-demand",
        term: "의료 수요 지수",
        def: "인구 구조 변화만으로 시군구 의료 수요가 기준연도보다 얼마나 늘어나는지 나타낸 지수.",
        tex: [String.raw`의료 수요 지수(t) = \dfrac{\sum_{연령대} 1인당 진료비 \times 연령대 인구(t)}{같은 값(${CR.baseYear})}`],
        where: [`1인당 진료비: 전국 연령대별 진료비 ÷ 주민등록 인구 (${CR.costYear}년 값으로 고정)`],
        links: [{ slug: "care", hash: "method", label: "의료·돌봄 수급 전망" }],
      },
      {
        id: "term-ltc-gap",
        term: "요양 정원 공백",
        def: "75세 이상 인구가 늘 때, 지금의 시설 비율을 유지하려면 더 필요한 노인의료복지시설 정원. 요양보호사도 같은 방식으로 계산합니다.",
        tex: [String.raw`요양 정원 공백(t) = 75세 이상(t) \times \dfrac{지금의 75세 이상 100명당 정원}{100} - 지금 정원`],
        diff: "등급 인정률 변화와 재가 서비스 확대는 반영하지 않은 근사입니다.",
        links: [{ slug: "care", hash: "method", label: "의료·돌봄 수급 전망" }],
      },
    ],
  },
  {
    id: "g-housing",
    title: "주거",
    terms: [
      {
        id: "term-burden",
        term: "주택구입 부담률",
        en: "Mortgage burden ratio",
        def: `보통 가구가 전용 ${HA.area}㎡ 아파트를 집값의 ${pct(HA.ltv)}를 빌려 사면, 매달 소득의 몇 %를 대출 상환에 쓰는지.`,
        tex: [String.raw`월 상환액 = 대출금 \times \dfrac{r}{1 - (1 + r)^{-n}}, \qquad r = \dfrac{연금리}{12},\quad n = ${HA.termYears * 12}`, String.raw`대출금 = ${HA.area}㎡ 가격 \times ${HA.ltv}`, String.raw`주택구입 부담률 = \dfrac{월 상환액}{가구 연소득 \div 12}`],
        where: [`${HA.termYears}년 원리금균등 상환`],
        diff: "한국주택금융공사 주택구입부담지수(K-HAI)는 중위소득 가구·중간가격 주택 기준의 지수입니다. 이 사이트는 실거래 평균가격(시도)·중앙값(시군구)과 가계금융복지조사 평균 가구소득으로 계산한 비율이라 수준을 직접 비교할 수 없습니다.",
        links: [{ slug: "housing", hash: "method", label: "주택구입 부담" }],
      },
      {
        id: "term-pir",
        term: "PIR",
        en: "Price to income ratio",
        def: "집값이 가구 연소득의 몇 년치인지.",
        tex: [String.raw`\mathrm{PIR} = \dfrac{${HA.area}㎡ 아파트 가격}{가구 연소득}`],
        diff: "흔히 인용되는 PIR은 중위 주택가격 ÷ 중위 가구소득입니다. 이 사이트의 시도 PIR은 실거래 평균가격과 평균 가구소득, 시군구 PIR은 실거래 중앙값과 시도 평균소득을 씁니다.",
        links: [{ slug: "housing", hash: "method", label: "주택구입 부담" }],
      },
      {
        id: "term-pyeong",
        term: "1년치 소득 면적",
        def: "가구 연소득을 모두 써서 살 수 있는 아파트 전용면적(평). 작을수록 집이 비쌉니다.",
        tex: [String.raw`1년치 소득 면적(평) = \dfrac{가구 연소득}{㎡당 가격} \div ${HA.pyeong}`],
        links: [{ slug: "housing", hash: "method", label: "주택구입 부담" }],
      },
      {
        id: "term-jeonse-ratio",
        term: "전세가율",
        en: "Jeonse-to-price ratio",
        def: "매매가 대비 전세 보증금의 비율. 높을수록 집값이 조금만 내려도 보증금을 돌려받기 어렵습니다.",
        tex: [String.raw`단지별 비율 = \dfrac{같은 단지의 전세 ㎡당 보증금 중앙값}{매매 ㎡당 가격 중앙값}`, String.raw`전세가율 = \mathrm{median}(단지별 비율)`],
        where: [`단지 10곳 이상 시군구만`],
        diff: "지역 전체 중앙값끼리 나누면 매매된 단지와 전세 계약된 단지가 달라 100%를 넘는 지역이 생깁니다. 그래서 같은 단지 안에서 먼저 비교합니다.",
        links: [{ slug: "housing", hash: "renewal", label: "전세 재계약" }],
      },
      {
        id: "term-renew",
        term: "재계약 인상률 · 갱신요구권 사용",
        def: "갱신 계약에서 보증금이 종전보다 얼마나 올랐는지(중앙값), 그리고 보증금을 낮춘 계약의 비율. 내린 비율이 늘면 역전세의 신호입니다. 함께 보여 주는 갱신요구권 사용 비율은 세입자가 계약갱신요구권(주택임대차보호법, 1회, 인상 5% 이내)을 쓴 갱신 계약의 비중입니다.",
        tex: [String.raw`인상률 = \dfrac{이번 보증금}{종전 보증금} - 1`],
        where: [`종전·이번 모두 전세인 갱신 계약만`],
        links: [{ slug: "housing", hash: "renewal", label: "전세 재계약" }],
      },
    ],
  },
  {
    id: "g-income",
    title: "소득·물가",
    terms: [
      {
        id: "term-real-wage",
        term: "실질임금",
        en: "Real wage",
        def: `명목 월급을 물가로 나눠 기준연도(${WG.baseYear}년) 원화 가치로 바꾼 값. 월급이 올라도 물가가 더 오르면 실질임금은 줄어듭니다.`,
        tex: [String.raw`실질임금(t) = 명목임금(t) \times \dfrac{물가지수(${WG.baseYear})}{물가지수(t)}`],
        diff: "평균 임금(1인 이상 사업체 임금총액)이라 고임금자에게 끌려 올라가며, 중위 임금이 아닙니다.",
        links: [{ slug: "wage", hash: "method", label: "실질임금과 구매력" }],
      },
      {
        id: "term-deflate",
        term: "물가 잣대 (디플레이트)",
        en: "Deflator",
        def: "명목 금액을 실질로 바꿀 때 나누는 물가지수. 이 사이트는 세 가지를 나란히 씁니다: 소비자물가지수(CPI), 자주 사는 품목만 모은 생활물가지수, 자가주거비포함지수.",
        diff: "국민계정의 GDP 디플레이터가 아니라 소비자 물가지수로 나눕니다. 시도별 실질임금은 각 시도 소비자물가로 나눕니다.",
        links: [{ slug: "wage", hash: "method", label: "실질임금과 구매력" }],
      },
      {
        id: "term-ppi",
        term: "품목별 구매력 지수",
        def: `같은 비율의 월급으로 그 품목을 ${WG.refYear}년보다 얼마나 더(덜) 살 수 있는지. 100보다 작으면 그 품목이 월급보다 빨리 비싸졌습니다.`,
        tex: [String.raw`구매력(t) = \dfrac{임금(t) \,/\, 임금(${WG.refYear})}{품목 가격지수(t) \,/\, 품목 가격지수(${WG.refYear})} \times 100`],
        diff: "가격지수 기반 상대값이며 절대 가격(원)이 아닙니다.",
        links: [{ slug: "wage", hash: "method", label: "실질임금과 구매력" }],
      },
      {
        id: "term-take-home",
        term: "세후 월급",
        en: "Take-home pay",
        def: "평균 월급에서 근로소득세·지방소득세와 4대보험 근로자 부담분을 뺀 금액. 연도별 세법과 요율을 코드로 구현한 간이 계산입니다.",
        diff: "부양가족 없는 1인, 비과세 소득·기타 공제 없음을 가정합니다. 실제 원천징수액은 사람마다 다릅니다. 명목소득이 오르면 누진세율 구간이 올라가는 효과(bracket creep)가 반영됩니다.",
        links: [{ slug: "wage", hash: "method", label: "실질임금과 구매력" }],
      },
      {
        id: "term-percentile",
        term: "분포 속 위치 (백분위)",
        en: "Percentile",
        def: "같은 집단에서 나보다 값이 낮은 사람(가구)의 비율. 공개된 구간별 인원이나 분위 경계값을 누적분포로 바꿔 구합니다.",
        tex: [String.raw`P(X > x) = s \cdot \left(\dfrac{x_0}{x}\right)^{\alpha}`, String.raw`\sigma = \sqrt{2 \ln \dfrac{평균}{중앙값}}`],
        where: [`구간 안: 직선 보간 (균등분포 가정)`, `마지막 구간 위: 파레토 꼬리 (위 첫째 식)`, `같은 나이대 순자산: 로그정규 가정 (위 둘째 식)`],
        diff: "표마다 대상이 다릅니다. 연말정산은 사람(연중 입·퇴사자 포함, 사업소득 제외), 일자리 통계는 일자리 단위입니다.",
        links: [{ slug: "me", hash: "method", label: "소득·자산 분포 속 위치" }],
      },
    ],
  },
  {
    id: "g-industry",
    title: "산업·상권",
    terms: [
      {
        id: "term-growth-score",
        term: "3축 성장 점수",
        def: "산업을 취업자·실질부가가치·수출 세 축의 10년 연평균 증가율로 성장·정체·쇠퇴로 나누는 기준.",
        formula: "축마다 경제 전체 증가율보다 1%p 이상 높으면 +1, 1%p 이상 낮으면 −1, 그 사이 0\n성장: 평균 +0.5 이상 & 취업자·부가가치 모두 증가\n쇠퇴: 평균 −0.5 이하 & 취업자나 부가가치 중 하나 감소\n고용 없는 성장: 부가가치는 크게 늘었는데 취업자 감소",
        links: [{ slug: "industry", hash: "method", label: "산업별 인력 수급 전망" }],
      },
      {
        id: "term-replace",
        term: "은퇴 대체 수요 · 노동생산성",
        def: "10년 안에 65세에 이르는 취업자 수. 은퇴로 비는 자리를 채우는 데 필요한 인력입니다.",
        tex: [String.raw`은퇴 대체 수요 \approx 60세 이상 취업자 + \tfrac{1}{2} \times 50대 취업자`, String.raw`노동생산성 = \dfrac{실질부가가치}{취업자 수}`],
        where: [`50대의 절반을 55~59세로 근사`, `실질부가가치: 2020년 연쇄가격`],
        links: [{ slug: "industry", hash: "method", label: "산업별 인력 수급 전망" }],
      },
      {
        id: "term-labor-gap",
        term: "노동공급 갭",
        def: "미래의 노동공급에서 산업별 노동수요를 뺀 값. 음수면 인력이 부족합니다.",
        formula: "공급 = 연령별 고용률(기준연도) × 추계 인구(중위), 기준연도 산업 점유율로 배분\n수요: hold(유지) · trend(최근 10년 증가율, 해마다 10%씩 둔화) · demo(수요를 이끄는 인구에 비례)\n갭 = 공급 − 수요",
        links: [{ slug: "industry", hash: "gap", label: "인력 수급" }],
      },
      {
        id: "term-vitality",
        term: "상권 활력 지수",
        def: "도소매·숙박음식점업의 현재 체력과 미래 소비 수요를 한 숫자로 묶은 지표. 50이 전국 평균 수준입니다.",
        tex: [String.raw`지수 = 50 + 15 \times \sum_k w_k\, z_k`],
        where: [`w: 사업체 증감 ${pct(CM.weights.estGrowth)} · 종사자 증감 ${pct(CM.weights.empGrowth)} · 순진입률(신생률 − 소멸률, ${CM.netEntryYears[0]}~${CM.netEntryYears[1]} 평균) ${pct(CM.weights.netEntry)} · 소비인구 2025→2030 ${pct(CM.weights.consumers2030)} · 청년(20~39세) 순이동 ${pct(CM.weights.youngMigration)}`, `0~100으로 자름 · 성장 58 이상 · 정체 42~58 · 위축 42 미만`],
        diff: "유동인구·카드매출 같은 상권 내부 자료가 없는 시군구 단위의 구조적 신호입니다. 골목 단위 판단에는 쓸 수 없습니다.",
        links: [{ slug: "commerce", hash: "method", label: "상권 활력 지수" }],
      },
      {
        id: "term-consumers",
        term: "소비인구",
        def: `상권의 주 고객층으로 보는 ${CM.consumerAges[0]}~${CM.consumerAges[1]}세 주민. 주민등록 기반 자체 추계(중위)로 미래 값을 구합니다.`,
        diff: "주민등록(내국인) 기준이라 관광·통근 수요가 빠집니다. 관광지는 점포 밀도가 높게 나옵니다.",
        links: [{ slug: "commerce", hash: "method", label: "상권 활력 지수" }],
      },
      {
        id: "term-oversupply",
        term: "점포 과잉 신호 · 소멸위험 상권",
        def: "점포 과잉: 최근 상권 사업체는 늘었는데 2035년 소비인구가 20% 이상 줄어드는 지역. 소멸위험: 2035년 소비인구가 20% 이상 줄고 최근 순진입률이 0 이하인 지역(지수와 관계없이 우선 적용).",
        links: [{ slug: "commerce", hash: "method", label: "상권 활력 지수" }],
      },
    ],
  },
  {
    id: "g-retire",
    title: "노후",
    terms: [
      {
        id: "term-life-exp",
        term: "기대여명",
        en: "Life expectancy at age x",
        def: "특정 나이의 사람이 앞으로 더 살 것으로 기대되는 평균 햇수. 완전생명표(1세별)를 씁니다.",
        diff: "기간생명표라 앞으로의 수명 개선이 빠져 있습니다. 실제 기대여명은 이보다 길 가능성이 높습니다(장래 생명표 참고).",
        links: [{ slug: "retire", hash: "method", label: "노후 소득과 은퇴 자금" }],
      },
      {
        id: "term-pension-gap",
        term: "연금 공백",
        def: "적정 노후생활비 중 연금으로 채워지지 않는 부분을 은퇴 기간 동안 더한 금액.",
        tex: [String.raw`필요 노후자금 = 적정생활비 \times 기대여명(은퇴 나이)`, String.raw`연금 공백 = (적정생활비 - 65세 이상 연금 월평균 수급액) \times 12 \times 기대여명`],
        where: [`적정생활비는 물가로 최신 가격 환산`],
        diff: "적정생활비는 국민노후보장패널의 인식 조사 결과입니다. 연금 평균액은 고액 수급자에게 끌려 올라가므로 중위값과 함께 봐야 합니다.",
        links: [{ slug: "retire", hash: "method", label: "노후 소득과 은퇴 자금" }],
      },
      {
        id: "term-depletion",
        term: "자금 소진 나이",
        def: "모아 둔 자산이 0 아래로 내려가는 나이. 실질 기준 연 단위 시뮬레이션입니다.",
        tex: [String.raw`잔고(t+1) = 잔고(t) \times (1 + 실질수익률) - (생활비 - 연금) \times 12`, String.raw`실질수익률 = 명목수익률 - 물가상승률`],
        links: [{ slug: "retire", hash: "calc", label: "은퇴 자금 계산기" }],
      },
    ],
  },
  {
    id: "g-verify",
    title: "검증과 불확실성",
    terms: [
      {
        id: "term-backtest",
        term: "과거 검증",
        en: "Backtest",
        def: `과거 어느 시점까지의 자료만으로 같은 방법을 다시 돌려, 그 뒤 실제 값과 비교하는 것. 인구 추계 엔진은 ${TR.btBase}년 말 인구만으로 이후를 예측해 실측과 비교했습니다.`,
        diff: "지금 정한 방법을 과거에 적용한 것이라 '그때 실제로 이렇게 예측했다'는 뜻은 아닙니다. 이를 보완하는 것이 실시간 장부입니다.",
        links: [{ slug: "track", label: "예측 성적표" }],
      },
      {
        id: "term-mape",
        term: "평균 오차 (평균 절대 백분율 오차)",
        en: "MAPE",
        def: "예측이 실제와 몇 % 어긋났는지를 부호 없이 평균한 값. 이 사이트에서 '평균 오차'는 모두 이 값이며, '작년과 같다'·'지금 인구 그대로' 같은 가장 단순한 예측(비교 기준)의 오차와 나란히 보여 줍니다. 모형의 오차가 이보다 작아야 쓸모가 있습니다.",
        tex: [String.raw`평균 오차 = \mathrm{mean}\left|\dfrac{예측}{실제} - 1\right|`],
        links: [{ slug: "track", label: "예측 성적표" }],
      },
      {
        id: "term-interval",
        term: "과거 검증 80% 범위 (예측 구간)",
        en: "Empirical prediction interval",
        def: "과거 검증에서 나온 시군구별 오차의 분포로, 실제 값이 들어올 가능성이 80%인 범위. 시군구 인구(5년 앞까지)와 시군구 초등학생 수(6년 앞까지) 그래프에 노란 음영으로 그립니다. 출산율 저위~고위 음영은 가정의 차이, 이 음영은 방법 자체의 오차입니다.",
        tex: [String.raw`오차 = \dfrac{예측}{실제} - 1`, String.raw`80\%\ 범위 = \left[\dfrac{예측}{1 + q_{90}},\ \dfrac{예측}{1 + q_{10}}\right]`],
        where: [`과거 검증, 시군구별`, `q₁₀, q₉₀: 오차의 10%·90% 분위수`],
        diff: "검증 기간(인구 2021~2025년)에 코로나19와 신도시 입주가 겹쳐 평시보다 넓을 수 있고, 검증하지 않은 먼 미래에는 그리지 않습니다.",
        links: [{ slug: "dongne", label: "시군구 인구 추계" }, { slug: "school", label: "초등학교 학령인구 전망" }],
      },
      {
        id: "term-ledger",
        term: "실시간 장부",
        en: "Live forecast ledger",
        def: "갱신 때마다 아직 실측이 없는 예측(올해·내년 출생아, 내년 인구·초등학생·대학 입학자 등)을 기록해 두고, 실측이 나오면 오차와 범위 적중 여부를 채점하는 기록. git 이력에 남습니다.",
        links: [{ slug: "track", label: "예측 성적표" }],
      },
      {
        id: "term-conditional",
        term: "조건부 시나리오",
        en: "Conditional scenario",
        def: "'이 조건이면 이렇게 된다'를 보여 주는 계산. 미래 값을 맞히려는 예측과 다릅니다. 집값·금리, 임금·물가, 출산율 전망이 여기에 속합니다.",
        links: [{ slug: "housing", hash: "scenario", label: "주택구입 부담 시나리오" }],
      },
    ],
  },
];
