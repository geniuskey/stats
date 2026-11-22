// 그림 앵커 id: 제목에서 만든 짧은 해시라 다시 빌드해도 링크가 그대로다 (같은 제목이 겹치면 화면에서 -2, -3을 붙인다)
export function figId(title?: string, id?: string) {
  if (id) return id;
  if (!title) return undefined;
  let h = 5381;
  for (const ch of title) h = ((h * 33) ^ ch.codePointAt(0)!) >>> 0;
  return `fig-${h.toString(36)}`;
}
