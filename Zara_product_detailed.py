import json
import csv
import re

def clean_html(raw_html):
    """
    HTML тагуудыг текстээс арилгана.
    Removes HTML tags from a string.
    """
    if raw_html is None:
        return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return cleantext.strip()

def convert_zara_json_to_csv(json_file_path, csv_file_path):
    """
    Zara бүтээгдэхүүний дэлгэрэнгүй JSON өгөгдлийг CSV файл руу хөрвүүлнэ,
    өнгөний хувилбар бүрт нэг мөр үүсгэж, хэмжээний мэдээллийг нэг баганад нэгтгэж,
    шинэчлэгдсэн SKU форматтай болгоно.

    Converts Zara product detail JSON data into a CSV file,
    creating a row for each color variant and consolidating size info into one column,
    with an updated SKU format.

    Args:
        json_file_path (str): Оролтын JSON файлын зам.
        csv_file_path (str): Гаралтын CSV файлын зам.
    """
    full_file_content = ""
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            full_file_content = f.read()
    except FileNotFoundError:
        print(f"Алдаа: JSON файл олдсонгүй {json_file_path}")
        return

    # Бодит JSON объектын эхлэл ба төгсгөлийг олно.
    # Энэ нь JSON-ийн өмнө JSON бус контент (жишээ нь, URL) байгаа тохиолдлыг зохицуулна.
    json_start = full_file_content.find('{')
    json_end = full_file_content.rfind('}')

    if json_start == -1 or json_end == -1:
        print(f"Алдаа: {json_file_path} файлд бүрэн JSON объект ({{...}}) олдсонгүй")
        return

    # Зөвхөн JSON хэсгийг салгаж авна.
    json_content = full_file_content[json_start : json_end + 1]

    try:
        data = json.loads(json_content)
    except json.JSONDecodeError as e:
        print(f"Алдаа: {json_file_path} файлаас JSON задалж чадсангүй. Дэлгэрэнгүй: {e}")
        print(f"Асуудалтай контентын эхлэл (задлагдсан JSON-ийн эхний 500 тэмдэгт):\n{json_content[:500]}")
        return

    product = data.get('product', {})
    print("\n--- JSON задлах & Бүтээгдэхүүний өгөгдөл шалгах ---")
    print(f"Бүтээгдэхүүний объект байна: {'product' in data}")
    print(f"Бүтээгдэхүүний түлхүүрүүд: {list(product.keys()) if product else 'Бүтээгдэхүүний объект байхгүй'}")


    if not product:
        print("Алдаа: JSON өгөгдөл дотор 'product' түлхүүр олдсонгүй. Бүтээгдэхүүний дэлгэрэнгүй мэдээллийг татаж чадахгүй байна.")
        return

    # CSV-ийн талбарын нэрсийг тодорхойлно (толгой хэсэг) - Шинэчлэгдсэн: 'sku_base' нь 'sku' болсон
    fieldnames = [
        'category_id', 'category_name', 'section_name', 'product_name', 'product_id', 
        'old_price', 'price', 'discount_percentage', 'display_discount_percentage', 'discount_label',
        'sku', 'sizes_available_by_color', 'description', 'composition', 'is_on_sale', 
        'images_url', 'color', 'color_hex_code', 'product_url', 'related_products'
    ]

    all_product_rows = []

    # Нийтлэг бүтээгдэхүүний мэдээллийг нэг удаа татаж авна
    base_category_id = data.get('category', {}).get('id')
    base_category_name = data.get('category', {}).get('name')
    base_section_name = data.get('category', {}).get('sectionName')
    base_product_name = product.get('name')
    base_product_id = product.get('id')
    
    # --- ТАЙЛБАР АВАХ (ШИНЭЧЛЭГДСЭН ЛОГИК) ---
    print("\n--- Тайлбар авах (Шинэчлэгдсэн логик) ---")
    detail = product.get('detail', {})
    
    # Алхам 1: detail-д байгаа description, rawDescription-ийг оролдож авна
    desc_temp = detail.get("description") or detail.get("rawDescription")
    
    # Алхам 2: хэрвээ дээр хоёр хоосон бол seo хэсгээс авна
    if not desc_temp:
        desc_temp = data.get("seo", {}).get("description")
    
    # Алхам 3: хэрвээ seo-д ч байхгүй бол productMetaData массивийн эхний элементийн description-ийг авч үзнэ
    if not desc_temp and data.get("productMetaData") and isinstance(data["productMetaData"], list) and len(data["productMetaData"]) > 0:
        desc_temp = data["productMetaData"][0].get("description")
    
    # Алхам 4: авсан текст дотор HTML код байж болзошгүй тул clean_html() функцээр цэвэрлэнэ
    base_description = clean_html(desc_temp) or "N/A"
    
    # rawDescription-д бас fallback хийх: хэрвээ detail.rawDescription хоосон байвал description-ийг raw_desc-д авчихна
    raw_desc = detail.get("rawDescription") or base_description

    print(f"Татаж авсан base_description: '{base_description[:100]}...' (100 тэмдэгтээр таслагдсан)") 
    # --- ТАЙЛБАР АВАХ ТӨГСГӨЛ ---

    # URL үүсгэхэд зориулсан parentId-г авна (жишээ нь, v1 параметр)
    base_parent_id = data.get('parentId')
    if not base_parent_id and product.get('bundleProductParents') and isinstance(product['bundleProductParents'], list):
        if product['bundleProductParents']:
            base_parent_id = product['bundleProductParents'][0].get('id')

    # Бүтээгдэхүүний нэрнээс URL slug үүсгэнэ (жишээ нь, "STRUCTURED CORSET TOP" -> "structured-corset-top")
    product_slug = re.sub(r'[^a-z0-9]+', '-', base_product_name.lower()) if base_product_name else "product"
    product_slug = product_slug.strip('-')

    # --- НАЙРЛАГА АВАХ (ШИНЭЧЛЭГДСЭН ЛОГИК) ---
    print("\n--- Найрлага авах (Шинэчлэгдсэн логик) ---")
    comp_list = []
    # detailedComposition.parts массив дотор хэсэг бүр (parts) давталттай
    for part in detail.get("detailedComposition", {}).get("parts", []):
        part_name = part.get("description", "Unknown Part")  # жишээ нь "OUTER SHELL"

        # тухайн хэсгийн components массив доторх материал, хувь хэмжээг авч
        for comp in part.get("components", []):
            mat = comp.get("material",   "Unknown")  # материалын нэр (e.g. "polyester")
            pct = comp.get("percentage", "N/A")      # хувь хэмжээ (e.g. "61%")
            # "OUTER SHELL: polyester 61%" форматаар жагсаалтад нэмнэ
            comp_list.append(f"{part_name}: {mat} {pct}")
    
    # detailedComposition.exceptions массив доторх онцгой тохиолдлуудыг нэмнэ
    if 'exceptions' in detail.get("detailedComposition", {}) and isinstance(detail["detailedComposition"]['exceptions'], list):
        for exception in detail["detailedComposition"]['exceptions']:
            if exception:
                comp_list.append(f"Бусад: {exception}")

    # Хэрвээ материал байгаа бол хооронд нь “; ” тусгаарлан нэг мөр болгон нэгтгэнэ
    base_composition = "; ".join(comp_list) if comp_list else "N/A"
    print(f"Эцсийн base_composition: '{base_composition[:150]}...' (150 тэмдэгтээр таслагдсан)") 
    # --- НАЙРЛАГА АВАХ ТӨГСГӨЛ ---

    # Холбоотой бүтээгдэхүүнүүдийг татаж авна (энэ нь бүтээгдэхүүний түвшний, хувилбарын түвшний биш)
    base_related_products_info = []
    if 'bundleProducts' in product and isinstance(product['bundleProducts'], list):
        for rp in product['bundleProducts']:
            rp_id = rp.get('id')
            rp_name = rp.get('name')
            rp_url = f"https://www.zara.cn/cn/en/product-p{rp_id}.html" if rp_id else "N/A"
            base_related_products_info.append(f"ID: {rp_id}, Нэр: {rp_name}, URL: {rp_url}")

    if 'similarProducts' in product and isinstance(product['similarProducts'], list):
        for rp in product['similarProducts']:
            rp_id = rp.get('id')
            rp_name = rp.get('name')
            rp_url = f"https://www.zara.cn/cn/en/product-p{rp_id}.html" if rp_id else "N/A"
            base_related_products_info.append(f"ID: {rp_id}, Нэр: {rp_name}, URL: {rp_url}")

    # Өнгөний нэрсийг hex код болон зургийн URL-тай холбох зураглал үүсгэнэ
    color_details_map = {}
    if product.get('detail') and product['detail'].get('colors') and isinstance(product['detail']['colors'], list):
        for color_data in product['detail']['colors']:
            color_name = color_data.get('name')
            color_hex_code = color_data.get('hexCode')
            images_for_color = []
            if 'xmedia' in color_data and isinstance(color_data['xmedia'], list):
                for media_item in color_data['xmedia']:
                    if media_item.get('type') == 'image' and 'url' in media_item:
                        img_url = media_item['url'].split('&w=')[0] if '{width}' in media_item['url'] else media_item['url']
                        images_for_color.append(img_url)
            if color_name:
                color_details_map[color_name] = {
                    'hexCode': color_hex_code,
                    'images_url': ", ".join(images_for_color)
                }
    
    # Мөр нэмэгдсэн эсэхийг шалгах тэмдэглэгээ
    rows_added = False

    # SKU үүсгэхэд зориулсан displayReference-г авна
    base_display_reference = product.get('detail', {}).get('displayReference')

    # Өнгөний хувилбар бүрээр нэг мөр үүсгэхээр давтана
    if product.get('detail') and product['detail'].get('colors') and isinstance(product['detail']['colors'], list):
        for color_data in product['detail']['colors']:
            rows_added = True
            current_color = color_data.get('name')
            current_color_hex_code = color_data.get('hexCode')
            current_color_id = color_data.get('id')
            
            # SKU үүсгэнэ: displayReference/color_id (жишээ нь, 5063/347/737)
            current_sku = None
            if base_display_reference and current_color_id:
                current_sku = f"{base_display_reference}/{current_color_id}"
            elif color_data.get('reference'): # displayReference/color_id амжилтгүй бол өнгөний тусгай лавлагаа руу буцна
                current_sku = color_data['reference']
            elif product.get('reference'): # Цаашдын бүтээгдэхүүний түвшний лавлагаа руу буцна
                current_sku = product.get('reference')


            # Энэ өнгөний зургуудыг авна
            current_images_url = color_details_map.get(current_color, {}).get('images_url', '')

            # Энэ өнгөний хэмжээний мэдээллийг нэгтгэнэ
            sizes_info_for_color = []
            current_prices_list = [] # Хамгийн бага үнийг олохын тулд бүх хэмжээнээс үнийг хадгална
            current_old_prices_list = [] # Хамгийн их хуучин үнийг олохын тулд бүх хэмжээнээс хуучин үнийг хадгална
            current_is_on_sale_status = False # Энэ өнгөний хувилбарын хямдралын статусыг хянана

            if 'sizes' in color_data and isinstance(color_data['sizes'], list):
                for size_detail in color_data['sizes']:
                    size_name = size_detail.get('name')
                    availability = size_detail.get('availability')
                    if size_name and availability:
                        sizes_info_for_color.append(f"{size_name} ({availability})")
                    
                    # Энэ өнгөний ерөнхий үнэ/хямдралыг тодорхойлохын тулд хэмжээнээс үнийн мэдээллийг цуглуулна
                    if size_detail.get('price') is not None:
                        current_prices_list.append(size_detail['price'])
                    if size_detail.get('oldPrice') is not None:
                        current_old_prices_list.append(size_detail['oldPrice'])
                    
                    # Хэрэв ямар нэг хэмжээ тодорхой хямдралтай эсвэл хөнгөлөлттэй бол өнгийг хямдралтай гэж тэмдэглэнэ
                    if size_detail.get('price') is not None and size_detail.get('oldPrice') is not None:
                        if size_detail['oldPrice'] > size_detail['price']:
                            current_is_on_sale_status = True
            
            consolidated_sizes_str = "; ".join(sizes_info_for_color)

            # Өнгөний үндсэн үнэ/хуучин үнэ/хөнгөлөлтийг тодорхойлно
            # Хэрэв боломжтой бол size_details-аас үнийг эхэнд тавина, үгүй бол ерөнхий бүтээгдэхүүний үнийг ашиглана
            final_price = None
            final_old_price = None
            final_discount_percentage = None
            final_display_discount_percentage = None
            final_discount_label = None

            if current_prices_list:
                final_price = min(current_prices_list) 
            else:
                final_price = product.get('price', {}).get('currentRetail')

            if current_old_prices_list:
                final_old_price = max(current_old_prices_list) 
            else:
                final_old_price = product.get('price', {}).get('oldRetail')

            # Хэрэв хөнгөлөлт байгаа бол тооцоолно
            if final_price is not None and final_old_price is not None and final_old_price > final_price:
                calculated_discount = ((final_old_price - final_price) / final_old_price) * 100
                final_discount_percentage = round(calculated_discount, 2)
                final_display_discount_percentage = int(round(calculated_discount)) 
                final_discount_label = f"-{int(round(calculated_discount))}%"
                current_is_on_sale_status = True # Хөнгөлөлт тооцоологдсон бол үнэн гэж баталгаажуулна
            
            # product.price эсвэл бүтээгдэхүүнээс шууд 'isOnSale' талбарыг эхэнд тавина
            product_level_is_on_sale = product.get('price', {}).get('isOnSale')
            if product_level_is_on_sale is None:
                product_level_is_on_sale = product.get('isOnSale')
            
            if product_level_is_on_sale is not None:
                current_is_on_sale_status = product_level_is_on_sale # Тодорхой тэмдэглэгээ байгаа бол дарна


            # Бүтээгдэхүүний URL-г үүсгэнэ
            current_product_url = None
            if base_product_id and base_parent_id:
                current_product_url = (
                    f"https://www.zara.cn/cn/en/{product_slug}-p{base_product_id}.html"
                    f"?v1={base_parent_id}" # v1 нь parentId гэж үзнэ
                )
            elif base_product_id:
                current_product_url = f"https://www.zara.cn/cn/en/{product_slug}-p{base_product_id}.html"

            # Тодорхойлсон base_description-г ашиглана (энэ нь бүтээгдэхүүний түвшний тайлбар байна)
            current_description = base_description 

            row = {
                'category_id': base_category_id,
                'category_name': base_category_name,
                'section_name': base_section_name,
                'product_name': base_product_name,
                'product_id': base_product_id,
                'old_price': final_old_price,
                'price': final_price,
                'discount_percentage': final_discount_percentage,
                'display_discount_percentage': final_display_discount_percentage,
                'discount_label': final_discount_label,
                'sku': current_sku, # Шинэчлэгдсэн SKU формат
                'sizes_available_by_color': consolidated_sizes_str, 
                'description': current_description, # current_description (base_description-аас) ашиглана
                'composition': base_composition, # base_composition ашиглана
                'is_on_sale': current_is_on_sale_status,
                'images_url': current_images_url,
                'color': current_color,
                'color_hex_code': current_color_hex_code,
                'product_url': current_product_url,
                'related_products': "; ".join(base_related_products_info)
            }
            all_product_rows.append(row)
    
    # Өнгө эсвэл хэмжээ огт олдсонгүй бол буцна
    if not rows_added:
        print("Анхааруулга: Өнгө/размерийн хувилбар олдсонгүй. Нэг ерөнхий бүтээгдэхүүний мөр нэмж байна.")
        general_images = []
        if 'xmedia' in product and isinstance(product['xmedia'], list):
            for media_item in product['xmedia']:
                if media_item.get('mediaType') == 'PRODUCT_XMEDIA_IMAGE' and 'url' in media_item:
                    general_images.append(media_item['url'])
        elif 'bundleProductImage' in product and isinstance(product['bundleProductImage'], list):
            for img in product['bundleProductImage']:
                if 'url' in img:
                    general_images.append(img['url'])

        general_product_price = product.get('price', {}).get('currentRetail')
        general_product_old_price = product.get('price', {}).get('oldRetail')
        
        current_is_on_sale_status = product.get('price', {}).get('isOnSale')
        if current_is_on_sale_status is None:
            current_is_on_sale_status = product.get('isOnSale')
        if current_is_on_sale_status is None:
            if general_product_price is not None and general_product_old_price is not None and general_product_old_price > general_product_price:
                current_is_on_sale_status = True
            else:
                current_is_on_sale_status = False

        general_product_discount_percentage = None
        general_product_display_discount_percentage = None
        general_product_discount_label = None

        if general_product_price is not None and general_product_old_price is not None and general_product_old_price > general_product_price:
            general_product_discount_percentage = ((general_product_old_price - general_product_price) / general_product_old_price) * 100
            general_product_discount_percentage = round(general_product_discount_percentage, 2)
            general_product_display_discount_percentage = int(round(general_product_discount_percentage))
            general_product_discount_label = f"-{int(round(general_product_discount_percentage))}%"
        
        fallback_sku = product.get('detail', {}).get('reference') or product.get('reference') or product.get('bundleProductReference')

        current_product_url = None
        if base_product_id and base_parent_id:
            current_product_url = (
                f"https://www.zara.cn/cn/en/{product_slug}-p{base_product_id}.html"
                f"?v1={base_parent_id}"
            )
        elif base_product_id:
            current_product_url = f"https://www.zara.cn/cn/en/{product_slug}-p{base_product_id}.html"

        row = {
            'category_id': base_category_id,
            'category_name': base_category_name,
            'section_name': base_section_name,
            'product_name': base_product_name,
            'product_id': base_product_id,
            'old_price': general_product_old_price,
            'price': general_product_price,
            'discount_percentage': general_product_discount_percentage,
            'display_discount_percentage': general_product_display_discount_percentage,
            'discount_label': general_product_discount_label,
            'sku': fallback_sku, # Fallback SKU
            'sizes_available_by_color': "", # Өнгө олдсонгүй бол тусгай хэмжээ байхгүй
            'description': base_description, # base_description ашиглана
            'composition': base_composition, # base_composition ашиглана
            'is_on_sale': current_is_on_sale_status,
            'images_url': ", ".join(general_images),
            'color': None,
            'color_hex_code': None,
            'product_url': current_product_url,
            'related_products': "; ".join(base_related_products_info)
        }
        all_product_rows.append(row)


    try:
        with open(csv_file_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_product_rows)
        print(f"\nӨгөгдлийг {csv_file_path} руу амжилттай хөрвүүллээ.")
    except IOError as e:
        print(f"\nАлдаа: CSV файл {csv_file_path} руу бичих үед алдаа гарлаа: {e}")

# Функцийг файлын нэрсээр дуудна
json_file = 'zara_product_detail.json'
csv_file = 'zara_product_details.csv'
convert_zara_json_to_csv(json_file, csv_file)
