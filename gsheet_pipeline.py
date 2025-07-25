"""Pipeline to scrape Zara categories, products and details, storing results in Google Sheets.

This script contains three main steps:
1. Fetch categories and write to a sheet named "Categories".
2. Read selected categories from the first sheet and fetch product lists,
   writing the results to a sheet named "product_lists".
3. Read selected products from the second sheet and fetch detailed
   information, writing the results to a sheet named "product_detailed".

Each sheet contains a column called "Selected". New rows default to "none".
Users can set this value to "selected" to include the row in the next step.

Google Sheets access requires a service account JSON key file. Provide the
spreadsheet ID via the SPREADSHEET_ID constant or environment variable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Dict, Iterable, List

import pandas as pd
import requests

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:  # pragma: no cover - gspread may not be installed
    gspread = None
    Credentials = None

# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID", "YOUR_SPREADSHEET_ID")
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "service_account.json")


def _authorize_gspread():
    """Authorize a gspread client using a service account."""
    if gspread is None:
        raise ImportError("gspread is required for Google Sheets interaction")

    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client


def _get_or_create_sheet(client: "gspread.Client", sheet_name: str):
    """Return a gspread worksheet creating it if missing."""
    ss = client.open_by_key(SPREADSHEET_ID)
    try:
        return ss.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        return ss.add_worksheet(title=sheet_name, rows="100", cols="20")


# ---------------------------------------------------------------------------
# Step 1: fetch categories
# ---------------------------------------------------------------------------
CATEGORY_URL = "https://www.zara.cn/cn/en/categories?ajax=true"


def _generate_product_link(seo_keyword: str | None, seo_id: str | None) -> str | None:
    if not seo_keyword or not seo_id:
        return None
    cleaned = re.sub(r"[^a-zA-Z0-9-]", "", seo_keyword).lower()
    return f"https://www.zara.cn/cn/en/{cleaned}-l{seo_id}.html"


def _extract_categories(data: Dict, level: int = 0, parent: str = "", out: List[Dict] | None = None) -> List[Dict]:
    if out is None:
        out = []
    name = data.get("name")
    path = f"{parent} > {name}" if parent else name
    seo = data.get("seo", {})
    row = {
        "Category ID": data.get("id"),
        "Category Name": name,
        "Full Path": path,
        "Section Name": data.get("sectionName"),
        "Level": level,
        "Layout": data.get("layout"),
        "Content Type": data.get("contentType"),
        "Redirected": data.get("isRedirected"),
        "Hidden In Menu": seo.get("isHiddenInMenu"),
        "Key": data.get("key"),
        "SEO ID": seo.get("seoCategoryId"),
        "SEO Keyword": seo.get("keyword"),
        "Must Display Content": data.get("attributes", {}).get("mustDisplayContent"),
        "Show Subcategories": data.get("attributes", {}).get("showSubcategories"),
        "Product Link": _generate_product_link(seo.get("keyword"), seo.get("seoCategoryId")),
    }
    out.append(row)
    for sub in data.get("subcategories", []):
        _extract_categories(sub, level + 1, path, out)
    return out


def fetch_categories() -> pd.DataFrame:
    """Return a dataframe of all categories."""
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(CATEGORY_URL, headers=headers, timeout=10)
    res.raise_for_status()
    payload = res.json()
    out: List[Dict] = []
    for cat in payload.get("categories", []):
        _extract_categories(cat, 0, "", out)
    df = pd.DataFrame(out)
    df["Selected"] = "none"
    return df


def write_categories_to_sheet():
    client = _authorize_gspread()
    sheet = _get_or_create_sheet(client, "Categories")
    df = fetch_categories()
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"Wrote {len(df)} categories to Google Sheets.")


# ---------------------------------------------------------------------------
# Step 2: product lists
# ---------------------------------------------------------------------------

PRODUCT_LIST_URL = "https://www.zara.cn/cn/en/category/{category_id}/products?ajax=true"


def fetch_product_list(category_id: int) -> Iterable[Dict]:
    headers = {"User-Agent": "Mozilla/5.0"}
    url = PRODUCT_LIST_URL.format(category_id=category_id)
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    data = res.json()
    for group in data.get("productGroups", []):
        for element in group.get("elements", []):
            for product in element.get("commercialComponents", []):
                product_id = product.get("id")
                name = product.get("name")
                detail = product.get("detail", {})
                seo_id = product.get("seo", {}).get("seoProductId")
                slug = re.sub(r"\s+", "-", name.lower()) if name else ""
                url = f"https://www.zara.cn/cn/en/{slug}-p{seo_id}.html" if seo_id else None
                yield {
                    "Category ID": category_id,
                    "Product ID": product_id,
                    "Product Name": name,
                    "Product URL": url,
                }


def write_product_lists_to_sheet():
    client = _authorize_gspread()
    ss = client.open_by_key(SPREADSHEET_ID)
    categories = ss.worksheet("Categories").get_all_records()
    selected = [c for c in categories if str(c.get("Selected")).lower() == "selected"]
    rows: List[Dict] = []
    for cat in selected:
        cid = cat.get("Category ID")
        try:
            for prod in fetch_product_list(int(cid)):
                prod["Selected"] = "none"
                rows.append(prod)
        except Exception as exc:  # pragma: no cover - network errors
            print(f"Failed to fetch products for category {cid}: {exc}")
    sheet = _get_or_create_sheet(client, "product_lists")
    df = pd.DataFrame(rows)
    if not df.empty:
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"Wrote {len(df)} product rows to Google Sheets.")
    else:
        print("No products to write.")


# ---------------------------------------------------------------------------
# Step 3: product details
# ---------------------------------------------------------------------------

PRODUCT_DETAIL_URL = "https://www.zara.cn/cn/en/products/{product_id}.json"


def fetch_product_detail(product_id: int) -> Dict:
    headers = {"User-Agent": "Mozilla/5.0"}
    url = PRODUCT_DETAIL_URL.format(product_id=product_id)
    res = requests.get(url, headers=headers, timeout=15)
    res.raise_for_status()
    data = res.json().get("product", {})
    return {
        "Product ID": product_id,
        "product_name": data.get("name"),
        "price": data.get("price"),
        "description": data.get("detail", {}).get("description"),
    }


def write_product_details_to_sheet():
    client = _authorize_gspread()
    ss = client.open_by_key(SPREADSHEET_ID)
    prod_rows = ss.worksheet("product_lists").get_all_records()
    selected = [p for p in prod_rows if str(p.get("Selected")).lower() == "selected"]
    detail_rows: List[Dict] = []
    for prod in selected:
        pid = prod.get("Product ID")
        try:
            detail = fetch_product_detail(int(pid))
            detail["Category ID"] = prod.get("Category ID")
            detail_rows.append(detail)
        except Exception as exc:  # pragma: no cover - network errors
            print(f"Failed to fetch detail for product {pid}: {exc}")
    sheet = _get_or_create_sheet(client, "product_detailed")
    df = pd.DataFrame(detail_rows)
    if not df.empty:
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        print(f"Wrote {len(df)} product detail rows to Google Sheets.")
    else:
        print("No product details to write.")


if __name__ == "__main__":  # pragma: no cover - manual execution entry
    import argparse

    parser = argparse.ArgumentParser(description="Zara scraping pipeline")
    parser.add_argument("step", choices=["categories", "lists", "details"], help="Step to run")
    args = parser.parse_args()

    if args.step == "categories":
        write_categories_to_sheet()
    elif args.step == "lists":
        write_product_lists_to_sheet()
    else:
        write_product_details_to_sheet()
