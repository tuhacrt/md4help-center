# md4help-center

Export Zendesk Help Center articles to Markdown files with YAML frontmatter - ideal for LLM training, documentation backups, or static site generation.

## Features

- Exports all articles from your Zendesk Help Center
- Converts HTML to clean Markdown
- Adds YAML frontmatter (title, URL, category, section, tags)
- Organizes files by category/section hierarchy
- Supports filtering via ignore lists
- Auto-detects error codes in titles and adds corresponding tags

## Installation

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/youruser/md4help-center.git
cd md4help-center
uv sync
```

## Configuration

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Edit `.env` with your Zendesk credentials:

```bash
ZENDESK_USER=your-email@example.com
ZENDESK_TOKEN=your-api-token
ZENDESK_DOMAIN=yourcompany.zendesk.com
```

To get an API token: Zendesk Admin > Apps and integrations > APIs > Zendesk API > Add API token.

## Usage

### Export Articles

```bash
uv run md4help-center
```

Output structure:

```text
backups_md/
└── 2025-05-28/
    └── en-us/
        ├── Category_Name/
        │   ├── Section_Name/
        │   │   ├── Article_Title.md
        │   │   └── Another_Article.md
        │   └── Other_Section/
        │       └── ...
        └── _log.csv
```

### Options

| Flag                 | Description                                                  |
| -------------------- | ------------------------------------------------------------ |
| `--no-section`       | Flatten structure - place articles directly under categories |
| `--ignore-file PATH` | JSON file specifying IDs to skip                             |

Example with options:

```bash
uv run md4help-center --no-section --ignore-file ignore.json
```

### Generate Structure File

Preview your Help Center structure without exporting:

```bash
uv run generate-info-file --output structure.json --lang en-us
```

## Ignore File Format

Create a JSON5 file to exclude specific content:

```json5
{
  "category": [
    { "id": 123456789 }
  ],
  "section": [
    { "id": 987654321 }
  ],
  "article": [
    { "id": 111222333 }
  ]
}
```

## Output Format

Each article becomes a Markdown file with frontmatter:

```markdown
---
title: "Getting Started Guide"
source_url: "https://yourcompany.zendesk.com/hc/en-us/articles/123456"
category: "Documentation"
section: "Basics"
tags: ["getting-started", "tutorial"]
---

# Getting Started Guide

[Article content in Markdown...]
```

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Setup pre-commit hooks
pre-commit install

# Run linter
uv run ruff check --fix .

# Run formatter
uv run ruff format .
```

## License

MIT
