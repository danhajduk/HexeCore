# Frontend Visual And Interaction Standard

Last Updated: 2026-04-07 US/Pacific

## Purpose

This document defines the canonical visual and interaction standard for Hexe node frontends.

Unlike the general frontend standard, this document is intentionally concrete.
Its goal is for new node UIs to look, feel, and behave like the established Hexe node/operator surfaces instead of inventing a new visual language for each repository.

This standard is derived from the implemented HexeEmail node UI and should be treated as the source of truth for node-facing UI presentation until replaced by a newer canonical reference.

Primary reference implementation:

- `../HexeEmail/frontend/src/App.jsx`
- `../HexeEmail/frontend/src/styles.css`
- `../HexeEmail/frontend/src/theme/tokens.css`
- `../HexeEmail/frontend/src/theme/base.css`
- `../HexeEmail/frontend/src/theme/components.css`
- `../HexeEmail/frontend/src/features/setup/SetupComponents.jsx`
- `../HexeEmail/frontend/src/features/providers/GmailSetupPage.jsx`
- `../HexeEmail/frontend/src/features/dashboard/OverviewDashboardSection.jsx`
- `../HexeEmail/frontend/src/features/dashboard/RuntimeDashboardSection.jsx`
- `../HexeEmail/frontend/src/features/dashboard/ScheduledTasksSection.jsx`
- `../HexeEmail/frontend/src/features/dashboard/TrackedOrdersSection.jsx`

## Rule Levels

- **Mandatory**
  Rules every new Hexe node UI must follow if it is expected to visually align with the standard node operator experience.
- **Recommended**
  Strong guidance that should usually be followed.
- **Optional**
  Acceptable variations that may be used when they do not weaken visual consistency.

## Core Principle

The node UI should feel like:

- one family of products
- one operator console model
- one status language
- one setup rhythm
- one dashboard grammar

and not like a collection of unrelated internal tools.

## 1. Canonical Visual Identity

### Mandatory

Node frontends must use the shared `--sx-*` token family as the base visual language.

Required baseline token categories:

- background
- panel
- border
- primary text
- muted text
- accent
- success
- warning
- danger
- spacing
- radius
- shadow
- font family

### Mandatory

The default node UI visual mode is dark.

Canonical baseline palette:

- `--sx-bg`: deep near-black blue
- `--sx-panel`: elevated blue-charcoal panel tone
- `--sx-border`: low-contrast cool border
- `--sx-text`: near-white foreground
- `--sx-text-muted`: desaturated secondary text
- `--sx-accent`: vivid violet accent
- `--sx-success`: green
- `--sx-warning`: amber
- `--sx-danger`: red

### Mandatory

When implementing or refreshing the shared node theme, use these exact baseline token values unless the standard is explicitly revised:

```css
:root {
  --sx-bg: 222 84% 5%;
  --sx-panel: 222 50% 10%;
  --sx-border: 217 20% 20%;
  --sx-text: 210 40% 98%;
  --sx-text-muted: 215 20% 65%;
  --sx-accent: 262 83% 58%;
  --sx-success: 142 71% 45%;
  --sx-warning: 38 92% 50%;
  --sx-danger: 0 84% 60%;

  --sx-space-1: 4px;
  --sx-space-2: 8px;
  --sx-space-3: 12px;
  --sx-space-4: 16px;
  --sx-space-5: 24px;
  --sx-space-6: 32px;

  --sx-radius-sm: 6px;
  --sx-radius-md: 10px;
  --sx-radius-lg: 14px;
  --sx-radius-pill: 999px;

  --sx-shadow-1: 0 1px 2px rgba(0, 0, 0, 0.3);
  --sx-shadow-2: 0 4px 10px rgba(0, 0, 0, 0.35);

  --sx-font-sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
}
```

### Recommended

Nodes may brand copy and feature names differently, but should not replace the foundational color language without an explicit standards update.

## 2. Page Background And Frame

### Mandatory

The application background must use the same atmospheric treatment pattern:

- a dark base background
- subtle radial accent bloom near the top-left
- optional secondary success/accent bloom offset elsewhere
- no flat white canvas

### Mandatory

The main page frame must follow this general pattern:

- full viewport minimum height
- centered application container
- width around `90vw`
- max width also constrained to `90vw`
- outer page padding around `24px` on desktop

### Mandatory

At small screens:

- content width expands to roughly `94vw`
- page padding drops to roughly `12px`

## 3. Layout Grammar

### Mandatory

The canonical node shell uses a two-column layout when space allows:

- left rail for setup flow or operational navigation
- right main content column for the active page/section

Canonical desktop ratios:

- left column: approximately `260px` to `320px`
- right column: remaining width
- gap: `24px`

### Mandatory

Operational multi-card sections should use consistent grid layouts:

- `24px` inter-card gap
- equal-width cards where practical
- stacked cards when the information density would make columns unreadable

### Mandatory

At widths around `900px` and below:

- two-column shells collapse to one column
- provider/setup/dashboard grids collapse to one column
- sticky sidebars become non-sticky

## 4. Typography And Copy Hierarchy

### Mandatory

Typography hierarchy must follow the implemented node UI shape:

- hero title: very large, compressed headline presence
- section headings: prominent but restrained
- supporting copy: muted and compact
- meta labels: small uppercase helper text

### Mandatory

Use these text roles consistently:

- `eyebrow` for product/context chip
- `h1` for page identity
- `h2` for cards and major sections
- `h3` for grouped subsections inside cards
- muted paragraph for descriptive helper copy
- tiny uppercase text for secondary metadata

### Recommended

Copy should be operator-oriented:

- direct
- status-first
- action-oriented
- low-drama
- explicit about what is blocked and what happens next

## 5. Card System

### Mandatory

The node UI is card-based.

Canonical card rules:

- dark panel background
- 1px border using the shared border tone
- medium radius around `10px`
- internal padding around `16px`
- light shadow

### Mandatory

Use card variants intentionally:

- standard card for most content
- stage card for the active setup step
- warning/degraded banner card for important operational warnings
- inset mini-panels inside cards for grouped facts or sub-settings

### Mandatory

Card headers must follow this pattern:

- heading row
- optional helper paragraph directly beneath
- bottom margin around `18px`
- no oversized decorative chrome

## 6. Status Language

### Mandatory

All node UIs must use the same four-tone state language:

- success
- warning
- danger
- neutral/meta

### Mandatory

The same status should not change colors between sections.

Examples:

- `trusted`, `approved`, `connected`, `configured` -> success
- `pending`, `connecting`, `oauth_pending` -> warning
- `rejected`, `expired`, `invalid`, `revoked` -> danger
- informational or secondary states -> neutral/meta

### Mandatory

Status surfaces must use the shared visual primitives:

- `status-pill`
- `status-badge`
- `health-indicator`
- `callout`
- `tone-*` card modifiers

### Recommended

Use colored border + tinted background + readable text, not color alone.

## 7. Hero Pattern

### Mandatory

Top-level setup or feature pages should begin with a hero card when they represent a full page or mode.

Canonical hero anatomy:

- eyebrow/context chip
- one or more status pills near the top line
- large `h1`
- short muted summary paragraph
- right-aligned action group on desktop

### Mandatory

On narrow screens:

- hero content stacks vertically
- actions become full-width buttons

## 8. Setup Flow Pattern

### Mandatory

The setup experience must use a visible flow sidebar.

Canonical flow sidebar rules:

- lives in the left column
- sticky near `top: 24px` on desktop
- uses a card container
- lists all steps in order
- shows one current step
- shows completed steps with explicit success affordance

### Mandatory

Each flow step entry must include:

- numeric index inside a circular token
- step label
- current/completed visual state
- optional completion check badge in the top-right

### Mandatory

Step tones:

- completed -> success tint
- current -> warning tint
- untouched -> neutral panel style

### Mandatory

The active step content should be rendered as a dedicated stage card on the right.

Stage card rules:

- one primary step title
- optional action aligned to the heading row
- one or more fact groups or callouts
- operator next-action clarity

## 9. Facts, State Grids, And Data Presentation

### Mandatory

Use `facts` or `state-grid` layouts instead of freeform text for structured state.

Canonical `state-grid` pattern:

- two columns on desktop
- left label column around `120px` to `180px`
- right value column fills remaining width
- labels muted
- important values rendered as `code`, pill, or status badge where appropriate

Canonical `facts` pattern:

- two equal columns on desktop
- each fact wrapped in its own bordered mini-panel
- `dt` muted and smaller
- `dd` stronger and larger

### Mandatory

At mobile widths:

- facts collapse to one column
- state grids collapse to one column

### Recommended

Prefer visible summaries over raw JSON blobs.

## 10. Form Design

### Mandatory

Forms must use a shared field rhythm:

- stacked labels and controls
- `8px` gap between label and control
- consistent padding inside inputs
- medium-radius fields
- dark panel input background
- full-width controls by default

### Mandatory

Form sections should be grouped in cards or inset window panels, not left floating on the page.

### Mandatory

Boolean controls should use one of the standard forms:

- toggle row for configuration enable/disable
- switch-pill grid for grouped runtime flags

### Recommended

Validation feedback should appear inline as callouts below the relevant action row, not hidden behind toasts only.

## 11. Buttons And Action Grouping

### Mandatory

Buttons must use a limited, repeatable hierarchy:

- primary button for the main step action
- ghost/default button for secondary actions
- disabled button for unavailable actions

### Mandatory

Action rows must:

- use `12px` gaps
- wrap on desktop when needed
- stack full-width on small screens

### Mandatory

Actions should be grouped by purpose.

Canonical grouping categories:

- configuration/setup
- runtime controls
- admin/diagnostics

## 12. Callouts And Warning Treatment

### Mandatory

Callouts are the primary in-card feedback pattern.

Canonical callout behavior:

- rectangular panel with medium radius
- padded around `12px 14px`
- bordered
- optional semantic tint

### Mandatory

Callout meanings:

- default callout: neutral instruction or context
- success callout: completed or validated state
- warning callout: waiting, blocked, or stale condition
- danger callout: failure, rejection, invalid state, or broken dependency

### Recommended

Prefer a short direct statement plus the next operator action.

## 13. Tables

### Mandatory

Dense operational collections such as tasks, records, or tracked entities should use the standard table treatment:

- full-width table
- collapsed borders
- header row with small uppercase labels
- row bottom borders
- hover tint on body rows
- horizontal overflow wrapper when content is wide

### Mandatory

Wide tables must remain usable through horizontal scrolling rather than forcing unreadable compression.

## 14. Selection And Capability Controls

### Mandatory

Multi-select capability or feature choices should use selectable option cards rather than plain checkbox lists when they represent primary onboarding decisions.

Canonical option-card rules:

- full-width row
- bordered tile
- left selection check token
- title/content stack on the right
- selected state uses success tint and stronger border

## 15. Runtime Toggles And Switch Cards

### Mandatory

Grouped runtime toggles must use the implemented switch-pill pattern for parity with the reference UI.

Canonical switch-pill rules:

- fixed minimum visual height around `56px`
- pill radius
- LED dot
- short label
- clear on/off tint
- disabled opacity state

### Recommended

Group toggles under uppercase category headers such as:

- Calls
- Analysis
- Label Family Flows

## 16. Navigation And Mode Separation

### Mandatory

Setup, provider configuration, operational dashboard, training, and diagnostics must feel like related modes inside one shell, not separate products.

### Mandatory

If a node uses a left rail for operational navigation, the nav must be:

- card-contained
- vertically stacked
- sticky on desktop
- ordinary flow content on mobile

## 17. Responsive Behavior

### Mandatory

The following responsive behaviors are required because they are part of the reference interaction model:

- desktop two-column shells collapse to one column around `900px`
- button rows stack vertically around `640px`
- flow sidebar loses sticky positioning below desktop widths
- wide fact grids collapse to one column
- control groups reduce column count before stacking

### Mandatory

No critical onboarding or operational action may become horizontally inaccessible on mobile.

## 18. Visual Boundaries Between Concerns

### Mandatory

The UI must preserve visible separation between:

- onboarding/setup
- provider setup
- operational controls
- diagnostics/admin functions

### Mandatory

Provider setup must feel like a later setup phase, not a replacement for trust/onboarding.

## 19. What Must Stay The Same

### Mandatory

If a new node claims alignment with the Hexe node visual standard, the following must remain recognizably the same:

- dark atmospheric shell
- centered page frame with generous breathing room
- card-first layout system
- setup flow sidebar with numbered steps
- shared status tone language
- pills/badges/callouts matching the reference pattern
- muted operator helper copy
- form/control styling and spacing rhythm
- responsive collapse behavior
- separation of setup, operations, and diagnostics

## 20. Allowed Variations

### Optional

These may vary without breaking the standard:

- node-specific hero copy
- exact feature naming
- exact number of dashboard cards
- provider-specific setup forms
- whether the node has training or runtime experiment pages

### Not allowed without updating the standard

- switching to a light-first visual language
- replacing cards with flat document-style pages
- inventing a different status-color system
- hiding setup progression
- using one-off form/button/badge styles per page
- collapsing setup, provider, and operational concerns into one undifferentiated page

## 21. Compliance Checklist

A node UI is visually aligned with this standard when:

- it uses the shared dark token system
- the shell, cards, and spacing follow the reference rhythm
- setup uses a visible left-rail flow model
- status indicators use the canonical tone semantics
- operational data is presented in facts/state-grid/table patterns
- forms, toggles, and action rows use the standard control grammar
- mobile collapse behavior remains readable and complete
- the overall interface feels recognizably like HexeEmail and Core-adjacent operator surfaces
