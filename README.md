# gh-init-repo

> Optimized workflow for creating GitHub repositories from local projects using GitHub CLI.

## Overview

`/gh-init-repo` is an interactive slash command that streamlines the process of:
1. Initializing a local Git repository
2. Creating a `.gitignore` file
3. Creating a basic `README.md`
4. Creating a GitHub repository via GitHub CLI
5. Pushing the initial commit

## Features

- ✅ **CLAUDE.md enforcement** - Requires CLAUDE.md before proceeding (blocking)
- ✅ **Visibility requirement** - Must specify `--public` or `--private` (blocking, default: private)
- ✅ **Interactive workflow** - Confirms every step before executing
- ✅ **Smart defaults** - Uses directory name as repository name
- ✅ **Automatic files** - Creates `.gitignore` and `README.md`
- ✅ **GitHub CLI integration** - Uses `gh` for fast repository creation

## Installation

### Via Local Plugins Directory

Clone or copy this plugin to your local plugins directory:

```bash
cp -r gh-init-repo ~/.claude/plugins/
```

Restart Claude Code to load the plugin.

### Via Marketplace (Coming Soon)

This plugin will be available for installation via marketplace.

## Prerequisites

1. **GitHub CLI** installed and authenticated:
   ```bash
   gh auth login
   ```

2. **Git** installed:
   ```bash
   git --version
   ```

## Usage

### Basic Usage

Navigate to your project directory and run:

```bash
# Create a private repository (default)
/gh-init-repo --private

# Create a public repository
/gh-init-repo --public

# Create with a custom repository name
/gh-init-repo --public my-custom-name
/gh-init-repo --private my-project
```

### Workflow

1. **Prechecks** - Verifies GitHub CLI auth and Git status
2. **CLAUDE.md check** - Blocks if CLAUDE.md doesn't exist (use `/init` to create)
3. **Visibility confirmation** - Requires `--public` or `--private` flag
4. **Repository details** - Confirms name, visibility, and location
5. **File review** - Shows what will be included in initial commit
6. **Create .gitignore** - Generates comprehensive .gitignore
7. **Create README.md** - Generates basic README template
8. **Initialize Git** - Runs `git init` with `main` branch
9. **Initial commit** - Stages and commits all files
10. **Create GitHub repo** - Uses `gh repo create` with push
11. **Verification** - Shows final status and next steps

### Requirements (Blocking)

#### CLAUDE.md Required

The command requires a `CLAUDE.md` file in the project directory. This ensures:

- Project context is preserved across Claude Code sessions
- Development guidelines are documented
- Team conventions are established

Create CLAUDE.md with:
- `/init` - Generates a template
- Manual creation - Create `CLAUDE.md` manually

#### Visibility Required

You **must** specify repository visibility:

```bash
/gh-init-repo --public   # Public repository
/gh-init-repo --private  # Private repository (default)
```

The command will **not proceed** without this flag.

## What Gets Created

### .gitignore

A comprehensive `.gitignore` with common exclusions for:
- Dependencies (node_modules/, vendor/, __pycache__)
- Environment files (.env, .env.local)
- Logs (*.log)
- IDE files (.vscode/, .idea/)
- Build outputs (dist/, build/)
- OS files (.DS_Store)

### README.md

A basic `README.md` template with sections for:
- Project name and description
- Overview
- Installation
- Usage
- Development
- License

## Examples

### New Node.js Project

```bash
mkdir my-express-app && cd my-express-app
npm init -y
# ... add some files ...
/gh-init-repo --private
```

### New Python Project

```bash
mkdir my-script && cd my-script
# ... add your script ...
/gh-init-repo --public my-python-script
```

### Existing Project

```bash
cd existing-project
# Make sure CLAUDE.md exists!
/gh-init-repo --private
```

## After Initialization

Once your repository is created:

```bash
# View repository on GitHub
gh repo view --web

# Add more files
git add .
git commit -m "Add new feature"
git push

# Create a branch
git checkout -b feature-name
```

## Troubleshooting

### GitHub CLI not authenticated

```bash
gh auth login
```

### Already a Git repository

The command will ask if you want to continue with the existing repository or stop.

### CLAUDE.md doesn't exist

Create it first:
```bash
/init  # Generates a template
# or manually create CLAUDE.md
```

Then run `/gh-init-repo` again.

### Repository name already exists

You'll be asked to choose a different name.

## License

MIT

## Contributing

Contributions welcome! Feel free to submit issues and pull requests.

---

**Made with ❤️ for fast project initialization**
