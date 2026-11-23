// 내 정보(출생연도·성별·사는 곳·자녀·연봉·가구소득·순자산·가구원 수).
// 이 브라우저(localStorage)에만 저장하고 어디에도 보내지 않는다. URL·분석 태그(dataLayer)에 넣지 않는다.
// 바뀌면 "profile:change" 이벤트(출생연도가 바뀌면 "born:change"도)로 열린 페이지가 바로 다시 그린다.
const KEY = "profile";
const LEGACY_BORN = "born"; // 첫 버전은 출생연도만 따로 저장했다
export const BORN_MIN = 1920;
export const bornMax = () => new Date().getFullYear();

export type Sex = "male" | "female";
export interface Region {
  id: string; // 시군구 코드 5자리
  name: string; // 시군구 이름
  sido: string; // 시도 약칭 (서울, 경기 …)
  sidoCode: string; // 시도 코드 2자리
}
export interface Profile {
  born?: number;
  sex?: Sex;
  region?: Region;
  kids?: number[]; // 자녀 출생연도
  salary?: number; // 내 연봉 (세전, 만원)
  hinc?: number; // 가구 연소득 (만원)
  net?: number; // 가구 순자산 (만원)
  size?: number; // 가구원 수
}

const okYear = (v: unknown): v is number => Number.isInteger(v) && (v as number) >= BORN_MIN && (v as number) <= bornMax();
const okNum = (v: unknown): v is number => typeof v === "number" && isFinite(v);

function clean(p: any): Profile {
  const out: Profile = {};
  if (!p || typeof p !== "object") return out;
  if (okYear(p.born)) out.born = p.born;
  if (p.sex === "male" || p.sex === "female") out.sex = p.sex;
  if (p.region && typeof p.region.id === "string" && /^\d{5}$/.test(p.region.id)) {
    out.region = { id: p.region.id, name: String(p.region.name ?? ""), sido: String(p.region.sido ?? ""), sidoCode: p.region.id.slice(0, 2) };
  }
  if (Array.isArray(p.kids)) {
    const k = [...new Set(p.kids.filter(okYear))].sort() as number[];
    if (k.length) out.kids = k.slice(0, 4);
  }
  for (const k of ["salary", "hinc", "net"] as const) if (okNum(p[k])) out[k] = p[k];
  if (Number.isInteger(p.size) && p.size >= 1 && p.size <= 9) out.size = p.size;
  return out;
}

export function getProfile(): Profile {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return clean(JSON.parse(raw));
    const b = Number(localStorage.getItem(LEGACY_BORN));
    return okYear(b) ? { born: b } : {};
  } catch {
    return {};
  }
}

function save(p: Profile) {
  try {
    if (Object.keys(p).length) localStorage.setItem(KEY, JSON.stringify(p));
    else localStorage.removeItem(KEY);
    localStorage.removeItem(LEGACY_BORN);
  } catch {}
}

/** 일부 항목만 바꾼다. 값이 null/undefined면 그 항목을 지운다 */
export function setProfile(patch: { [K in keyof Profile]?: Profile[K] | null }) {
  const prev = getProfile();
  const next: any = { ...prev };
  for (const [k, v] of Object.entries(patch)) {
    if (v == null || (Array.isArray(v) && !v.length)) delete next[k];
    else next[k] = v;
  }
  const p = clean(next);
  if (JSON.stringify(p) === JSON.stringify(prev)) return;
  save(p);
  emit(prev, p);
}

export function clearProfile() {
  const prev = getProfile();
  save({});
  emit(prev, {});
}

function emit(prev: Profile, p: Profile) {
  window.dispatchEvent(new CustomEvent("profile:change", { detail: p }));
  if (prev.born !== p.born) window.dispatchEvent(new CustomEvent("born:change", { detail: p.born ?? null }));
  // 그림에 표시하는 사람(나 + 자녀)이 바뀌었을 때
  if (prev.born !== p.born || String(prev.kids ?? "") !== String(p.kids ?? "")) window.dispatchEvent(new CustomEvent("people:change"));
}

/** 그림에 함께 표시할 사람: 나(보라) + 자녀(초록). who는 라벨에 쓰는 짧은 이름 */
export interface Person {
  born: number;
  who: string;
  kid: boolean;
  color: string;
}
export function people(p: Profile = getProfile()): Person[] {
  const out: Person[] = [];
  if (p.born) out.push({ born: p.born, who: "나", kid: false, color: "var(--me)" });
  for (const k of p.kids ?? []) out.push({ born: k, who: `${k}년생`, kid: true, color: "var(--kid)" });
  return out;
}

/** 내 정보가 바뀔 때(다른 탭 포함) 호출. now=true면 지금 값으로 한 번 바로 부른다 */
export function onProfile(fn: (p: Profile) => void, now = true) {
  const h = () => fn(getProfile());
  window.addEventListener("profile:change", h);
  window.addEventListener("storage", (e) => (e.key === KEY || e.key === LEGACY_BORN) && h());
  if (now) h();
}

// ---- 출생연도만 쓰는 곳을 위한 짧은 이름
export const getBorn = () => getProfile().born ?? null;
export const setBorn = (y: number | null) => setProfile({ born: y });
/** 출생연도가 바뀔 때만 부른다 */
export function onBorn(fn: (y: number | null) => void, now = true) {
  let last: number | null | undefined = undefined;
  onProfile((p) => {
    const y = p.born ?? null;
    if (y === last) return;
    const first = last === undefined;
    last = y;
    if (!first || now) fn(y);
  });
}

/** 상단 칩의 설정 창 열기 */
export function openBornPicker() {
  window.dispatchEvent(new CustomEvent("born:open"));
}
export const openProfile = openBornPicker;

/** 그 해 말 기준 만 나이 (주민등록 연말 인구와 같은 기준) */
export const ageAt = (born: number, year: number) => year - born;

// ---- 페이지마다 붙는 "○○년생에게" 상자
export interface MeTile {
  k: string;
  v: string;
  n?: string;
  href?: string;
}
export interface MeContent {
  tiles?: MeTile[];
  lead?: string; // HTML 허용 (페이지가 만든 숫자만 넣는다)
  foot?: string; // HTML 허용
}

/** 받침에 맞는 조사: josa("마포구", "은", "는") → "마포구는" */
export function josa(w: string, withBatchim: string, without: string) {
  const c = w.charCodeAt(w.length - 1);
  if (c < 0xac00 || c > 0xd7a3) return w + without;
  return w + ((c - 0xac00) % 28 ? withBatchim : without);
}

export const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

/** 상자 머리에 붙는 짧은 이름표: "1990년생 · 마포구" */
export function profileLabel(p: Profile, uses: (keyof Profile)[] = ["born", "region"]) {
  const parts: string[] = [];
  if (uses.includes("born") && p.born) parts.push(`${p.born}년생`);
  if (uses.includes("sex") && p.sex) parts.push(p.sex === "male" ? "남자" : "여자");
  if (uses.includes("region") && p.region) parts.push(p.region.name);
  return parts.join(" · ");
}

/**
 * [data-me] 상자를 채운다.
 * need: 이 상자에 꼭 있어야 하는 항목. 하나도 없으면 한 줄짜리 설정 안내만 보인다(기본: 출생연도).
 * build가 null을 돌려주면(이 페이지와 무관한 나이 등) 상자를 숨긴다.
 */
type BoxOpts = { prompt?: string; uses?: (keyof Profile)[] };
export function meBox(host: HTMLElement | null, build: (born: number, p: Profile) => MeContent | null, opts?: BoxOpts): void;
export function meBox(host: HTMLElement | null, build: (born: number | null, p: Profile) => MeContent | null, opts: BoxOpts & { need: (keyof Profile)[] }): void;
export function meBox(host: HTMLElement | null, build: (born: any, p: Profile) => MeContent | null, opts: BoxOpts & { need?: (keyof Profile)[] } = {}) {
  if (!host) return;
  const need = opts.need ?? ["born"];
  const uses = opts.uses ?? need;
  const prompt =
    opts.prompt ??
    (need.length === 1 && need[0] === "born"
      ? "출생연도를 넣으면 이 페이지의 숫자를 내 나이에 맞춰 보여 드립니다."
      : "내 정보(출생연도·사는 곳 등)를 넣으면 이 페이지의 숫자를 내 기준으로 보여 드립니다.");
  onProfile((p) => {
    host.hidden = false;
    const has = need.some((k) => p[k] != null);
    host.classList.toggle("is-empty", !has);
    if (!has) {
      host.innerHTML = `<p class="me-prompt"><span class="me-dot" aria-hidden="true"></span>${esc(prompt)} <button type="button" class="me-set">내 정보 입력</button></p>`;
      host.querySelector(".me-set")!.addEventListener("click", openBornPicker);
      return;
    }
    const c = build(p.born ?? null, p);
    if (!c) {
      host.hidden = true;
      return;
    }
    const tiles = (c.tiles ?? [])
      .map((t) => {
        const inner = `<div class="k">${esc(t.k)}</div><div class="v">${esc(t.v)}</div>${t.n ? `<div class="n">${esc(t.n)}</div>` : ""}`;
        return t.href ? `<a class="me-tile is-link" href="${esc(t.href)}">${inner}</a>` : `<div class="me-tile">${inner}</div>`;
      })
      .join("");
    host.innerHTML =
      `<div class="me-head"><span class="me-badge"><span class="me-dot" aria-hidden="true"></span><span data-born-text></span></span><button type="button" class="me-edit">바꾸기</button></div>` +
      (c.lead ? `<p class="me-lead">${c.lead}</p>` : "") +
      (tiles ? `<div class="me-tiles">${tiles}</div>` : "") +
      (c.foot ? `<p class="me-foot">${c.foot}</p>` : "");
    // 이름표 글자는 CSS attr()로만 보여 준다 (클릭 텍스트 수집 등에 실리지 않게)
    const label = profileLabel(p, uses);
    host.querySelector<HTMLElement>("[data-born-text]")!.dataset.bornText = label ? `${label} 기준` : "내 기준";
    host.querySelector(".me-edit")!.addEventListener("click", openBornPicker);
  });
}

/** 페이지에 이미 실린 그림 데이터 중 type이 같은 첫 spec (중복으로 싣지 않으려고) */
export function pageSpec<T = any>(type: string): T | null {
  for (const s of document.querySelectorAll<HTMLScriptElement>("[data-chart] > script[type='application/json']")) {
    try {
      const j = JSON.parse(s.textContent || "{}");
      if (j.type === type) return j as T;
    } catch {}
  }
  return null;
}

/** 페이지 안 <script type="application/json" id=...> 읽기 */
export function pageJson<T = any>(id: string): T {
  return JSON.parse(document.getElementById(id)?.textContent || "{}") as T;
}
