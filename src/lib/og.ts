// 공유 미리보기 카드(Open Graph 1200×630) — 빌드 시 페이지마다 PNG 를 만든다
import fs from "node:fs";
import path from "node:path";
import satori from "satori";
import sharp from "sharp";
import { SERVICES } from "./nav";
import { HEADLINES } from "./headlines";
import { int, pct } from "./format";
import dongne from "../data/dongne.json";
import school from "../data/school.json";
import commerce from "../data/commerce.json";

export interface Card {
  key: string; // 페이지 경로(앞뒤 / 없이), 홈은 "index"
  eyebrow: string;
  title: string;
  num?: string;
  numColor?: string;
  label?: string;
  chips?: string[];
}

const C = {
  page: "#f9f9f7",
  surface: "#f3f2ee",
  text: "#0b0b0b",
  text2: "#52514e",
  muted: "#898781",
  border: "#e1e0d9",
  blue: "#2a78d6",
  orange: "#eb6834",
  red: "#d03b3b",
  green: "#006300",
};
const signColor = (v: number | null | undefined) => (v == null ? C.text : v < 0 ? C.red : C.blue);
const svc = (slug: string) => SERVICES.find((s) => s.slug === slug)!;

/** 페이지 경로 → 카드 키 (Base 레이아웃과 이미지 엔드포인트가 함께 쓴다) */
export function ogKey(pathname: string, base: string): string {
  let p = pathname.startsWith(base) ? pathname.slice(base.length) : pathname;
  p = p.replace(/^\/+|\/+$/g, "");
  return p || "index";
}

export function allCards(): Card[] {
  const cards: Card[] = [
    { key: "index", eyebrow: "숫자 너머", title: "공공 통계로 보는\n대한민국의 미래", label: "흩어진 공공 통계를 결합해 기존에 없던 지표와 추계를 만듭니다", chips: SERVICES.map((s) => s.short) },
    { key: "map", eyebrow: "숫자 너머", title: "지도로 보기", label: "229개 시군구의 인구·집값·이사 지표를 지도 위에서", chips: ["인구 전망", "집값 부담", "전세가율", "인구이동"] },
    { key: "methodology", eyebrow: "숫자 너머", title: "방법론과 한계", label: "데이터 수집 · 결합 · 추계 방법을 모두 공개합니다", chips: ["KOSIS OpenAPI", "코호트 변화율법", "Hamilton-Perry", "과거 검증"] },
    { key: "glossary", eyebrow: "숫자 너머", title: "용어 사전", label: "이 사이트의 지표가 무엇을 뜻하고 어떻게 계산되는지", chips: ["주택구입 부담률", "PIR", "코호트 변화율법", "나우캐스트"] },
    { key: "changes", eyebrow: "숫자 너머", title: "수정 이력", label: "고친 것, 바꾼 것을 모두 적어 둡니다", chips: ["정정", "방법 변경", "새 지표"] },
  ];
  for (const s of SERVICES) {
    const h = HEADLINES[s.slug];
    cards.push({ key: s.slug, eyebrow: s.name, title: s.desc, num: h.num, label: h.label, chips: [...s.combo] });
  }
  const dn = dongne as any;
  for (const r of dn.regions) {
    const m = r.m;
    cards.push({
      key: `dongne/${r.id}`, eyebrow: svc("dongne").name, title: `${r.sido} ${r.name}`,
      num: pct(m.ch2045, 0, true), numColor: signColor(m.ch2045),
      label: `${dn.meta.end}년 인구 추계 · ${int(m.pop2025)}명 → ${int(m.pop2045)}명 · 지속가능성 지수 ${m.index}`,
    });
  }
  const sc = school as any;
  for (const r of sc.regions.filter((x: any) => x.level !== "nation")) {
    const s = r.summary;
    const title = r.level === "sgg" ? `${r.sido} ${r.name}` : r.name;
    cards.push({
      key: `school/${r.id}`, eyebrow: svc("school").name, title,
      num: pct(s.change2035, 0, true), numColor: signColor(s.change2035),
      label: `초등학생 ${sc.meta.lastActual}→2035년 · ${int(s.current)}명 → ${int(s.y2035)}명`,
    });
  }
  const CLS: Record<string, [string, string]> = { growth: ["성장", C.green], stagnant: ["정체", C.text2], shrink: ["위축", C.orange], decline: ["소멸위험", C.red] };
  for (const r of (commerce as any).regions) {
    const [label, color] = CLS[r.class] ?? ["", C.text];
    const cc = r.metrics.consumerChange2035;
    cards.push({
      key: `commerce/${r.id}`, eyebrow: svc("commerce").name, title: `${r.sido} ${r.name}`,
      num: r.index.toFixed(1), numColor: color,
      label: `상권 활력 지수 · ${label}${cc == null ? "" : ` · 2035년 소비인구 ${pct(cc / 100, 0, true)}`}`,
    });
  }
  return cards;
}

// ---- 렌더링
type El = { type: string; props: Record<string, any> };
const h = (type: string, style: Record<string, any>, ...children: any[]): El => ({
  type,
  props: { style, children: children.length === 1 ? children[0] : children },
});

let fonts: { name: string; data: Buffer; weight: 400 | 700 | 800; style: "normal" }[] | null = null;
function loadFonts() {
  if (fonts) return fonts;
  const dir = path.join(process.cwd(), "node_modules/pretendard/dist/public/static");
  const f = (file: string) => fs.readFileSync(path.join(dir, file));
  fonts = [
    { name: "Pretendard", data: f("Pretendard-Regular.otf"), weight: 400, style: "normal" },
    { name: "Pretendard", data: f("Pretendard-Bold.otf"), weight: 700, style: "normal" },
    { name: "Pretendard", data: f("Pretendard-ExtraBold.otf"), weight: 800, style: "normal" },
  ];
  return fonts;
}

function mark(): El {
  // 사이트 로고와 같은 막대 + 점선 화살표
  return {
    type: "svg",
    props: {
      width: 44, height: 44, viewBox: "0 0 24 24",
      children: [
        { type: "rect", props: { x: 2, y: 13, width: 4, height: 9, rx: 1.5, fill: C.blue } },
        { type: "rect", props: { x: 10, y: 8, width: 4, height: 14, rx: 1.5, fill: C.blue, opacity: 0.7 } },
        { type: "path", props: { d: "M17 3 L22 3 L22 8", fill: "none", stroke: C.orange, "stroke-width": 2.2, "stroke-linecap": "round", "stroke-linejoin": "round" } },
        { type: "path", props: { d: "M14 11 L22 3", fill: "none", stroke: C.orange, "stroke-width": 2.2, "stroke-linecap": "round", "stroke-dasharray": "3 2.4" } },
      ],
    },
  };
}

// 숫자 앞 하이픈을 타이포그래피 마이너스로
const minus = (t?: string) => t?.replace(/-(?=\d)/g, "\u2212");

function layout(c: Card): El {
  c = { ...c, num: minus(c.num), label: minus(c.label) };
  const titleSize = c.num ? (c.title.length > 22 ? 48 : 60) : 76;
  const lines = c.title.split("\n");
  // satori 는 padding 을 상자 밖으로 더하므로(content-box) 바깥은 여백 없이 두고 안쪽 상자 크기를 직접 정한다
  return h("div", { width: 1200, height: 630, display: "flex", background: C.page, fontFamily: "Pretendard", color: C.text, position: "relative" },
    h("div", { position: "absolute", left: 0, top: 0, width: 1200, height: 10, display: "flex" },
      h("div", { flex: 3, background: C.blue }), h("div", { flex: 1, background: C.orange })),
    h("div", { display: "flex", flexDirection: "column", width: 1056, height: 530, marginLeft: 72, marginTop: 56 },
    // 머리: 로고 + 서비스 이름
    h("div", { display: "flex", alignItems: "center", gap: 16 },
      mark(),
      h("div", { fontSize: 30, fontWeight: 800 }, "숫자 너머"),
      c.eyebrow !== "숫자 너머" ? h("div", { display: "flex", fontSize: 26, fontWeight: 700, color: C.blue, marginLeft: 12, padding: "6px 18px", borderRadius: 999, background: "#e6effa" }, c.eyebrow) : h("div", { display: "flex" })),
    // 본문
    h("div", { display: "flex", flexDirection: "column", flexGrow: 1, flexShrink: 1, flexBasis: 0, minHeight: 0, justifyContent: "center", gap: 18 },
      h("div", { display: "flex", flexDirection: "column", fontSize: titleSize, fontWeight: 800, lineHeight: 1.18, letterSpacing: -1.5 },
        ...lines.map((l) => h("div", { display: "flex" }, l))),
      c.num ? h("div", { display: "flex", fontSize: c.num.length > 9 ? 104 : 132, fontWeight: 800, color: c.numColor ?? C.blue, letterSpacing: -4, lineHeight: 1 }, c.num) : h("div", { display: "flex" }),
      c.label ? h("div", { display: "flex", fontSize: 30, color: C.text2, lineHeight: 1.35 }, c.label) : h("div", { display: "flex" }),
      c.chips && !c.num ? h("div", { display: "flex", flexWrap: "wrap", gap: 12, marginTop: 8 },
        ...c.chips.map((t) => h("div", { display: "flex", fontSize: 24, fontWeight: 700, color: C.text2, padding: "8px 20px", borderRadius: 999, background: C.surface, border: `1.5px solid ${C.border}` }, t))) : h("div", { display: "flex" })),
    // 발: 결합 재료 + 도메인
    h("div", { display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: `2px solid ${C.border}`, paddingTop: 22, fontSize: 24, color: C.muted },
      h("div", { display: "flex" }, c.chips && c.num ? `${c.chips.join(" × ")} 통계 결합` : "통계청 KOSIS 공공 통계 결합 · 자체 추계"),
      h("div", { display: "flex", fontWeight: 700, color: C.text2 }, "stats.euiyun.com"))));
}

export async function renderCard(c: Card): Promise<Buffer> {
  const svg = await satori(layout(c) as any, { width: 1200, height: 630, fonts: loadFonts() });
  return sharp(Buffer.from(svg)).png({ compressionLevel: 9, palette: true, quality: 90 }).toBuffer();
}
