import os
import datetime
import csv
import dotenv
import requests
import re
import markdownify

dotenv.load_dotenv()

ZENDESK_API_TOKEN = os.getenv('ZENDESK_TOKEN')
ZENDESK_USER_EMAIL = os.getenv('ZENDESK_USER')
ZENDESK_DOMAIN = os.getenv('ZENDESK_DOMAIN')
ZENDESK_SUBDOMAIN = f'https://{ZENDESK_DOMAIN}'
BACKUP_FOLDER = 'backups_md'
LANGUAGE = 'en-us'

# --- Helper function to sanitize names for paths/filenames ---
def sanitize_name(name):
    if not name:
        return "Unnamed"
    name = name.replace('/', '_').replace('\\', '_')
    safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in name).strip()
    safe_name = re.sub(r'[_ ]+', '_', safe_name)
    if not safe_name or safe_name == '_' or all(c == '_' for c in safe_name):
        return "Sanitized_Content"
    return safe_name

def fetch_all_zendesk_data(endpoint, credentials):
    """Helper to fetch all paginated data from a Zendesk endpoint."""
    results = []
    current_endpoint = endpoint
    while current_endpoint:
        response = requests.get(current_endpoint, auth=credentials)
        if response.status_code == 404:
            print(f"Warning: Endpoint {current_endpoint} not found (404). Skipping.")
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
            print(f"Warning: No standard data key found in response from {current_endpoint}. Data: {data}")

        current_endpoint = data.get('next_page')
    return results

def main():
    date_today = datetime.date.today()
    base_run_path = os.path.join(BACKUP_FOLDER, str(date_today), LANGUAGE)
    if not os.path.exists(base_run_path):
        os.makedirs(base_run_path)

    log = []
    credentials = (f'{ZENDESK_USER_EMAIL}/token', ZENDESK_API_TOKEN)

    print("Fetching categories...")
    try:
        categories_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/categories.json'
        categories_data = fetch_all_zendesk_data(categories_endpoint, credentials)
        category_map = {cat['id']: sanitize_name(cat['name']) for cat in categories_data}
        print(f"Found {len(category_map)} categories.")
    except requests.exceptions.HTTPError as e:
        print(f"Failed to retrieve categories: {e}")
        return
    except Exception as e:
        print(f"An error occurred fetching categories: {e}")
        return

    print("Fetching sections...")
    try:
        sections_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/sections.json'
        sections_data = fetch_all_zendesk_data(sections_endpoint, credentials)
        section_map = {
            sec['id']: {
                'name': sanitize_name(sec['name']),
                'category_id': sec['category_id']
            } for sec in sections_data
        }
        print(f"Found {len(section_map)} sections.")
    except requests.exceptions.HTTPError as e:
        print(f"Failed to retrieve sections: {e}")
        return
    except Exception as e:
        print(f"An error occurred fetching sections: {e}")
        return

    print("Fetching articles...")
    try:
        articles_endpoint = f'{ZENDESK_SUBDOMAIN}/api/v2/help_center/{LANGUAGE.lower()}/articles.json'
        all_articles = fetch_all_zendesk_data(articles_endpoint, credentials)
    except requests.exceptions.HTTPError as e:
        print(f"Failed to retrieve articles: {e}")
        return
    except Exception as e:
        print(f"An error occurred fetching articles: {e}")
        return

    print(f"Processing {len(all_articles)} articles...")
    for article in all_articles:
        if article.get('body') is None:
            print(f"Article ID {article['id']} has no body, skipping.")
            continue

        article_id = article['id'] # Used in log
        article_title = article['title']
        safe_article_title = sanitize_name(article_title)
        article_url = article.get('html_url', 'URL_Not_Available') # Used in log and MD

        # Fetching labels/tags for the article from 'label_names'
        label_names = article.get('label_names', [])
        tags_line = ""
        if label_names:
            tags_line = "Tags: " + ", ".join(label_names)

        section_id = article.get('section_id')
        category_name = "Uncategorized"
        section_name = "Uncategorized"

        if section_id and section_id in section_map:
            section_info = section_map[section_id]
            section_name = section_info['name']
            category_id = section_info.get('category_id')
            if category_id and category_id in category_map:
                category_name = category_map[category_id]

        article_folder_path = os.path.join(base_run_path, category_name, section_name)
        if not os.path.exists(article_folder_path):
            os.makedirs(article_folder_path)

        html_body = article['body']
        try:
            md_body = markdownify.markdownify(html_body, heading_style='ATX') if html_body else ''
        except Exception as e:
            print(f"Error converting article ID {article_id} ('{article_title}') to Markdown: {e}")
            md_body = "Error during Markdown conversion."

        # Prepare Markdown content: Title, then Tags (if any), then body, then Source URL
        md_content = f"# {article_title}\n\n"
        if tags_line: # Only add the tags line if there are any tags
            md_content += f"{tags_line}\n\n" # Add two newlines for separation before body
        md_content += f"{md_body}\n\n---\nSource URL: {article_url}"

        base_filename = f"{safe_article_title}.md"
        filename_to_save = base_filename
        counter = 1
        while os.path.exists(os.path.join(article_folder_path, filename_to_save)):
            name_part, extension_part = os.path.splitext(base_filename)
            filename_to_save = f"{name_part}_{counter}{extension_part}"
            counter += 1

        filepath = os.path.join(article_folder_path, filename_to_save)

        try:
            with open(filepath, mode='w', encoding='utf-8') as f:
                f.write(md_content)
            print(f"Copied: {category_name}/{section_name}/{filename_to_save}")
            # Update log entry with article_id and article_url, remove author_id
            log.append((article_id, category_name, section_name, filename_to_save, article_title, article_url))
        except Exception as e:
            print(f"Error writing file for article ID {article_id} ('{article_title}'): {e}")

    log_filepath = os.path.join(base_run_path, '_log.csv')
    try:
        with open(log_filepath, mode='w', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            # Update log header
            writer.writerow(('Article ID', 'Category', 'Section', 'File', 'Title', 'Article URL'))
            writer.writerows(log)
        print(f"Log file created at {log_filepath}")
    except Exception as e:
        print(f"Error writing log file: {e}")

if __name__ == '__main__':
    main()
    print("Backup process finished.")
