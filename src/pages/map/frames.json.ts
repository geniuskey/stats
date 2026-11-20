// 지도 연도별 지표 값 (빌드 때 정적 파일로 생성)
import type { APIRoute } from "astro";
import { buildFrames } from "../../lib/mapFrames";

export const GET: APIRoute = () => new Response(JSON.stringify(buildFrames()), { headers: { "Content-Type": "application/json" } });
