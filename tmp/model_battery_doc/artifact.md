# Model battery analysis document contract

## Reference

- Source: `/Users/forstmac/Desktop/NTU/PE6201/A2/PE6201_A2_Team_Report_Framework.docx`
- SHA-256: `90e80316a3521155c890872dc6c8fd633026ea3146854096446fb7f6612a029c`
- Cached metadata: 15 pages, 1 section, 117 body paragraphs, 22 tables
- Package inspection: `word/document.xml`, `word/styles.xml`, `word/header1.xml`, `word/footer1.xml`
- Rendering limitation: the packaged LibreOffice runtime is unavailable on this host; the final is rendered through Word-compatible OOXML and structurally validated.

## Page system

- Letter portrait, 12240 by 15840 twips
- Margins: top and bottom 1037 twips; left and right 1181 twips
- Header and footer distance: 720 twips
- One section with default header and footer relationships preserved

## Typography and components

- Reuse source paragraph styles: Title `aa`, Subtitle `ac`, Normal `a1`, Heading 1 `1`, Heading 2 `21`
- Force title and headings to black with direct formatting
- Body text: Aptos 10.5 pt, 1.12 line spacing, 6 pt after
- Comparison tables: fixed widths, dark blue header fill, white header text, light gray borders, alternating pale blue rows
- No decorative rules or boxed callouts
- Header: `PE6201 A2 Model Battery Analysis`
- Footer: `Team working document | Page N`

## Content flow

1. Title, scope, and main conclusion
2. Evaluation design and interpretation limits
3. Cross-model result tables
4. Per-model failure analysis
5. Cross-model findings and report implications
6. Source files and follow-up checks

## Slot map

- The framework body is replaced because this is a separate evidence memo, not the final 2,000-word report.
- The framework styles, theme, numbering, relationships, page geometry, and package support parts are preserved.
- Header and footer text are intentionally updated for the new document purpose.
- All metrics are generated from `A2_scaffold/results_live_*.json`; analysis is explicitly marked as interpretation where appropriate.

## Fidelity gates

- Reference file remains byte-for-byte unchanged.
- Section geometry and style identifiers remain source-derived.
- Tables must wrap without fixed row heights.
- Every model name, trial count, failure count, token count, and cost must match its JSON source.
- The final package must open as valid OOXML and round-trip to plain text through macOS `textutil`.
