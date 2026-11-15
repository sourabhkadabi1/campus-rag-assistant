# Design: PESU Academy

The shared Hallmark system for chat, pricing, and administration screens.

## System
- Genre: modern-minimal
- Shape: app screens, preserving routes and interactions
- Theme: Console, monochrome dark only
- Reference: ChatGPT's near-black ground, charcoal sidebar and active rows, quiet white text
- Signature: answers grounded in course material with source citations

## Tokens
`src/app/tokens.css` is the source of truth. Dark graphite is the only appearance. Surfaces step from near-black to charcoal; neutral text carries the interface. Blue identifies sources, while green and red are reserved for success and error.

## Surfaces and shape
- Ground, sidebar, and raised work areas use three charcoal levels.
- Grouped regions use soft rounded corners. Chat and tables stay flatter and use rules for separation.
- No gradients, glows, or decorative motion.

## Controls
- Primary actions use a quiet raised charcoal fill.
- Secondary actions use a subtle outline or hover fill.
- Focus is an immediate, high-contrast outline.

## Motion
State changes only; reduced motion removes transitions and animation.

## Exports
`src/app/tokens.css`, shared styles in `src/app/globals.css`, and the Tailwind palette in `tailwind.config.ts`.
