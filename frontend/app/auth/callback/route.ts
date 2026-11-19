import { NextResponse, type NextRequest } from "next/server";
import { getSupabaseServer } from "@/lib/supabase/server";

/** Retour des liens e-mail Supabase (confirmation d'inscription, invitation, lien magique). */
export async function GET(request: NextRequest) {
  const { searchParams, origin } = new URL(request.url);
  const code = searchParams.get("code");
  const next = searchParams.get("next") ?? "/tableau-de-bord";
  // n'accepter qu'un chemin interne (pas de redirection ouverte)
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/tableau-de-bord";

  if (code) {
    const supabase = await getSupabaseServer();
    const { error } = await supabase.auth.exchangeCodeForSession(code);
    if (!error) return NextResponse.redirect(`${origin}${safeNext}`);
  }
  return NextResponse.redirect(`${origin}/login?error=lien_invalide`);
}
