import requests
import time
import hmac
import hashlib
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---- CONFIG ----
PARTNER_ID = 2011711
PARTNER_KEY = "shpk6370504e5868504e59736d774474545870505952744b635a566c7471586c"
TOKEN_FILE = "access_token_expire.json"
TOKEN_REFRESH_BEFORE = 600        # 10 phút trước khi hết hạn thì refresh
ORDER_TIME_RANGE = 24 * 60 * 60   # 24h gần nhất
PAGE_SIZE = 20

FROM_EMAIL = "xuanhaiptit@gmail.com"
APP_PASSWORD = "jzepikklfowgnhuh"
TO_EMAIL = "xuanhaiptit@gmail.com"

# ========== UTILS ==========

def send_email(subject, body, to_email=TO_EMAIL, from_email=FROM_EMAIL, app_password=APP_PASSWORD):
    """Gửi email cảnh báo."""
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, to_email, msg.as_string())
    print("Đã gửi mail thành công tới", to_email)

def generate_signature(key, base_string):
    """Sinh chữ ký Shopee."""
    return hmac.new(key.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256).hexdigest()

def load_token():
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_token(token_info):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_info, f)

# ========== SHOPEE API ==========

HOST = "https://partner.shopeemobile.com"      # ✔ đúng domain

def refresh_access_token(partner_id, partner_key, shop_id, refresh_token):
    path = "/api/v2/auth/access_token/get"
    timestamp = int(time.time())

    # 1) Base-string chỉ 3 thành phần (partner_id + path + timestamp)
    base_string = f"{partner_id}{path}{timestamp}"
    sign = generate_signature(partner_key, base_string)

    url = f"{HOST}{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"

    body = {
        "partner_id": partner_id,      # để kiểu int
        "shop_id": shop_id,            # int
        "refresh_token": refresh_token
    }

    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, json=body, headers=headers)
    print("STATUS:", resp.status_code)
    print("Headers:", resp.headers.get("content-type"))
    print("Body preview:", resp.text[:500])
    # 2) Bắt các trường hợp không phải JSON
    if not resp.headers.get("content-type", "").lower().startswith("application/json"):
        raise Exception(f"Refresh token HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    if "access_token" in data and "expire_in" in data:
        return data
    raise Exception(f"Refresh token failed: {data}")



def get_order_list(partner_id, partner_key, shop_id, access_token):
    """Lấy danh sách order mới nhất."""
    path = "/api/v2/order/get_order_list"
    timestamp = int(time.time())
    base_string = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    sign = generate_signature(partner_key, base_string)
    now = int(time.time())
    params = {
        "access_token": access_token,
        "order_status": "READY_TO_SHIP",
        "page_size": PAGE_SIZE,
        "partner_id": partner_id,
        "response_optional_fields": "order_status",
        "shop_id": shop_id,
        "sign": sign,
        "time_range_field": "create_time",
        "timestamp": timestamp,
        "time_from": now - ORDER_TIME_RANGE,
        "time_to": now
    }
    url = "https://partner.shopeemobile.com/api/v2/order/get_order_list"
    resp = requests.get(url, params=params)
    data = resp.json()
    return data.get("response", {}).get("order_list", [])

def get_order_detail(partner_id, partner_key, shop_id, access_token, order_sn_list):
    """Lấy chi tiết đơn."""
    if not order_sn_list:
        return []
    path = "/api/v2/order/get_order_detail"
    timestamp = int(time.time())
    base_string = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    sign = generate_signature(partner_key, base_string)
    url = f"https://partner.shopeemobile.com{path}"
    order_sn_list_str = ",".join(order_sn_list)
    params = {
        "partner_id": partner_id,
        "timestamp": timestamp,
        "sign": sign,
        "access_token": access_token,
        "shop_id": shop_id,
        "order_sn_list": order_sn_list_str,
    }
    resp = requests.get(url, params=params)
    try:
        data = resp.json()
    except Exception as e:
        print("JSON decode error:", e)
        return []
    return data.get("response", {}).get("order_list", [])

def filter_hoa_toc(order_details):
    """Lọc đơn hỏa tốc dựa vào trường logistics_service_type."""
    fast_orders = []
    for order in order_details:
        logistics_type = order.get("logistics_service_type", "").upper()
        if "FAST" in logistics_type or "HỎA TỐC" in logistics_type:
            fast_orders.append(order)
    return fast_orders

# ========== MAIN LOGIC ==========

def main():
    # Load và kiểm tra token
    token_info = load_token()
    shop_id = token_info["shop_id"]

    # Refresh access_token nếu sắp hết hạn
    if time.time() > token_info["access_token_expire"] - TOKEN_REFRESH_BEFORE:
        print("Access_token gần hết hạn, tự động refresh...")
        new_token_data = refresh_access_token(
            PARTNER_ID, PARTNER_KEY, shop_id, token_info["refresh_token"]
        )
        token_info["access_token"] = new_token_data["access_token"]
        token_info["refresh_token"] = new_token_data["refresh_token"]
        token_info["access_token_expire"] = time.time() + new_token_data["expire_in"]
        save_token(token_info)
        print("Đã refresh xong access_token!")

    # Lấy danh sách đơn READY_TO_SHIP trong 24h gần nhất
    orders = get_order_list(PARTNER_ID, PARTNER_KEY, shop_id, token_info["access_token"])
    if not orders:
        print("Không có đơn nào mới trong 24h.")
        send_email("KHÔNG ĐƠN HỎA TỐC MỚI", "Bạn KHÔNG có đơn hỏa tốc mới")
        return

    order_sn_list = [order["order_sn"] for order in orders]
    print(f"Có {len(order_sn_list)} đơn mới, kiểm tra chi tiết...")

    order_details = get_order_detail(PARTNER_ID, PARTNER_KEY, shop_id, token_info["access_token"], order_sn_list)
    fast_orders = filter_hoa_toc(order_details)

    if fast_orders:
        print(f"==> Có {len(fast_orders)} đơn hỏa tốc mới:")
        for order in fast_orders:
            print(f"- order_sn: {order.get('order_sn')} | logistics_service_type: {order.get('logistics_service_type')}")
        send_email("ĐƠN HỎA TỐC MỚI", f"Bạn có {len(fast_orders)} đơn hỏa tốc mới\n" + "\n".join([f"- {o['order_sn']}" for o in fast_orders]))
    else:
        print("Không có đơn hỏa tốc nào mới trong 24h.")
        send_email("KHÔNG ĐƠN HỎA TỐC MỚI", "Bạn KHÔNG có đơn hỏa tốc mới")



if __name__ == "__main__":
    main()
