"""Utility to fetch Zendesk Help Center structure and save it as a JSON file for reference."""

import argparse
import datetime  # Ensure datetime is imported
import json
import os

import dotenv
import requests

# It's good practice to load dotenv here if this module might be run directly
# or if its functions are called in a context where .env hasn't been loaded yet.
# However, if the package entry points always load it, this might be redundant.
# For safety and direct script execution, keeping it is fine.
dotenv.load_dotenv()

ZENDESK_API_TOKEN = os.getenv('ZENDESK_TOKEN')
ZENDESK_USER_EMAIL = os.getenv('ZENDESK_USER')
ZENDESK_DOMAIN = os.getenv('ZENDESK_DOMAIN')
ZENDESK_SUBDOMAIN = f'https://{ZENDESK_DOMAIN}'
DEFAULT_LANGUAGE = 'en-us'


# Helper function (Consider moving to a shared utils.py if used by main.py too)
def fetch_all_zendesk_data_util(endpoint: str, credentials: tuple, item_type: str) -> list:
    """Fetch all paginated data from a Zendesk endpoint."""
    results = []
    current_endpoint = endpoint
    print(f'Fetching all {item_type} from {endpoint}...')
    while current_endpoint:
        try:
            response = requests.get(current_endpoint, auth=credentials, timeout=30)
            if response.status_code == 404:
                print(f'Warning: Endpoint {current_endpoint} for {item_type} not found (404). Skipping.')
                break
            response.raise_for_status()
            data = response.json()

            data_key = None
            # Prioritize direct keys based on item_type
            if item_type == 'articles' and 'articles' in data:
                data_key = 'articles'
            elif item_type == 'sections' and 'sections' in data:
                data_key = 'sections'
            elif item_type == 'categories' and 'categories' in data:
                data_key = 'categories'
            # Fallback for generic keys or if the main key is the item_type itself
            elif item_type in data and isinstance(data[item_type], list):
                data_key = item_type
            elif f'{item_type}s' in data and isinstance(data[f'{item_type}s'], list):
                data_key = f'{item_type}s'  # e.g. category -> categories
            elif 'results' in data and isinstance(data['results'], list):
                data_key = 'results'

            if data_key and data_key in data:
                results.extend(data[data_key])
            else:
                print(
                    f'Warning: No standard data key ({item_type} or common alternatives) found in response '
                    f'from {current_endpoint}. Data keys: {list(data.keys())}'
                )

            current_endpoint = data.get('next_page')
        except requests.exceptions.RequestException as e:
            print(f'Error fetching {item_type} from {current_endpoint}: {e}')
            break
        except json.JSONDecodeError as e:
            print(f'Error decoding JSON for {item_type} from {current_endpoint}: {e}')
            break
    print(f'Finished fetching {item_type}. Total items: {len(results)}')
    return results


def generate_info_file(output_file: str, language: str) -> None:
    """Fetch the Zendesk structure and save it to a JSON file."""
    if not all([ZENDESK_USER_EMAIL, ZENDESK_API_TOKEN, ZENDESK_DOMAIN]):
        print('Error: Zendesk credentials or domain not found in environment variables.')
        print('Please ensure ZENDESK_TOKEN, ZENDESK_USER, and ZENDESK_DOMAIN are set.')
        return

    credentials = (f'{ZENDESK_USER_EMAIL}/token', ZENDESK_API_TOKEN)
    lang_lower = language.lower()

    print(f'\n--- Generating Zendesk structure for language: {language} ---')

    categories_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{lang_lower}/categories.json'
    categories = fetch_all_zendesk_data_util(categories_endpoint, credentials, 'categories')

    sections_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{lang_lower}/sections.json'
    sections = fetch_all_zendesk_data_util(sections_endpoint, credentials, 'sections')

    articles_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{lang_lower}/articles.json?per_page=100'
    articles_raw = fetch_all_zendesk_data_util(articles_endpoint, credentials, 'articles')

    articles_by_section_id = {}
    unmapped_articles_info = []
    all_fetched_section_ids = {sec['id'] for sec in sections}

    for article in articles_raw:
        article_info = {
            'id': article['id'],
            'title': article.get('title', 'No Title'),
            'html_url': article.get('html_url', 'No URL'),
        }
        section_id = article.get('section_id')

        if section_id and section_id in all_fetched_section_ids:
            articles_by_section_id.setdefault(section_id, []).append(article_info)
        else:
            unmapped_articles_info.append({**article_info, 'section_id_referenced': section_id})

    output_structure = {
        'language': language,
        'generation_date': datetime.datetime.now(tz=datetime.UTC).isoformat(),  # Use timezone.utc
        'categories': [],
        'articles_not_in_listed_sections': unmapped_articles_info,
    }

    for cat_data in categories:
        category_entry = {
            'id': cat_data['id'],
            'name': cat_data.get('name', 'Unnamed Category'),  # Zendesk uses 'name' for categories
            'html_url': cat_data.get('html_url', 'No URL'),
            'sections': [],
        }
        for sec_data in sections:
            if sec_data.get('category_id') == cat_data['id']:
                section_entry = {
                    'id': sec_data['id'],
                    'name': sec_data.get('name', 'Unnamed Section'),  # Zendesk uses 'name' for sections
                    'html_url': sec_data.get('html_url', 'No URL'),
                    'articles': articles_by_section_id.get(sec_data['id'], []),
                }
                category_entry['sections'].append(section_entry)
        output_structure['categories'].append(category_entry)

    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_structure, f, indent=2, ensure_ascii=False)
        print(f'\nSuccessfully generated Zendesk structure at: {output_file}')
    except OSError as e:
        print(f"Error writing structure file '{output_file}': {e}")
    except Exception as e:  # noqa: BLE001
        print(f'An unexpected error occurred while writing the structure file: {e}')


# NEW: Define a main function for the command-line interface
def main_cli() -> None:
    """Command-line interface entry point for generating the structure file."""
    parser = argparse.ArgumentParser(
        description='Generate a JSON file with Zendesk Help Center structure (categories, sections, articles).'
    )
    parser.add_argument(
        '--output',
        default='zendesk_structure.json',
        help='Filename for the output JSON structure. (default: zendesk_structure.json)',
    )
    parser.add_argument(
        '--lang',
        default=DEFAULT_LANGUAGE,
        help=f'Language code for the Help Center content (e.g., en-us, es, fr). (default: {DEFAULT_LANGUAGE})',
    )
    args = parser.parse_args()

    # The dotenv.load_dotenv() at the top of the file should have already run.
    # Now, check if the constants were successfully loaded.
    if not all([ZENDESK_USER_EMAIL, ZENDESK_API_TOKEN, ZENDESK_DOMAIN, ZENDESK_SUBDOMAIN]):
        print(
            'Error: Crucial Zendesk credentials or domain (ZENDESK_TOKEN, ZENDESK_USER, ZENDESK_DOMAIN) '
            'are missing from your environment or .env file.'
        )
        return 1  # Indicate an error exit status

    generate_info_file(output_file=args.output, language=args.lang)
    return 0  # Indicate success


if __name__ == '__main__':
    # This allows running "python md4help_center/info_generator.py" directly
    exit_status = main_cli()
    exit(exit_status)  # Propagate the exit status
