# md4help-center

Zendesk Help Center to Markdown exporter - converts help center articles into LLM-friendly Markdown files with YAML frontmatter.

## Architecture

```text
src/md4help_center/
├── __init__.py          # Package exports: main, generate_info_file
├── main.py              # Core exporter: fetches articles → converts to Markdown
└── info_generator.py    # Structure generator: outputs JSON tree of help center
```

### Data Flow

1. Authenticate with Zendesk API using email/token
2. Fetch categories → sections → articles (handles pagination)
3. Filter by ignore lists (optional)
4. Convert HTML bodies to Markdown via `markdownify`
5. Write files with YAML frontmatter to `backups_md/{date}/{locale}/{category}/{section}/`

## Commands

```bash
# Main exporter
uv run md4help-center [--no-section] [--ignore-file path/to/ignore.json]

# Structure generator (outputs JSON tree for reference/debugging)
uv run generate-info-file [--output filename.json] [--lang en-us]
```

## Environment Variables

Required in `.env`:

```bash
ZENDESK_USER=email@example.com
ZENDESK_TOKEN=your_api_token
ZENDESK_DOMAIN=yourcompany.zendesk.com
```

## Code Conventions

- **Formatter/Linter**: Ruff (single quotes, 120 char line length)
- **Python**: 3.13+
- **Package manager**: uv
- **Pre-commit hooks**: ruff, ruff-format, uv-lock, uv-export

Run before committing:

```bash
uv run ruff check --fix .
uv run ruff format .
```

## Key Functions

| Function                   | Location             | Purpose                      |
| -------------------------- | -------------------- | ---------------------------- |
| `main()`                   | main.py:81           | CLI entry point for exporter |
| `fetch_all_zendesk_data()` | main.py:48           | Paginated API fetcher        |
| `sanitize_name()`          | main.py:24           | Safe filename generator      |
| `generate_info_file()`     | info_generator.py:74 | JSON structure generator     |

## Output Format

Articles are saved as Markdown with YAML frontmatter:

```markdown
---
title: "Article Title"
source_url: "https://..."
category: "Category Name"
section: "Section Name"
tags: ["tag1", "tag2"]
---

# Article Title

[converted markdown content]
```

## Ignore File Format

JSON5 file for `--ignore-file`:

```json5
{
  "category": [{ "id": 123456 }],
  "section": [{ "id": 789012 }],
  "article": [{ "id": 345678 }]
}
```
