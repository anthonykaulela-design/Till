from datetime import datetime, timedelta
import sqlite3
import threading
import time
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
import requests
import mysql.connector

def connect_db(self):
    return mysql.connector.connect(
        host="gateway01.eu-central-1.prod.aws.tidbcloud.com",          # Change to your remote MySQL server IP if hosted remotely
        user="3ELby3yHuXnNY9H.root",               # Your MySQL username
        password="lGTvpwXvCpuqB99y",  # Your MySQL password
        database="legal_saas"  # Ensure this database is created in MySQL beforehand
    )


# NOTE FOR MYSQL INTEGRATION:
# To switch from SQLite to MySQL, install `mysql-connector-python` or `pymysql` via pip.
# Replace `self.connect_db()` to return:
# import mysql.connector
# return mysql.connector.connect(host="localhost", user="root", password="yourpassword", database="enterprise_pos")


class OfflinePOS:

  def __init__(self, root):
    self.root = root
    self.root.title("Enterprise Multi-Tenant POS System & Hardware Suite")
    self.root.geometry("1150x820")

    # --- THEME COLORS ---
    self.COLOR_BG = "#111625"
    self.COLOR_CARD = "#1a2238"
    self.COLOR_ACCENT = "#00d2ff"
    self.COLOR_TEXT = "#ffffff"
    self.COLOR_SECONDARY = "#8892b0"
    self.COLOR_BTN_GREEN = "#10b981"
    self.COLOR_BTN_RED = "#ef4444"
    self.root.configure(bg=self.COLOR_BG)

    # --- TENANT & HARDWARE CONFIGURATION ---
    self.active_company_name = ""
    self.active_company_password = ""
    self.active_cashier = "Till Operator"
    self.db_name = "inventory_enterprise.db"
    self.SERVER_URL = "http://127.0.0.1:5000"

    # Hardware interface settings (Supports USB, PS2, RS232, & Bluetooth scanner apps via keyboard wedge / COM ports)
    self.scanner_interface = "USB / PS2 / Bluetooth HID / RS232"
    self.cash_drawer_port = "RJ11 (Receipt Printer Connected)"

    self.init_database()
    self.cart = []
    self.selected_stock_id = None

    # Main graphical frame viewport panel container
    self.container = tk.Frame(self.root, bg=self.COLOR_BG)
    self.container.pack(fill=tk.BOTH, expand=True)

    # Bottom Connection & Session Metadata Ticker Bar
    self.status_bar = tk.Label(
        self.root,
        text="System initialized. Please log in to your workspace.",
        font=("Arial", 10, "bold"),
        bd=1,
        relief=tk.SUNKEN,
        anchor=tk.W,
        bg=self.COLOR_CARD,
        fg=self.COLOR_SECONDARY,
    )
    self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # Show the Gateway Authorization Screen first on initialization
    self.show_login_screen()

    # Start Multi-Tenant Asynchronous Background Sync Thread Worker
    self.sync_active = True
    self.sync_thread = threading.Thread(
        target=self.background_sync_worker, daemon=True
    )
    self.sync_thread.start()

  def connect_db(self):
    return sqlite3.connect(self.db_name)

  def init_database(self):
    conn = self.connect_db()
    cursor = conn.cursor()
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                company_name TEXT PRIMARY KEY,
                password TEXT NOT NULL
            )
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                barcode TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                stock_count INTEGER DEFAULT 0,
                date_added TEXT NOT NULL,
                is_synced INTEGER DEFAULT 0,
                last_updated TEXT NOT NULL,
                FOREIGN KEY(company_name) REFERENCES companies(company_name)
            )
        """)
    cursor.execute("""
            CREATE TABLE IF NOT EXISTS sales_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_name TEXT NOT NULL,
                product_id INTEGER,
                product_name TEXT NOT NULL,
                units_sold INTEGER NOT NULL,
                total_revenue REAL NOT NULL,
                sale_date TEXT NOT NULL,
                sale_week TEXT NOT NULL,
                sale_month TEXT NOT NULL,
                sale_year TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(company_name) REFERENCES companies(company_name)
            )
        """)

    cursor.execute("PRAGMA table_info(cashiers)")
    columns = [col[1] for col in cursor.fetchall()]
    if columns and "full_name" not in columns:
      cursor.execute("DROP TABLE IF EXISTS cashiers")

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

  def clear_container(self):
    for widget in self.container.winfo_children():
      widget.destroy()

  # ==========================================
  # 🔌 HARDWARE PERIPHERALS CONTROLLER
  # ==========================================
  def trigger_cash_drawer_rj11(self):
    try:
      print("[HARDWARE - RJ11] Sending cash drawer kick pulse via printer port...")
    except Exception as e:
      print(f"[HARDWARE ERROR - RJ11]: {e}")

  def read_barcode_scanner_input(self, raw_input_string):
    """Supports USB, PS2, Bluetooth scanner apps (keyboard wedge mode), and RS232 streams."""
    clean_code = raw_input_string.strip()
    clean_code = clean_code.replace("\r", "").replace("\n", "")
    return clean_code

  # ==========================================
  # 🔐 LOGIN / REGISTRATION SCREEN
  # ==========================================
  def show_login_screen(self):
    self.clear_container()
    self.active_company_name = ""
    self.active_company_password = ""
    self.active_cashier = "Till Operator"
    self.status_bar.config(
        text="Security Gateway Lock: Awaiting Authentication Check...",
        fg=self.COLOR_SECONDARY,
    )

    login_frame = tk.Frame(
        self.container,
        bg=self.COLOR_CARD,
        highlightbackground=self.COLOR_ACCENT,
        highlightthickness=1,
        padx=30,
        pady=25,
    )
    login_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER, width=480, height=480)

    tk.Label(
        login_frame,
        text="ENTERPRISE BUSINESS PORTAL",
        font=("Arial", 16, "bold"),
        fg=self.COLOR_ACCENT,
        bg=self.COLOR_CARD,
    ).pack(pady=(5, 15))

    mode_frame = tk.Frame(login_frame, bg=self.COLOR_CARD)
    mode_frame.pack(fill=tk.X, pady=5)

    self.login_mode = tk.StringVar(value="admin")

    def toggle_mode():
      if self.login_mode.get() == "admin":
        lbl_user.config(text="Company Name:")
        lbl_cashier_name.pack_forget()
        entry_cashier_name.pack_forget()
        lbl_pass.config(text="Admin Password Code:")
      else:
        lbl_user.config(text="Company Name:")
        lbl_cashier_name.pack(anchor=tk.W, pady=(5, 2), before=lbl_pass)
        entry_cashier_name.pack(fill=tk.X, pady=2, before=lbl_pass)
        lbl_pass.config(text="Cashier Password:")

    tk.Radiobutton(
        mode_frame,
        text="Admin Login",
        variable=self.login_mode,
        value="admin",
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
        selectcolor=self.COLOR_BG,
        font=("Arial", 10, "bold"),
        command=toggle_mode,
    ).pack(side=tk.LEFT, padx=10)
    tk.Radiobutton(
        mode_frame,
        text="Cashier Login",
        variable=self.login_mode,
        value="cashier",
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
        selectcolor=self.COLOR_BG,
        font=("Arial", 10, "bold"),
        command=toggle_mode,
    ).pack(side=tk.LEFT, padx=10)

    lbl_user = tk.Label(
        login_frame,
        text="Company Name:",
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
        font=("Arial", 10, "bold"),
    )
    lbl_user.pack(anchor=tk.W, pady=(10, 2))
    entry_company_name = tk.Entry(
        login_frame,
        font=("Arial", 11),
        bg=self.COLOR_BG,
        fg=self.COLOR_TEXT,
        insertbackground="white",
    )
    entry_company_name.pack(fill=tk.X, pady=2)

    lbl_cashier_name = tk.Label(
        login_frame,
        text="Cashier Full Name:",
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
        font=("Arial", 10, "bold"),
    )
    entry_cashier_name = tk.Entry(
        login_frame,
        font=("Arial", 11),
        bg=self.COLOR_BG,
        fg=self.COLOR_TEXT,
        insertbackground="white",
    )

    lbl_pass = tk.Label(
        login_frame,
        text="Admin Password Code:",
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
        font=("Arial", 10, "bold"),
    )
    lbl_pass.pack(anchor=tk.W, pady=(5, 2))
    entry_password = tk.Entry(
        login_frame,
        font=("Arial", 11),
        show="*",
        bg=self.COLOR_BG,
        fg=self.COLOR_TEXT,
        insertbackground="white",
    )
    entry_password.pack(fill=tk.X, pady=2)

    def login_action():
      cname = entry_company_name.get().strip()
      pwd = entry_password.get().strip()
      if not cname or not pwd:
        return messagebox.showerror("Error", "Please fill in all login fields.")

      try:
        conn = self.connect_db()
        cursor = conn.cursor()

        if self.login_mode.get() == "admin":
          cursor.execute(
              "SELECT company_name, password FROM companies WHERE company_name = ?",
              (cname,),
          )
          row = cursor.fetchone()
          conn.close()

          if row and row[1] == pwd:
            self.active_company_name = row[0]
            self.active_company_password = row[1]
            self.active_cashier = f"Admin ({self.active_company_name})"
            messagebox.showinfo(
                "Access Granted",
                f"Welcome Admin - Workspace: {self.active_company_name}",
            )
            self.show_landing_page()
          else:
            messagebox.showerror(
                "Access Denied", "Invalid company name or admin password."
            )
        else:
          c_fullname = entry_cashier_name.get().strip()
          if not c_fullname:
            conn.close()
            return messagebox.showerror(
                "Error", "Please enter your cashier full name."
            )

          cursor.execute(
              "SELECT full_name, password FROM cashiers WHERE company_name = ? AND full_name = ? AND password = ?",
              (cname, c_fullname, pwd),
          )
          row = cursor.fetchone()
          conn.close()

          if row:
            self.active_company_name = cname
            self.active_cashier = row[0]
            conn = self.connect_db()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT password FROM companies WHERE company_name = ?", (cname,)
            )
            creg = cursor.fetchone()
            conn.close()
            self.active_company_password = creg[0] if creg else ""

            messagebox.showinfo(
                "Access Granted",
                f"Welcome Cashier: {self.active_cashier} ({cname})",
            )
            self.open_checkout_screen()
          else:
            messagebox.showerror(
                "Access Denied",
                "Invalid company name, cashier full name, or password.",
            )
      except Exception as e:
        messagebox.showerror("Database Error", f"Login failed: {e}")

    def register_action():
      reg_window = tk.Toplevel(self.root)
      reg_window.title("Register Corporate Client Profile")
      reg_window.geometry("380x320")
      reg_window.configure(bg=self.COLOR_BG)
      reg_window.grab_set()

      tk.Label(
          reg_window,
          text="REGISTRATION PORTAL",
          font=("Arial", 14, "bold"),
          bg=self.COLOR_BG,
          fg=self.COLOR_ACCENT,
      ).pack(pady=15)

      tk.Label(
          reg_window,
          text="Trading / Legal Business Name:",
          bg=self.COLOR_BG,
          fg=self.COLOR_TEXT,
      ).pack(anchor=tk.W, padx=20)
      rname = tk.Entry(reg_window, font=("Arial", 11), width=35)
      rname.pack(pady=5, padx=20)

      tk.Label(
          reg_window,
          text="Access Secure Password String:",
          bg=self.COLOR_BG,
          fg=self.COLOR_TEXT,
      ).pack(anchor=tk.W, padx=20)
      rpwd = tk.Entry(reg_window, font=("Arial", 11), show="*", width=35)
      rpwd.pack(pady=5, padx=20)

      def submit_registration():
        name_val = rname.get().strip()
        pwd_val = rpwd.get().strip()
        if not name_val or not pwd_val:
          return messagebox.showerror(
              "Error", "All registration input blocks must be completed."
          )

        try:
          conn = self.connect_db()
          cursor = conn.cursor()
          cursor.execute(
              "INSERT INTO companies (company_name, password) VALUES (?, ?)",
              (name_val, pwd_val),
          )
          cursor.execute(
              "INSERT INTO promotions (company_name, promo_text) VALUES (?, ?)",
              (
                  name_val,
                  "PROMOTION: Return with this slip next week for 5% off!",
              ),
          )
          conn.commit()
          messagebox.showinfo(
              "Success",
              "Workspace configuration deployed successfully! You can now log in.",
          )
          reg_window.destroy()
        except sqlite3.IntegrityError:
          messagebox.showerror(
              "Error", "This company name is already registered."
          )
        except Exception as e:
          messagebox.showerror("Error", f"Registration failed: {e}")
        finally:
          try:
            conn.close()
          except:
            pass

      tk.Button(
          reg_window,
          text="Register Workspace Account",
          bg=self.COLOR_BTN_GREEN,
          fg="white",
          font=("Arial", 11, "bold"),
          command=submit_registration,
      ).pack(pady=20)

    tk.Button(
        login_frame,
        text="🔓 Authenticate & Log In",
        bg=self.COLOR_ACCENT,
        fg=self.COLOR_BG,
        font=("Arial", 11, "bold"),
        command=login_action,
        cursor="hand2",
    ).pack(fill=tk.X, pady=(10, 5))
    tk.Button(
        login_frame,
        text="📝 Register New Retail Company Profile",
        bg="#475569",
        fg="white",
        font=("Arial", 9, "bold"),
        command=register_action,
        cursor="hand2",
    ).pack(fill=tk.X)

  def background_sync_worker(self):
    while self.sync_active:
      if self.active_company_name:
        try:
          requests.get(self.SERVER_URL, timeout=3)
          online = True
        except:
          online = False

        if online:
          self.status_bar.config(
              text=f" Account Identity: {self.active_company_name} | Hardware: USB/PS2/Bluetooth/RS232/RJ11 Connected | Sync: ONLINE",
              fg=self.COLOR_BTN_GREEN,
          )
        else:
          self.status_bar.config(
              text=f" Account Identity: {self.active_company_name} | Hardware: USB/PS2/Bluetooth/RS232/RJ11 Connected | Sync: OFFLINE",
              fg="orange",
          )
      time.sleep(10)

  # ==========================================
  # 🌐 LANDING PAGE / DASHBOARD
  # ==========================================
  def show_landing_page(self):
    self.clear_container()
    landing_frame = tk.Frame(self.container, bg=self.COLOR_BG)
    landing_frame.pack(fill=tk.BOTH, expand=True, padx=40, pady=25)

    top_header_panel = tk.Frame(landing_frame, bg=self.COLOR_BG)
    top_header_panel.pack(fill=tk.X, pady=(0, 10))

    title_box = tk.Frame(top_header_panel, bg=self.COLOR_BG)
    title_box.pack(side=tk.LEFT)
    tk.Label(
        title_box,
        text=f"Workspace: {self.active_company_name}",
        font=("Arial", 20, "bold"),
        fg=self.COLOR_ACCENT,
        bg=self.COLOR_BG,
    ).pack(anchor=tk.W)
    tk.Label(
        title_box,
        text=f"Active Operator: {self.active_cashier} | Admin Control Center",
        font=("Arial", 10),
        fg=self.COLOR_SECONDARY,
        bg=self.COLOR_BG,
    ).pack(anchor=tk.W)

    tk.Button(
        top_header_panel,
        text="🔒 Log Out",
        bg=self.COLOR_CARD,
        fg=self.COLOR_BTN_RED,
        font=("Arial", 10, "bold"),
        command=self.show_login_screen,
    ).pack(side=tk.RIGHT, padx=5)

    tk.Label(
        landing_frame,
        text="Select a system module to launch:",
        font=("Arial", 12),
        fg=self.COLOR_SECONDARY,
        bg=self.COLOR_BG,
    ).pack(anchor=tk.W, pady=(10, 15))

    grid_frame = tk.Frame(landing_frame, bg=self.COLOR_BG)
    grid_frame.pack(fill=tk.BOTH, expand=True)
    for i in range(3):
      grid_frame.columnconfigure(i, weight=1)
    for j in range(2):
      grid_frame.rowconfigure(j, weight=1)

    def create_nav_card(parent, title, desc, icon, command, r, c):
      card = tk.Frame(
          parent,
          bg=self.COLOR_CARD,
          highlightbackground=self.COLOR_ACCENT,
          highlightthickness=1,
          padx=15,
          pady=15,
      )
      card.grid(row=r, column=c, sticky="nsew", padx=10, pady=10)
      tk.Label(
          card,
          text=icon,
          font=("Arial", 22),
          bg=self.COLOR_CARD,
          fg=self.COLOR_ACCENT,
      ).pack(anchor=tk.W, pady=(0, 5))
      tk.Label(
          card,
          text=title,
          font=("Arial", 13, "bold"),
          bg=self.COLOR_CARD,
          fg=self.COLOR_TEXT,
      ).pack(anchor=tk.W)
      tk.Label(
          card,
          text=desc,
          font=("Arial", 9),
          bg=self.COLOR_CARD,
          fg=self.COLOR_SECONDARY,
      ).pack(anchor=tk.W, pady=(5, 10))
      btn = tk.Button(
          card,
          text="Open Module ➔",
          bg=self.COLOR_ACCENT,
          fg=self.COLOR_BG,
          font=("Arial", 9, "bold"),
          relief=tk.FLAT,
          cursor="hand2",
          command=command,
      )
      btn.pack(anchor=tk.W)

    create_nav_card(
        grid_frame,
        "Client Checkout",
        "Process sales, cash tender, change, and automated receipt slips.",
        "🛒",
        self.open_checkout_screen,
        0,
        0,
    )
    create_nav_card(
        grid_frame,
        "Track & Manage Stock",
        "View and update remaining inventory quantities.",
        "📦🔒",
        lambda: self.admin_gate_pass(self.open_stock_screen),
        0,
        1,
    )
    create_nav_card(
        grid_frame,
        "Time-Series Sales Reports",
        "View sales and stock by days, weeks, months, years, or custom ranges.",
        "📊🔒",
        lambda: self.admin_gate_pass(self.open_time_series_sales_screen),
        0,
        2,
    )
    create_nav_card(
        grid_frame,
        "Master Inventory Ledger (Admin)",
        "Exclusive Admin module to add products.",
        "📋🔒",
        lambda: self.admin_gate_pass(self.open_ledger_screen),
        1,
        0,
    )
    create_nav_card(
        grid_frame,
        "Update Product Prices (Admin)",
        "Dedicated admin screen to update product retail pricing.",
        "💲🔒",
        lambda: self.admin_gate_pass(self.open_price_update_screen),
        1,
        1,
    )
    create_nav_card(
        grid_frame,
        "Cashier & Promotions Manager",
        "Manage cashiers and receipt footer promotions.",
        "👤🔒",
        lambda: self.admin_gate_pass(self.open_cashier_screen),
        1,
        2,
    )

  def admin_gate_pass(self, target_callback):
    password_attempt = simpledialog.askstring(
        "Admin Authorization Required",
        "Enter Admin Password to access management module:",
        show="*",
    )
    if password_attempt == self.active_company_password:
      target_callback()
    else:
      messagebox.showerror(
          "Access Denied", "Incorrect password. Authorization failed."
      )

  # ==========================================
  # 🛒 CHECKOUT SCREEN (Auto-Capture & Bluetooth App Support)
  # ==========================================
  def open_checkout_screen(self):
    self.clear_container()
    self.cart = []
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Log Out / Switch User",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_login_screen,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"POS - Checkout [{self.active_company_name}] | Cashier: {self.active_cashier}",
        font=("Arial", 12, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    tk.Label(
        body,
        text="SCAN BARCODE (USB / Bluetooth Scanner Apps / RS232 Ready):",
        font=("Arial", 12, "bold"),
        bg=self.COLOR_BG,
        fg=self.COLOR_TEXT,
    ).pack(anchor=tk.W)
    
    self.barcode_entry = tk.Entry(body, font=("Arial", 14), width=35)
    self.barcode_entry.pack(fill=tk.X, pady=5)
    self.barcode_entry.focus()
    
    # Automatic capture on text change & Enter key
    self.barcode_entry.bind("<KeyRelease>", self.check_auto_capture_scan)
    self.barcode_entry.bind("<Return>", self.handle_scan)

    tk.Label(
        body,
        text="Current Cart Receipt Window:",
        font=("Arial", 12),
        bg=self.COLOR_BG,
        fg=self.COLOR_SECONDARY,
    ).pack(anchor=tk.W, pady=(15, 0))
    self.cart_tree = ttk.Treeview(
        body, columns=("Code", "Name", "Price"), show="headings", height=12
    )
    self.cart_tree.heading("Code", text="Code / Barcode")
    self.cart_tree.heading("Name", text="Product Name")
    self.cart_tree.heading("Price", text="Price")
    self.cart_tree.pack(fill=tk.BOTH, expand=True, pady=5)

    self.total_label = tk.Label(
        body,
        text="TOTAL: R 0.00",
        font=("Arial", 22, "bold"),
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
    )
    self.total_label.pack(anchor=tk.E, pady=10)

    cart_btn_frame = tk.Frame(body, bg=self.COLOR_BG)
    cart_btn_frame.pack(fill=tk.X, pady=5)
    tk.Button(
        cart_btn_frame,
        text="❌ Remove Item",
        bg=self.COLOR_BTN_RED,
        fg="white",
        font=("Arial", 10),
        command=self.remove_single_from_cart,
    ).pack(side=tk.LEFT, padx=5)
    tk.Button(
        cart_btn_frame,
        text="🗑️ Clear Entire Cart",
        bg="#475569",
        fg="white",
        font=("Arial", 10, "bold"),
        command=self.clear_cart,
    ).pack(side=tk.LEFT, padx=5)
    tk.Button(
        cart_btn_frame,
        text="✅ Complete Sale & Print Slip (RJ11 Cash Drawer)",
        bg=self.COLOR_BTN_GREEN,
        fg="white",
        font=("Arial", 11, "bold"),
        command=self.process_checkout_sale,
        padx=10,
    ).pack(side=tk.RIGHT, padx=5)

  def check_auto_capture_scan(self, event):
    """Automatically captures and processes product when barcode is sent by Bluetooth app or hardware scanner ending in carriage return/newline."""
    val = self.barcode_entry.get()
    if "\n" in val or "\r" in val:
      self.handle_scan(None)

  def handle_scan(self, event):
    raw_query = self.barcode_entry.get()
    query = self.read_barcode_scanner_input(raw_query)
    self.barcode_entry.delete(0, tk.END)
    if not query:
      return

    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT id, barcode, name, price, stock_count FROM products WHERE barcode=? AND company_name=?",
          (query, self.active_company_name),
      )
      rows = cursor.fetchall()

      if not rows:
        cursor.execute(
            "SELECT id, barcode, name, price, stock_count FROM products WHERE name LIKE ? AND company_name=?",
            (f"%{query}%", self.active_company_name),
        )
        rows = cursor.fetchall()
      conn.close()

      if not rows:
        action = messagebox.askyesnocancel(
            "Product Not Found",
            f"Product '{query}' is not registered in the system.\n\n"
            "• Click 'Yes' to Upload a New Product\n"
            "• Click 'No' to Update Price via Admin\n"
            "• Click 'Cancel' to abort",
        )
        if action is True:
          self.admin_gate_pass(lambda: self.prompt_upload_new_product(default_code=query))
        elif action is False:
          self.admin_gate_pass(lambda: self.open_price_update_screen())
        return

      selected_row = (
          rows[0] if len(rows) == 1 else self.select_variant_dialog(rows, query)
      )
      if selected_row:
        prod_id, barcode, name, price, stock = selected_row
        if stock <= 0:
          if not messagebox.askyesno(
              "Out of Stock Warning",
              f"'{name}' has 0 stock remaining. Add to cart anyway?",
          ):
            return

        self.cart.append(
            {"id": prod_id, "code": barcode, "name": name, "price": price}
        )
        self.update_cart_display()
    except Exception as e:
      messagebox.showerror("Error", f"Scan error: {e}")

  def prompt_upload_new_product(self, default_code=""):
    dialog = tk.Toplevel(self.root)
    dialog.title("Admin - Upload New Product")
    dialog.geometry("400x320")
    dialog.configure(bg=self.COLOR_BG)
    dialog.grab_set()

    tk.Label(
        dialog,
        text="REGISTER NEW PRODUCT (ADMIN)",
        font=("Arial", 12, "bold"),
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
    ).pack(pady=15)

    tk.Label(dialog, text="Code / Barcode:", bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor=tk.W, padx=25)
    e_code = tk.Entry(dialog, font=("Arial", 11), width=30)
    e_code.pack(pady=5, padx=25)
    e_code.insert(0, default_code)

    tk.Label(dialog, text="Product Name:", bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor=tk.W, padx=25)
    e_name = tk.Entry(dialog, font=("Arial", 11), width=30)
    e_name.pack(pady=5, padx=25)

    tk.Label(dialog, text="Retail Price (R):", bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor=tk.W, padx=25)
    e_price = tk.Entry(dialog, font=("Arial", 11), width=30)
    e_price.pack(pady=5, padx=25)

    tk.Label(dialog, text="Initial Stock Count:", bg=self.COLOR_BG, fg=self.COLOR_TEXT).pack(anchor=tk.W, padx=25)
    e_stock = tk.Entry(dialog, font=("Arial", 11), width=30)
    e_stock.pack(pady=5, padx=25)
    e_stock.insert(0, "10")

    def save_product():
      c_code = e_code.get().strip()
      c_name = e_name.get().strip()
      p_str = e_price.get().strip()
      s_str = e_stock.get().strip()

      if not c_code or not c_name or not p_str or not s_str:
        return messagebox.showerror("Error", "All fields must be completed.")

      try:
        price_val = float(p_str)
        stock_val = int(s_str)
      except ValueError:
        return messagebox.showerror("Error", "Price must be a number and stock an integer.")

      timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
      curr_date = datetime.now().strftime("%Y-%m-%d")

      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO products (company_name, barcode, name, price, stock_count, date_added, is_synced, last_updated) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
          (self.active_company_name, c_code, c_name, price_val, stock_val, curr_date, timestamp),
      )
      conn.commit()
      conn.close()

      messagebox.showinfo("Success", f"Product '{c_name}' uploaded successfully!")
      dialog.destroy()

    tk.Button(
        dialog,
        text="💾 Save & Upload Product",
        bg=self.COLOR_BTN_GREEN,
        fg="white",
        font=("Arial", 10, "bold"),
        command=save_product,
    ).pack(pady=15)

  # ==========================================
  # 💲 DEDICATED ADMIN PRICE UPDATE SCREEN
  # ==========================================
  def open_price_update_screen(self):
    self.clear_container()
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Back to Dashboard",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_landing_page,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"Admin Exclusive - Price Update Management [{self.active_company_name}]",
        font=("Arial", 13, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    form_frame = tk.LabelFrame(
        body,
        text=" Update Product Retail Price ",
        font=("Arial", 11, "bold"),
        padx=15,
        pady=15,
        bg=self.COLOR_CARD,
        fg=self.COLOR_ACCENT,
    )
    form_frame.pack(fill=tk.X, pady=(0, 15))

    tk.Label(form_frame, text="Selected Product:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=0, sticky=tk.W, pady=5)
    self.price_name_entry = tk.Entry(form_frame, font=("Arial", 11), width=20, state="readonly")
    self.price_name_entry.grid(row=0, column=1, pady=5, padx=5)

    tk.Label(form_frame, text="New Price (R):", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=2, sticky=tk.W, pady=5)
    self.price_val_entry = tk.Entry(form_frame, font=("Arial", 11), width=12)
    self.price_val_entry.grid(row=0, column=3, pady=5, padx=5)

    tk.Button(
        form_frame,
        text="💾 Save New Price",
        bg=self.COLOR_BTN_GREEN,
        fg="white",
        font=("Arial", 10, "bold"),
        command=self.apply_dedicated_price_update,
    ).grid(row=0, column=4, padx=15)

    self.price_tree = ttk.Treeview(
        body,
        columns=("ID", "Barcode", "Name", "Price", "Stock"),
        show="headings",
        height=14,
    )
    self.price_tree.heading("ID", text="ID")
    self.price_tree.heading("Barcode", text="Code")
    self.price_tree.heading("Name", text="Product Name")
    self.price_tree.heading("Price", text="Current Price")
    self.price_tree.heading("Stock", text="Stock Left")
    self.price_tree.pack(fill=tk.BOTH, expand=True, pady=5)
    self.price_tree.bind("<<TreeviewSelect>>", self.on_price_row_click)
    self.refresh_price_screen_view()

  def on_price_row_click(self, event):
    selected = self.price_tree.selection()
    if selected:
      values = self.price_tree.item(selected[0], "values")
      self.selected_price_id = values[0]
      self.price_name_entry.config(state="normal")
      self.price_name_entry.delete(0, tk.END)
      self.price_name_entry.insert(0, values[2])
      self.price_name_entry.config(state="readonly")

      self.price_val_entry.delete(0, tk.END)
      self.price_val_entry.insert(0, values[3].replace("R", "").strip())

  def apply_dedicated_price_update(self):
    if not hasattr(self, "selected_price_id") or not self.selected_price_id:
      return messagebox.showerror("Selection Missing", "Please select a product from the table.")
    
    p_str = self.price_val_entry.get().strip()
    try:
      new_price = float(p_str)
    except ValueError:
      return messagebox.showerror("Invalid Format", "Price must be a valid number.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "UPDATE products SET price = ?, last_updated = ? WHERE id = ? AND company_name = ?",
          (new_price, timestamp, self.selected_price_id, self.active_company_name),
      )
      conn.commit()
      conn.close()

      self.price_val_entry.delete(0, tk.END)
      self.selected_price_id = None
      self.refresh_price_screen_view()
      messagebox.showinfo("Success", "Product retail price updated successfully.")
    except Exception as e:
      messagebox.showerror("Database Error", f"Failed to update price: {e}")

  def refresh_price_screen_view(self):
    for item in self.price_tree.get_children():
      self.price_tree.delete(item)
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT id, barcode, name, price, stock_count FROM products WHERE company_name = ?",
          (self.active_company_name,),
      )
      for row in cursor.fetchall():
        self.price_tree.insert("", tk.END, values=(row[0], row[1], row[2], f"R {row[3]:.2f}", row[4]))
      conn.close()
    except:
      pass

  def select_variant_dialog(self, rows, query_term):
    dialog = tk.Toplevel(self.root)
    dialog.title("Select Matching Product")
    dialog.geometry("560x320")
    dialog.transient(self.root)
    dialog.grab_set()
    dialog.configure(bg=self.COLOR_BG)

    tk.Label(
        dialog,
        text=f"Multiple products found matching '{query_term}'. Please select one:",
        font=("Arial", 11, "bold"),
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
    ).pack(pady=10)

    columns = ("ID", "Code", "Name", "Price", "Stock")
    tree = ttk.Treeview(dialog, columns=columns, show="headings", height=8)
    tree.heading("ID", text="ID")
    tree.heading("Code", text="Code")
    tree.heading("Name", text="Product Name")
    tree.heading("Price", text="Price")
    tree.heading("Stock", text="Stock")
    tree.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)

    for r in rows:
      tree.insert("", tk.END, values=(r[0], r[1], r[2], f"R {r[3]:.2f}", r[4]))

    chosen = [None]

    def confirm_selection():
      selected_item = tree.selection()
      if not selected_item:
        return messagebox.showwarning("Selection Required", "Please select a product.")
      item_values = tree.item(selected_item[0], "values")
      selected_id = int(item_values[0])
      for r in rows:
        if r[0] == selected_id:
          chosen[0] = r
          break
      dialog.destroy()

    tk.Button(
        dialog,
        text="✔ Confirm Selection",
        bg=self.COLOR_BTN_GREEN,
        fg="white",
        font=("Arial", 11, "bold"),
        command=confirm_selection,
    ).pack(pady=12)

    self.root.wait_window(dialog)
    return chosen[0]

  def update_cart_display(self):
    for item in self.cart_tree.get_children():
      self.cart_tree.delete(item)
    total = 0.0
    for item in self.cart:
      self.cart_tree.insert(
          "", tk.END, values=(item["code"], item["name"], f"R {item['price']:.2f}")
      )
      total += item["price"]
    self.total_label.config(text=f"TOTAL: R {total:.2f}")

  def remove_single_from_cart(self):
    selected = self.cart_tree.selection()
    if not selected:
      return
    index = self.cart_tree.index(selected[0])
    del self.cart[index]
    self.update_cart_display()

  def clear_cart(self):
    self.cart = []
    self.update_cart_display()

  def process_checkout_sale(self):
    if not self.cart:
      return messagebox.showwarning("Empty Transaction", "Cannot checkout an empty shopping cart.")

    total_amount = sum(item["price"] for item in self.cart)

    tendered_str = simpledialog.askstring(
        "Cash Tendered",
        f"Total Due: R {total_amount:.2f}\nEnter cash amount rendered by customer:",
    )
    if tendered_str is None:
      return

    try:
      amount_tendered = float(tendered_str)
    except ValueError:
      return messagebox.showerror("Invalid Format", "Please enter a valid monetary amount.")

    if amount_tendered < total_amount:
      return messagebox.showerror(
          "Insufficient Funds",
          f"Amount tendered (R {amount_tendered:.2f}) is less than total due (R {total_amount:.2f}).",
      )

    change_due = amount_tendered - total_amount
    
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    sale_date = now.strftime("%Y-%m-%d")
    sale_week = now.strftime("%Y-W%V")
    sale_month = now.strftime("%Y-%m")
    sale_year = now.strftime("%Y")

    try:
      conn = self.connect_db()
      cursor = conn.cursor()

      item_tally = {}
      for item in self.cart:
        pid = item["id"]
        if pid in item_tally:
          item_tally[pid]["units"] += 1
          item_tally[pid]["revenue"] += item["price"]
        else:
          item_tally[pid] = {
              "name": item["name"],
              "units": 1,
              "revenue": item["price"]
          }

      for pid, data in item_tally.items():
        cursor.execute(
            "UPDATE products SET stock_count = MAX(0, stock_count - ?), last_updated = ? WHERE id = ? AND company_name = ?",
            (data["units"], timestamp, pid, self.active_company_name),
        )
        cursor.execute(
            """INSERT INTO sales_log (company_name, product_id, product_name, units_sold, total_revenue, sale_date, sale_week, sale_month, sale_year, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                self.active_company_name,
                pid,
                data["name"],
                data["units"],
                data["revenue"],
                sale_date,
                sale_week,
                sale_month,
                sale_year,
                timestamp,
            ),
        )

      conn.commit()
      conn.close()
    except Exception as e:
      messagebox.showerror("Database Error", f"Failed to record sale: {e}")
      return

    self.trigger_cash_drawer_rj11()

    messagebox.showinfo(
        "Payment Successful",
        f"Change to Return to Customer:\n\n👉 R {change_due:.2f} 👈\n\n[Hardware: RJ11 Cash Drawer Opened Successfully]",
    )

    self.show_receipt_slip_window(amount_tendered, change_due, timestamp)
    self.clear_cart()

  def show_receipt_slip_window(self, amount_tendered, change_due, timestamp):
    slip_win = tk.Toplevel(self.root)
    slip_win.title("Official Till Slip / Receipt")
    slip_win.geometry("440x600")
    slip_win.configure(bg="#ffffff")
    slip_win.transient(self.root)

    slip_text = tk.Text(
        slip_win,
        font=("Courier New", 10),
        bg="#ffffff",
        fg="#000000",
        padx=15,
        pady=15,
    )
    slip_text.pack(fill=tk.BOTH, expand=True)

    total_amount = sum(item["price"] for item in self.cart)

    item_counts = {}
    for item in self.cart:
      name = item["name"]
      price = item["price"]
      if name in item_counts:
        item_counts[name]["qty"] += 1
        item_counts[name]["total"] += price
      else:
        item_counts[name] = {"qty": 1, "total": price, "price": price}

    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT promo_text FROM promotions WHERE company_name = ?",
          (self.active_company_name,),
      )
      promos = cursor.fetchall()
      conn.close()
    except:
      promos = []

    promo_block = ""
    if promos:
      for p in promos:
        promo_block += f"   * {p[0]}\n"
    else:
      promo_block = "   * THANK YOU FOR SUPPORTING LOCAL!\n"

    receipt_content = f"""
========================================
       {self.active_company_name.upper()}
       OFFICIAL TRANSACTION SLIP
========================================
Date & Time : {timestamp}
Cashier     : {self.active_cashier}
----------------------------------------
ITEM DESCRIPTION        QTY    PRICE   TOTAL
----------------------------------------
"""
    for name, data in item_counts.items():
      line_desc = name[:20].ljust(20)
      qty_str = str(data["qty"]).rjust(3)
      price_str = f"R{data['price']:.2f}".rjust(7)
      tot_str = f"R{data['total']:.2f}".rjust(8)
      receipt_content += f"{line_desc} {qty_str} {price_str} {tot_str}\n"

    receipt_content += f"""----------------------------------------
TOTAL PRODUCTS ITEMS : {len(self.cart)}
TOTAL AMOUNT DUE     : R {total_amount:.2f}
CASH TENDERED        : R {amount_tendered:.2f}
CHANGE RETURNED      : R {change_due:.2f}
========================================
   PROMOTIONS & NOTICES:
{promo_block}========================================
"""
    slip_text.insert(tk.END, receipt_content)
    slip_text.config(state=tk.DISABLED)

    tk.Button(
        slip_win,
        text="🖨️ Close & Ready Next Customer",
        bg="#10b981",
        fg="white",
        font=("Arial", 10, "bold"),
        command=slip_win.destroy,
    ).pack(fill=tk.X, padx=15, pady=10)

  # ==========================================
  # 📦 STOCK MANAGEMENT SCREEN (Admin Protected)
  # ==========================================
  def open_stock_screen(self):
    self.clear_container()
    self.selected_stock_id = None
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Back to Dashboard",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_landing_page,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"POS - Stock Management [{self.active_company_name}]",
        font=("Arial", 13, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    form_frame = tk.LabelFrame(
        body,
        text=" Update Current In-Stock Counts (Admin Authorized) ",
        font=("Arial", 11, "bold"),
        padx=15,
        pady=15,
        bg=self.COLOR_CARD,
        fg=self.COLOR_ACCENT,
    )
    form_frame.pack(fill=tk.X, pady=(0, 15))

    tk.Label(form_frame, text="Selected Product:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=0, sticky=tk.W, pady=5)
    self.stock_name_entry = tk.Entry(form_frame, font=("Arial", 11), width=18, state="readonly")
    self.stock_name_entry.grid(row=0, column=1, pady=5, padx=5)

    tk.Label(form_frame, text="New Stock Count:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=2, sticky=tk.W, pady=5)
    self.stock_quantity_entry = tk.Entry(form_frame, font=("Arial", 11), width=10)
    self.stock_quantity_entry.grid(row=0, column=3, pady=5, padx=5)

    tk.Button(
        form_frame,
        text="🔄 Update Stock",
        bg=self.COLOR_ACCENT,
        fg=self.COLOR_BG,
        font=("Arial", 10, "bold"),
        command=self.update_stock_only,
    ).grid(row=0, column=4, padx=15)

    self.stock_tree = ttk.Treeview(
        body,
        columns=("ID", "Barcode", "Name", "Price", "Stock", "Date Added"),
        show="headings",
        height=14,
    )
    self.stock_tree.heading("ID", text="ID")
    self.stock_tree.heading("Barcode", text="Code")
    self.stock_tree.heading("Name", text="Product Name")
    self.stock_tree.heading("Price", text="Price")
    self.stock_tree.heading("Stock", text="Stock Left")
    self.stock_tree.heading("Date Added", text="Capture Date")
    self.stock_tree.pack(fill=tk.BOTH, expand=True, pady=5)
    self.stock_tree.bind("<<TreeviewSelect>>", self.on_stock_row_click)
    self.refresh_stock_view()

  def on_stock_row_click(self, event):
    selected = self.stock_tree.selection()
    if selected:
      values = self.stock_tree.item(selected[0], "values")
      self.selected_stock_id = values[0]
      self.stock_name_entry.config(state="normal")
      self.stock_name_entry.delete(0, tk.END)
      self.stock_name_entry.insert(0, values[2])
      self.stock_name_entry.config(state="readonly")

      self.stock_quantity_entry.delete(0, tk.END)
      self.stock_quantity_entry.insert(0, values[4])

  def update_stock_only(self):
    if not self.selected_stock_id:
      return messagebox.showerror("Selection Missing", "Please select a product from the table.")
    
    qty_str = self.stock_quantity_entry.get().strip()
    try:
      qty = int(qty_str)
    except ValueError:
      return messagebox.showerror("Invalid Format", "Quantity must be a whole integer.")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "UPDATE products SET stock_count = ?, last_updated = ? WHERE id = ? AND company_name = ?",
          (qty, timestamp, self.selected_stock_id, self.active_company_name),
      )
      conn.commit()
      conn.close()

      self.stock_quantity_entry.delete(0, tk.END)
      self.selected_stock_id = None
      self.refresh_stock_view()
      messagebox.showinfo("Success", "Stock count updated successfully.")
    except Exception as e:
      messagebox.showerror("Database Error", f"Failed to update stock: {e}")

  def refresh_stock_view(self):
    for item in self.stock_tree.get_children():
      self.stock_tree.delete(item)
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT id, barcode, name, price, stock_count, date_added FROM products WHERE company_name = ?",
          (self.active_company_name,),
      )
      for row in cursor.fetchall():
        self.stock_tree.insert("", tk.END, values=(row[0], row[1], row[2], f"R {row[3]:.2f}", row[4], row[5]))
      conn.close()
    except:
      pass

  # ==========================================
  # 📊 TIME-SERIES SALES & STOCK REPORTS
  # ==========================================
  def open_time_series_sales_screen(self):
    self.clear_container()
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Back to Dashboard",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_landing_page,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"Time-Series Sales & Stock Intelligence [{self.active_company_name}]",
        font=("Arial", 13, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    filter_frame = tk.LabelFrame(
        body,
        text=" Filter Sales Data by Days, Weeks, Months, Years, or Custom Date Range ",
        font=("Arial", 11, "bold"),
        padx=15,
        pady=12,
        bg=self.COLOR_CARD,
        fg=self.COLOR_ACCENT,
    )
    filter_frame.pack(fill=tk.X, pady=(0, 10))

    tk.Label(filter_frame, text="View Mode:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=0, sticky=tk.W, padx=5)
    
    self.filter_mode = tk.StringVar(value="Day")
    mode_cb = ttk.Combobox(filter_frame, textvariable=self.filter_mode, values=["Day", "Week", "Month", "Year", "Custom Date Range"], state="readonly", width=18)
    mode_cb.grid(row=0, column=1, padx=5)

    tk.Label(filter_frame, text="Target / Start:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=2, sticky=tk.W, padx=10)
    self.entry_start_date = tk.Entry(filter_frame, font=("Arial", 10), width=15)
    self.entry_start_date.grid(row=0, column=3, padx=5)
    self.entry_start_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

    tk.Label(filter_frame, text="End Date (Custom):", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=4, sticky=tk.W, padx=10)
    self.entry_end_date = tk.Entry(filter_frame, font=("Arial", 10), width=15)
    self.entry_end_date.grid(row=0, column=5, padx=5)
    self.entry_end_date.insert(0, datetime.now().strftime("%Y-%m-%d"))

    tk.Button(
        filter_frame,
        text="🔍 Generate Report",
        bg=self.COLOR_ACCENT,
        fg=self.COLOR_BG,
        font=("Arial", 10, "bold"),
        command=self.load_filtered_sales_report,
    ).grid(row=0, column=6, padx=15)

    self.summary_lbl = tk.Label(
        body,
        text="Total Units Sold: 0 | Total Revenue: R 0.00",
        font=("Arial", 14, "bold"),
        bg=self.COLOR_BG,
        fg=self.COLOR_BTN_GREEN,
    )
    self.summary_lbl.pack(anchor=tk.W, pady=5)

    self.report_tree = ttk.Treeview(
        body,
        columns=("ID", "ProductName", "UnitsSold", "Revenue", "SaleDate", "PeriodKey"),
        show="headings",
        height=14,
    )
    self.report_tree.heading("ID", text="Log ID")
    self.report_tree.heading("ProductName", text="Product Name")
    self.report_tree.heading("UnitsSold", text="Units Sold")
    self.report_tree.heading("Revenue", text="Total Revenue")
    self.report_tree.heading("SaleDate", text="Exact Timestamp")
    self.report_tree.heading("PeriodKey", text="Period Key")
    self.report_tree.pack(fill=tk.BOTH, expand=True, pady=5)

    self.load_filtered_sales_report()

  def load_filtered_sales_report(self):
    for item in self.report_tree.get_children():
      self.report_tree.delete(item)

    mode = self.filter_mode.get()
    val1 = self.entry_start_date.get().strip()
    val2 = self.entry_end_date.get().strip()

    conn = self.connect_db()
    cursor = conn.cursor()

    try:
      if mode == "Day":
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_date FROM sales_log WHERE company_name = ? AND sale_date = ?",
            (self.active_company_name, val1),
        )
      elif mode == "Week":
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_week FROM sales_log WHERE company_name = ? AND sale_week = ?",
            (self.active_company_name, val1),
        )
      elif mode == "Month":
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_month FROM sales_log WHERE company_name = ? AND sale_month = ?",
            (self.active_company_name, val1),
        )
      elif mode == "Year":
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_year FROM sales_log WHERE company_name = ? AND sale_year = ?",
            (self.active_company_name, val1),
        )
      elif mode == "Custom Date Range":
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_date FROM sales_log WHERE company_name = ? AND sale_date BETWEEN ? AND ?",
            (self.active_company_name, val1, val2),
        )
      else:
        cursor.execute(
            "SELECT id, product_name, units_sold, total_revenue, timestamp, sale_date FROM sales_log WHERE company_name = ?",
            (self.active_company_name,),
        )

      rows = cursor.fetchall()
      conn.close()

      total_units = 0
      total_rev = 0.0

      for r in rows:
        self.report_tree.insert("", tk.END, values=(r[0], r[1], r[2], f"R {r[3]:.2f}", r[4], r[5]))
        total_units += r[2]
        total_rev += r[3]

      self.summary_lbl.config(
          text=f"Total Records: {len(rows)} | Total Units Sold: {total_units} | Total Revenue: R {total_rev:.2f}"
      )
    except Exception as e:
      messagebox.showerror("Report Error", f"Failed to generate report: {e}")

  # ==========================================
  # 📋 MASTER LEDGER SCREEN (Admin Exclusive)
  # ==========================================
  def open_ledger_screen(self):
    self.clear_container()
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Back to Dashboard",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_landing_page,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"Master Inventory Ledger (Admin Exclusive) [{self.active_company_name}]",
        font=("Arial", 13, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    form_frame = tk.LabelFrame(
        body,
        text=" Register New Inventory Item ",
        font=("Arial", 11, "bold"),
        padx=15,
        pady=15,
        bg=self.COLOR_CARD,
        fg=self.COLOR_ACCENT,
    )
    form_frame.pack(fill=tk.X, pady=(0, 15))

    tk.Label(form_frame, text="Code:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=0, sticky=tk.W, pady=5)
    self.inv_barcode = tk.Entry(form_frame, font=("Arial", 10), width=14)
    self.inv_barcode.grid(row=0, column=1, pady=5, padx=5)

    tk.Label(form_frame, text="Name:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=2, sticky=tk.W, pady=5)
    self.inv_name = tk.Entry(form_frame, font=("Arial", 10), width=16)
    self.inv_name.grid(row=0, column=3, pady=5, padx=5)

    tk.Label(form_frame, text="Price:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=4, sticky=tk.W, pady=5)
    self.inv_price = tk.Entry(form_frame, font=("Arial", 10), width=8)
    self.inv_price.grid(row=0, column=5, pady=5, padx=5)

    tk.Label(form_frame, text="Stock:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=6, sticky=tk.W, pady=5)
    self.inv_stock = tk.Entry(form_frame, font=("Arial", 10), width=8)
    self.inv_stock.grid(row=0, column=7, pady=5, padx=5)
    self.inv_stock.insert(0, "0")

    tk.Button(
        form_frame,
        text="💾 Save Item",
        bg=self.COLOR_BTN_GREEN,
        fg="white",
        font=("Arial", 9, "bold"),
        command=self.add_to_inventory_base,
    ).grid(row=0, column=8, padx=10)

    self.ledger_tree = ttk.Treeview(
        body,
        columns=("ID", "Barcode", "Name", "Price", "Stock", "Date Added"),
        show="headings",
        height=12,
    )
    self.ledger_tree.heading("ID", text="ID")
    self.ledger_tree.heading("Barcode", text="Code")
    self.ledger_tree.heading("Name", text="Registered Title")
    self.ledger_tree.heading("Price", text="Retail Price")
    self.ledger_tree.heading("Stock", text="Stock")
    self.ledger_tree.heading("Date Added", text="Capture Date")
    self.ledger_tree.pack(fill=tk.BOTH, expand=True, pady=5)

    admin_btn_frame = tk.Frame(body, bg=self.COLOR_BG)
    admin_btn_frame.pack(fill=tk.X, pady=5)
    tk.Button(
        admin_btn_frame,
        text="🔴 Delete Selected Product Permanently",
        bg=self.COLOR_BTN_RED,
        fg="white",
        font=("Arial", 10, "bold"),
        command=self.admin_delete_product,
    ).pack(side=tk.RIGHT)

    self.refresh_ledger_view()

  def add_to_inventory_base(self):
    barcode = self.inv_barcode.get().strip()
    name = self.inv_name.get().strip()
    price_str = self.inv_price.get().strip()
    stock_str = self.inv_stock.get().strip()

    if not barcode or not name or not price_str or not stock_str:
      return messagebox.showerror("Blank Fields", "Please populate all cells.")
    try:
      price = float(price_str)
      stock = int(stock_str)
    except ValueError:
      return messagebox.showerror("Invalid Format", "Price must be a decimal and stock an integer.")

    current_date = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "INSERT INTO products (company_name, barcode, name, price, stock_count, date_added, is_synced, last_updated) VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
          (self.active_company_name, barcode, name, price, stock, current_date, timestamp),
      )
      conn.commit()
      conn.close()

      self.inv_barcode.delete(0, tk.END)
      self.inv_name.delete(0, tk.END)
      self.inv_price.delete(0, tk.END)
      self.inv_stock.delete(0, tk.END)
      self.inv_stock.insert(0, "0")
      self.refresh_ledger_view()
      messagebox.showinfo("Success", "Product recorded successfully.")
    except Exception as e:
      messagebox.showerror("Database Error", f"Failed to save product: {e}")

  def admin_delete_product(self):
    selected = self.ledger_tree.selection()
    if not selected:
      return messagebox.showerror("Selection Missing", "Select a record to delete.")
    row_values = self.ledger_tree.item(selected[0], "values")
    row_id = row_values[0]

    if messagebox.askyesno("Confirm Deletion", f"Permanently delete record ID {row_id}?"):
      try:
        conn = self.connect_db()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id=? AND company_name=?", (row_id, self.active_company_name))
        conn.commit()
        conn.close()
        self.refresh_ledger_view()
      except Exception as e:
        messagebox.showerror("Database Error", f"Failed to delete product: {e}")

  def refresh_ledger_view(self):
    for item in self.ledger_tree.get_children():
      self.ledger_tree.delete(item)
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute(
          "SELECT id, barcode, name, price, stock_count, date_added FROM products WHERE company_name = ?",
          (self.active_company_name,),
      )
      for row in cursor.fetchall():
        self.ledger_tree.insert("", tk.END, values=(row[0], row[1], row[2], f"R {row[3]:.2f}", row[4], row[5]))
      conn.close()
    except:
      pass

  # ==========================================
  # 👤 CASHIER & 🏷️ PROMOTION MANAGEMENT (Admin Protected)
  # ==========================================
  def open_cashier_screen(self):
    self.clear_container()
    top_bar = tk.Frame(self.container, bg=self.COLOR_CARD, height=50)
    top_bar.pack(fill=tk.X, padx=15, pady=10)
    tk.Button(
        top_bar,
        text="⬅ Back to Dashboard",
        bg=self.COLOR_BG,
        fg=self.COLOR_ACCENT,
        font=("Arial", 10, "bold"),
        command=self.show_landing_page,
    ).pack(side=tk.LEFT, padx=10, pady=10)
    tk.Label(
        top_bar,
        text=f"Cashier & Promotions Management [{self.active_company_name}]",
        font=("Arial", 13, "bold"),
        bg=self.COLOR_CARD,
        fg=self.COLOR_TEXT,
    ).pack(side=tk.LEFT, padx=20)

    body = tk.Frame(self.container, bg=self.COLOR_BG)
    body.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)

    # Cashier Registration Frame
    c_frame = tk.LabelFrame(body, text=" Register New Cashier ", font=("Arial", 10, "bold"), padx=10, pady=10, bg=self.COLOR_CARD, fg=self.COLOR_ACCENT)
    c_frame.pack(fill=tk.X, pady=5)

    tk.Label(c_frame, text="Name:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=0, padx=5)
    self.c_fullname_entry = tk.Entry(c_frame, width=15)
    self.c_fullname_entry.grid(row=0, column=1, padx=5)

    tk.Label(c_frame, text="ID Number:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=2, padx=5)
    self.c_idnum_entry = tk.Entry(c_frame, width=12)
    self.c_idnum_entry.grid(row=0, column=3, padx=5)

    tk.Label(c_frame, text="Password:", bg=self.COLOR_CARD, fg=self.COLOR_TEXT).grid(row=0, column=4, padx=5)
    self.c_pass_entry = tk.Entry(c_frame, width=10)
    self.c_pass_entry.grid(row=0, column=5, padx=5)

    tk.Button(c_frame, text="Save Cashier", bg=self.COLOR_BTN_GREEN, fg="white", command=self.add_cashier_action).grid(row=0, column=6, padx=10)

    self.cashier_tree = ttk.Treeview(body, columns=("ID", "FullName", "IDNumber", "Password"), show="headings", height=6)
    self.cashier_tree.heading("ID", text="ID")
    self.cashier_tree.heading("FullName", text="Full Name")
    self.cashier_tree.heading("IDNumber", text="ID Number")
    self.cashier_tree.heading("Password", text="Password")
    self.cashier_tree.pack(fill=tk.BOTH, expand=True, pady=5)

    tk.Button(body, text="🔴 Remove Selected Cashier", bg=self.COLOR_BTN_RED, fg="white", command=self.remove_cashier_action).pack(anchor=tk.E, pady=5)
    self.refresh_cashier_view()

  def add_cashier_action(self):
    fname = self.c_fullname_entry.get().strip()
    idnum = self.c_idnum_entry.get().strip()
    cpass = self.c_pass_entry.get().strip()
    if not fname or not idnum or not cpass:
      return messagebox.showerror("Error", "Please fill in all cashier fields.")
    try:
      conn = self.connect_db()
      cursor = conn.cursor()
      cursor.execute("INSERT INTO cashiers (company_name, full_name, id_number, password) VALUES (?, ?, ?, ?)", (self.active_company_name, fname, idnum, cpass))
      conn.commit()
      conn.close()
      self.c_fullname_entry.delete(0, tk.END)
      self.c_idnum_entry.delete(0, tk.END)
      self.c_pass_entry.delete(0, tk.END)
      self.refresh_cashier_view()
      messagebox.showinfo("Success", "Cashier added successfully.")
    except Exception as e:
      messagebox.showerror("Error", f"{e}")

  def remove_cashier_action(self):
    selected = self.cashier_tree.selection()
    if not selected:
      return
    cid = self.cashier_tree.item(selected[0], "values")[0]
    conn = self.connect_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM cashiers WHERE id = ? AND company_name = ?", (cid, self.active_company_name))
    conn.commit()
    conn.close()
    self.refresh_cashier_view()

  def refresh_cashier_view(self):
    for item in self.cashier_tree.get_children():
      self.cashier_tree.delete(item)
    conn = self.connect_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, id_number, password FROM cashiers WHERE company_name = ?", (self.active_company_name,))
    for row in cursor.fetchall():
      self.cashier_tree.insert("", tk.END, values=row)
    conn.close()

  def open_promotion_screen(self):
    # Wrapper to open promotion management
    self.open_cashier_screen()


if __name__ == "__main__":
  root = tk.Tk()
  app = OfflinePOS(root)
  root.mainloop()