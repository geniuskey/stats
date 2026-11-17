import type { APIRoute } from "astro";
import { allCards, renderCard, type Card } from "../../lib/og";

export function getStaticPaths() {
  return allCards().map((c) => ({ params: { key: c.key }, props: { card: c } }));
}

export const GET: APIRoute = async ({ props }) => {
  const png = await renderCard((props as { card: Card }).card);
  return new Response(new Uint8Array(png), { headers: { "Content-Type": "image/png" } });
};
