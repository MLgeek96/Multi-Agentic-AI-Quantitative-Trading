# FE5209 multi-agent project materials

## Latest deck

- [Expanded 12-slide PowerPoint with speaker notes](FE5209_Multi_Agent_Project_Expanded.pptx)
- [Matching PDF preview](../output/pdf/FE5209_Multi_Agent_Project_Expanded.pdf)
- [Interactive fund explainer](design/three-pm-fund.html): download and open in a browser.

The latest deck is dated 14 October 2026. It describes a proposed USD 5 million
paper fund with equity momentum, pairs trading and crypto PMs. Initial illustrative
mandates are USD 1.5 million per PM and USD 0.5 million of central cash. Pairs
frequency is confirmed as daily. The teammates' exact tickers, momentum cadence
and signal/fill conventions still need confirmation.

Each proposed AI PM representative selects diagnostic tools and writes a memo
linked to computed evidence. Quantitative engines calculate target positions.
A coordinator combines portfolios and assigns capital, and an independent risk
controller governs execution. The combined fund and connected AI representatives
remain proposed work. The slides distinguish that scope from the existing crypto
prototype and its research limitations.

The PDF is a visual preview. Editable objects and presenter notes are in the PPTX.
GitHub stores these files; this upload does not deploy a trading service.

## Earlier short version

- [Original 9-slide scope deck](FE5209_Multi_Agent_Project_Scope_v2.pptx)
- [Original PDF preview](../output/pdf/FE5209_Multi_Agent_Project_Scope.pdf)

## Build sources

- [Expanded deck builder](source/build_deck.mjs)
- [PDF preview exporter](source/export_pdf_preview.py)
- [Editable explainer fragment](design/three-pm-fund.fragment.html)

The builder uses the Codex desktop bundled `@oai/artifact-tool` runtime and the
presentation skill's finalizer. It requires access to those local dependencies,
including the bundled Python runtime. It does not install dependencies or call
an LLM or market-data API. Generated scratch files stay under ignored directories.

Set these environment variables using the paths reported by Codex's workspace
dependency loader:

| Variable | Value |
| --- | --- |
| `RUNTIME_NODE` | Bundled Node.js executable |
| `RUNTIME_NODE_MODULES` | Bundled Node.js package directory |
| `RUNTIME_PYTHON` | Bundled Python executable |
| `FE5209_PRESENTATION_SKILL_DIR` | Installed presentations skill directory |
| `FE5209_DECK_BUILD_DIR` | A new local build directory for each run |

Then run from the repository root in PowerShell:

```powershell
& $env:RUNTIME_NODE presentations/source/build_deck.mjs
& $env:RUNTIME_PYTHON presentations/source/export_pdf_preview.py
```

The default build directory is `.codex-build/fe5209-deck-rebuild`. The builder
writes the PPTX under its `exports/` subdirectory and PNGs under `previews/`.
The PDF exporter uses the same build directory and validates all 12 pages and
the USD 5 million allocation. Set `FE5209_DECK_OUTPUT_DIR` to use a different
export directory. Existing exports and validation receipts are preserved, so
choose a fresh build directory when rebuilding.

The sources reproduce the expanded deck. The earlier short deck is retained as
a reviewed historical export. Raw market data, credentials, local databases,
LLM transcripts and temporary chart workbooks are excluded from this upload.
