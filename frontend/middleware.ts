import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/signup", "/forgot-password", "/auth/callback", "/demonstration"];
/** Page d'accueil publique (exacte : « / » ne doit pas rendre publiques toutes les routes). */
const PUBLIC_EXACT = ["/"];

/**
 * Rafraîchit la session Supabase et redirige les visiteurs non connectés.
 * Il s'agit d'un confort de navigation : la sécurité réelle est assurée
 * par l'API (vérification du JWT) et par RLS en base.
 */
export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll: () => request.cookies.getAll(),
        setAll: (toSet) => {
          toSet.forEach(({ name, value }) => request.cookies.set(name, value));
          response = NextResponse.next({ request });
          toSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options));
        },
      },
    },
  );

  // getUser() valide le jeton auprès de Supabase (contrairement à getSession()).
  const { data: { user } } = await supabase.auth.getUser();
  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_EXACT.includes(path) || PUBLIC_PATHS.some((p) => path === p || path.startsWith(`${p}/`));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }
  if (user && (path === "/login" || path === "/signup" || path === "/forgot-password")) {
    const url = request.nextUrl.clone();
    url.pathname = "/tableau-de-bord";
    url.search = "";
    return NextResponse.redirect(url);
  }
  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|robots.txt).*)"],
};
