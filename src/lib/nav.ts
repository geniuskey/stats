// name: 정식 이름(페이지·메뉴·공유 카드). title: 질문형 부제(홈 카드·검색 제목)
export const SERVICES = [
  { slug: "me", name: "소득·자산 분포 속 위치", title: "나는 어디쯤?", short: "나는 어디쯤", desc: "내 나이·연봉·가구소득·순자산이 통계 분포에서 차지하는 위치", combo: ["연말정산", "일자리 소득", "가계금융", "생명표"] },
  { slug: "korea", name: "인구 장기 전망", title: "대한민국의 미래", short: "대한민국", desc: "출생·사망·이동을 결합한 2050년 인구와 고령화 전망", combo: ["출생", "사망", "이민", "연령별 인구"] },
  { slug: "births", name: "출생아 나우캐스트", title: "올해 아기는 몇 명 태어날까?", short: "출생", desc: "월별 출생·혼인으로 공식 발표보다 먼저 추정한 올해와 내년 출생아", combo: ["월별 출생", "혼인", "합계출산율", "과거 오차"] },
  { slug: "dongne", name: "시군구 인구 추계", title: "우리 동네의 미래", short: "우리 동네", desc: "시군구별 인구 추계와 성장·축소 가능성", combo: ["인구이동", "출생", "사업체", "주택"] },
  { slug: "move", name: "연령별 인구이동", title: "누가, 어디로 이사 가나?", short: "이사", desc: "행정동 전입신고로 본 나이별·지역별 인구이동", combo: ["전입신고", "연령", "행정동", "시군구"] },
  { slug: "school", name: "초등학교 학령인구 전망", title: "학교는 얼마나 남을까?", short: "학교", desc: "지역별 초등학생 수·학급 수 전망", combo: ["출생아", "학령인구", "학교", "교원"] },
  { slug: "univ", name: "대학 충원 전망", title: "대학은 얼마나 남을까?", short: "대학", desc: "18세 인구로 본 시도별 대학 입학 자리 채움률 전망", combo: ["18세 인구", "대학 입학자", "고교 졸업자"] },
  { slug: "care", name: "의료·돌봄 수급 전망", title: "우리 동네 의료·돌봄", short: "의료·돌봄", desc: "고령화로 늘어나는 의료 수요와 요양 시설·인력·소아과 공백", combo: ["연령별 인구", "요양시설", "의료인력", "진료비"] },
  { slug: "wage", name: "실질임금과 구매력", title: "내 월급의 실질 가치", short: "실질 월급", desc: "물가·주거비·세금을 반영한 실질 구매력", combo: ["임금", "물가", "주거비", "세금"] },
  { slug: "housing", name: "주택구입 부담", title: "집값을 감당할 수 있을까?", short: "집값 부담", desc: "지역별 주택구입 부담의 변화", combo: ["소득", "주택가격", "금리", "대출"] },
  { slug: "industry", name: "산업별 인력 수급 전망", title: "대한민국 산업의 미래", short: "산업", desc: "산업구조와 고용수요의 변화", combo: ["산업별 고용", "생산", "수출", "인구"] },
  { slug: "commerce", name: "상권 활력 지수", title: "소멸하는 상권, 성장하는 상권", short: "상권", desc: "상권 변화의 조기 신호", combo: ["사업체", "창업·폐업", "가구", "인구"] },
  { slug: "retire", name: "노후 소득과 은퇴 자금", title: "은퇴 후 대한민국", short: "은퇴", desc: "은퇴 후 생활비와 자금 시나리오", combo: ["기대수명", "연금", "물가", "가계지출"] },
  { slug: "track", name: "예측 성적표", title: "이 사이트의 예측은 얼마나 맞았나?", short: "성적표", desc: "이 사이트의 예측이 얼마나 맞았는지: 과거 검증과 실시간 채점", combo: ["백테스트", "실시간 장부", "공식 추계 비교"] },
] as const;

// 상단 메뉴 묶음 (성적표는 방법론 옆 고정 링크)
export const NAV_GROUPS = [
  { title: "인구와 지역", slugs: ["korea", "births", "dongne", "move", "commerce"] },
  { title: "교육·의료", slugs: ["school", "univ", "care"] },
  { title: "살림과 일", slugs: ["me", "wage", "housing", "retire", "industry"] },
] as const;

/** 브라우저 탭·검색 결과 제목: "정식 이름 — 질문" */
export const pageTitle = (slug: string) => {
  const s = SERVICES.find((x) => x.slug === slug)!;
  return s.name === s.title ? s.name : `${s.name} — ${s.title}`;
};
export const svcName = (slug: string) => SERVICES.find((x) => x.slug === slug)!.name;
