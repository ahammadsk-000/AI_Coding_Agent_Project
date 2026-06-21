import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/** Derive up-to-2-letter initials from a name or email, for avatars. */
export function initials(raw: string): string {
  const parts = raw.trim().split(/[\s@._-]+/).filter(Boolean);
  const a = parts[0] ?? "";
  const b = parts.length > 1 ? parts[1] ?? "" : "";
  const out = (a.charAt(0) + b.charAt(0)).toUpperCase();
  if (out.length >= 2) return out;
  if (a.length >= 2) return a.slice(0, 2).toUpperCase();
  return (a.charAt(0) || "?").toUpperCase();
}
