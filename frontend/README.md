# Prepwise — landing page (UI only)

Landing page for the Intelligent AI-Based Placement Preparation & Skill Gap
Analysis system. This is a UI-only build — no backend, no real resume
parsing. React + Vite, plain CSS (no framework), palette 1 ("Quiet
confidence") from the design discussion.

## Run it

```
npm install
npm run dev
```

Then open the printed localhost URL. `npm run build` produces a production
build in `dist/`; `npm run lint` runs oxlint.

## Structure

```
src/
  components/
    Navbar.jsx / .css          sticky header, two-tone logo mark
    Hero.jsx / .css            headline + ProfileGlance visual, entrance animation
    ProfileGlance.jsx / .css   hero visual: resume snippet -> scanning sweep -> extracted skill tags
    Pipeline.jsx / .css        the 4-step "how it works" section, one color per step
    DashboardMockup.jsx / .css animated proficiency panel (used once, in DashboardSection)
    DashboardSection.jsx / .css  dashboard showcase + copy
    ResumeUpload.jsx / .css    interactive drag-and-drop with a simulated parse progress bar
    Footer.jsx / .css
  hooks/
    useReveal.js               IntersectionObserver hook powering the .reveal / .reveal-stagger scroll animations
  index.css                    design tokens (colors, type, spacing), base styles, shared .blob-field decoration
  App.jsx                      assembles the sections
  main.jsx                     entry point
```

## Design tokens

All colors, fonts, radii, and easing live as CSS custom properties at the
top of `src/index.css`. Change the palette there and it propagates
everywhere -- no colors are hardcoded in component files.

- Display font: Fraunces (headings) -- Body font: Inter
- Primary: #2B3A67 -- Accent: #5B8DEF -- Growth/success: #3FA796 -- Warn: #C9852F

## Known gaps (by design, since this is UI only)

- Resume upload doesn't parse anything -- it's a scripted progress animation.
- ProfileGlance (hero) and DashboardMockup have hardcoded sample data.
- No routing, no auth, no API calls yet.

## Suggested next steps

- Wire ResumeUpload to an actual upload endpoint once Module 1 (profile
  parser) has an API contract.
- Replace ProfileGlance's and DashboardMockup's hardcoded data with real profile data.
- Add a dedicated /dashboard route once you move past the landing page.
