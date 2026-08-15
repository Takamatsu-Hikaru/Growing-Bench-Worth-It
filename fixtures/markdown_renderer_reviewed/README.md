# Documentation renderer

`renderMarkdown(source)` renders Markdown for the documentation surface.
The application uses markdown-it 14.1.0 with raw HTML disabled and has an existing allowlist sanitizer. Inputs larger than 100 KiB must be rejected. Read `config/source-policy.json` before choosing controls.
