// 연도 재생기: ▶ 버튼 + 슬라이더 + 현재 연도. 피라미드·지도·와플 등 프레임 시각화가 공용으로 쓴다.
import { reduced } from "./anim";


export interface PlayerOpts {
  start?: number; // 시작 프레임 인덱스
  speed?: number; // 프레임당 ms
  /** 쓰지 않음: 모든 재생기는 멈춘 상태로 시작하고 사용자가 ▶를 눌러야 움직인다 (보려는 시점에 이미 끝나 있지 않게) */
  autoplay?: boolean;
  projFrom?: number; // 이 인덱스부터 '추계' 표시
  label?: (i: number) => string;
  /** 있으면 ▶ 재생이 프레임 사이도 같은 속력으로 끊김 없이 이어 그린다: t는 소수 프레임(2.4 = 2와 3 사이 40%).
   *  가감속 없이 speed ms마다 한 프레임씩 나아간다. 슬라이더를 끌면 기존처럼 onFrame(i)으로 간다. */
  smooth?: (t: number) => void;
}
export interface Player {
  el: HTMLElement;
  set(i: number, animate?: boolean): void;
  play(): void;
  pause(): void;
  get index(): number;
}

// 시점이 이보다 적으면(4~5년) 재생 버튼 없이 슬라이더만 둔다: 몇 칸 넘기는 데 재생은 과하다
export const MIN_PLAY = 7;

const PLAY = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M7 4.5v15l12.5-7.5z" fill="currentColor"/></svg>';
const PAUSE = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><rect x="6" y="4.5" width="4" height="15" rx="1.2" fill="currentColor"/><rect x="14" y="4.5" width="4" height="15" rx="1.2" fill="currentColor"/></svg>';
const REPLAY = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M5 12a7 7 0 1 0 2.05-4.95" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/><path d="M4 4v4.5h4.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

export function makePlayer(host: HTMLElement, labels: (string | number)[], onFrame: (i: number, animate: boolean) => void, opts: PlayerOpts = {}): Player {
  const n = labels.length;
  const speed = opts.speed ?? 360;
  const lab = opts.label ?? ((i: number) => String(labels[i]));
  const few = n < MIN_PLAY;
  const wrap = document.createElement("div");
  wrap.className = "player";
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "player-btn";
  btn.setAttribute("aria-label", "재생");
  btn.innerHTML = PLAY;
  const range = document.createElement("input");
  range.type = "range";
  range.min = "0";
  range.max = String(n - 1);
  range.step = "1";
  range.className = "player-range";
  range.setAttribute("aria-label", "연도");
  const out = document.createElement("output");
  out.className = "player-label";
  const ticks = document.createElement("div");
  ticks.className = "player-ticks";
  // 처음·끝·추계 시작 눈금 (시점이 적으면 모두)
  const tickIdx = new Set(few ? labels.map((_, i) => i) : [0, n - 1]);
  if (opts.projFrom != null && opts.projFrom > 0 && opts.projFrom < n) tickIdx.add(opts.projFrom);
  for (const i of tickIdx) {
    const t = document.createElement("span");
    t.style.left = `${(i / Math.max(1, n - 1)) * 100}%`;
    t.textContent = String(labels[i]);
    if (i === opts.projFrom) t.classList.add("proj");
    if (i === n - 1 && n > 1) t.classList.add("end");
    ticks.appendChild(t);
  }
  const track = document.createElement("div");
  track.className = "player-track";
  if (opts.projFrom != null && opts.projFrom > 0) {
    const pz = document.createElement("div");
    pz.className = "player-proj";
    pz.style.left = `${(opts.projFrom / Math.max(1, n - 1)) * 100}%`;
    track.appendChild(pz);
  }
  track.append(range, ticks);
  if (few) {
    btn.hidden = true;
    wrap.classList.add("few");
  }
  wrap.append(btn, track, out);
  host.appendChild(wrap);

  let idx = Math.max(0, Math.min(n - 1, opts.start ?? 0));
  let timer = 0;
  let raf = 0;
  const smooth = opts.smooth && !reduced() ? opts.smooth : undefined;
  const paint = (t = idx) => {
    range.value = String(idx);
    range.style.setProperty("--p", `${(t / Math.max(1, n - 1)) * 100}%`);
    out.textContent = lab(idx);
    out.classList.toggle("is-proj", opts.projFrom != null && idx >= opts.projFrom);
    range.setAttribute("aria-valuetext", lab(idx));
  };
  const set = (i: number, animate = true) => {
    idx = Math.max(0, Math.min(n - 1, i));
    paint();
    onFrame(idx, animate);
  };
  const pause = () => {
    clearInterval(timer);
    cancelAnimationFrame(raf);
    timer = 0;
    btn.innerHTML = idx >= n - 1 ? REPLAY : PLAY;
    btn.setAttribute("aria-label", idx >= n - 1 ? "처음부터 재생" : "재생");
    wrap.classList.remove("playing");
  };
  const play = () => {
    if (timer) return;
    if (idx >= n - 1) set(0, false);
    btn.innerHTML = PAUSE;
    btn.setAttribute("aria-label", "일시정지");
    wrap.classList.add("playing");
    if (smooth) {
      timer = -1; // 재생 중 표시
      let t = idx;
      let last = performance.now();
      const step = (now: number) => {
        t = Math.min(n - 1, t + Math.max(0, now - last) / speed);
        last = now;
        idx = Math.floor(t);
        paint(t);
        smooth(t);
        if (t >= n - 1) return pause();
        raf = requestAnimationFrame(step);
      };
      raf = requestAnimationFrame(step);
      return;
    }
    timer = window.setInterval(() => {
      if (idx >= n - 1) return pause();
      set(idx + 1, true);
      if (idx >= n - 1) pause();
    }, speed);
  };
  btn.addEventListener("click", () => (timer ? pause() : play()));
  range.addEventListener("input", () => {
    pause();
    set(Number(range.value), true);
    btn.innerHTML = idx >= n - 1 ? REPLAY : PLAY;
  });
  paint();
  if (idx >= n - 1) btn.innerHTML = REPLAY;
  return {
    el: wrap,
    set,
    play,
    pause,
    get index() {
      return idx;
    },
  };
}
