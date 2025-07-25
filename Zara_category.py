import json
import pandas as pd
import re
import requests

def generate_product_link(seo_keyword, seo_id):
    """
    Generates a product link using the provided pattern:
    /cn/en/{keyword}-l{seo_id}.html
    Returns None if seo_keyword or seo_id is missing.
    """
    full_url = None
    if seo_keyword and seo_id:
        cleaned_keyword = re.sub(r'[^a-zA-Z0-9-]', '', seo_keyword).lower()
        url_path = f"/cn/en/{cleaned_keyword}-l{seo_id}.html"
        full_url = f"https://www.zara.cn{url_path}"
    return full_url

def extract_category_data(category, level=0, parent_path="", all_categories_data=None):
    """
    Recursively extracts category information and appends it to a list.
    """
    if all_categories_data is None:
        all_categories_data = []

    current_path = f"{parent_path} > {category['name']}" if parent_path else category['name']
    
    category_id = category.get('id')
    category_name = category.get('name', 'N/A')
    section_name = category.get('sectionName', 'N/A')
    
    seo_info = category.get('seo', {})
    seo_id = seo_info.get('seoCategoryId')
    seo_keyword = seo_info.get('keyword')
    
    product_link = generate_product_link(seo_keyword, seo_id)

    row_data = {
        'Category ID': category_id,
        'Category Name': category_name,
        'Full Path': current_path,
        'Section Name': section_name,
        'Level': level - 1,
        'Layout': category.get('layout', 'N/A'),
        'Content Type': category.get('contentType', 'N/A'),
        'Redirected': category.get('isRedirected', False),
        'Key': category.get('key', 'N/A'),
        'SEO ID': seo_id,
        'SEO Keyword': seo_keyword,
        'Hidden In Menu': seo_info.get('isHiddenInMenu', False),
        'Must Display Content': category.get('attributes', {}).get('mustDisplayContent', False),
        'Show Subcategories': category.get('attributes', {}).get('showSubcategories', False),
        'Product Link': product_link
    }
    all_categories_data.append(row_data)

    subcategories = category.get('subcategories', [])
    for subcat in subcategories:
        extract_category_data(subcat, level + 1, current_path, all_categories_data)
    
    return all_categories_data

url = "https://www.zara.cn/cn/en/categories?ajax=true"

# Add User-Agent header
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

try:
    response = requests.get(url, headers=headers) # headers added to the request
    response.raise_for_status()
    data = response.json()
except requests.exceptions.RequestException as e:
    print(f"Error while fetching data from URL: {e}")
    exit()
except json.JSONDecodeError:
    print(f"Data fetched from URL is not in JSON format. Please check the URL: {url}")
    exit()

categories_data_list = []
main_categories = data.get('categories', [])
if main_categories:
    for main_category in main_categories:
        extract_category_data(main_category, level=0, parent_path="", all_categories_data=categories_data_list)
else:
    print("No category information found in the fetched data.")
    exit()

df = pd.DataFrame(categories_data_list)

filtered_df = df[
    (df['Section Name'] == 'WOMAN') & 
    (df['Level'] == 1) & 
    (df['Layout'] == 'products-category-view') &
    (df['Category Name'] != 'VIEW ALL') 
]

output_csv_file = 'Zara_category.csv'
filtered_df.to_csv(output_csv_file, index=False, encoding='utf-8-sig') 

print(f"Filtered data successfully exported to '{output_csv_file}'.")
print(f"Total {len(filtered_df)} category information exported.")
