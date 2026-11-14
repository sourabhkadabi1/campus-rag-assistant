# Design: PESU Academy

The shared Hallmark system for the student assistant, pricing, and administration screens.

## System
- Genre: modern-minimal
- Shape: app screens, preserving the existing route structure and interactions
- Theme: Console, adapted into light paper and dark graphite modes
- Axes: calm instrument workspace / amber for person and action / blue for source and instrument
- Signature: course-grounded answers with nearby citations

## Tokens
`src/app/tokens.css` is the source of truth. Light mode is the warm neutral paper palette; dark mode is graphite. The amber and cool blue meanings stay consistent between modes.

## Surfaces and shape
- Ground, raised panel, and inset work surface form three clear levels.
- Use rounded panels for grouped content, compact rounded controls for actions, and pills only for short filters or status.
- Tables and chat content stay mostly flat, separated by rules rather than nested cards.
- No glow, gradient surfaces, or ornamental motion.

## Controls
- Primary: amber fill, compact rounded corners, 44px minimum hit target.
- Secondary: raised paper surface with a quiet rule.
- Focus is an immediate high-contrast outline.

## Meaning
- Amber marks a person, current action, or selected state.
- Cool blue marks citations, source references, or instrument output.
- Green and red are reserved for success and error states.

## Motion
State changes only; reduced motion removes transitions and animation.

## Exports
`src/app/tokens.css`, the shared styles in `src/app/globals.css`, and the Tailwind palette in `tailwind.config.ts`.
