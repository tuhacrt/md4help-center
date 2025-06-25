"""script to fetch and backup Zendesk Help Center articles and categories as Markdown files."""

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
    # Allow letters, numbers, spaces, hyphens, and underscores. Replace others with an underscore.
    safe_name = name.strip()

    # Collapse multiple spaces into a single space
    safe_name = re.sub(r' +', ' ', safe_name)
    # Collapse multiple underscores into a single underscore
    safe_name = re.sub(r'_+', '_', safe_name)
    # Replace " into ', for dify compatibility
    safe_name = safe_name.replace('"', "'")

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
    parser.add_argument(
        '--ignore-file',
        type=str,
        default=None,
        help='Path to a JSON file specifying category_ids, section_ids, or article_ids to ignore.',
    )
    args = parser.parse_args()

    ignore_config = {'ignore_category_ids': set(), 'ignore_section_ids': set(), 'ignore_article_ids': set()}
    if args.ignore_file:
        try:
            with open(args.ignore_file, encoding='utf-8') as f:
                loaded_ignores = json5.load(f)
                raw_cat_ignores = loaded_ignores.get('category', [])
                raw_sec_ignores = loaded_ignores.get('section', [])
                raw_art_ignores = loaded_ignores.get('article', [])

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
        except (json5.JSONDecodeError, ValueError) as e:
            print(f"Warning: Error decoding ignore file '{args.ignore_file}'. Error: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"Warning: Could not load or parse ignore file '{args.ignore_file}': {e}.")

    date_today = datetime.datetime.now(tz=datetime.UTC).date()
    base_run_path = os.path.join(BACKUP_FOLDER, str(date_today), LANGUAGE)
    if not os.path.exists(base_run_path):
        os.makedirs(base_run_path)

    log = []
    credentials = (f'{ZENDESK_USER_EMAIL}/token', ZENDESK_API_TOKEN)
    if not all([ZENDESK_USER_EMAIL, ZENDESK_API_TOKEN, ZENDESK_DOMAIN]):
        print('Error: Zendesk credentials not found. Please set ZENDESK_TOKEN, ZENDESK_USER, and ZENDESK_DOMAIN.')
        return

    # --- Fetch, Filter, and Backup Categories ---
    print('Fetching categories...')
    category_map = {}
    try:
        categories_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/categories.json'
        raw_categories_data = fetch_all_zendesk_data(categories_endpoint, credentials)

        categories_data_filtered = [
            cat for cat in raw_categories_data if cat['id'] not in ignore_config['ignore_category_ids']
        ]

        # Process filtered categories: create pages and build the map for later use
        for cat in categories_data_filtered:
            sanitized_name = sanitize_name(cat['name'])
            # Store details in the map for articles/sections to use
            category_map[cat['id']] = {
                'name': sanitized_name,
                'original_name': cat['name'],
            }

        kept_category_ids = set(category_map.keys())
        print(f'Fetched {len(raw_categories_data)} categories, keeping and backing up {len(category_map)}.')
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching categories: {e}')
        return

    # --- Fetch and Filter Sections ---
    print('Fetching sections...')
    section_map = {}
    try:
        sections_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/sections.json'
        raw_sections_data = fetch_all_zendesk_data(sections_endpoint, credentials)

        sections_data_filtered = [
            sec
            for sec in raw_sections_data
            if sec['id'] not in ignore_config['ignore_section_ids'] and sec.get('category_id') in kept_category_ids
        ]

        section_map = {
            sec['id']: {'name': sanitize_name(sec['name']), 'category_id': sec['category_id']}
            for sec in sections_data_filtered
        }
        kept_section_ids = set(section_map.keys())
        print(f'Fetched {len(raw_sections_data)} sections, keeping {len(section_map)} after filtering.')
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching sections: {e}')
        return

    # --- Fetch and Filter Articles ---
    print('Fetching articles...')
    all_articles = []
    try:
        articles_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/articles.json'
        raw_articles_data = fetch_all_zendesk_data(articles_endpoint, credentials)

        all_articles = [
            art
            for art in raw_articles_data
            if art['id'] not in ignore_config['ignore_article_ids'] and art.get('section_id') in kept_section_ids
        ]
        print(f'Fetched {len(raw_articles_data)} articles, keeping {len(all_articles)} after filtering.')
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
        section_name_val = 'Unsectioned'

        if section_id and section_id in section_map:
            section_info = section_map[section_id]
            section_name_val = section_info['name']
            category_id = section_info.get('category_id')
            if category_id and category_id in category_map:
                # MODIFIED: Get correct name from category_map object
                category_name_val = category_map[category_id]['name']

        if args.no_section:
            article_folder_path = os.path.join(base_run_path, category_name_val)
            display_path_segment = category_name_val
        else:
            article_folder_path = os.path.join(base_run_path, category_name_val, section_name_val)
            display_path_segment = f'{category_name_val}/{section_name_val}'

        os.makedirs(article_folder_path, exist_ok=True)

        html_body = article['body']
        md_body = markdownify.markdownify(html_body, heading_style='ATX') if html_body else ''

        frontmatter = '---\n'
        frontmatter += f'title: "{article_title_val.replace('"', '"')}"\n'
        frontmatter += f'article_id: {article_id_val}\n'
        frontmatter += f'source_url: "{article_url_val}"\n'
        frontmatter += f'category: "{category_map.get(category_id, {}).get("original_name", "Uncategorized")}"\n'
        frontmatter += f'section: "{section_name_val}"\n'
        frontmatter += f'tags: {label_names if label_names else "[]"}\n'
        frontmatter += f'created_at: "{created_at_val}"\n'
        frontmatter += f'updated_at: "{updated_at_val}"\n'
        frontmatter += '---\n\n'

        md_content = frontmatter + f'# {article_title_val}\n\n' + f'{md_body}\n'

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
            print(f'Copied article: {display_path_segment}/{filename_to_save}')
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
