
import os
import io
import re
import sqlite3
import hashlib
import secrets
from datetime import datetime, date

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from dotenv import load_dotenv

# =========================================================
# 1. CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="FINORA AI | Financial Management",
    page_icon="💗",
    layout="wide",
    initial_sidebar_state="expanded"
)

load_dotenv()

DB_PATH = "finora.db"

# Optional AI providers
try:
    from google import genai
except ImportError:
    genai = None

try:
    from groq import Groq
except ImportError:
    Groq = None


def get_secret(name):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name)


GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
GROQ_API_KEY = get_secret("GROQ_API_KEY")


# =========================================================
# 2. PINK PROFESSIONAL THEME
# =========================================================

st.markdown("""
<style>
    .stApp {
        background: #fff9fc;
        color: #493542;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg,#f6d9e7,#fff0f6);
        border-right: 1px solid #edc4d8;
    }

    [data-testid="stSidebar"] * {
        color: #654357;
    }

    h1,h2,h3 {
        color: #91456d !important;
        font-weight: 700;
    }

    [data-testid="stMetric"] {
        background: white;
        border: 1px solid #f0d1e0;
        padding: 17px;
        border-radius: 14px;
        box-shadow: 0 3px 12px rgba(140,65,105,.06);
    }

    [data-testid="stMetricValue"] {
        color: #a34275;
    }

    [data-testid="stMetricLabel"] {
        color: #86647a;
    }

    .stButton > button {
        background: #bd5c8c;
        color: white;
        border: none;
        border-radius: 9px;
        font-weight: 600;
    }

    .stButton > button:hover {
        background: #963f6b;
        color: white;
    }

    [data-testid="stFileUploader"] {
        background: white;
        border: 1px dashed #d995b5;
        border-radius: 12px;
        padding: 12px;
    }

    [data-testid="stDataFrame"] {
        border: 1px solid #efd2e0;
        border-radius: 10px;
    }

    .finora-header {
        background: linear-gradient(110deg,#f3c5d9,#fcebf3);
        border: 1px solid #ecc6d9;
        padding: 25px;
        border-radius: 16px;
        margin-bottom: 20px;
    }

    .finora-header h2 {
        color: #813657 !important;
        margin: 0;
    }

    .finora-header p {
        color: #765166;
        margin-bottom: 0;
    }

    .small-note {
        color: #896d7e;
        font-size: 12px;
    }

    div[data-baseweb="tab-list"] {
        gap: 8px;
    }
</style>
""", unsafe_allow_html=True)


# =========================================================
# 3. DATABASE
# =========================================================

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = db()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        full_name TEXT,
        role TEXT NOT NULL,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_date TEXT,
        transaction_type TEXT,
        category TEXT,
        description TEXT,
        amount REAL,
        created_by TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        account_name TEXT,
        account_type TEXT
    );

    CREATE TABLE IF NOT EXISTS journal_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_number TEXT,
        journal_date TEXT,
        description TEXT,
        account_code TEXT,
        account_name TEXT,
        debit REAL DEFAULT 0,
        credit REAL DEFAULT 0,
        created_by TEXT,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS budgets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT,
        category TEXT,
        budget_amount REAL,
        created_by TEXT
    );

    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT,
        document_type TEXT,
        description TEXT,
        uploaded_by TEXT,
        uploaded_at TEXT
    );

    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        activity TEXT,
        created_at TEXT
    );
    """)

    # Default Chart of Accounts
    defaults = [
        ("1001", "Kas", "Aset"),
        ("1002", "Bank", "Aset"),
        ("1101", "Piutang", "Aset"),
        ("1201", "Peralatan", "Aset"),
        ("2001", "Utang", "Liabilitas"),
        ("3001", "Modal", "Ekuitas"),
        ("4001", "Pendapatan", "Pendapatan"),
        ("5001", "Beban Operasional", "Beban"),
        ("5002", "Beban Administrasi", "Beban"),
    ]

    for item in defaults:
        cur.execute("""
            INSERT OR IGNORE INTO accounts
            (code, account_name, account_type)
            VALUES (?, ?, ?)
        """, item)

    conn.commit()
    conn.close()


init_db()


def query_df(sql, params=()):
    conn = db()
    result = pd.read_sql_query(sql, conn, params=params)
    conn.close()
    return result


def execute(sql, params=()):
    conn = db()
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def log_activity(activity):
    execute("""
        INSERT INTO audit_logs (username, activity, created_at)
        VALUES (?, ?, ?)
    """, (
        st.session_state.get("username", "system"),
        activity,
        datetime.now().isoformat(timespec="seconds")
    ))


def money(value):
    try:
        return "Rp " + f"{float(value):,.0f}".replace(",", ".")
    except Exception:
        return "Rp 0"


# =========================================================
# 4. AUTHENTICATION
# =========================================================

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        200000
    ).hex()
    return f"{salt}${hashed}"


def verify_password(password, stored):
    try:
        salt, old_hash = stored.split("$")
        return secrets.compare_digest(
            hash_password(password, salt).split("$")[1],
            old_hash
        )
    except Exception:
        return False


def user_count():
    return query_df("SELECT COUNT(*) AS total FROM users").iloc[0]["total"]


def login_screen():
    st.markdown("""
    <div class="finora-header">
        <h2>💗 FINORA AI</h2>
        <p>Smart Financial Management, Accounting & Audit System</p>
    </div>
    """, unsafe_allow_html=True)

    if user_count() == 0:
        st.subheader("Buat Akun Administrator Pertama")

        with st.form("first_admin"):
            name = st.text_input("Nama lengkap")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            confirm = st.text_input("Konfirmasi password", type="password")
            submit = st.form_submit_button("Buat Administrator")

            if submit:
                if not name or not username or not password:
                    st.error("Semua kolom wajib diisi.")
                elif password != confirm:
                    st.error("Konfirmasi password tidak sama.")
                elif len(password) < 8:
                    st.error("Password minimal 8 karakter.")
                else:
                    execute("""
                        INSERT INTO users
                        (username,password,full_name,role,created_at)
                        VALUES (?,?,?,?,?)
                    """, (
                        username.strip(),
                        hash_password(password),
                        name.strip(),
                        "Admin",
                        datetime.now().isoformat()
                    ))
                    st.success("Administrator berhasil dibuat. Silakan login.")
                    st.rerun()
        return

    login_tab, info_tab = st.tabs(["Login", "Informasi"])

    with login_tab:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submit = st.form_submit_button("Masuk ke FINORA AI")

            if submit:
                users = query_df(
                    "SELECT * FROM users WHERE username=?",
                    (username.strip(),)
                )

                if (
                    not users.empty
                    and verify_password(password, users.iloc[0]["password"])
                ):
                    user = users.iloc[0]
                    st.session_state.authenticated = True
                    st.session_state.username = user["username"]
                    st.session_state.full_name = user["full_name"]
                    st.session_state.role = user["role"]
                    log_activity("Login")
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

    with info_tab:
        st.write("FINORA AI merupakan sistem pengelolaan keuangan, akuntansi, dan pemeriksaan data berbantuan AI.")
        st.write("Akun pengguna baru dibuat oleh Administrator.")


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    login_screen()
    st.stop()


# =========================================================
# 5. AI ENGINE - GEMINI AND GROQ
# =========================================================

def ask_ai(prompt, provider="Gemini", model=None):
    try:
        if provider == "Gemini":
            if not GEMINI_API_KEY or genai is None:
                return "Gemini belum tersedia. Periksa GEMINI_API_KEY dan package google-genai."

            client = genai.Client(api_key=GEMINI_API_KEY)
            model = model or "gemini-2.5-flash"

            response = client.models.generate_content(
                model=model,
                contents=prompt
            )

            return response.text or "AI tidak memberikan jawaban."

        if provider == "Groq":
            if not GROQ_API_KEY or Groq is None:
                return "Groq belum tersedia. Periksa GROQ_API_KEY dan package groq."

            client = Groq(api_key=GROQ_API_KEY)
            model = model or "llama-3.3-70b-versatile"

            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "Kamu adalah FINORA AI, asisten keuangan dan audit profesional. Gunakan bahasa Indonesia."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            return response.choices[0].message.content

    except Exception as error:
        return f"AI Error: {error}"

    return "Provider AI tidak dikenali."


def ai_controls(key="ai"):
    provider = st.selectbox(
        "AI Provider",
        ["Gemini", "Groq"],
        key=f"{key}_provider"
    )

    if provider == "Gemini":
        model = st.selectbox(
            "Model Gemini",
            ["gemini-2.5-flash"],
            key=f"{key}_model"
        )
    else:
        model = st.selectbox(
            "Model Groq",
            [
                "llama-3.1-8b-instant",
                "llama-3.3-70b-versatile",
                "openai/gpt-oss-120b"
            ],
            key=f"{key}_model"
        )

    return provider, model


# =========================================================
# 6. SIDEBAR NAVIGATION
# =========================================================

st.sidebar.markdown("""
# 💗 FINORA AI
<small>Financial Intelligence System</small>
""", unsafe_allow_html=True)

st.sidebar.write(f"Pengguna: **{st.session_state.full_name}**")
st.sidebar.caption(f"Role: {st.session_state.role}")

menu_items = [
    "Dashboard",
    "Manajemen Keuangan",
    "Sistem Akuntansi",
    "Financial Copilot AI",
    "AI Audit",
    "Budgeting & Planning",
    "Dokumen & Bukti",
    "Laporan Audit",
    "Analytics & Reports"
]

if st.session_state.role == "Admin":
    menu_items.append("User Management")

page = st.sidebar.radio("MENU UTAMA", menu_items)

if st.sidebar.button("Logout", use_container_width=True):
    log_activity("Logout")
    for key in [
        "authenticated", "username",
        "full_name", "role"
    ]:
        st.session_state.pop(key, None)
    st.rerun()


# =========================================================
# 7. DASHBOARD
# =========================================================

def dashboard():
    st.markdown("""
    <div class="finora-header">
        <h2>Financial Overview</h2>
        <p>Selamat datang di FINORA AI. Pantau kondisi keuangan secara terintegrasi.</p>
    </div>
    """, unsafe_allow_html=True)

    df = query_df("SELECT * FROM transactions")

    income = 0
    expense = 0

    if not df.empty:
        income = df.loc[
            df.transaction_type == "Pendapatan", "amount"
        ].sum()

        expense = df.loc[
            df.transaction_type == "Pengeluaran", "amount"
        ].sum()

    budgets = query_df("SELECT SUM(budget_amount) AS total FROM budgets")
    total_budget = budgets.iloc[0]["total"] or 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Pendapatan", money(income))
    c2.metric("Total Pengeluaran", money(expense))
    c3.metric("Saldo Bersih", money(income - expense))
    c4.metric("Total Anggaran", money(total_budget))

    st.divider()

    if df.empty:
        st.info("Belum ada transaksi. Silakan tambahkan transaksi terlebih dahulu.")
        return

    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], errors="coerce"
    )

    left, right = st.columns(2)

    with left:
        st.subheader("📈 Tren Keuangan")

        monthly = df.dropna(subset=["transaction_date"]).copy()
        monthly["Bulan"] = monthly.transaction_date.dt.to_period("M").astype(str)

        chart_data = monthly.groupby(
            ["Bulan", "transaction_type"]
        )["amount"].sum().reset_index()

        fig = px.line(
            chart_data,
            x="Bulan",
            y="amount",
            color="transaction_type",
            markers=True
        )

        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white"
        )

        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("📊 Komposisi Keuangan")

        category = df.groupby(
            "transaction_type"
        )["amount"].sum().reset_index()

        fig = px.pie(
            category,
            names="transaction_type",
            values="amount",
            hole=0.5
        )

        st.plotly_chart(fig, use_container_width=True)

    st.subheader("Transaksi Terbaru")
    st.dataframe(
        df.sort_values("transaction_date", ascending=False).head(10),
        use_container_width=True,
        hide_index=True
    )


# =========================================================
# 8. FINANCIAL MANAGEMENT
# =========================================================

def financial_management():
    st.title("💰 Manajemen Keuangan")

    tab1, tab2, tab3 = st.tabs([
        "Input Transaksi",
        "Import Excel",
        "Data Transaksi"
    ])

    with tab1:
        with st.form("transaction_form"):
            tanggal = st.date_input("Tanggal transaksi", value=date.today())

            jenis = st.selectbox(
                "Jenis transaksi",
                ["Pendapatan", "Pengeluaran"]
            )

            kategori = st.text_input("Kategori")
            deskripsi = st.text_input("Deskripsi")
            nominal = st.number_input("Nominal", min_value=0.0, step=10000.0)

            submit = st.form_submit_button("Simpan Transaksi")

            if submit:
                if not kategori or nominal <= 0:
                    st.error("Kategori dan nominal wajib diisi.")
                else:
                    execute("""
                        INSERT INTO transactions
                        (transaction_date,transaction_type,category,
                        description,amount,created_by,created_at)
                        VALUES (?,?,?,?,?,?,?)
                    """, (
                        str(tanggal), jenis, kategori, deskripsi,
                        nominal, st.session_state.username,
                        datetime.now().isoformat()
                    ))
                    log_activity("Menambahkan transaksi")
                    st.success("Transaksi berhasil disimpan.")
                    st.rerun()

    with tab2:
        st.write("Format Excel minimal: `transaction_date`, `transaction_type`, `category`, `description`, `amount`.")

        uploaded = st.file_uploader(
            "Upload Excel transaksi",
            type=["xlsx", "xls"],
            key="finance_import"
        )

        if uploaded:
            try:
                imported = pd.read_excel(uploaded)
                st.dataframe(imported.head(20), use_container_width=True)

                if st.button("Import Seluruh Data"):
                    required = [
                        "transaction_date",
                        "transaction_type",
                        "category",
                        "description",
                        "amount"
                    ]

                    if not all(c in imported.columns for c in required):
                        st.error("Kolom Excel belum sesuai format.")
                    else:
                        conn = db()
                        success = 0

                        for _, row in imported.iterrows():
                            amount = pd.to_numeric(
                                row["amount"], errors="coerce"
                            )

                            if pd.isna(amount) or amount <= 0:
                                continue

                            if row["transaction_type"] not in [
                                "Pendapatan", "Pengeluaran"
                            ]:
                                continue

                            conn.execute("""
                                INSERT INTO transactions
                                (transaction_date,transaction_type,category,
                                description,amount,created_by,created_at)
                                VALUES (?,?,?,?,?,?,?)
                            """, (
                                str(row["transaction_date"]),
                                str(row["transaction_type"]),
                                str(row["category"]),
                                str(row["description"]),
                                float(amount),
                                st.session_state.username,
                                datetime.now().isoformat()
                            ))
                            success += 1

                        conn.commit()
                        conn.close()

                        log_activity(f"Import {success} transaksi")
                        st.success(f"{success} transaksi berhasil diimpor.")
                        st.rerun()

            except Exception as error:
                st.error(str(error))

    with tab3:
        df = query_df("SELECT * FROM transactions ORDER BY transaction_date DESC")
        st.dataframe(df, use_container_width=True, hide_index=True)

        if not df.empty:
            st.download_button(
                "Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                "finora_transactions.csv",
                "text/csv"
            )


# =========================================================
# 9. ACCOUNTING SYSTEM
# =========================================================

def accounting_system():
    st.title("📚 Sistem Akuntansi")

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Daftar Akun",
        "Input Jurnal",
        "Buku Besar",
        "Neraca Saldo",
        "Laporan Laba Rugi"
    ])

    accounts = query_df("SELECT * FROM accounts ORDER BY code")

    with tab1:
        st.dataframe(accounts, use_container_width=True, hide_index=True)

        with st.form("add_account"):
            code = st.text_input("Kode akun")
            name = st.text_input("Nama akun")
            account_type = st.selectbox(
                "Jenis akun",
                ["Aset", "Liabilitas", "Ekuitas", "Pendapatan", "Beban"]
            )

            if st.form_submit_button("Tambah Akun"):
                if code and name:
                    try:
                        execute("""
                            INSERT INTO accounts
                            (code,account_name,account_type)
                            VALUES (?,?,?)
                        """, (code, name, account_type))
                        st.success("Akun berhasil ditambahkan.")
                        st.rerun()
                    except Exception as error:
                        st.error(f"Gagal menambahkan akun: {error}")

    with tab2:
        st.write("Setiap jurnal dibuat dalam dua baris: debit dan kredit.")

        if accounts.empty:
            st.warning("Daftar akun belum tersedia.")
        else:
            options = {
                f"{r['code']} - {r['account_name']}": r
                for _, r in accounts.iterrows()
            }

            with st.form("journal_form"):
                journal_date = st.date_input("Tanggal jurnal", value=date.today())
                description = st.text_input("Keterangan jurnal")
                debit_account = st.selectbox("Akun Debit", list(options.keys()))
                credit_account = st.selectbox("Akun Kredit", list(options.keys()))
                amount = st.number_input("Nominal jurnal", min_value=0.0)
                submit = st.form_submit_button("Simpan Jurnal")

                if submit:
                    if (
                        amount <= 0
                        or debit_account == credit_account
                        or not description
                    ):
                        st.error("Periksa nominal, akun, dan keterangan.")
                    else:
                        number = "JRN-" + datetime.now().strftime("%Y%m%d%H%M%S")
                        debit = options[debit_account]
                        credit = options[credit_account]

                        conn = db()

                        for account, dr, cr in [
                            (debit, amount, 0),
                            (credit, 0, amount)
                        ]:
                            conn.execute("""
                                INSERT INTO journal_entries
                                (journal_number,journal_date,description,
                                account_code,account_name,debit,credit,
                                created_by,created_at)
                                VALUES (?,?,?,?,?,?,?,?,?)
                            """, (
                                number, str(journal_date), description,
                                account["code"], account["account_name"],
                                dr, cr, st.session_state.username,
                                datetime.now().isoformat()
                            ))

                        conn.commit()
                        conn.close()

                        log_activity(f"Membuat jurnal {number}")
                        st.success("Jurnal berhasil disimpan dan seimbang.")
                        st.rerun()

    journals = query_df(
        "SELECT * FROM journal_entries ORDER BY journal_date DESC"
    )

    with tab3:
        if journals.empty:
            st.info("Belum ada jurnal.")
        else:
            st.dataframe(journals, use_container_width=True)

    with tab4:
        if journals.empty:
            st.info("Belum ada data neraca saldo.")
        else:
            trial = journals.groupby(
                ["account_code", "account_name"]
            )[["debit", "credit"]].sum().reset_index()

            trial["Saldo Debit"] = (
                trial["debit"] - trial["credit"]
            ).clip(lower=0)

            trial["Saldo Kredit"] = (
                trial["credit"] - trial["debit"]
            ).clip(lower=0)

            st.dataframe(
                trial,
                use_container_width=True,
                hide_index=True
            )

            st.metric("Total Debit", money(trial["debit"].sum()))
            st.metric("Total Kredit", money(trial["credit"].sum()))

    with tab5:
        if journals.empty:
            st.info("Belum ada data laporan laba rugi.")
        else:
            report = journals.groupby(
                "account_name"
            )[["debit", "credit"]].sum().reset_index()

            report["Saldo"] = report["credit"] - report["debit"]

            st.subheader("Pendapatan")
            st.dataframe(
                report[report["account_name"].isin(
                    accounts.loc[
                        accounts.account_type == "Pendapatan",
                        "account_name"
                    ]
                )],
                use_container_width=True
            )

            st.subheader("Beban")
            st.dataframe(
                report[report["account_name"].isin(
                    accounts.loc[
                        accounts.account_type == "Beban",
                        "account_name"
                    ]
                )],
                use_container_width=True
            )


# =========================================================
# 10. FINANCIAL COPILOT AI
# =========================================================

def financial_copilot():
    st.title("🤖 Financial Copilot AI")
    st.write("Scenario Planning, Financial Analysis & Strategic Insights")

    provider, model = ai_controls("copilot")

    uploaded = st.file_uploader(
        "Upload Excel Financial Data",
        type=["xlsx", "xls"],
        key="copilot_file"
    )

    if uploaded:
        try:
            df = pd.read_excel(uploaded)

            st.subheader("Data Preview")
            st.dataframe(df.head(100), use_container_width=True)

            if "Category" in df.columns and "Base Forecast" in df.columns:
                df["Base Forecast"] = pd.to_numeric(
                    df["Base Forecast"], errors="coerce"
                )

                df = df.dropna(subset=["Base Forecast"]).copy()

                if "Optimistic" not in df.columns:
                    df["Optimistic"] = df["Base Forecast"] * 1.15

                if "Pessimistic" not in df.columns:
                    df["Pessimistic"] = df["Base Forecast"] * 0.90

                if "Worst Case" not in df.columns:
                    df["Worst Case"] = df["Base Forecast"] * 0.75

                st.subheader("📊 Scenario Planning")
                st.dataframe(df, use_container_width=True)

                fig = px.bar(
                    df,
                    x="Category",
                    y=[
                        "Base Forecast",
                        "Optimistic",
                        "Pessimistic",
                        "Worst Case"
                    ],
                    barmode="group"
                )

                st.plotly_chart(fig, use_container_width=True)

                if st.button("Generate Financial Analysis"):
                    prompt = f"""
                    Kamu adalah FINORA Financial Copilot.
                    Analisis data berikut:

                    {df.head(100).to_string(index=False)}

                    Bahas:
                    1. Executive Summary
                    2. Revenue dan EBIT jika tersedia
                    3. OPEX, CAPEX, COGS jika tersedia
                    4. Cash Flow dan Likuiditas jika tersedia
                    5. Risiko keuangan
                    6. Skenario Optimistic, Pessimistic, Worst Case
                    7. Strategi jangka pendek dan panjang.

                    Jangan mengarang metrik yang tidak ada dalam data.
                    Jelaskan bahwa skenario adalah simulasi, bukan prediksi pasti.
                    """

                    with st.spinner("AI menganalisis data..."):
                        result = ask_ai(prompt, provider, model)

                    st.markdown(result)
            else:
                st.warning(
                    "Untuk Scenario Planning, Excel harus memiliki "
                    "kolom Category dan Base Forecast."
                )

            st.session_state.copilot_data = df

        except Exception as error:
            st.error(f"Gagal membaca Excel: {error}")

    st.divider()
    st.subheader("💬 Chat with Financial Copilot")

    if "copilot_chat" not in st.session_state:
        st.session_state.copilot_chat = []

    for item in st.session_state.copilot_chat:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])

    question = st.chat_input("Tanyakan tentang EBIT, cash flow, CAPEX, ESG, dan keuangan...")

    if question:
        st.session_state.copilot_chat.append({
            "role": "user",
            "content": question
        })

        context = ""
        if "copilot_data" in st.session_state:
            context = st.session_state.copilot_data.head(100).to_string(index=False)

        prompt = f"""
        Kamu adalah FINORA AI Financial Copilot.

        Data pengguna:
        {context}

        Pertanyaan:
        {question}

        Jawab berdasarkan data yang tersedia.
        Jika data tidak tersedia, jelaskan keterbatasannya.
        Berikan penjelasan dan rekomendasi yang relevan.
        """

        answer = ask_ai(prompt, provider, model)

        st.session_state.copilot_chat.append({
            "role": "assistant",
            "content": answer
        })

        st.rerun()

    if st.button("Reset Chat"):
        st.session_state.copilot_chat = []
        st.success("Riwayat chat dihapus.")
        st.rerun()


# =========================================================
# 11. AI AUDIT ENGINE
# =========================================================

def audit_engine(df):
    data = df.copy()
    findings = []

    def finding(category, risk, count, description, recommendation):
        findings.append({
            "Kategori": category,
            "Risiko": risk,
            "Jumlah Temuan": int(count),
            "Deskripsi": description,
            "Rekomendasi": recommendation
        })

    # Data kosong
    missing = int(data.isna().sum().sum())

    finding(
        "Data Tidak Lengkap",
        "Sedang" if missing else "Rendah",
        missing,
        f"Ditemukan {missing} sel kosong.",
        "Lengkapi data berdasarkan dokumen sumber."
    )

    # Duplicate exact rows
    duplicate_count = int(data.duplicated().sum())

    finding(
        "Duplikasi Baris",
        "Tinggi" if duplicate_count else "Rendah",
        duplicate_count,
        f"Ditemukan {duplicate_count} baris duplikat persis.",
        "Cocokkan nomor bukti, tanggal, nominal, dan penerima."
    )

    # Numeric columns
    amount_cols = []

    for col in data.columns:
        converted = pd.to_numeric(data[col], errors="coerce")

        if converted.notna().sum() > 0:
            if any(x in str(col).lower() for x in [
                "amount", "nominal", "jumlah", "debit",
                "credit", "kredit", "budget", "actual",
                "realisasi", "saldo", "nilai"
            ]):
                data[col] = converted
                amount_cols.append(col)

    # Negative values
    negative_total = 0

    for col in amount_cols:
        negative_total += int((data[col] < 0).sum())

    finding(
        "Nominal Negatif",
        "Sedang" if negative_total else "Rendah",
        negative_total,
        f"Ditemukan {negative_total} nilai negatif.",
        "Periksa retur, koreksi, pembalikan, dan kesalahan input."
    )

    # Outliers IQR
    outlier_total = 0

    for col in amount_cols:
        values = data[col].dropna()

        if len(values) < 4 or values.nunique() < 2:
            continue

        q1 = values.quantile(.25)
        q3 = values.quantile(.75)
        iqr = q3 - q1

        if iqr <= 0:
            continue

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outlier_total += int(
            ((data[col] < lower) | (data[col] > upper)).sum()
        )

    finding(
        "Nilai Ekstrem",
        "Sedang" if outlier_total else "Rendah",
        outlier_total,
        f"Ditemukan {outlier_total} nilai ekstrem berdasarkan IQR.",
        "Periksa transaksi ekstrem dengan bukti pendukung."
    )

    # Date validation
    date_cols = [
        col for col in data.columns
        if any(x in str(col).lower() for x in ["tanggal", "date", "tgl"])
    ]

    invalid_dates = 0

    for col in date_cols:
        original = data[col].notna()
        parsed = pd.to_datetime(data[col], errors="coerce")
        invalid_dates += int((original & parsed.isna()).sum())

    finding(
        "Tanggal Tidak Valid",
        "Sedang" if invalid_dates else "Rendah",
        invalid_dates,
        f"Ditemukan {invalid_dates} tanggal tidak valid.",
        "Periksa tanggal transaksi dan konsistensi periode."
    )

    # Debit and credit
    normalized = {str(c).strip().lower(): c for c in data.columns}
    debit_col = normalized.get("debit")
    credit_col = normalized.get("credit") or normalized.get("kredit")

    if debit_col and credit_col:
        debit = pd.to_numeric(data[debit_col], errors="coerce").fillna(0)
        credit = pd.to_numeric(data[credit_col], errors="coerce").fillna(0)

        difference = abs(debit.sum() - credit.sum())

        finding(
            "Keseimbangan Debit Kredit",
            "Tinggi" if difference > .01 else "Rendah",
            1 if difference > .01 else 0,
            f"Selisih total debit dan kredit: {difference:,.2f}.",
            "Periksa keseimbangan jurnal per nomor jurnal, bukan hanya total."
        )

    # Budget actual
    budget_col = normalized.get("budget")
    actual_col = normalized.get("actual")

    if budget_col and actual_col:
        budget = pd.to_numeric(data[budget_col], errors="coerce")
        actual = pd.to_numeric(data[actual_col], errors="coerce")

        data["Variance"] = actual - budget
        data["Variance %"] = (
            data["Variance"] / budget.replace(0, float("nan"))
        ) * 100

        overspending = int((actual > budget).sum())

        finding(
            "Realisasi Melebihi Anggaran",
            "Tinggi" if overspending else "Rendah",
            overspending,
            f"Ditemukan {overspending} baris dengan realisasi di atas anggaran.",
            "Periksa persetujuan anggaran, alasan selisih, dan bukti transaksi."
        )

    return data, pd.DataFrame(findings)


def ai_audit():
    st.markdown("""
    <div class="finora-header">
        <h2>🔍 FINORA AI Audit Center</h2>
        <p>Automated Financial Audit, Risk Detection & Recommendations</p>
    </div>
    """, unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload Excel untuk Audit",
        type=["xlsx", "xls"],
        key="audit_upload"
    )

    if not uploaded:
        st.info("Upload file Excel untuk memulai pemeriksaan.")
        return

    try:
        excel = pd.ExcelFile(uploaded)

        sheet = st.selectbox(
            "Pilih sheet",
            excel.sheet_names,
            key="audit_sheet"
        )

        df = pd.read_excel(uploaded, sheet_name=sheet)

        if df.empty:
            st.error("Sheet tidak memiliki data.")
            return

        st.subheader("Data yang Akan Diperiksa")
        st.write(f"{len(df):,} baris | {len(df.columns)} kolom")
        st.dataframe(df.head(100), use_container_width=True)

        if st.button("🔎 Jalankan Audit Otomatis", type="primary"):
            audited, findings = audit_engine(df)

            st.session_state.audit_data = audited
            st.session_state.audit_findings = findings
            st.session_state.audit_report = None

            log_activity(
                f"Melakukan audit Excel: {uploaded.name}"
            )

        if "audit_findings" not in st.session_state:
            return

        findings = st.session_state.audit_findings
        audited = st.session_state.audit_data

        st.divider()
        st.subheader("📊 Ringkasan Hasil Audit")

        high = int((findings["Risiko"] == "Tinggi").sum())
        medium = int((findings["Risiko"] == "Sedang").sum())
        low = int((findings["Risiko"] == "Rendah").sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Jumlah Baris", f"{len(audited):,}")
        c2.metric("Risiko Tinggi", high)
        c3.metric("Risiko Sedang", medium)
        c4.metric("Risiko Rendah", low)

        st.subheader("📋 Temuan Audit")
        st.dataframe(findings, use_container_width=True)

        st.subheader("📈 Grafik Tingkat Risiko")

        risk_chart = findings.groupby("Risiko").size().reset_index(name="Jumlah")
        fig = px.bar(
            risk_chart,
            x="Risiko",
            y="Jumlah",
            color="Risiko",
            title="Jumlah Kategori Temuan Berdasarkan Risiko"
        )
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("🤖 AI Audit Report")
        provider, model = ai_controls("audit")

        if st.button("Generate Laporan dan Rekomendasi AI"):
            prompt = f"""
            Kamu adalah FINORA AI, asisten audit keuangan profesional.

            Analisis hasil pemeriksaan berikut:

            Jumlah baris data: {len(audited)}

            Temuan:
            {findings.to_string(index=False)}

            Sampel data:
            {audited.head(100).to_string(index=False)}

            Buat laporan dengan struktur:

            1. Ringkasan Eksekutif
            2. Tujuan dan Ruang Lingkup Pemeriksaan
            3. Metode Pemeriksaan
            4. Temuan Audit
            5. Analisis Risiko
            6. Dampak Keuangan
            7. Kemungkinan Penyebab
            8. Rekomendasi Perbaikan
            9. Prioritas Tindak Lanjut
            10. Kesimpulan

            Gunakan bahasa Indonesia profesional.
            Bedakan fakta dan dugaan.
            Jangan menyatakan fraud sebagai fakta.
            Jangan mengarang dokumen, bukti, atau nominal.
            Jelaskan keterbatasan pemeriksaan.
            """

            with st.spinner("AI sedang menyusun laporan audit..."):
                report = ask_ai(prompt, provider, model)

            st.session_state.audit_report = report

        if st.session_state.get("audit_report"):
            st.markdown(st.session_state.audit_report)

        st.divider()
        st.subheader("📥 Download Hasil Audit")

        excel_buffer = io.BytesIO()

        with pd.ExcelWriter(
            excel_buffer,
            engine="openpyxl"
        ) as writer:
            audited.to_excel(
                writer,
                sheet_name="Data Audit",
                index=False
            )
            findings.to_excel(
                writer,
                sheet_name="Temuan Audit",
                index=False
            )

        st.download_button(
            "Download Laporan Audit Excel",
            data=excel_buffer.getvalue(),
            file_name="FINORA_AI_Audit.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if st.session_state.get("audit_report"):
            report_text = st.session_state.audit_report

            st.download_button(
                "Download Laporan AI TXT",
                data=report_text.encode("utf-8"),
                file_name="FINORA_AI_Audit_Report.txt",
                mime="text/plain"
            )

            # Optional PDF export
            try:
                from reportlab.lib.pagesizes import A4
                from reportlab.platypus import (
                    SimpleDocTemplate, Paragraph, Spacer
                )
                from reportlab.lib.styles import getSampleStyleSheet
                from reportlab.lib.units import cm

                pdf_buffer = io.BytesIO()
                doc = SimpleDocTemplate(
                    pdf_buffer,
                    pagesize=A4,
                    rightMargin=2*cm,
                    leftMargin=2*cm
                )

                styles = getSampleStyleSheet()
                story = [
                    Paragraph("FINORA AI - LAPORAN AUDIT", styles["Title"]),
                    Spacer(1, 16)
                ]

                for line in report_text.splitlines():
                    if line.strip():
                        safe_line = (
                            line.replace("&", "&amp;")
                            .replace("<", "&lt;")
                            .replace(">", "&gt;")
                        )
                        story.append(
                            Paragraph(safe_line, styles["BodyText"])
                        )
                        story.append(Spacer(1, 7))

                doc.build(story)

                st.download_button(
                    "Download Laporan Audit PDF",
                    data=pdf_buffer.getvalue(),
                    file_name="FINORA_AI_Audit_Report.pdf",
                    mime="application/pdf"
                )

            except ImportError:
                st.caption(
                    "PDF memerlukan package reportlab. Tambahkan ke requirements.txt."
                )

    except Exception as error:
        st.error(f"Audit gagal dijalankan: {error}")


# =========================================================
# 12. BUDGETING AND PLANNING
# =========================================================

def budgeting():
    st.title("📅 Budgeting & Planning")

    tab1, tab2 = st.tabs(["Input Anggaran", "Budget vs Actual"])

    with tab1:
        with st.form("budget_form"):
            period = st.text_input(
                "Periode",
                value=datetime.now().strftime("%Y-%m")
            )
            category = st.text_input("Kategori anggaran")
            amount = st.number_input("Nilai anggaran", min_value=0.0)

            if st.form_submit_button("Simpan Anggaran"):
                if category and amount > 0:
                    execute("""
                        INSERT INTO budgets
                        (period,category,budget_amount,created_by)
                        VALUES (?,?,?,?)
                    """, (
                        period, category, amount,
                        st.session_state.username
                    ))
                    st.success("Anggaran berhasil disimpan.")
                    st.rerun()

    with tab2:
        budgets = query_df("SELECT * FROM budgets")

        if budgets.empty:
            st.info("Belum ada anggaran.")
        else:
            transactions = query_df("""
                SELECT category, SUM(amount) AS actual
                FROM transactions
                WHERE transaction_type='Pengeluaran'
                GROUP BY category
            """)

            comparison = budgets.merge(
                transactions,
                on="category",
                how="left"
            )

            comparison["actual"] = comparison["actual"].fillna(0)
            comparison["variance"] = (
                comparison["actual"] - comparison["budget_amount"]
            )

            comparison["status"] = comparison.apply(
                lambda r: "Melebihi Anggaran"
                if r["variance"] > 0 else "Dalam Anggaran",
                axis=1
            )

            st.dataframe(comparison, use_container_width=True)

            fig = px.bar(
                comparison,
                x="category",
                y=["budget_amount", "actual"],
                barmode="group"
            )

            st.plotly_chart(fig, use_container_width=True)


# =========================================================
# 13. DOCUMENTS AND EVIDENCE
# =========================================================

def documents():
    st.title("📁 Dokumen & Bukti")

    uploaded = st.file_uploader(
        "Upload dokumen pendukung",
        type=["pdf", "png", "jpg", "jpeg", "xlsx", "docx"],
        key="document_upload"
    )

    if uploaded:
        document_type = st.selectbox(
            "Jenis dokumen",
            [
                "Invoice",
                "Kuitansi",
                "Bukti Transfer",
                "Kontrak",
                "Laporan",
                "Lainnya"
            ]
        )

        description = st.text_input("Keterangan dokumen")

        if st.button("Simpan Metadata Dokumen"):
            execute("""
                INSERT INTO documents
                (filename,document_type,description,uploaded_by,uploaded_at)
                VALUES (?,?,?,?,?)
            """, (
                uploaded.name,
                document_type,
                description,
                st.session_state.username,
                datetime.now().isoformat()
            ))

            st.success(
                "Metadata tersimpan. File belum disimpan permanen ke penyimpanan cloud."
            )

    docs = query_df(
        "SELECT * FROM documents ORDER BY uploaded_at DESC"
    )

    st.subheader("Riwayat Dokumen")
    st.dataframe(docs, use_container_width=True, hide_index=True)


# =========================================================
# 14. AUDIT REPORT
# =========================================================

def audit_report():
    st.title("📑 Laporan Audit")

    if "audit_findings" not in st.session_state:
        st.info("Jalankan pemeriksaan di menu AI Audit terlebih dahulu.")
        return

    findings = st.session_state.audit_findings

    st.subheader("Daftar Temuan")
    st.dataframe(findings, use_container_width=True)

    report = st.session_state.get("audit_report")

    if report:
        st.subheader("Laporan dan Rekomendasi AI")
        st.markdown(report)
    else:
        st.warning("Laporan AI belum dibuat. Buka menu AI Audit untuk membuat laporan.")


# =========================================================
# 15. ANALYTICS AND REPORTS
# =========================================================

def analytics():
    st.title("📊 Analytics & Reports")

    df = query_df("SELECT * FROM transactions")

    if df.empty:
        st.info("Belum ada data transaksi untuk dianalisis.")
        return

    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"], errors="coerce"
    )

    start, end = st.columns(2)

    with start:
        date_start = st.date_input(
            "Tanggal awal",
            value=df.transaction_date.min().date()
        )

    with end:
        date_end = st.date_input(
            "Tanggal akhir",
            value=df.transaction_date.max().date()
        )

    filtered = df[
        (df.transaction_date.dt.date >= date_start)
        & (df.transaction_date.dt.date <= date_end)
    ]

    st.subheader("Ringkasan Periode")

    income = filtered.loc[
        filtered.transaction_type == "Pendapatan", "amount"
    ].sum()

    expense = filtered.loc[
        filtered.transaction_type == "Pengeluaran", "amount"
    ].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Pendapatan", money(income))
    c2.metric("Pengeluaran", money(expense))
    c3.metric("Surplus / Defisit", money(income - expense))

    category = filtered.groupby(
        ["category", "transaction_type"]
    )["amount"].sum().reset_index()

    fig = px.bar(
        category,
        x="category",
        y="amount",
        color="transaction_type",
        barmode="group"
    )

    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(filtered, use_container_width=True)


# =========================================================
# 16. USER MANAGEMENT
# =========================================================

def user_management():
    st.title("👥 User Management")

    if st.session_state.role != "Admin":
        st.error("Hanya Admin yang dapat mengakses menu ini.")
        return

    tab1, tab2 = st.tabs(["Tambah Pengguna", "Daftar Pengguna"])

    with tab1:
        with st.form("create_user"):
            full_name = st.text_input("Nama lengkap")
            username = st.text_input("Username baru")
            password = st.text_input("Password", type="password")

            role = st.selectbox(
                "Role",
                ["Finance", "Auditor", "Manager"]
            )

            submit = st.form_submit_button("Buat Pengguna")

            if submit:
                if not full_name or not username or len(password) < 8:
                    st.error("Lengkapi data. Password minimal 8 karakter.")
                else:
                    try:
                        execute("""
                            INSERT INTO users
                            (username,password,full_name,role,created_at)
                            VALUES (?,?,?,?,?)
                        """, (
                            username.strip(),
                            hash_password(password),
                            full_name,
                            role,
                            datetime.now().isoformat()
                        ))

                        st.success("Pengguna berhasil dibuat.")
                        st.rerun()

                    except Exception as error:
                        st.error(f"Gagal membuat pengguna: {error}")

    with tab2:
        users = query_df("""
            SELECT id,username,full_name,role,created_at
            FROM users
        """)

        st.dataframe(users, use_container_width=True, hide_index=True)


# =========================================================
# 17. ACTIVITY LOG
# =========================================================

def activity_log():
    st.title("📜 Activity Log")

    if st.session_state.role != "Admin":
        st.warning("Activity log hanya dapat dilihat oleh Admin.")
        return

    logs = query_df(
        "SELECT * FROM audit_logs ORDER BY created_at DESC"
    )

    st.dataframe(logs, use_container_width=True, hide_index=True)


# =========================================================
# 18. MAIN ROUTER
# =========================================================

if page == "Dashboard":
    dashboard()

elif page == "Manajemen Keuangan":
    financial_management()

elif page == "Sistem Akuntansi":
    accounting_system()

elif page == "Financial Copilot AI":
    financial_copilot()

elif page == "AI Audit":
    ai_audit()

elif page == "Budgeting & Planning":
    budgeting()

elif page == "Dokumen & Bukti":
    documents()

elif page == "Laporan Audit":
    audit_report()

elif page == "Analytics & Reports":
    analytics()

elif page == "User Management":
    user_management()


# =========================================================
# 19. FOOTER
# =========================================================

st.sidebar.divider()
st.sidebar.caption("FINORA AI © 2026")
st.sidebar.caption("Smart Financial Management System")
