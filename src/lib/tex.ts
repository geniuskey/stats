// 수식 조판: 빌드 때 KaTeX로 HTML(+스크린리더용 MathML)을 만든다. 브라우저 스크립트는 없다.
// 식은 TeX로 쓰되 한글은 그대로 적는다: 한글 덩어리(앞뒤 숫자·"세"·"㎡" 포함)는 자동으로 \text{}로 감싼다.
//   "인구(a세, t+1) = 0∼9세(t) \times 1인당 진료비"  →  \text{인구}(a\text{세}, t+1) = \text{0∼9세}(t) \times \text{1인당 진료비}
// "~"는 TeX에서 공백이므로 쓰지 말고 "∼"를 쓴다(자동으로 바꿔 준다). 한글과 영문 약어 사이 띄어쓰기는 "\ ".
import katex from "katex";

const KO = /[0-9.]*(?:∼[0-9]+)?[가-힣㎡](?:[가-힣㎡0-9·∼' ]*[가-힣㎡])?/g;

export function prep(src: string) {
  return src.replace(/~/g, "∼").replace(KO, (m) => `\\text{${m}}`);
}

export function tex(src: string, display = true) {
  return katex.renderToString(prep(src), { displayMode: display, throwOnError: true, strict: "ignore", output: "htmlAndMathml" });
}

/** 부호 있는 계수: "+ 0.43" / "- 0.02" */
export const signed = (v: number) => (v < 0 ? `- ${Math.abs(v)}` : `+ ${v}`);
