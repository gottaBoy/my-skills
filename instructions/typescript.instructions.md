---
description: "Use when writing TypeScript/React code in the Next.js web app. React 19 + TypeScript 5.x + Tailwind CSS 4. Covers component patterns, Server/Client Components, API calls, and project conventions."
applyTo: "web/**/*.{ts,tsx}"
---

# TypeScript/React Coding Standards — autodrive web

> 本文件属于 Spec 层 — 提供编码规范。执行时配合 `execution-governor` 确保 TDD 和 Scope Fence。

## Tech Stack
- React 19 + TypeScript 5.x
- Tailwind CSS 4
- Next.js (App Router)

## Component Pattern
```tsx
// ✅ Functional components with interface props
interface TripCardProps {
  tripId: number;
  title: string;
  onSelect: (id: number) => void;
}

export function TripCard({ tripId, title, onSelect }: TripCardProps) {
  return <div onClick={() => onSelect(tripId)}>{title}</div>;
}
```

## React 19 Notes
- Use `useActionState` for form actions (replaces `useFormState`)
- Use `useOptimistic` for optimistic UI updates
- Server Components by default; add `'use client'` only when needed
- `use` API for reading promises/context in render

## Tailwind CSS 4 Notes
- CSS-first configuration (no `tailwind.config.js` needed)
- Use `@layer` directives for custom styles
- Use `@theme` for design tokens

## Conventions
- Use `interface` over `type` for component props
- Server components by default; add `'use client'` only when needed
- API calls go through `lib/api/` helpers, not inline fetch
- Use Next.js App Router patterns (layout.tsx, page.tsx, loading.tsx)

## Styling
- Use Tailwind CSS for styling
- Avoid inline styles except for dynamic values

## Testing
- Use `npm run lint` for static analysis
- Run `npm run build` to catch type errors before pushing
