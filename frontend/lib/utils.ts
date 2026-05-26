// Tiny `cn` helper to combine Tailwind class strings, dropping falsy values.
// Hand-written replacement for `clsx + tailwind-merge` since we don't need
// merge semantics yet (no class conflicts in our small component set).

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
