// 숫자 표기 (서버·클라이언트 공용)

export type Fmt = "int" | "man" | "pct" | "pct1" | "pctS" | "pct1S" | "pp" | "won" | "manwon" | "eok" | "dec1" | "dec2" | "x" | "year" | "age";

const nf0 = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const nf2 = new Intl.NumberFormat("ko-KR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

export function int(v: number | null | undefined): string {
  return v == null || !isFinite(v) ? "–" : nf0.format(Math.round(v));
}

/** 큰 수를 만·억 단위로 */
export function compact(v: number | null | undefined, digits = 1): string {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  const s = v < 0 ? "-" : "";
  if (a >= 1e8) return s + trim((a / 1e8).toFixed(digits)) + "억";
  if (a >= 1e4) return s + trim((a / 1e4).toFixed(a >= 1e6 ? 0 : digits)) + "만";
  return s + nf0.format(a);
}
function trim(x: string) {
  return x.replace(/\.0+$/, "");
}

export function pct(v: number | null | undefined, digits = 0, sign = false): string {
  if (v == null || !isFinite(v)) return "–";
  const x = v * 100;
  const s = sign && x > 0 ? "+" : "";
  return s + x.toFixed(digits) + "%";
}

export function signed(v: number | null | undefined, f: (n: number) => string = int): string {
  if (v == null || !isFinite(v)) return "–";
  return (v > 0 ? "+" : "") + f(v);
}

export function won(v: number | null | undefined): string {
  if (v == null || !isFinite(v)) return "–";
  const a = Math.abs(v);
  if (a >= 1e8) {
    const eok = Math.floor(a / 1e8);
    const man = Math.round((a - eok * 1e8) / 1e4);
    return (v < 0 ? "-" : "") + eok + "억" + (man ? " " + nf0.format(man) + "만" : "") + "원";
  }
  if (a >= 1e4) return (v < 0 ? "-" : "") + nf0.format(Math.round(a / 1e4)) + "만원";
  return nf0.format(Math.round(v)) + "원";
}

export function fmt(v: number | null | undefined, f: Fmt = "int"): string {
  switch (f) {
    case "man":
      return compact(v);
    case "pct":
      return pct(v, 0);
    case "pct1":
      return pct(v, 1);
    case "pctS":
      return pct(v, 0, true);
    case "pct1S":
      return pct(v, 1, true);
    case "pp":
      return v == null ? "–" : (v > 0 ? "+" : "") + nf1.format(v) + "%p";
    case "year":
      return v == null ? "–" : String(Math.round(v)) + "년";
    case "age":
      return v == null ? "–" : nf1.format(v) + "세";
    case "won":
      return won(v);
    case "manwon":
      return v == null ? "–" : nf0.format(v) + "만원";
    case "eok":
      return v == null ? "–" : nf1.format(v) + "억";
    case "dec1":
      return v == null ? "–" : nf1.format(v);
    case "dec2":
      return v == null ? "–" : nf2.format(v);
    case "x":
      return v == null ? "–" : nf1.format(v) + "배";
    default:
      return int(v);
  }
}

/** 축 눈금용: 짧게 */
export function tick(v: number, f: Fmt = "int"): string {
  if (f === "pct" || f === "pct1" || f === "pctS" || f === "pct1S") return (f.endsWith("S") && v > 0 ? "+" : "") + Math.round(v * 100) + "%";
  if (f === "pp") return (v > 0 ? "+" : "") + v + "%p";
  if (f === "year") return String(v);
  if (f === "age") return v + "세";
  if (f === "won") return compact(v, 0);
  if (f === "dec1" || f === "dec2" || f === "x") return String(Math.round(v * 100) / 100);
  if (f === "eok") return v + "억";
  if (f === "manwon") return compact(v * 1e4, 0);
  const a = Math.abs(v);
  if (a >= 1e4) return compact(v, a >= 1e5 ? 0 : 1);
  return nf0.format(v);
}
