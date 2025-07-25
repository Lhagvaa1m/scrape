import pandas as pd
import requests
import json
import re
import csv
import time
import random
import os

# 1. User-Agent-уудын жагсаалт
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0.3 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 10; SM-G973F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Mobile Safari/537.36"
]

# 2. Proxy-уудын жагсаалт (Жишээ нь, таны proxy provider-аас авсан жагсаалт)
PROXIES = [
    # "http://your_proxy_ip_1:port_1",
    # "http://your_proxy_ip_2:port_2",
    # "http://user:pass@your_authenticated_proxy:port",
]

def get_random_user_agent():
    return random.choice(USER_AGENTS)

def get_random_proxy():
    if PROXIES:
        return {"http": random.choice(PROXIES), "https": random.choice(PROXIES)}
    return None

def create_product_slug(product_name):
    """
    Бүтээгдэхүүний нэрнээс URL-д тохиромжтой slug үүсгэх.
    Жишээ нь: "VOLUMINOUS TEXTURED DRESS" -> "voluminous-textured-dress"
    """
    slug = product_name.lower()
    slug = re.sub(r'\s+', '-', slug)  # Хоосон зайг зураасаар солих
    slug = re.sub(r'[^a-z0-9-]', '', slug) # Зөвхөн үсэг, тоо, зураасыг үлдээх
    slug = slug.strip('-') # Эхлэл төгсгөлийн зураасыг арилгах
    return slug

def fetch_products_for_category(category_id, retries=5, delay_between_retries=10):
    """
    Given a category ID, fetches product data for that category with retries and proxy rotation.
    """
    category_product_url = f"https://www.zara.cn/cn/en/category/{category_id}/products?ajax=true"
    
    for attempt in range(retries):
        user_agent = get_random_user_agent()
        proxy = get_random_proxy()
        is_429_error = False # Reset flag for each attempt
        
        headers = {'User-Agent': user_agent}
        
        print(f"Fetching products for category {category_id} (Attempt {attempt + 1}/{retries})")
        print(f"  URL: {category_product_url}")
        print(f"  User-Agent: {user_agent}")
        if proxy:
            print(f"  Proxy: {proxy['http']}")
        else:
            print("  No proxy used.")

        try:
            response = requests.get(category_product_url, headers=headers, proxies=proxy, timeout=15)
            response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
            data = response.json()
            return data
        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error {e.response.status_code} for category {category_id}: {e}")
            if e.response.status_code == 429: # Too Many Requests
                is_429_error = True
                print(f"  Rate limit hit. Waiting for {delay_between_retries * (attempt + 1)} seconds before retrying...")
                time.sleep(delay_between_retries * (attempt + 1)) # Exponential backoff
            elif 400 <= e.response.status_code < 500:
                print(f"  Client error, likely permanent. Skipping category for this attempt.")
                break # Don't retry client errors unless specifically handled
            else: # Server errors, might be temporary
                print(f"  Server error, retrying...")
                time.sleep(random.uniform(5, 10)) # Random delay for server errors
        except requests.exceptions.ConnectionError as e:
            print(f"Connection Error for category {category_id}: {e}")
            print(f"  Retrying in {random.uniform(5, 10):.2f} seconds...")
            time.sleep(random.uniform(5, 10))
        except requests.exceptions.Timeout:
            print(f"Timeout Error for category {category_id}.")
            print(f"  Retrying in {random.uniform(5, 10):.2f} seconds...")
            time.sleep(random.uniform(5, 10))
        except json.JSONDecodeError as e: # Bind exception to 'e'
            print(f"Failed to decode JSON for category {category_id}. Response was: {response.text[:200]}...")
            print(f"  Error details: {e}")
            print(f"  Retrying with a new proxy/user-agent...")
            time.sleep(random.uniform(5, 10)) # Wait before trying again with different params
        except Exception as e:
            print(f"An unexpected error occurred for category {category_id}: {e}")
            print(f"  Retrying in {random.uniform(5, 10):.2f} seconds...")
            time.sleep(random.uniform(5, 10))
        
        # Add a delay before the next retry attempt if not explicitly delayed and not a 429
        if attempt < retries - 1 and not is_429_error:
            time.sleep(random.uniform(1, 5)) # Shorter random delay for general retries

    print(f"Failed to fetch data for category {category_id} after {retries} attempts.")
    return None

# process_and_save_products функцийн тодорхойлолтыг Category ID болон Category Name-ийг хүлээн авах болгож өөрчлөх
def process_and_save_products(json_data, csv_writer, current_products_count, source_category_id, source_category_name):
    """
    Processes the JSON product data and writes it to a CSV writer,
    including the source category information.
    """
    BASE_URL = "https://www.zara.cn/cn/en/"
    products_added_in_current_batch = 0

    if 'productGroups' in json_data:
        for group in json_data['productGroups']:
            if 'elements' in group:
                for element in group['elements']:
                    if 'commercialComponents' in element:
                        for product in element['commercialComponents']:
                            # Extracting product information
                            product_id = product.get('id', '')
                            reference = product.get('reference', '')
                            name = product.get('name', '')
                            description = product.get('description', '')
                            brand_code = product.get('brand', {}).get('brandGroupCode', '')
                            product_type = product.get('type', '')
                            kind = product.get('kind', '')
                            availability = product.get('availability', '')

                            current_price_raw = product.get('price')
                            old_price_raw = product.get('oldPrice')
                            current_price = f"{current_price_raw / 100:.2f}" if isinstance(current_price_raw, (int, float)) else ''
                            old_price = f"{old_price_raw / 100:.2f}" if isinstance(old_price_raw, (int, float)) else ''

                            discount_percentage = product.get('discountPercentage', '')
                            discount_label = product.get('discountLabel', '')
                            is_on_sale = "true" if product.get('displayDiscountPercentage', 0) > 0 else "false"

                            section_name = product.get('sectionName', '')
                            family_name = product.get('familyName', '')
                            subfamily_name = product.get('subfamilyName', '')
                            seo_keyword = product.get('seo', {}).get('keyword', '')
                            seo_product_id = product.get('seo', {}).get('seoProductId', '')
                            
                            # **Зургийн мэдээлэл нэмэх хэсэг:**
                            xmedia_info = product.get('xmedia', [])
                            image_url = ''
                            if xmedia_info:
                                # Эхний зураг (гол зураг байх магадлалтай)
                                first_image = xmedia_info[0]
                                if 'sources' in first_image:
                                    if first_image['sources']:
                                        image_url = first_image['sources'][0].get('url', '')

                            grid_position = product.get('gridPosition', '')
                            zoomed_grid_position = product.get('zoomedGridPosition', '')
                            show_extra_image_on_hover = product.get('showExtraImageOnHover', False)
                            has_xmedia_double = product.get('hasXmediaDouble', False)
                            price_unavailable = product.get('priceUnavailable', False)

                            display_reference = product.get('detail', {}).get('displayReference', '')

                            # Generating product URL
                            product_slug = create_product_slug(name)
                            product_url = f"{BASE_URL}{product_slug}-p{seo_product_id}.html?v1=N/A&v2=N/A"

                            detail_info = product.get('detail', {})
                            colors = detail_info.get('colors', [])

                            if not colors:
                                sku_code = display_reference if display_reference else ''
                                csv_writer.writerow({
                                    'Product ID': product_id,
                                    'Reference': reference,
                                    'Display Reference': display_reference,
                                    'Product Name': name,
                                    'Product URL': product_url,
                                    'Description': description,
                                    'Brand Code': brand_code,
                                    'Type': product_type,
                                    'Kind': kind,
                                    'Availability': availability,
                                    'Current Price (MNT)': current_price,
                                    'Old Price (MNT)': old_price,
                                    'Discount Percentage': discount_percentage,
                                    'Discount Label': discount_label,
                                    'Is On Sale': is_on_sale,
                                    'Section Name': section_name,
                                    'Family Name': family_name,
                                    'Subfamily Name': subfamily_name,
                                    'SEO Keyword': seo_keyword,
                                    'SEO Product ID': seo_product_id,
                                    'Color ID': '',
                                    'Color Name': '',
                                    'SKU Code': sku_code,
                                    'Size ID': '', 'Size Name': '', 'Outer Code': '', 'Material Composition': '',
                                    'Grid Position': grid_position,
                                    'Zoomed Grid Position': zoomed_grid_position,
                                    'Show Extra Image On Hover': show_extra_image_on_hover,
                                    'Has Xmedia Double': has_xmedia_double,
                                    'Price Unavailable': price_unavailable,
                                    'Image URL': image_url, # Зургийн URL нэмсэн
                                    'Source Category ID': source_category_id, # Source Category ID нэмсэн
                                    'Source Category Name': source_category_name # Source Category Name нэмсэн
                                })
                                products_added_in_current_batch += 1
                            else:
                                for color in colors:
                                    color_id_raw = color.get('id', '')
                                    color_name = color.get('name', '')

                                    sku_code = ""
                                    if display_reference:
                                        sku_code = display_reference
                                        if color_id_raw and isinstance(color_id_raw, int):
                                            last_three_digits_color_id = str(color_id_raw)[-3:]
                                            sku_code = f"{sku_code}/{last_three_digits_color_id}"
                                    else:
                                        if color_id_raw and isinstance(color_id_raw, int):
                                            sku_code = str(color_id_raw)

                                    sizes = color.get('sizes', [])

                                    if not sizes:
                                        csv_writer.writerow({
                                            'Product ID': product_id,
                                            'Reference': reference,
                                            'Display Reference': display_reference,
                                            'Product Name': name,
                                            'Product URL': product_url,
                                            'Description': description,
                                            'Brand Code': brand_code,
                                            'Type': product_type,
                                            'Kind': kind,
                                            'Availability': availability,
                                            'Current Price (MNT)': current_price,
                                            'Old Price (MNT)': old_price,
                                            'Discount Percentage': discount_percentage,
                                            'Discount Label': discount_label,
                                            'Is On Sale': is_on_sale,
                                            'Section Name': section_name,
                                            'Family Name': family_name,
                                            'Subfamily Name': subfamily_name,
                                            'SEO Keyword': seo_keyword,
                                            'SEO Product ID': seo_product_id,
                                            'Color ID': color_id_raw,
                                            'Color Name': color_name,
                                            'SKU Code': sku_code,
                                            'Size ID': '', 'Size Name': '', 'Outer Code': '', 'Material Composition': '',
                                            'Grid Position': grid_position,
                                            'Zoomed Grid Position': zoomed_grid_position,
                                            'Show Extra Image On Hover': show_extra_image_on_hover,
                                            'Has Xmedia Double': has_xmedia_double,
                                            'Price Unavailable': price_unavailable,
                                            'Image URL': image_url, # Зургийн URL нэмсэн
                                            'Source Category ID': source_category_id, # Source Category ID нэмсэн
                                            'Source Category Name': source_category_name # Source Category Name нэмсэн
                                        })
                                        products_added_in_current_batch += 1
                                    else:
                                        for size in sizes:
                                            size_id = size.get('sizeId', '')
                                            size_name = size.get('name', '')
                                            outer_code = size.get('outerCode', '')
                                            composition_data = size.get('composition', [])
                                            material_composition = '; '.join([
                                                f"{comp.get('name', '')}: {comp.get('composition', '')}"
                                                for comp in composition_data
                                            ])

                                            csv_writer.writerow({
                                                'Product ID': product_id,
                                                'Reference': reference,
                                                'Display Reference': display_reference,
                                                'Product Name': name,
                                                'Product URL': product_url,
                                                'Description': description,
                                                'Brand Code': brand_code,
                                                'Type': product_type,
                                                'Kind': kind,
                                                'Availability': availability,
                                                'Current Price (MNT)': current_price,
                                                'Old Price (MNT)': old_price,
                                                'Discount Percentage': discount_percentage,
                                                'Discount Label': discount_label,
                                                'Is On Sale': is_on_sale,
                                                'Section Name': section_name,
                                                'Family Name': family_name,
                                                'Subfamily Name': subfamily_name,
                                                'SEO Keyword': seo_keyword,
                                                'SEO Product ID': seo_product_id,
                                                'Color ID': color_id_raw,
                                                'Color Name': color_name,
                                                'SKU Code': sku_code,
                                                'Size ID': size_id,
                                                'Size Name': size_name,
                                                'Outer Code': outer_code,
                                                'Material Composition': material_composition,
                                                'Grid Position': grid_position,
                                                'Zoomed Grid Position': zoomed_grid_position,
                                                'Show Extra Image On Hover': show_extra_image_on_hover,
                                                'Has Xmedia Double': has_xmedia_double,
                                                'Price Unavailable': price_unavailable,
                                                'Image URL': image_url, # Зургийн URL нэмсэн
                                                'Source Category ID': source_category_id, # Source Category ID нэмсэн
                                                'Source Category Name': source_category_name # Source Category Name нэмсэн
                                            })
                                            products_added_in_current_batch += 1
    else:
        print("Warning: 'productGroups' key not found in the fetched JSON data.")
    return current_products_count + products_added_in_current_batch

def log_failed_category(category_id, category_name, error_message, log_file='failed_categories.txt'):
    """
    Амжилтгүй болсон категорийг txt файл руу бичих.
    """
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(f"Category ID: {category_id}, Category Name: {category_name}, Error: {error_message}\n")
    print(f"Logged failed category: {category_name} (ID: {category_id}) to {log_file}")

def main():
    """Fetch all products for categories listed in a CSV file."""
    category_csv_file = 'Zara_category.csv'
    output_products_csv_file = 'Zara_all_category_products.csv'
    failed_categories_log_file = 'failed_categories.txt'

    # Start fresh for failed categories log
    if os.path.exists(failed_categories_log_file):
        os.remove(failed_categories_log_file)

    try:
        categories_df = pd.read_csv(category_csv_file)
        print(f"Successfully loaded category data from '{category_csv_file}'.")
    except FileNotFoundError:
        print(f"Error: Category CSV file '{category_csv_file}' not found. Please ensure it's in the same directory.")
        return

    # Define CSV fieldnames (from your Zara_product.py)
    # Шинэ багануудыг нэмсэн: 'Image URL', 'Source Category ID', 'Source Category Name'
    fieldnames = [
        'Product ID', 'Reference', 'Display Reference', 'Product Name', 'Product URL',
        'Description', 'Brand Code', 'Type', 'Kind', 'Availability',
        'Current Price (MNT)', 'Old Price (MNT)', 'Discount Percentage', 'Discount Label',
        'Is On Sale',
        'Section Name', 'Family Name', 'Subfamily Name', 'SEO Keyword', 'SEO Product ID',
        'Color ID', 'Color Name', 'SKU Code',
        'Size ID', 'Size Name', 'Outer Code', 'Material Composition',
        'Grid Position', 'Zoomed Grid Position', 'Show Extra Image On Hover',
        'Has Xmedia Double', 'Price Unavailable',
        'Image URL', # Шинэ багана
        'Source Category ID', # Шинэ багана
        'Source Category Name' # Шинэ багана
    ]

    products_count = 0
    with open(output_products_csv_file, 'w', newline='', encoding='utf-8-sig') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=fieldnames)
        writer.writeheader()

        for index, row in categories_df.iterrows():
            category_id = row['Category ID']
            seo_keyword = row['SEO Keyword']
            category_name = row['Category Name']

            print(f"\nProcessing category: {category_name} (ID: {category_id})")

            product_json_data = fetch_products_for_category(category_id)
            if product_json_data:
                # process_and_save_products функцийг дуудахдаа категорийн мэдээллийг дамжуулах
                products_count = process_and_save_products(
                    product_json_data, writer, products_count, category_id, category_name
                )
                print(f"Total products processed so far: {products_count}")
            else:
                error_msg = f"Failed to fetch or process products for category ID: {category_id}"
                log_failed_category(category_id, category_name, error_msg, failed_categories_log_file)
                print(f"Skipping category {category_name} due to data fetching issues.")

            sleep_time = random.uniform(2, 7)
            print(f"Waiting for {sleep_time:.2f} seconds before next category...")
            time.sleep(sleep_time)

    print(f"\nAll product data from all categories saved to '{output_products_csv_file}'.")
    print(f"Total products processed: {products_count}")
    print(f"Check '{failed_categories_log_file}' for any categories that failed to process.")


if __name__ == '__main__':
    main()