# 숫자 너머 — stats.euiyun.com

공공 통계를 **보여주는** 사이트가 아니라, 여러 통계를 **결합해** 기존에 없던 지표와 미래 추계를 만드는 서비스입니다.

| 서비스 | 결합 데이터 | 새 지표·예측 |
|---|---|---|
| 대한민국의 미래 | 출생·사망·이동·연령별 인구 | 2050년 인구·고령화, 실제 출생 vs 공식 시나리오 |
| 우리 동네의 미래 | 인구이동·출생·사업체·주택 | 229개 시군구 2045 추계, 지속가능성 지수 |
| 학교는 얼마나 남을까? | 출생아·학령인구·학교·교원 | 시군구별 초등학생·학급·입학생 2045 추계 (과거 검증 포함) |
| 내 월급의 실질 가치 | 임금·물가·주거비·세금 | 세후 실질 구매력, 연봉 환산 계산기 |
| 집값을 감당할 수 있을까? | 소득·주택가격·금리·대출 | 주택구입 부담률, PIR, 2030 시나리오, 계산기 |
| 대한민국 산업의 미래 | 산업별 고용·생산·수출·인구 | 은퇴 대체 수요, 2035/2045 인력 과부족 |
| 소멸하는 상권, 성장하는 상권 | 사업체·창업·폐업·인구 | 상권 활력 지수, 점포 과잉 조기 신호 |
| 은퇴 후 대한민국 | 기대수명·연금·물가·가계지출 | 연금 공백, 자금 소진 나이 계산기 |
| 나는 어디쯤? | 연말정산·일자리 소득·가계금융·생명표·인구 | 내 연봉·가구소득·순자산·나이의 분포 속 위치 |
| 올해 아기는 몇 명 태어날까? | 월별 출생·혼인·합계출산율 | 공식 발표 전 올해 출생아·합계출산율 나우캐스트, 혼인 시차로 내년 출생아 예측 (과거 오차 공개) |
| 대학은 얼마나 남을까? | 18세 인구·대학/전문대 입학자·고교 졸업자 | 2050년까지 시도별 입학 자리 채움률, 지역 탄력성 배분 (과거 검증 포함) |
| 우리 동네 의료·돌봄 | 연령별 인구·요양시설·요양보호사·의사·소아과·연령별 진료비 | 시군구 의료 수요 지수, 요양 정원·인력 공백, 소아과 공백 |
| 예측 성적표 | 모든 모듈의 백테스트 + 실시간 장부 | 인구 엔진 과거 검증, 예측을 적어 두고 실측이 나오면 자동 채점 |

## 구조

```
etl/            Python(표준 라이브러리만) — KOSIS OpenAPI 수집·결합·추계
  kosis.py      API 클라이언트(캐시: data/raw/)
  regions.py    행정구역 표준화
  pop.py        소지역 인구추계 엔진 (Hamilton-Perry + 출산율 시나리오)
  build_*.py    서비스별 데이터 생성 → src/data/*.json
  run_all.py    전체 실행
  build_track.py 예측 성적표: 과거 검증 모음 + 실시간 장부 (마지막에 실행, 직전 track.json의 장부를 이어 씀)
  validate.py   생성 데이터 검증 (범위 규칙 + 직전 버전과 비교)
  geo/          시군구·시도 경계 → src/data/geo.json (SVG 경로, 한 번만 실행)
  datagokr.py   공공데이터포털 API 공용 도구 (인증키, 한도 감지, 재시도)
  mois/         행안부 행정동 간 인구이동(성·만나이별, 월별) 수집기 (원자료는 data/mois/, git 제외)
  molit/        국토부 아파트 매매·전월세 실거래가 수집기 (원자료는 data/molit/, git 제외)
    collect.py  수집·이어받기·status·export(월별 csv.gz)
    lawd.json   조회할 현재 시군구 코드 256개 (국토부가 과거 거래도 현재 코드로 제공, make_lawd.py로 생성)
src/            Astro 정적 사이트 (SVG 차트·지도 자체 구현, 외부 차트 라이브러리 없음)
docs/modules/   서비스별 방법론
```

## 시각화 구성 요소

| 구성 요소 | 파일 | 용도 |
|---|---|---|
| `KoreaMap` | `components/KoreaMap.astro`, `lib/map.ts` | 시군구(229)·시도(17) 단계구분도. 지표 토글, 연도 재생, 시도 클릭 확대, 순위 목록 연동, `only`(한 시도만)·`highlight` |
| `ChartSwitch` | `components/ChartSwitch.astro` | 같은 데이터를 여러 차트 형태로 전환 (숨긴 차트는 처음 열 때 그림) |
| 차트 | `lib/charts.ts`, `lib/charts-extra.ts` | line · column · pyramid(연도 프레임 재생) · area(누적/100%) · stack · scatter(버블) · race(막대 레이스) · waffle(100칸) |
| 재생기 | `lib/player.ts` | ▶/슬라이더/연도 표시. 피라미드·지도·와플·레이스 공용 |
| 색 척도 | `lib/scale.ts` | 계급 구분: 순차(파랑)·발산(빨강↔회색↔파랑). CSS 변수 + `color-mix`라 다크 모드 자동 |
| 모션 | `lib/anim.ts` | 화면 진입 시 선 그리기·막대 성장·숫자 카운트업·스크롤 등장. `prefers-reduced-motion` 존중 |
| 공유 카드 | `lib/og.ts`, `pages/og/[...key].png.ts` | 페이지마다 1200×630 OG 이미지를 빌드 때 생성 (satori + Pretendard → sharp PNG). 대표 숫자는 `lib/headlines.ts`를 홈과 공유 |
| 시뮬레이터 | `lib/popsim.ts` | 출산율·이민·사망률 개선을 바꿔 2050년 인구를 브라우저에서 재계산 (ETL과 같은 코호트 모형) |

지도 경계는 [vuski/admdongkor](https://github.com/vuski/admdongkor) 행정동 경계(2025-12-31, 통계청 SGIS 기반)를 시군구로 합쳐 만듭니다: `etl/geo/build.sh` (node·python3 필요).

## 실행

```bash
echo "KOSIS_API_KEY=발급받은키" > .env    # https://kosis.kr/openapi/
npm install
npm run etl          # 데이터 생성 (uv 필요, 또는: cd etl && python3 run_all.py)
npm run validate     # 생성 결과를 git HEAD와 비교해 검증
npm run dev
```

### 공공데이터포털 수집 (선택)

인증키는 계정에 하나라 `.env`의 `DATA_GO_KR_API_KEY`(또는 `MOLIT_API_KEY`) 하나를 모든 API가 함께 씁니다. 하루 호출 한도는 API마다 따로입니다.

**행안부 인구이동** (`행정안전부_지역별 인구이동 현황` 활용신청)

```bash
python3 etl/mois/collect_move.py          # 2022-10~현재, 행정동→행정동 · 시도쌍 256개 × 월
python3 etl/mois/collect_move.py status
python3 etl/mois/collect_move.py export   # data/mois/move/lv3/YYYYMM.csv.gz
```

전국 한 달이 약 20만 행(내려받기 1~2GB, 압축 저장 약 4MB)입니다. 호출 수보다 내려받기 시간이 병목이라 4개를 동시에 받습니다.

**국토부 아파트 실거래가**

공공데이터포털에서 `국토교통부_아파트 매매 실거래가 상세 자료`, `국토교통부_아파트 전월세 실거래가 자료`를 활용신청하고 `.env`에 `MOLIT_API_KEY=일반인증키`를 넣습니다.

```bash
python3 etl/molit/collect.py          # 최근 5년 수집. 하루 한도에 걸리면 멈추고 다음 실행 때 이어받음
python3 etl/molit/collect.py status   # 진행 상황
python3 etl/molit/collect.py export   # data/molit/{trade,rent}/YYYYMM.csv.gz + manifest.json
```

종류별로 256개 시군구 × 61개월, 약 1만 6천 번을 호출합니다. 최근 달은 신고 기한과 계약 해제 때문에 확정되기 전(달이 끝나고 90일)까지 하루 한 번 다시 받습니다.

배포: `main`에 푸시하면 GitHub Actions가 빌드해 GitHub Pages(stats.euiyun.com)에 배포합니다. 매월 2회 KOSIS 데이터를 자동으로 다시 받아 재계산합니다(저장소 Secret `KOSIS_API_KEY` 필요). 재계산 결과는 `etl/validate.py`가 지역 수·핵심 지표 범위·직전 버전 대비 변화를 확인하고, 하나라도 어긋나면 커밋·배포하지 않고 실패로 끝납니다(사이트는 직전 데이터 유지). 정상적인 큰 변화(기준연도 교체 등)라면 Actions에서 `refresh`와 `skip_validation`을 켜고 수동 실행합니다.

데이터 출처: 통계청 KOSIS 국가통계포털(공공누리 제1유형). 이 사이트의 결합 지표·추계는 국가승인통계가 아닙니다.
