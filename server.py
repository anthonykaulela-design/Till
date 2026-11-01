from flask import Flask, jsonify, request
import mysql.connector

app = Flask(__name__)

def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="your_password",
        database="enterprise_pos"
    )

@app.route("/")
def home():
    return jsonify({"status": "Enterprise POS Sync Server Online", "version": "1.0.0"})

@app.route("/upload", methods=["POST"])
def upload_sales():
    company = request.headers.get("X-Company-Name")
    payload = request.json
    
    conn = get_db()
    cursor = conn.cursor()
    for item in payload:
        cursor.execute(
            """INSERT INTO sales_log (company_name, product_id, product_name, units_sold, total_revenue, sale_date, sale_week, sale_month, sale_year, timestamp)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                company,
                item.get("product_id"),
                item["name"],
                item["units"],
                item["revenue"],
                item["sale_date"],
                item["sale_week"],
                item["sale_month"],
                item["sale_year"],
                item["timestamp"]
            )
        )
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "synced_items": len(payload)}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)