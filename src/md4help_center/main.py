"""script to fetch and backup Zendesk Help Center articles as Markdown files."""

import argparse
import csv
import datetime
import os
import re

import dotenv
import json5
import markdownify  # type: ignore
import requests

dotenv.load_dotenv()

ZENDESK_API_TOKEN = os.getenv('ZENDESK_TOKEN')
ZENDESK_USER_EMAIL = os.getenv('ZENDESK_USER')
ZENDESK_DOMAIN = os.getenv('ZENDESK_DOMAIN')
ZENDESK_SUBDOMAIN = f'https://{ZENDESK_DOMAIN}'
BACKUP_FOLDER = 'backups_md'
LANGUAGE = 'en-us'


def sanitize_name(name: str) -> str:
    """Sanitize names to be safe for use in file paths and URLs."""
    if not name:
        return 'Unnamed'
    name = name.replace('/', '_').replace('\\', '_')
    safe_name = ''.join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip()
    safe_name = re.sub(r'[_ ]+', '_', safe_name)
    if not safe_name or safe_name == '_' or all(c == '_' for c in safe_name):
        return 'Sanitized_Content'
    return safe_name


def fetch_all_zendesk_data(endpoint: str, credentials: tuple) -> list:
    """Fetch all paginated data from a Zendesk endpoint."""
    results = []
    current_endpoint = endpoint
    while current_endpoint:
        try:  # Added try-except for network/request issues
            response = requests.get(current_endpoint, auth=credentials, timeout=30)  # Added timeout
            if response.status_code == 404:
                print(f'Warning: Endpoint {current_endpoint} not found (404). Skipping.')
                break
            response.raise_for_status()
            data = response.json()

            data_key = None
            if 'articles' in data:
                data_key = 'articles'
            elif 'sections' in data:
                data_key = 'sections'
            elif 'categories' in data:
                data_key = 'categories'

            if data_key and data_key in data:
                results.extend(data[data_key])
            else:
                print(f'Warning: No standard data key found in response from {current_endpoint}. Data: {data}')

            current_endpoint = data.get('next_page')
        except requests.exceptions.RequestException as e:
            print(f'Error fetching data from {current_endpoint}: {e}')
            break  # Stop trying if a request fails
    return results


def main() -> None:
    """Fetch and backup Zendesk Help Center articles."""
    parser = argparse.ArgumentParser(description='Fetch and backup Zendesk Help Center articles as Markdown files.')
    parser.add_argument(
        '--no-section',
        action='store_true',
        help='Place articles directly under category folders, without section subfolders.',
    )
    # --- New argument for ignore file ---
    parser.add_argument(
        '--ignore-file',
        type=str,
        default=None,  # Changed from default='ignore.json' to make it optional unless specified
        help='Path to a JSON file specifying category_ids, section_ids, or article_ids to ignore.',
    )
    args = parser.parse_args()

    ignore_config = {'ignore_category_ids': set(), 'ignore_section_ids': set(), 'ignore_article_ids': set()}
    if args.ignore_file:
        try:
            with open(args.ignore_file, encoding='utf-8') as f:
                loaded_ignores = json5.load(f)

                # Get lists of objects, default to empty list if key is missing
                raw_cat_ignores = loaded_ignores.get('category', [])
                raw_sec_ignores = loaded_ignores.get('section', [])
                raw_art_ignores = loaded_ignores.get('article', [])

                # Extract IDs, ensuring items are dicts and have an 'id' key
                if isinstance(raw_cat_ignores, list):
                    ignore_config['ignore_category_ids'] = {
                        item['id'] for item in raw_cat_ignores if isinstance(item, dict) and 'id' in item
                    }
                else:
                    print("Warning: 'category' in ignore file is not a list. Skipping category ignores.")

                if isinstance(raw_sec_ignores, list):
                    ignore_config['ignore_section_ids'] = {
                        item['id'] for item in raw_sec_ignores if isinstance(item, dict) and 'id' in item
                    }
                else:
                    print("Warning: 'section' in ignore file is not a list. Skipping section ignores.")

                if isinstance(raw_art_ignores, list):
                    ignore_config['ignore_article_ids'] = {
                        item['id'] for item in raw_art_ignores if isinstance(item, dict) and 'id' in item
                    }
                else:
                    print("Warning: 'article' in ignore file is not a list. Skipping article ignores.")

            print(f'Loaded ignore configuration from {args.ignore_file}')
            if ignore_config['ignore_category_ids']:
                print(f'Ignoring category IDs: {sorted(ignore_config["ignore_category_ids"])}')
            if ignore_config['ignore_section_ids']:
                print(f'Ignoring section IDs: {sorted(ignore_config["ignore_section_ids"])}')
            if ignore_config['ignore_article_ids']:
                print(f'Ignoring article IDs: {sorted(ignore_config["ignore_article_ids"])}')

        except FileNotFoundError:
            print(f"Warning: Ignore file '{args.ignore_file}' not found. Proceeding without ignoring specific items.")
        except (json5.JSONDecodeError, ValueError) as e:  # Catching broader errors json5 might raise
            print(
                f"Warning: Error decoding ignore file '{args.ignore_file}'. "
                f"Please ensure it's a valid JSON5/JSONC format. Error: {e}"
            )
        except Exception as e:  # noqa: BLE001
            print(
                f"Warning: Could not load or parse ignore file '{args.ignore_file}': {e}. "
                'Proceeding without specific ignores.'
            )

    date_today = datetime.datetime.now(tz=datetime.UTC).date()
    base_run_path = os.path.join(BACKUP_FOLDER, str(date_today), LANGUAGE)
    if not os.path.exists(base_run_path):
        os.makedirs(base_run_path)

    log = []
    credentials = (f'{ZENDESK_USER_EMAIL}/token', ZENDESK_API_TOKEN)
    if not all([ZENDESK_USER_EMAIL, ZENDESK_API_TOKEN, ZENDESK_DOMAIN]):
        print('Error: Zendesk credentials or domain not found in environment variables (.env file).')
        print('Please ensure ZENDESK_TOKEN, ZENDESK_USER, and ZENDESK_DOMAIN are set.')
        return

    # --- Fetch and Filter Categories ---
    print('Fetching categories...')
    category_map = {}
    kept_category_ids = set()
    try:
        categories_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/categories.json'
        raw_categories_data = fetch_all_zendesk_data(categories_endpoint, credentials)

        categories_data_filtered = []
        for cat in raw_categories_data:
            if cat['id'] in ignore_config['ignore_category_ids']:
                print(f"Ignoring category: ID {cat['id']}, Name '{cat.get('name', 'N/A')}' (due to ignore file).")
                continue
            categories_data_filtered.append(cat)

        category_map = {cat['id']: sanitize_name(cat['name']) for cat in categories_data_filtered}
        kept_category_ids = set(category_map.keys())
        print(f'Fetched {len(raw_categories_data)} categories, keeping {len(category_map)} after filtering.')
    except requests.exceptions.HTTPError as e:
        print(f'Failed to retrieve categories: {e}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching categories: {e}')
        return

    # --- Fetch and Filter Sections ---
    print('Fetching sections...')
    section_map = {}
    kept_section_ids = set()
    try:
        sections_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/sections.json'
        raw_sections_data = fetch_all_zendesk_data(sections_endpoint, credentials)

        sections_data_filtered = []
        for sec in raw_sections_data:
            if sec['id'] in ignore_config['ignore_section_ids']:
                print(f"Ignoring section: ID {sec['id']}, Name '{sec.get('name', 'N/A')}' (due to ignore file).")
                continue
            if sec.get('category_id') not in kept_category_ids:
                # This section's category was filtered out
                print(
                    f"Ignoring section: ID {sec['id']}, Name '{sec.get('name', 'N/A')}' "
                    f'(its category ID {sec.get("category_id")} was ignored).'
                )
                continue
            sections_data_filtered.append(sec)

        section_map = {
            sec['id']: {'name': sanitize_name(sec['name']), 'category_id': sec['category_id']}
            for sec in sections_data_filtered
        }
        kept_section_ids = set(section_map.keys())
        print(f'Fetched {len(raw_sections_data)} sections, keeping {len(section_map)} after filtering.')
    except requests.exceptions.HTTPError as e:
        print(f'Failed to retrieve sections: {e}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching sections: {e}')
        return

    # --- Fetch and Filter Articles ---
    print('Fetching articles...')
    all_articles = []
    try:
        articles_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/articles.json'
        raw_articles_data = fetch_all_zendesk_data(articles_endpoint, credentials)

        articles_data_filtered = []
        for art in raw_articles_data:
            if art['id'] in ignore_config['ignore_article_ids']:
                print(f"Ignoring article: ID {art['id']}, Title '{art.get('title', 'N/A')}' (due to ignore file).")
                continue

            article_section_id = art.get('section_id')
            if article_section_id and article_section_id not in kept_section_ids:
                # This article's section was filtered out (either directly or its category was)
                print(
                    f"Ignoring article: ID {art['id']}, Title '{art.get('title', 'N/A')}' "
                    f'(its section ID {article_section_id} was ignored or belongs to an ignored category).'
                )
                continue
            # If article_section_id is None, it means it's not in a section we're tracking (or truly has no section)
            # If it has no section_id, but we want to process it, it will fall into "Uncategorized"
            # The current logic: if section_id is None, it passes the filter.
            # If an article with no section_id should still be mapped to a category, this needs more complex handling.
            # However, Zendesk articles are typically expected to have a section_id.
            articles_data_filtered.append(art)

        all_articles = articles_data_filtered
        print(f'Fetched {len(raw_articles_data)} articles, keeping {len(all_articles)} after filtering.')

    except requests.exceptions.HTTPError as e:
        print(f'Failed to retrieve articles: {e}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching articles: {e}')
        return

    print(f'Processing {len(all_articles)} articles...')
    for article in all_articles:
        if article.get('body') is None:
            print(f'Article ID {article["id"]} has no body, skipping.')
            continue

        article_id_val = article['id']
        article_title_val = article['title']
        safe_article_title = sanitize_name(article_title_val)
        article_url_val = article.get('html_url', 'URL_Not_Available')
        label_names = article.get('label_names', [])
        created_at_val = article.get('created_at', '')
        updated_at_val = article.get('updated_at', '')

        section_id = article.get('section_id')
        category_name_val = 'Uncategorized'
        section_name_val = 'Unsectioned'  # Default if no section or section not in map

        if section_id and section_id in section_map:
            section_info = section_map[section_id]
            section_name_val = section_info['name']
            category_id = section_info.get('category_id')
            if category_id and category_id in category_map:
                category_name_val = category_map[category_id]
            # If category_id is not in category_map, category_name_val remains 'Uncategorized'
            # This can happen if a section somehow has a category_id that was not fetched/kept
        elif section_id:  # Section ID exists but not in our kept map (should have been filtered already)
            print(
                f'Warning: Article ID {article_id_val} references section ID {section_id} '
                "which was not processed. Placing in 'Uncategorized/Unsectioned'."
            )

        display_path_segment: str
        if args.no_section:
            article_folder_path = os.path.join(base_run_path, category_name_val)
            display_path_segment = category_name_val
        else:
            article_folder_path = os.path.join(base_run_path, category_name_val, section_name_val)
            display_path_segment = f'{category_name_val}/{section_name_val}'

        if not os.path.exists(article_folder_path):
            os.makedirs(article_folder_path)

        html_body = article['body']
        try:
            md_body = markdownify.markdownify(html_body, heading_style='ATX') if html_body else ''
        except Exception as e:  # noqa: BLE001
            print(f"Error converting article ID {article_id_val} ('{article_title_val}') to Markdown: {e}")
            md_body = 'Error during Markdown conversion.'

        frontmatter = '---\n'
        frontmatter += f'title: "{article_title_val.replace('"', '\\"')}"\n'
        frontmatter += f'article_id: {article_id_val}\n'
        frontmatter += f'source_url: "{article_url_val}"\n'
        frontmatter += f'category: "{category_name_val}"\n'
        frontmatter += f'section: "{section_name_val}"\n'
        if label_names:
            frontmatter += 'tags:\n'
            for tag in label_names:
                frontmatter += f'  - "{tag.replace('"', '\\"')}"\n'
        else:
            frontmatter += 'tags: []\n'
        if created_at_val:
            frontmatter += f'created_at: "{created_at_val}"\n'
        if updated_at_val:
            frontmatter += f'updated_at: "{updated_at_val}"\n'
        frontmatter += '---\n\n'

        md_content = frontmatter
        md_content += f'# {article_title_val}\n\n'  # Add H1 title from article title
        md_content += f'{md_body}\n'

        base_filename = f'{safe_article_title}.md'
        filename_to_save = base_filename
        counter = 1
        while os.path.exists(os.path.join(article_folder_path, filename_to_save)):
            name_part, extension_part = os.path.splitext(base_filename)
            filename_to_save = f'{name_part}_{counter}{extension_part}'
            counter += 1

        filepath = os.path.join(article_folder_path, filename_to_save)

        try:
            with open(filepath, mode='w', encoding='utf-8') as f:
                f.write(md_content)
            print(f'Copied: {display_path_segment}/{filename_to_save}')
            log.append(
                (
                    article_id_val,
                    category_name_val,
                    section_name_val,
                    filename_to_save,
                    article_title_val,
                    article_url_val,
                )
            )
        except Exception as e:  # noqa: BLE001
            print(f"Error writing file for article ID {article_id_val} ('{article_title_val}'): {e}")

    log_filepath = os.path.join(base_run_path, '_log.csv')
    try:
        with open(log_filepath, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(('Article ID', 'Category', 'Section', 'File', 'Title', 'Article URL'))
            writer.writerows(log)
        print(f'Log file created at {log_filepath}')
    except Exception as e:  # noqa: BLE001
        print(f'Error writing log file: {e}')


if __name__ == '__main__':
    main()
    print('Backup process finished.')
