---
description: Initialize local Git repo and create GitHub repository interactively
argument-hint: --public | --private [repo-name]
allowed-tools: Bash(git init:*), Bash(git add:*), Bash(git commit:*), Bash(git remote:*), Bash(git branch:*), Bash(git push:*), Bash(git status:*), Bash(gh repo create:*), Bash(gh auth status:*), Bash(test -f:*), Bash(basename:*), Bash(pwd:*), Read, Write
---

# gh-init-repo: Initialize Git and GitHub Repository

Interactive workflow to initialize a Git repository locally and create the corresponding GitHub repository using GitHub CLI.

## Preconditions

First, verify that GitHub CLI is authenticated and the current directory is not already a Git repository.

```bash
# Check GitHub CLI authentication
!gh auth status

# Check if already a Git repository
test -d .git && GIT_REPO_EXISTS="yes" || GIT_REPO_EXISTS="no"
```

If GitHub CLI is not authenticated, instruct the user to run `gh auth login` first.

If the directory is already a Git repository, ask if they want to:
1. Continue with this repository (add remote and push)
2. Stop and run in a different directory

**Workflow State Variables:**
- `$GIT_REPO_EXISTS` - "yes" if already a git repo, "no" otherwise
- `$CLAUDE_MD_EXISTS` - "yes" if CLAUDE.md exists, "no" otherwise
- `$README_EXISTS` - "yes" if README.md exists, "no" otherwise

Use these variables in workflow decisions rather than re-checking.

## CLAUDE.md Requirement (BLOCKING)

Before proceeding, check if CLAUDE.md exists in the current directory:

```bash
test -f CLAUDE.md && CLAUDE_MD_EXISTS="yes" || CLAUDE_MD_EXISTS="no"
```

**If CLAUDE.md does NOT exist, this is BLOCKING:**

You MUST stop and ask the user to create a CLAUDE.md file first. Explain:

"⚠️ **CLAUDE.md is required** before initializing a Git repository.

A CLAUDE.md file provides project context for Claude Code across sessions. Without it, you lose the benefits of Claude's memory system.

Please create a CLAUDE.md file with:
- Project purpose
- Key technologies
- Development guidelines
- Team conventions

Run `/init` to create a template, or create CLAUDE.md manually.

Once CLAUDE.md exists, run `/gh-init-repo` again."

**Only proceed after CLAUDE.md exists.**

## Visibility Requirement (BLOCKING)

Check the command arguments for visibility flag:

```bash
# $ARGUMENTS contains the full argument string
```

**If neither `--public` nor `--private` is specified, this is BLOCKING:**

You MUST ask the user to specify visibility:

"⚠️ **Repository visibility is required**

Please specify:
- `/gh-init-repo --public` for a public repository
- `/gh-init-repo --private` for a private repository (default)

You can also include a custom repository name:
- `/gh-init-repo --public my-custom-name`
- `/gh-init-repo --private my-project"

**Do NOT proceed until visibility is specified.**

## Interactive Workflow

Once preconditions are met and requirements are satisfied, proceed interactively:

### Step 1: Confirm Repository Details

Get the current directory name as the default repository name:

```bash
!basename $(pwd)
```

Ask the user to confirm:

"📋 **Repository Details:**

- **Name:** [directory-name]
- **Visibility:** [--public or --private from arguments]
- **Location:** [current working directory]

Confirm? (yes/no/edit name)"

If they want to edit the name, ask for the new name and update the repository name.

### Step 2: Review Files to Commit

Show what will be included in the initial commit:

```bash
!git status --short 2>/dev/null || echo "No files yet (new repository)"
```

Explain what will be created:
- `.gitignore` with common exclusions
- `README.md` with basic project information
- All existing files in the directory

Ask: "Proceed with these files? (yes/no)"

### Step 3: Create .gitignore

Create a comprehensive `.gitignore` file:

```bash
cat > .gitignore << 'EOF'
# Dependencies
node_modules/
vendor/
__pycache__/
*.pyc
.pip
venv/
ENV/

# Environment files
.env
.env.local
.env.*.local
*.env

# Logs
*.log
npm-debug.log*
yarn-debug.log*
yarn-error.log*
pnpm-debug.log*
lerna-debug.log*

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Build outputs
dist/
build/
*.min.js
*.min.css

# Testing
coverage/
.nyc_output/

# Misc
.cache/
.temp/
tmp/
*.tmp
EOF
```

Ask: ".gitignore created. Review or proceed? (review/proceed)"

If they want to review, show the contents and ask to continue.

### Step 4: Create/Update README.md

Check if README.md exists:

```bash
test -f README.md && README_EXISTS="yes" || README_EXISTS="no"
```

**If README.md does NOT exist, create a basic one:**

```markdown
# [Repository Name]

> [Brief description of what this project does]

## Overview

[Project overview and purpose]

## Installation

```bash
# Installation instructions
```

## Usage

```bash
# Usage examples
```

## Development

[Development guidelines and setup]

## License

[License information]

---

*Created with `/gh-init-repo`*
```

Ask: "README.md created. Customize later or edit now? (later/edit)"

### Step 5: Initialize Git Repository

Initialize the repository:

```bash
!git init
!test -d .git || { echo "❌ Git initialization failed - .git directory not created"; return 1; }
!git branch -M main
echo "✅ Git repository initialized with 'main' branch"
```

### Step 6: Stage and Commit

Show the status again:

```bash
git status
```

Ask: "Ready to commit. Enter a commit message or press Enter for default:"

Default commit message: "feat: initial commit"

Execute:

```bash
!git add .
!git commit -m "[commit message from user or default]"
!git log -1 --oneline || { echo "❌ Commit failed"; return 1; }
echo "✅ Initial commit created"
```

### Step 7: Create GitHub Repository

Use GitHub CLI to create the repository:

```bash
# Parse visibility from arguments
# If $ARGUMENTS contains --public, create public
# If $ARGUMENTS contains --private or neither, create private

!gh repo create [repo-name] --[visibility] --source=. --remote=origin --push
!git remote get-url origin >/dev/null || { echo "❌ GitHub repository creation failed - remote 'origin' not found"; return 1; }
echo "✅ GitHub repository created and pushed"
```

The `--source=.` flag adds the current directory as a remote.
The `--remote=origin` flag names the remote "origin".
The `--push` flag pushes the current branch immediately.

### Step 8: Final Verification

Show the final status:

```bash
echo "Repository URL: $(git remote get-url origin)"
git status
```

Provide a summary:

"✨ **Repository initialized successfully!**

🔗 **GitHub:** [repository URL]
📁 **Local:** [working directory]
🌿 **Branch:** main

**Next steps:**
- Add more files: `git add . && git commit -m 'message' && git push`
- Create branches: `git checkout -b feature-name`
- View on GitHub: `gh repo view --web`

Happy coding! 🚀"

## Error Handling

If any step fails:

1. **Git init fails**: Explain the error and suggest checking directory permissions
2. **GitHub CLI fails**: Suggest running `gh auth login` to re-authenticate
3. **Push fails**: Check for authentication issues or merge conflicts
4. **Repository name exists**: Ask for a different name or to use `--source` with existing repo

## Tips

- Use `--public` for open source projects
- Use `--private` (default) for personal or private projects
- Customize the commit message for better history
- Edit README.md after creation to add project-specific details
- Run `gh repo view --web` to open the repository in a browser
