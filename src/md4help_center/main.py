"""script to fetch and backup Zendesk Help Center articles as Markdown files."""

import argparse
import csv
import datetime
import os
import re

import dotenv
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
        response = requests.get(current_endpoint, auth=credentials)
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
    return results


def main() -> None:
    """Fetch and backup Zendesk Help Center articles."""
    # --- CLI Argument Parsing ---
    parser = argparse.ArgumentParser(description='Fetch and backup Zendesk Help Center articles as Markdown files.')
    parser.add_argument(
        '--no-section',
        action='store_true',
        help='Place articles directly under category folders, without section subfolders.',
    )
    args = parser.parse_args()
    # --- End CLI Argument Parsing ---

    date_today = datetime.datetime.now(tz=datetime.UTC).date()
    base_run_path = os.path.join(BACKUP_FOLDER, str(date_today), LANGUAGE)
    if not os.path.exists(base_run_path):
        os.makedirs(base_run_path)

    log = []
    credentials = (f'{ZENDESK_USER_EMAIL}/token', ZENDESK_API_TOKEN)

    print('Fetching categories...')
    try:
        categories_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/categories.json'
        categories_data = fetch_all_zendesk_data(categories_endpoint, credentials)
        category_map = {cat['id']: sanitize_name(cat['name']) for cat in categories_data}
        print(f'Found {len(category_map)} categories.')
    except requests.exceptions.HTTPError as e:
        print(f'Failed to retrieve categories: {e}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching categories: {e}')
        return

    print('Fetching sections...')
    try:
        sections_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/sections.json'
        sections_data = fetch_all_zendesk_data(sections_endpoint, credentials)
        section_map = {
            sec['id']: {'name': sanitize_name(sec['name']), 'category_id': sec['category_id']} for sec in sections_data
        }
        print(f'Found {len(section_map)} sections.')
    except requests.exceptions.HTTPError as e:
        print(f'Failed to retrieve sections: {e}')
        return
    except Exception as e:  # noqa: BLE001
        print(f'An error occurred fetching sections: {e}')
        return

    print('Fetching articles...')
    try:
        articles_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/articles.json'
        all_articles = fetch_all_zendesk_data(articles_endpoint, credentials)
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
        section_name_val = 'Uncategorized'  # Still fetch section name for metadata

        if section_id and section_id in section_map:
            section_info = section_map[section_id]
            section_name_val = section_info['name']
            category_id = section_info.get('category_id')
            if category_id and category_id in category_map:
                category_name_val = category_map[category_id]

        # --- Adjust article_folder_path based on --no-section flag ---
        display_path_segment: str
        if args.no_section:
            article_folder_path = os.path.join(base_run_path, category_name_val)
            display_path_segment = category_name_val
        else:
            article_folder_path = os.path.join(base_run_path, category_name_val, section_name_val)
            display_path_segment = f'{category_name_val}/{section_name_val}'
        # --- End path adjustment ---

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
        frontmatter += f'section: "{section_name_val}"\n'  # Section name still in frontmatter
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
        md_content += f'# {article_title_val}\n\n'
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
            # Use display_path_segment for clearer print output
            print(f'Copied: {display_path_segment}/{filename_to_save}')
            log.append(
                (
                    article_id_val,
                    category_name_val,
                    section_name_val,  # Section name is still logged
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
