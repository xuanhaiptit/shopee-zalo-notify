import requests
import time
import hmac
import hashlib
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---- CONFIG ----
PARTNER_ID = 2011711               # Thay bằng Partner_id của bạn
PARTNER_KEY = "shpk6370504e5868504e59736d774474545870505952744b635a566c7471586c"   # Thay bằng Partner_key
TOKEN_FILE = "access_token_expire.json"   # File lưu token (relative path)
TOKEN_REFRESH_BEFORE = 600         # Refresh token khi còn <10 phút
ORDER_TIME_RANGE = 24*60*60        # Lấy đơn trong 24h gần nhất
PAGE_SIZE = 20                     # Số đơn mỗi lần gọi (tối đa 50)
# ---------------

def send_email(subject, body, to_email, from_email="xuanhaiptit@gmail.com", app_password="jzepikklfowgnhuh"):
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
    server.login(from_email, app_password)
    text = msg.as_string()
    server.sendmail(from_email, to_email, text)
    server.quit()
    print("Đã gửi mail thành công tới", to_email)
    
def notify_zalo_oa(message, user_id, zalo_oa_access_token):
    url = "https://openapi.zalo.me/v2.0/oa/message"   # sửa lại v2.0
    headers = {
        "access_token": zalo_oa_access_token,
        "Content-Type": "application/json"
    }
    payload = {
        "recipient": {
            "user_id": user_id
        },
        "message": {
            "text": message
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    print("Zalo OA response:", response.status_code, response.text)
    try:
        return response.json()
    except Exception as e:
        return {"error": "not_json", "raw": response.text}

    
def generate_signature(key, base_string):
    return hmac.new(key.encode('utf-8'), base_string.encode('utf-8'), hashlib.sha256).hexdigest()

def load_token():
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def save_token(token_info):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_info, f)

def refresh_access_token(partner_id, partner_key, shop_id, refresh_token):
    path = "/api/v2/auth/access_token/get"
    timestamp = int(time.time())
    base_string = f"{partner_id}{path}{timestamp}{refresh_token}{shop_id}"
    sign = generate_signature(partner_key, base_string)
    url = f"https://partner.shopeemobile.com{path}?partner_id={partner_id}&timestamp={timestamp}&sign={sign}"

    body = {
        "refresh_token": refresh_token,
        "shop_id": shop_id,
        "partner_id": partner_id
    }
    headers = {"Content-Type": "application/json"}
    resp = requests.post(url, json=body, headers=headers)
    data = resp.json()
    print("Refresh access_token response:", data)
    if data.get("access_token") and data.get("expire_in"):
        return data
    else:
        raise Exception(f"Refresh token failed: {data}")

def get_order_list(partner_id, partner_key, shop_id, access_token):
    path = "/api/v2/order/get_order_list"
    timestamp = int(time.time())
    base_string = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    sign = hmac.new(
        partner_key.encode(),
        base_string.encode(),
        hashlib.sha256
    ).hexdigest()
    
    now = int(time.time())
    params = {
        "access_token": access_token,
        # KHÔNG truyền cursor nếu chưa phân trang
        "order_status": "READY_TO_SHIP",   # hoặc trạng thái khác bạn muốn lấy
        "page_size": 20,
        "partner_id": partner_id,
        "response_optional_fields": "order_status",
        "shop_id": shop_id,
        "sign": sign,
        "time_range_field": "create_time",
        "timestamp": timestamp,
        "time_from": now - 3 * 24 * 60 * 60,  # 3 ngày trước
        "time_to": now
    }

    url = "https://partner.shopeemobile.com/api/v2/order/get_order_list"
    resp = requests.get(url, params=params)
    

    data = resp.json()
    if data.get("response", {}).get("order_list"):
        return data["response"]["order_list"]
    else:
        print("No order found or error:", data)
        return []


def get_order_detail(partner_id, partner_key, shop_id, access_token, order_sn_list):
    path = "/api/v2/order/get_order_detail"
    timestamp = int(time.time())
    base_string = f"{partner_id}{path}{timestamp}{access_token}{shop_id}"
    sign = generate_signature(partner_key, base_string)
    url = f"https://partner.shopeemobile.com{path}"

    # order_sn_list phải là string, phân cách bằng dấu phẩy
    order_sn_list_str = ",".join(order_sn_list)

    params = {
        "partner_id": partner_id,
        "timestamp": timestamp,
        "sign": sign,
        "access_token": access_token,
        "shop_id": shop_id,
        "order_sn_list": order_sn_list_str,
        # Nếu muốn lấy thêm trường gì, thêm vào đây
        # "response_optional_fields": "total_amount"
    }

    resp = requests.get(url, params=params)
    try:
        data = resp.json()
    except Exception as e:
        print("JSON decode error:", e)
        return []

    if data.get("response", {}).get("order_list"):
        return data["response"]["order_list"]
    else:
        print("Get order detail response:", data)
        return []


def filter_hoa_toc(order_details):
    #print("order_details:", resp.status_code)
    # Kiểm tra logistics_service_type hoặc field khác tùy vào shop của bạn
    fast_orders = []
    for order in order_details:
        logistics_type = order.get("logistics_service_type", "")
        # Thực tế bạn nên kiểm tra giá trị thực tế trả về từ API
        if "FAST" in logistics_type.upper() or "HỎA TỐC" in logistics_type.upper():
            fast_orders.append(order)
    return fast_orders

def main():
    # Load token
    token_info = load_token()
    shop_id = token_info["shop_id"]

    # Auto refresh access_token nếu sắp hết hạn
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

    # Gọi API lấy đơn mới nhất
    order_sn_list = get_order_list(PARTNER_ID, PARTNER_KEY, shop_id, token_info["access_token"])
    if not order_sn_list:
        print("Không có đơn nào mới trong 24h.")
        return
    order_sn_list = [order["order_sn"] for order in order_sn_list]
    
    print(f"Có {len(order_sn_list)} đơn mới, kiểm tra chi tiết...")
    order_details = get_order_detail(PARTNER_ID, PARTNER_KEY, shop_id, token_info["access_token"], order_sn_list)
    fast_orders = filter_hoa_toc(order_details)
    zalo_oa_access_token = "jBeBEe0dP6-ylWazZIPkQBg-0ZU9F1yS-zG50x1B8rM4h31KrZ0qPf7HAqh33orsd-aNG_yF06-_nMeamY5PCgxdJXQJFqSQpE9TCO5-P3dRubusktjH88pcJZxO7s8wi-1l4uyZQ3F-kc0CcKnc9EYIJtgfJLvMxePKPjr1OcAzX0r2z6mXJvgPIswc0KezrDbm7OOtR33tqtm_dWPL0QFUEpJ-AWu0dEC21VSNSIYtqm8U-ZCLIuYc16wwRpixXwqnAjKs2XYupHKmqnaH7xNV93x50oisWzKc9kaWCGwlo5WnqpHr5fBiQ1EdEGGzcwDt0VSwJmcwsLqgsqrRF-_CIX_V3daFWFLqCS4GNJEEwc4M_NvmGgw6ObtnVKHZXgWjFUrj0tQwbsyboMi86OAI8W_DToK2TMa5h5vcXJXcQm"
    user_id = "1391639123705599205"

    to_email = "xuanhaiptit@gmail.com"
    if fast_orders:
        print(f"==> Có {len(fast_orders)} đơn hỏa tốc mới:")
        for order in fast_orders:
            print(f"- order_sn: {order.get('order_sn')} | logistics_service_type: {order.get('logistics_service_type')}")
        msg = "Có đơn hỏa tốc nhé"
        #notify_zalo_oa(msg, user_id, zalo_oa_access_token)
        subject = "ĐƠN HỎA TỐC MỚI"
        body = "Bạn có đơn hỏa tốc mới"
    else:
        print("Không có đơn hỏa tốc nào mới trong 24h.")
        msg = "Không có đơn hỏa tốc nào mới trong 24h."
        #notify_zalo_oa(msg, user_id, zalo_oa_access_token)
        subject = "KHÔNG ĐƠN HỎA TỐC MỚI"
        body = "Bạn KHÔNG có đơn hỏa tốc mới"
        
    send_email(subject, body, to_email)
    
if __name__ == "__main__":
    main()
