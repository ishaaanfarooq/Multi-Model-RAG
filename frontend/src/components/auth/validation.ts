// Client-side checks that mirror backend/auth/routes.py, so most mistakes are caught before a
// round trip. The server still validates everything.

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
// Built at runtime: the `\p{…}` escapes need ES2018, and tsconfig targets ES2017.
const LETTER_RE = new RegExp("\\p{L}", "u");
const SYMBOL_RE = new RegExp("[^\\p{L}\\p{N}\\s]", "u");

export const utf8Bytes = (s: string) => new TextEncoder().encode(s).length;

export const normalizeEmail = (email: string) => email.trim().toLowerCase();

export function emailError(email: string): string | null {
  const v = normalizeEmail(email);
  if (!v) return "Enter your email address.";
  if (v.length > 254) return "Email must be at most 254 characters.";
  if (!EMAIL_RE.test(v)) return "Enter a valid email address.";
  return null;
}

export function nameError(name: string): string | null {
  const n = name.trim().length;
  if (n === 0) return "Enter your name.";
  if (n < 2 || n > 60) return "Name must be 2-60 characters.";
  return null;
}

export type PasswordChecks = { length: boolean; letter: boolean; number: boolean; symbol: boolean; tooLong: boolean };

export function passwordChecks(password: string): PasswordChecks {
  const bytes = utf8Bytes(password);
  return {
    length: bytes >= 8,
    letter: LETTER_RE.test(password),
    number: /[0-9]/.test(password),
    symbol: SYMBOL_RE.test(password),
    tooLong: bytes > 72, // bcrypt only reads the first 72 bytes
  };
}

export function newPasswordError(password: string): string | null {
  if (!password) return "Choose a password.";
  const c = passwordChecks(password);
  if (!c.length) return "Password must be at least 8 characters.";
  if (c.tooLong) return "Password must be at most 72 bytes.";
  if (!c.letter || !c.number) return "Password must contain at least one letter and one number.";
  return null;
}
