# Publishing to GitHub

## 1. Create the repo

```bash
# Install GitHub CLI if needed
brew install gh
gh auth login

# Create repo (from the fundops directory)
cd fundops
gh repo create fundops --public --description "AI-powered personal investment research platform" --source=. --push
```

## 2. Set repo topics and metadata

```bash
gh repo edit --add-topic ai,investment,finance,stock-screener,portfolio,fastapi,react,sec-edgar,openai,python
gh repo edit --homepage "https://thomasjhang.github.io/fundops"
```

## 3. Enable GitHub Pages

```bash
# GitHub Pages serves from docs/ folder on main branch
gh api repos/thomasjhang/fundops/pages -X POST -f source.branch=main -f source.path=/docs
```

Or manually: GitHub repo → Settings → Pages → Source: "Deploy from a branch" → Branch: `main`, Folder: `/docs` → Save.

## 4. Verify

- Repo: https://github.com/thomasjhang/fundops
- Pages: https://thomasjhang.github.io/fundops (may take a few minutes to deploy)

## Before pushing

Make sure these are clean:
- [ ] `.env` is in `.gitignore` (already done)
- [ ] `*.db` is in `.gitignore` (already done)
- [ ] `backend/core/.cache/` is in `.gitignore` (already done)
- [ ] No API keys in source code (run `grep -rn "your_key_here" . --include="*.py" --include="*.yaml"`)
- [ ] `config/workflow.yaml` uses `${SEC_USER_AGENT}` not a real email

All of these are already configured.
