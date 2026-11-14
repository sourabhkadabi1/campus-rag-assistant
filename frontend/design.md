# Design: PESU Academy

The locked system. Every Hallmark run reads this first and pages share it. Change it on purpose; the file is the rule.

## System
- Genre: editorial
- Shape of the first page: app screen
- Theme: Broadside, bill
- Axes: warm paper / serif display / vermilion signal · posture: committed
- Shared across chat, pricing, and admin. Marketing composition belongs to each route; the academic paper and ink system stays fixed.

## Tokens
`src/app/tokens.css` is the source of truth. The roles:

```css
:root {
  --color-paper: oklch(94% .025 82); --color-paper-2: oklch(89% .032 82); --color-paper-3: oklch(85% .035 82);
  --color-ink: oklch(19% .012 48); --color-ink-2: oklch(31% .018 52); --color-muted: oklch(42% .02 65); --color-rule: oklch(73% .025 78);
  --color-accent: oklch(51% .17 32); --color-accent-ink: oklch(97% .02 82); --color-focus: oklch(50% .18 32);
  --font-display: Georgia, "Times New Roman", serif; --font-body: "Arial Narrow", "Aptos Narrow", Arial, sans-serif;
  --radius-card: 0; --radius-pill: 0; --rule-hair: 1px; --rule-bar: 4px;
}
```

The spacing, type, easing and duration scales also live in `src/app/tokens.css`.

## Controls
- Primary: ink fill, square corners, 44px minimum target
- Secondary: paper surface with a rule, same corners and target

## Motion
- Character: still; motion communicates state only; reduced motion removes transitions and animation.

## Exports
`src/app/tokens.css` and the Tailwind palette in `tailwind.config.ts`.
