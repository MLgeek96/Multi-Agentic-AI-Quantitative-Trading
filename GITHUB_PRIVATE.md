# Private GitHub repository

Target: `bakapig/Multi-Agentic-AI-Quantitative-Trading`.

This checkout contains source, configuration, tests and research reports. Raw data,
processed caches, virtual environments, trained models, backtest blobs, runtime
databases, agent/LLM transcripts, credentials and scratch directories are excluded.
Required assignment ledgers already in `live/` can be versioned; market-data caches
and logs are ignored. Private visibility grants access only to authorized accounts;
secrets must still stay out of commits.

Initial publication from the project directory:

```powershell
gh auth status
git init -b main
git add .github README.md ARCHITECTURE.md GITHUB_PRIVATE.md requirements.txt .gitignore crypto_agents crypto_quant config scripts tests references reports live freqtrade algorithmic_trading_strategy_project_brief_execution_roadmap.md
git diff --cached --stat
python scripts/check_publication.py
git commit -m "Add quantitative research and audited agent architecture"
gh repo create bakapig/Multi-Agentic-AI-Quantitative-Trading --private --source . --remote origin --push
gh repo view bakapig/Multi-Agentic-AI-Quantitative-Trading --json visibility,url
```

These are one-time setup commands; do not repeat initialization or repository
creation after this checkout is published. Check visibility before pushing to an
existing remote. Git author identity is configured locally or globally with
`git config user.name` and `git config user.email`.

For later changes:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
git status --short
git add crypto_agents crypto_quant config scripts tests ARCHITECTURE.md README.md reports
git diff --cached --stat
python scripts/check_publication.py
git commit -m "Describe the change"
git push origin main
```

If assignment ledgers change, add the intended `live/` files explicitly. Data is
recreated using the downloader/prepare commands in README, not stored in GitHub.
Invite teammates through the repository's Settings -> Collaborators. Publication
does not install a schedule, fetch fresh candles or enable exchange orders.

Reference: [GitHub CLI private repository creation](https://cli.github.com/manual/gh_repo_create).
