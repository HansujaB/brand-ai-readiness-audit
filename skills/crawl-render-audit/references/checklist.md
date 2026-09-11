# Access and rendering checks

- Robots rules: preserve exact matched directive, crawler role, URL and permission outcome. Do not fetch denied paths, including redirects/assets.
- Indexability: record HTTP status, response headers and meta directives. Intentional exclusions need review.
- Sitemap: malformed published XML is actionable; absence alone is not.
- Rendering: compare facts/substantive sections, never text length or framework signatures. Record viewport and partial resource failures.
- Markup: parse nested JSON-LD, microdata and RDFa; contextual missing-markup suggestions only. Compare the same entity before claiming disagreement.
- PDF/media: extract text when possible; scanned/media-only claims require visual verification. Unsupported cases remain unknown.
- Coverage: absent browser/parser or exhausted deadline is not_run, never a site finding.
