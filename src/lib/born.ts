// 내 출생연도: 이 브라우저(localStorage)에만 저장하고 어디에도 보내지 않는다.
// URL·분석 태그(dataLayer)에 넣지 않는다. 바뀌면 "born:change" 이벤트로 열린 페이지가 바로 다시 그린다.
const KEY = "born";
export const BORN_MIN = 1920;
export const bornMax = () => new Date().getFullYear();

export function getBorn(): number | null {
  try {
    const v = Number(localStorage.getItem(KEY));
    return Number.isInteger(v) && v >= BORN_MIN && v <= bornMax() ? v : null;
  } catch {
    return null;
  }
}

export function setBorn(y: number | null) {
  const ok = y != null && Number.isInteger(y) && y >= BORN_MIN && y <= bornMax();
  try {
    if (ok) localStorage.setItem(KEY, String(y));
    else localStorage.removeItem(KEY);
  } catch {}
  window.dispatchEvent(new CustomEvent("born:change", { detail: ok ? y : null }));
}

/** 출생연도가 바뀔 때(다른 탭 포함) 호출. now=true면 지금 값으로 한 번 바로 부른다 */
export function onBorn(fn: (y: number | null) => void, now = true) {
  const h = () => fn(getBorn());
  window.addEventListener("born:change", h);
  window.addEventListener("storage", (e) => e.key === KEY && h());
  if (now) h();
}

/** 상단 칩의 설정 창 열기 */
export function openBornPicker() {
  window.dispatchEvent(new CustomEvent("born:open"));
}

/** 그 해 말 기준 만 나이 (주민등록 연말 인구와 같은 기준) */
export const ageAt = (born: number, year: number) => year - born;

// ---- 페이지마다 붙는 "○○년생에게" 상자
export interface MeTile {
  k: string;
  v: string;
  n?: string;
}
export interface MeContent {
  tiles?: MeTile[];
  lead?: string; // HTML 허용 (페이지가 만든 숫자만 넣는다)
  foot?: string; // HTML 허용
}

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!);

/**
 * [data-me] 상자를 채운다. 출생연도가 없으면 한 줄짜리 설정 안내만 보인다.
 * build(born)이 null을 돌려주면(이 페이지와 무관한 나이 등) 상자를 숨긴다.
 */
export function meBox(host: HTMLElement | null, build: (born: number) => MeContent | null, prompt = "출생연도를 설정하면 이 페이지의 숫자를 내 나이에 맞춰 보여 드립니다.") {
  if (!host) return;
  onBorn((born) => {
    host.hidden = false;
    host.classList.toggle("is-empty", born == null);
    if (born == null) {
      host.innerHTML = `<p class="me-prompt"><span class="me-dot" aria-hidden="true"></span>${esc(prompt)} <button type="button" class="me-set">출생연도 설정</button></p>`;
      host.querySelector(".me-set")!.addEventListener("click", openBornPicker);
      return;
    }
    const c = build(born);
    if (!c) {
      host.hidden = true;
      return;
    }
    const tiles = (c.tiles ?? [])
      .map((t) => `<div class="me-tile"><div class="k">${esc(t.k)}</div><div class="v">${esc(t.v)}</div>${t.n ? `<div class="n">${esc(t.n)}</div>` : ""}</div>`)
      .join("");
    host.innerHTML =
      `<div class="me-head"><span class="me-badge"><span class="me-dot" aria-hidden="true"></span><span data-born-text></span></span><button type="button" class="me-edit">바꾸기</button></div>` +
      (c.lead ? `<p class="me-lead">${c.lead}</p>` : "") +
      (tiles ? `<div class="me-tiles">${tiles}</div>` : "") +
      (c.foot ? `<p class="me-foot">${c.foot}</p>` : "");
    // 출생연도 글자는 CSS attr()로만 보여 준다 (클릭 텍스트 수집 등에 실리지 않게)
    host.querySelector<HTMLElement>("[data-born-text]")!.dataset.bornText = `${born}년생에게`;
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

