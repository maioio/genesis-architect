# Genesis Architect — Website Design System

> Written BEFORE any CSS. The page must grow from this, not the other way around.

## Product truth
Genesis is a research-first scaffolder for developers. It reads real GitHub
failures and builds them out of your project before you hit them. The buyer
is a working developer who distrusts marketing polish and reads code.

## The one big idea (the signature)
**The terminal IS the hero.** Not a screenshot beside text — the actual
command output, front and center, doing the thing. Everything else is quiet
around it. This is the "one detail at 120%, everything else at 80%" rule.

## Voice
Plain, confident, a little dry. Engineer-to-engineer. No hype words
("revolutionary", "powerful", "seamless"). PAS framing: name the pain, twist
it, resolve it. One sanctioned wink in the footer.

## Color (restrained — 1 accent, lots of neutral)
- Paper / base:  #ffffff pure, with #f6f7f9 panels (NOT warm beige, NOT dark)
- Ink:           #0b0d12 (near-black, slightly cool)
- Muted text:    #5d6470
- Hairline:      #ececf0
- ONE accent:    #0b62f5 (a single confident blue, used sparingly)
- Terminal bg:   #0b0d12 (the ink, reused — terminal feels like the ink block)
Rule: accent appears only on the primary CTA, links, and the terminal prompt.
Nowhere else. No gradients. No second accent.

## Type (one expressive pairing, not Inter-default)
- Display + UI:  "Geist" (geometric, modern, what real dev tools use)
- Mono:          "Geist Mono" (terminal, labels, code)
- NO serif. NO Inter as display. Sizes: 13 / 15 / 17 / 21 / 28 / 44 / 72.
- Headline weight 600, never 800 (800 reads as "AI shouting").
- Tight tracking on display (-0.03em). Generous line-height on body (1.6).

## Layout grammar
- 1080px max, lots of margin. Left-aligned, NOT centered (centered = generic).
- Asymmetric hero: headline left, terminal right, unequal columns.
- Hairline dividers between sections, no boxes-everywhere.
- Spacing scale only: 4 8 12 16 24 32 48 72 112. Group spacing < gap spacing.

## What makes it NOT look AI (the anti-slop contract)
- No emoji icons. No gradient backgrounds. No rounded-card-with-left-border.
- No "everything centered". No 3 identical feature cards with icons.
- The hero shows the product working (terminal), not a generic illustration.
- Real code block, high on the page, copyable.
- Whitespace does the work, not borders.
- One accent color, used with discipline.

## Sections (earned, dev-tool specific)
1. Hero — headline names the product + live terminal
2. Code proof — one real command, readable, copyable
3. Workflow — one task in 4 steps (not a feature grid)
4. Free vs Pro — honest table
5. Pricing — founder's price, first 50
6. Footer — one dry wink
