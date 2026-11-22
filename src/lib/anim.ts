// 모션 유틸: 트윈, 화면 진입 감지, 숫자 카운트업, 스크롤 리빌.
// prefers-reduced-motion 이면 모든 애니메이션은 즉시 최종 상태로 간다.

export const reduced = () => typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
export const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
export const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** ms 동안 fn(0..1)을 호출. 취소 함수를 돌려준다. */
export function tween(ms: number, fn: (k: number) => void, done?: () => void, ease = easeOut) {
  if (reduced() || ms <= 0) {
    fn(1);
    done?.();
    return () => {};
  }
  let raf = 0;
  const t0 = performance.now();
  const step = (now: number) => {
    const t = Math.min(1, Math.max(0, (now - t0) / ms)); // 첫 rAF 시각이 t0보다 앞설 수 있다
    fn(ease(t));
    if (t < 1) raf = requestAnimationFrame(step);
    else done?.();
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}

/** 요소가 화면에 들어오면 한 번 실행 */
export function onVisible(el: Element, fn: () => void, threshold = 0.2) {
  if (typeof IntersectionObserver === "undefined") return fn();
  const io = new IntersectionObserver(
    (es) => {
      for (const e of es)
        if (e.isIntersecting) {
          io.disconnect();
          fn();
        }
    },
    { threshold, rootMargin: "0px 0px -8% 0px" },
  );
  io.observe(el);
}

const NUM = /-?\d[\d,]*(?:\.\d+)?/g;
/** 텍스트 안의 숫자들을 0에서 목표값까지 올린다 (서식·소수 자릿수 보존, 연도처럼 보이는 수는 제외) */
export function countUp(el: HTMLElement, ms = 1100) {
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; parts: (string | { v: number; dec: number; comma: boolean })[] }[] = [];
  let n: Node | null;
  while ((n = walker.nextNode())) {
    const text = n.textContent || "";
    const parts: (string | { v: number; dec: number; comma: boolean })[] = [];
    let last = 0;
    let any = false;
    for (const m of text.matchAll(NUM)) {
      const raw = m[0];
      const v = Number(raw.replace(/,/g, ""));
      const isYear = /^\d{4}$/.test(raw) && v >= 1900 && v <= 2100;
      parts.push(text.slice(last, m.index));
      if (isYear || !isFinite(v)) parts.push(raw);
      else {
        parts.push({ v, dec: (raw.split(".")[1] || "").length, comma: raw.includes(",") });
        any = true;
      }
      last = (m.index ?? 0) + raw.length;
    }
    parts.push(text.slice(last));
    if (any) nodes.push({ node: n as Text, parts });
  }
  if (!nodes.length) return;
  const fmt = (p: { v: number; dec: number; comma: boolean }, k: number) => {
    const x = p.v * k;
    const s = x.toFixed(p.dec);
    if (!p.comma) return s;
    const [i, d] = s.split(".");
    return i.replace(/\B(?=(\d{3})+(?!\d))/g, ",") + (d ? "." + d : "");
  };
  const paint = (k: number) => {
    for (const { node, parts } of nodes) node.textContent = parts.map((p) => (typeof p === "string" ? p : fmt(p, k))).join("");
  };
  paint(0);
  tween(ms, paint);
}

/** 숫자 카운트업·스크롤 등장은 쓰지 않는다: 숫자는 처음부터 최종 값으로 보여 준다(보고서 관례).
 *  차트의 선 그리기·막대 성장만 남긴다(lib/charts). [data-count]·.reveal 표식은 남아 있어도 무해하다. */
export function initMotion(_root: ParentNode = document) {}
