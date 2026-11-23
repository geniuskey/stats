// 내 정보 설정 창의 '사는 곳' 목록: 시군구 코드·이름·시도 (빌드 때 정적 파일로 생성)
import type { APIRoute } from "astro";
import dongne from "../data/dongne.json";

export const GET: APIRoute = () => {
  const list = (dongne as any).regions
    .map((r: any) => [r.id, r.name, r.sido])
    .sort((a: string[], b: string[]) => (a[2] + a[1]).localeCompare(b[2] + b[1], "ko"));
  return new Response(JSON.stringify(list), { headers: { "Content-Type": "application/json" } });
};
