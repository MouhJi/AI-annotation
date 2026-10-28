# Landing assets

- `annotation-editor.png` is copied unchanged from `docs/phase6-viewer.png`.
  It is an actual application screenshot using a sample image in Viewer mode,
  not a screenshot of a customer's dataset or evidence of adoption/performance.
- Manrope variable font subsets are hosted locally in `/fonts/`, downloaded from
  Google Fonts on 2026-10-28. See `/fonts/Manrope-OFL.txt` for the SIL Open Font
  License. Vietnamese, Latin and extended Latin subsets cover the landing copy.
- The animated hero reuses the repository's SVG street illustration in
  `src/components/landing/ProductPreview.tsx`. Images, object names and annotator
  names in this preview are explicitly sample content. It does not call YOLO or
  change a project. Autoplay stops on manual interaction, offscreen, in hidden
  tabs, and under reduced-motion preference; visitors can pause/resume it.
- Icons in `icons/` are the Phosphor regular SVG set, downloaded from
  https://github.com/phosphor-icons/core/tree/main/assets/regular.
  The MIT license is included at `icons/LICENSE`. They are served locally.

The landing contains no customer logos, testimonials, usage figures, pricing
promises, analytics scripts or remote font requests. Privacy/usage footer links
open factual FAQ disclosures; deployment-specific legal terms belong to the
installation operator. Authentication, protected routes and the global fallback
route are intentionally unchanged.
