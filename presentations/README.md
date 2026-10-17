# FE5209 investor materials

The current system is Pairs-only. Use the updated speaking script and
[current architecture](../ARCHITECTURE.md#human-ai-and-code-ownership).
The slide decks below retain the earlier multi-PM mandate and are historical
until regenerated. Crypto is no longer connected to the active fund.

## Investor roadshow, 17 October 2026

- [Human, AI and code ownership diagram](../ARCHITECTURE.md#human-ai-and-code-ownership)
- [Editable 14-slide investor roadshow](roadshow_20261017/FE5209_Investor_Roadshow_v2.pptx)
- [Roadshow PDF preview](../output/pdf/FE5209_Investor_Roadshow_v2.pdf)
- [Four-slide one-minute pitch](roadshow_20261017/FE5209_60_Second_Pitch_v2.pptx)
- [Pitch and submission guide](../output/pdf/FE5209_Roadshow_Pitch_and_Submission_Guide.pdf)
- [Presentation materials ZIP](roadshow_20261017/FE5209_Roadshow_Materials.zip)

The proposed governance is Investors, a human Board of Directors, an Investment
Committee / CIO, and three strategy PMs. The Investment Committee takes the
presentation role previously called Portfolio Coordinator. Coded risk retains
approval authority. This revision reflects the newer local crypto/pairs
integration and separates historical crypto baseline results from pending
consolidated fund performance.

The pack includes a 124-word narration script, timed storyboard in the guide,
draft subtitles and a detailed checklist for the 24 October submission. It is
a presentation handoff pack rather than the final course ZIP. Member names,
final out-of-sample results, strategy/data packaging and optional video recording
remain team work. No Canvas or registration-sheet update has taken place.

### Full investor walkthrough

The [editable speaking script](roadshow_20261017/Investor_System_Walkthrough_and_QA.docx)
and [plain-text rehearsal copy](roadshow_20261017/Investor_System_Walkthrough_and_QA.txt)
provide a complete Pairs-only walkthrough with current dashboard cues, the
teammate strategy source, independent risk, Committee Chair and Phantom Book,
15 investor questions, and a one-minute pitch. The account is now USD 1.5M Pairs,
USD 1.5M Momentum reserve, and USD 2M central cash. The
[document builder](source/build_investor_walkthrough.py) and
[narration content](source/pairs_walkthrough_content.py) retain the source.
The existing PPTX files and earlier narration have not been regenerated.

Rebuild these materials with [build_roadshow.mjs](source/build_roadshow.mjs), then
[export_roadshow_pack.py](source/export_roadshow_pack.py). They use the same runtime
variables described below. Use fresh build and output directories and set
`FE5209_PDF_OUTPUT_DIR` to a fresh PDF directory when rebuilding because finalized
files are preserved. The PDF previews are raster slide images.
Native editable content and the presenter notes remain in the PowerPoint files.

## Earlier scope deck, 14 October 2026

- [Expanded 12-slide PowerPoint with speaker notes](FE5209_Multi_Agent_Project_Expanded.pptx)
- [Matching PDF preview](../output/pdf/FE5209_Multi_Agent_Project_Expanded.pdf)
- [Interactive fund explainer](design/three-pm-fund.html): download and open in a browser.

That earlier deck is dated 14 October 2026. It describes a proposed USD 5 million
paper fund with equity momentum, pairs trading and crypto PMs. Initial illustrative
mandates are USD 1.5 million per PM and USD 0.5 million of central cash. Pairs
frequency is confirmed as daily. The teammates' exact tickers, momentum cadence
and signal/fill conventions still need confirmation.

Each proposed AI PM representative selects diagnostic tools and writes a memo
linked to computed evidence. Quantitative engines calculate target positions.
A coordinator combines portfolios and assigns capital, and an independent risk
controller governs execution. The slides describe the design before the local
two-PM integration. The [current implementation guide](../fund_agents/README.md)
now runs the Pairs PM with diagnostic tools and independent fund risk.
Momentum, automatic LLM provider calls, fills and consolidated performance
remain future work. The deck has not been regenerated for this implementation.

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
