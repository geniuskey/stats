// 떠 있는 목차: 본문 섹션 제목(h2)으로 자동 생성. 넓은 화면은 오른쪽 여백에 고정, 좁은 화면은 '목차' 버튼으로 펼친다.
// 섹션이 3개 미만인 페이지(홈·지도 등)에는 만들지 않는다.

export function initToc() {
  const heads = [...document.querySelectorAll<HTMLElement>("main section > h2")].filter(
    (h) => !h.classList.contains("sr-only") && h.offsetParent !== null && h.textContent?.trim(),
  );
  if (heads.length < 3) return;

  const items = heads.map((h, i) => {
    const sec = h.parentElement as HTMLElement;
    const target = sec.id ? sec : h;
    if (!target.id) target.id = `sec-${i + 1}`;
    return { h, id: target.id, text: h.textContent!.trim().replace(/\s+/g, " ") };
  });

  const nav = document.createElement("nav");
  nav.className = "toc";
  nav.setAttribute("aria-label", "이 페이지 목차");
  nav.innerHTML = `
    <button type="button" class="toc-btn" aria-expanded="false" aria-controls="toc-list">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h10M4 18h13"/></svg>
      <span>목차</span>
    </button>
    <div class="toc-panel" id="toc-list">
      <div class="toc-head">이 페이지</div>
      <ol></ol>
      <a class="toc-top" href="#top">↑ 맨 위로</a>
    </div>`;
  const ol = nav.querySelector("ol")!;
  const links = items.map((it) => {
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = `#${it.id}`;
    a.textContent = it.text;
    li.appendChild(a);
    ol.appendChild(li);
    return a;
  });
  document.body.appendChild(nav);

  const btn = nav.querySelector<HTMLButtonElement>(".toc-btn")!;
  const setOpen = (open: boolean) => {
    nav.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", String(open));
  };
  btn.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
  nav.addEventListener("click", (e) => {
    if ((e.target as HTMLElement).closest("a")) setOpen(false);
  });
  nav.querySelector<HTMLAnchorElement>(".toc-top")!.addEventListener("click", (e) => {
    e.preventDefault();
    window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    history.replaceState(null, "", location.pathname + location.search);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav.classList.contains("is-open")) {
      setOpen(false);
      btn.focus();
    }
  });
  document.addEventListener("click", (e) => {
    if (!nav.contains(e.target as Node)) setOpen(false);
  });

  // 지금 읽는 섹션 표시: 화면 위쪽 1/3 선을 지난 마지막 제목. 첫 제목 전(머리말)과 맨 아래도 처리.
  let ticking = false;
  const update = () => {
    ticking = false;
    const line = Math.min(window.innerHeight * 0.33, 240);
    let cur = -1;
    items.forEach((it, i) => {
      if (it.h.getBoundingClientRect().top <= line) cur = i;
    });
    if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) cur = items.length - 1;
    links.forEach((a, i) => {
      if (i === cur) a.setAttribute("aria-current", "location");
      else a.removeAttribute("aria-current");
    });
    // 본문을 조금 내려야 나타난다 (머리말에서는 방해하지 않게)
    nav.classList.toggle("is-shown", window.scrollY > 240);
  };
  const onScroll = () => {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  update();
}
