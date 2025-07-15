import requests
import hmac
import hashlib
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pprint
from datetime import datetime, time as dt_time
import time
from zoneinfo import ZoneInfo   # có sẵn từ Python 3.9

# ---- CONFIG ----
PARTNER_ID = 2011711
PARTNER_KEY = "shpk74414273766e577065514e78766c704b64756a75456a624c4f7257756d54"
TOKEN_FILE = "access_token_expire.json"
TOKEN_REFRESH_BEFORE = 600        # 10 phút trước khi hết hạn thì refresh
ORDER_TIME_RANGE = 24 * 60 * 60   # 24h gần nhất
PAGE_SIZE = 100

FROM_EMAIL = "xuanhaiptit@gmail.com"
APP_PASSWORD = "jzepikklfowgnhuh"
TO_EMAILS = ["xuanhaiptit@gmail.com",
             "nguyenthigiang3007@gmail.com"]

TZ = ZoneInfo("Asia/Bangkok")
QUIET_START = dt_time(20, 0)   # 20:00
QUIET_END   = dt_time(7, 0)    # 06:00
# ========== UTILS ==========
def in_quiet_hours(now=None):
    if now is None:
        now = datetime.now(TZ).time()
    return now >= QUIET_START or now < QUIET_END

def send_email(subject, body, to_emails=TO_EMAILS,
               from_email=FROM_EMAIL, app_password=APP_PASSWORD):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    subject_with_time = f"{subject} - {now_str}"
    """Gửi email cảnh báo cho nhiều người."""
    # Nếu dùng list, hiển thị To: với các địa chỉ cách nhau bằng dấu phẩy
    if isinstance(to_emails, (list, tuple)):
        to_header = ", ".join(to_emails)
    else:   # vẫn cho phép truyền chuỗi đơn
        to_emails = [to_emails]
        to_header = to_emails[0]

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_header
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(from_email, app_password)
        server.sendmail(from_email, to_emails, msg.as_string())

    print("Đã gửi mail thành công tới:", to_header)

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

def send_slack_message(message, webhook_url):
    payload = {
        "text": message
    }
    try:
        resp = requests.post(webhook_url, json=payload)
        print("Đã gửi Slack:", resp.status_code, resp.text)
    except Exception as e:
        print("Lỗi gửi Slack:", e)

SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/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"  # dán webhook của bạn vào đây

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
        "response_optional_fields": "package_list,fulfillment_list"
    }
    resp = requests.get(url, params=params)
    try:
        data = resp.json()
    except Exception as e:
        print("JSON decode error:", e)
        return []
    return data.get("response", {}).get("order_list", [])

def filter_hoa_toc(order_details):
    """
    Trả về list order hỏa tốc dựa trên shipping_carrier bên trong package_list.
    """
    fast_keywords = {"SPX INSTANT", "GRABEXPRESS", "AHAMOVE"}
    fast_orders = []

    for order in order_details:
        packages = order.get("package_list", []) or order.get("fulfillment_list", [])
        for pkg in packages:
            carrier = (pkg.get("shipping_carrier") or "").upper()
            if any(k in carrier for k in fast_keywords):
                fast_orders.append(order)
                break   # tìm thấy 1 package hỏa tốc là đủ

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
        #send_email("KHÔNG ĐƠN HỎA TỐC MỚI", "Bạn KHÔNG có đơn hỏa tốc mới")
        return

    order_sn_list = [order["order_sn"] for order in orders]
    print(f"Có {len(order_sn_list)} đơn mới, kiểm tra chi tiết...")

    order_details = get_order_detail(PARTNER_ID, PARTNER_KEY, shop_id, token_info["access_token"], order_sn_list)
    #print(order_details)
    #pprint.pprint(order_details)
    fast_orders = filter_hoa_toc(order_details)

    if fast_orders:
        print(f"==> Có {len(fast_orders)} đơn hỏa tốc mới:")
        for order in fast_orders:
            print(f"- order_sn: {order.get('order_sn')} | logistics_service_type: {order.get('logistics_service_type')}")
            if in_quiet_hours():
                print("Đang trong khung giờ yên lặng (20h-06h) – không gửi email.")
            else:
                send_email("CÓ ĐƠN HỎA TỐC NHÉ BẠN", f"Bạn có {len(fast_orders)} đơn hỏa tốc mới\n" + "\n".join([f"- {o['order_sn']}" for o in fast_orders]))
        
    else:
        print("Không có đơn hỏa tốc nào mới trong 24h.")



if __name__ == "__main__":
    main()
