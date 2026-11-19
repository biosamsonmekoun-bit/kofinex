// Même politique que supabase/config.toml (minimum_password_length, password_requirements)
export const MIN_PASSWORD = 10;

export function passwordIssue(password: string, confirm: string): string | null {
  if (!password) return null;
  if (password.length < MIN_PASSWORD) return `Au moins ${MIN_PASSWORD} caractères.`;
  if (!/[a-z]/.test(password) || !/[A-Z]/.test(password) || !/\d/.test(password)) {
    return "Le mot de passe doit contenir une minuscule, une majuscule et un chiffre.";
  }
  if (confirm && confirm !== password) return "Les mots de passe ne correspondent pas.";
  return null;
}
