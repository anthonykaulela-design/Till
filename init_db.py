def init_database(self):
    conn = self.connect_db()
    cursor = conn.cursor()

    # 1. Companies Table (Master Admin Accounts)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                company_name TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)

    # 2. Products Table (Inventory & Sales Tracker)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                barcode TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock_count INTEGER DEFAULT 0,
                items_bought INTEGER DEFAULT 0,
                date_added TEXT NOT NULL,
                is_synced INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL,
                FOREIGN KEY(company_name) REFERENCES companies(company_name)
            )
        """)

    # 3. Cashiers Table (Full Name, ID Number, & Password Authentication)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS cashiers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                full_name TEXT NOT NULL,
                id_number TEXT NOT NULL,
                password TEXT NOT NULL,
                FOREIGN KEY(company_name) REFERENCES companies(company_name)
            )
        """)

    # 4. Promotions Table (Custom Receipt Footers & Notices)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS promotions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                promo_text TEXT NOT NULL,
                FOREIGN KEY(company_name) REFERENCES companies(company_name)
            )
        """)

    conn.commit()
    conn.close()
```[cite: 12]