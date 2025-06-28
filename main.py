import datetime

def get_shopee_orders():
    # Chỗ này bạn viết logic gọi API Shopee thật
    # Demo: luôn trả về một đơn hỏa tốc
    return [{"id": 123, "type": "hỏa tốc"}]

def notify_zalo(message):
    # Chỗ này bạn gọi API Zalo thật
    print(f"Gửi Zalo: {message}")

def main():
    now = datetime.datetime.now()
    print(f"--- Chạy job lúc: {now} ---")
    orders = get_shopee_orders()
    for order in orders:
        if order['type'] == 'hỏa tốc':
            notify_zalo(f"Đơn hỏa tốc mới: {order['id']} lúc {now}")

if __name__ == "__main__":
    main()
