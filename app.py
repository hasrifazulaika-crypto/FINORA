
import os
import sqlite3
import hashlib
import hmac
import secrets
from datetime import date

import streamlit as st
import pandas as pd
import plotly.express as px

# =========================================================
# 1. KONFIGURASI APLIKASI
# =========================================================

st.set_page_config(
    page_title="FINORA AI",
    page_icon="📊",
    layout="wide"
)

DB_NAME = "finora.db"


# =========================================================
# 2. DATABASE SQLITE
# =========================================================

def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_date TEXT NOT NULL,
            description TEXT,
            category TEXT,
            transaction_type TEXT,
            amount REAL NOT NULL,
            created_by TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT NOT NULL,
            category TEXT NOT NULL,
            budget_amount REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS journals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            journal_date TEXT NOT NULL,
            description TEXT,
            account TEXT,
            debit REAL DEFAULT 0,
            credit REAL DEFAULT 0,
            created_by TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            activity TEXT,
            activity_time TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def log_activity(username, activity):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_logs (username, activity) VALUES (?, ?)",
        (username, activity)
    )
    conn.commit()
    conn.close()


init_database()


# =========================================================
# 3. KEAMANAN PASSWORD
# =========================================================

def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        100000
    ).hex()

    return f"{salt}${hashed}"


def verify_password(password, stored_password):
    try:
        salt, saved_hash = stored_password.split("$")
        return hmac.compare_digest(
            hash_password(password, salt).split("$")[1],
            saved_hash
        )
    except Exception:
        return False


# =========================================================
# 4. SISTEM LOGIN MULTI-USER
# =========================================================

def register_user(username, password, role):
    conn = get_connection()

    try:
        conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hash_password(password), role)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def authenticate_user(username, password):
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ?",
        (username,)
    ).fetchone()
    conn.close()

    if user and verify_password(password, user["password"]):
        return {
            "username": user["username"],
            "role": user["role"]
        }

    return None


def login_page():
    st.title("📊 FINORA AI")
    st.subheader("Smart Financial Management, Accounting & Audit System")

    conn = get_connection()
    user_count = conn.execute(
        "SELECT COUNT(*) FROM users"
    ).fetchone()[0]
    conn.close()

    tab1, tab2 = st.tabs(["Login", "Registrasi"])

    with tab1:
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")

            if submitted:
                user = authenticate_user(username, password)

                if user:
                    st.session_state.user = user
                    log_activity(username, "Login")
                    st.rerun()
                else:
                    st.error("Username atau password salah.")

    with tab2:
        st.write("Buat akun untuk menggunakan FINORA AI.")

        with st.form("register_form"):
            new_username = st.text_input("Username baru")
            new_password = st.text_input(
                "Password baru",
                type="password"
            )
            confirm_password = st.text_input(
                "Konfirmasi password",
                type="password"
            )

            if user_count == 0:
                st.info("Akun pertama akan menjadi Admin.")
                role = "Admin"
            else:
                role = "Finance"
                st.caption(
                    "Registrasi mandiri menghasilkan akun Finance. "
                    "Admin dapat mengelola pengguna dan perannya."
                )

            submitted = st.form_submit_button("Daftar")

            if submitted:
                if not new_username or not new_password:
                    st.error("Username dan password wajib diisi.")
                elif new_password != confirm_password:
                    st.error("Konfirmasi password tidak sama.")
                elif len(new_password) < 8:
                    st.error("Password minimal 8 karakter.")
                else:
                    success = register_user(
                        new_username,
                        new_password,
                        role
                    )

                    if success:
                        st.success(
                            f"Registrasi berhasil. Peran akun: {role}. "
                            "Silakan login."
                        )
                    else:
                        st.error("Username sudah digunakan.")


# =========================================================
# 5. FUNGSI DATA
# =========================================================

def load_transactions():
    conn = get_connection()
    df = pd.read_sql_query(
        "SELECT * FROM transactions ORDER BY transaction_date DESC",
        conn
    )
    conn.close()
    return df


def load_budgets():
    conn = get_connection()
    df = pd.read_sql_query("SELECT * FROM budgets", conn)
    conn.close()
    return df


def money(value):
    return f"Rp {value:,.0f}"


# =========================================================
# 6. AI HYBRID: GEMINI DAN GROQ
# =========================================================

def get_api_key(name):
    value = os.getenv(name)

    try:
        if name in st.secrets:
            value = st.secrets[name]
    except Exception:
        pass

    return value


def ask_ai(prompt, provider="Gemini", model=None):
    try:
        if provider == "Gemini":
            api_key = get_api_key("GEMINI_API_KEY")

            if not api_key:
                return "API Key Gemini belum diatur."

            from google import genai

            client = genai.Client(api_key=api_key)
            selected_model = model or "gemini-2.5-flash"

            response = client.models.generate_content(
                model=selected_model,
                contents=prompt
            )

            return response.text or "AI tidak menghasilkan jawaban."

        elif provider == "Groq":
            api_key = get_api_key("GROQ_API_KEY")

            if not api_key:
                return "API Key Groq belum diatur."

            from groq import Groq

            client = Groq(api_key=api_key)
            selected_model = model or "llama-3.3-70b-versatile"

            response = client.chat.completions.create(
                model=selected_model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Kamu adalah FINORA AI, asisten ahli "
                            "keuangan, akuntansi, dan audit. "
                            "Analisis data secara objektif. "
                            "Jangan mengarang informasi."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3
            )

            return response.choices[0].message.content

    except Exception as error:
        return f"Terjadi kesalahan AI: {error}"

    return "Provider AI tidak dikenali."


# =========================================================
# 7. DASHBOARD
# =========================================================

def dashboard():
    st.title("📊 FINORA AI Dashboard")
    st.write("Ringkasan kondisi keuangan dan aktivitas organisasi.")

    df = load_transactions()

    if df.empty:
        total_income = 0
        total_expense = 0
    else:
        total_income = df.loc[
            df["transaction_type"] == "Pendapatan", "amount"
        ].sum()

        total_expense = df.loc[
            df["transaction_type"] == "Pengeluaran", "amount"
        ].sum()

    balance = total_income - total_expense

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Pendapatan", money(total_income))
    c2.metric("Total Pengeluaran", money(total_expense))
    c3.metric("Selisih Pendapatan - Pengeluaran", money(balance))

    st.divider()

    if not df.empty:
        st.subheader("📈 Grafik Pendapatan dan Pengeluaran")

        chart_df = (
            df.groupby("transaction_type")["amount"]
            .sum()
            .reset_index()
        )

        fig = px.pie(
            chart_df,
            names="transaction_type",
            values="amount",
            hole=0.4
        )

        st.plotly_chart(fig, use_container_width=True)

        st.subheader("Transaksi Terbaru")
        st.dataframe(df.head(10), use_container_width=True)
    else:
        st.info("Belum ada transaksi. Tambahkan transaksi pada menu Manajemen Keuangan.")


# =========================================================
# 8. MANAJEMEN KEUANGAN
# =========================================================

def financial_management(username):
    st.title("💰 Manajemen Keuangan")

    tab1, tab2 = st.tabs([
        "Input Transaksi",
        "Data Transaksi"
    ])

    with tab1:
        with st.form("transaction_form"):
            transaction_date = st.date_input(
                "Tanggal transaksi",
                value=date.today()
            )

            description = st.text_input("Keterangan")
            category = st.text_input("Kategori")

            transaction_type = st.selectbox(
                "Jenis transaksi",
                ["Pendapatan", "Pengeluaran"]
            )

            amount = st.number_input(
                "Jumlah (Rp)",
                min_value=0.0,
                step=10000.0
            )

            submitted = st.form_submit_button("Simpan Transaksi")

            if submitted:
                if not description or not category or amount <= 0:
                    st.error("Lengkapi data transaksi dengan benar.")
                else:
                    conn = get_connection()
                    conn.execute("""
                        INSERT INTO transactions
                        (transaction_date, description, category,
                         transaction_type, amount, created_by)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        str(transaction_date),
                        description,
                        category,
                        transaction_type,
                        amount,
                        username
                    ))
                    conn.commit()
                    conn.close()

                    log_activity(username, "Menambahkan transaksi")
                    st.success("Transaksi berhasil disimpan.")
                    st.rerun()

    with tab2:
        df = load_transactions()

        if df.empty:
            st.info("Belum ada transaksi.")
        else:
            st.dataframe(df, use_container_width=True)

            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download Data Transaksi CSV",
                data=csv,
                file_name="finora_transactions.csv",
                mime="text/csv"
            )


# =========================================================
# 9. SISTEM AKUNTANSI
# =========================================================

def accounting_system(username):
    st.title("📚 Sistem Akuntansi")
    st.write("Pencatatan jurnal umum sederhana.")

    with st.form("journal_form"):
        journal_date = st.date_input("Tanggal jurnal", value=date.today())
        description = st.text_input("Keterangan jurnal")
        account = st.text_input("Nama akun")
        debit = st.number_input("Debit (Rp)", min_value=0.0)
        credit = st.number_input("Kredit (Rp)", min_value=0.0)

        submitted = st.form_submit_button("Simpan Jurnal")

        if submitted:
            if not description or not account:
                st.error("Keterangan dan nama akun wajib diisi.")
            elif (debit > 0 and credit > 0) or (debit == 0 and credit == 0):
                st.error("Isi salah satu: Debit atau Kredit.")
            else:
                conn = get_connection()
                conn.execute("""
                    INSERT INTO journals
                    (journal_date, description, account,
                     debit, credit, created_by)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    str(journal_date),
                    description,
                    account,
                    debit,
                    credit,
                    username
                ))
                conn.commit()
                conn.close()

                st.success("Jurnal berhasil disimpan.")
                st.rerun()

    conn = get_connection()
    journal_df = pd.read_sql_query(
        "SELECT * FROM journals ORDER BY journal_date DESC",
        conn
    )
    conn.close()

    st.subheader("📖 Daftar Jurnal")
    st.dataframe(journal_df, use_container_width=True)

    if not journal_df.empty:
        total_debit = journal_df["debit"].sum()
        total_credit = journal_df["credit"].sum()

        c1, c2 = st.columns(2)
        c1.metric("Total Debit", money(total_debit))
        c2.metric("Total Kredit", money(total_credit))

        if abs(total_debit - total_credit) < 0.01:
            st.success("Total debit dan kredit seimbang.")
        else:
            st.warning(
                "Total debit dan kredit belum seimbang. "
                "Periksa pencatatan jurnal."
            )


# =========================================================
# 10. BUDGETING DAN BUDGET VS ACTUAL AI
# =========================================================

def budgeting_module():
    st.title("📊 Budgeting & Planning")
    st.subheader("Budget vs. Actuals AI")
    st.write(
        "Unggah data anggaran dan realisasi untuk menghitung "
        "variance serta memperoleh analisis keuangan berbasis AI."
    )

    tab1, tab2 = st.tabs([
        "Analisis Excel",
        "Input Anggaran"
    ])

    with tab1:
        uploaded_file = st.file_uploader(
            "📂 Upload file Excel",
            type=["xlsx", "xls"],
            key="budget_excel"
        )

        if uploaded_file:
            try:
                df = pd.read_excel(uploaded_file)

                required_columns = ["Category", "Budget", "Actual"]

                if not all(col in df.columns for col in required_columns):
                    st.error(
                        "File wajib memiliki kolom: "
                        "Category, Budget, dan Actual."
                    )
                else:
                    df["Budget"] = pd.to_numeric(
                        df["Budget"], errors="coerce"
                    )
                    df["Actual"] = pd.to_numeric(
                        df["Actual"], errors="coerce"
                    )

                    if df[["Budget", "Actual"]].isna().any().any():
                        st.error(
                            "Kolom Budget dan Actual harus berisi angka."
                        )
                    else:
                        df["Variance"] = df["Actual"] - df["Budget"]

                        df["Variance %"] = (
                            df["Variance"]
                            / df["Budget"].replace(0, float("nan"))
                        ) * 100

                        st.subheader("📋 Data dengan Perhitungan Variance")
                        st.dataframe(df, use_container_width=True)

                        total_budget = df["Budget"].sum()
                        total_actual = df["Actual"].sum()
                        total_variance = total_actual - total_budget

                        c1, c2, c3 = st.columns(3)
                        c1.metric("Total Budget", money(total_budget))
                        c2.metric("Total Actual", money(total_actual))
                        c3.metric(
                            "Total Variance",
                            money(total_variance)
                        )

                        st.caption(
                            "Variance positif berarti realisasi lebih besar "
                            "dari anggaran. Untuk pendapatan, kondisi ini "
                            "dapat berarti pencapaian di atas target; "
                            "untuk pengeluaran, dapat berarti pemborosan."
                        )

                        st.subheader("📈 Budget vs. Actual")

                        fig = px.bar(
                            df,
                            x="Category",
                            y=["Budget", "Actual"],
                            barmode="group",
                            title="Perbandingan Anggaran dan Realisasi"
                        )

                        st.plotly_chart(
                            fig,
                            use_container_width=True
                        )

                        fig_variance = px.bar(
                            df,
                            x="Category",
                            y="Variance",
                            color="Variance",
                            title="Variance per Kategori",
                            color_continuous_scale="RdYlGn"
                        )

                        st.plotly_chart(
                            fig_variance,
                            use_container_width=True
                        )

                        st.subheader("🤖 AI-Powered Variance Analysis")

                        provider = st.selectbox(
                            "Pilih AI Provider",
                            ["Gemini", "Groq"],
                            key="budget_provider"
                        )

                        if provider == "Gemini":
                            model = st.selectbox(
                                "Model Gemini",
                                ["gemini-2.5-flash"],
                                key="budget_gemini_model"
                            )
                        else:
                            model = st.selectbox(
                                "Model Groq",
                                [
                                    "llama-3.1-8b-instant",
                                    "llama-3.3-70b-versatile",
                                    "openai/gpt-oss-120b"
                                ],
                                key="budget_groq_model"
                            )

                        if st.button("🤖 Generate AI Financial Analysis"):
                            prompt = f"""
                            Kamu adalah FINORA AI, analis keuangan,
                            akuntansi, dan audit.

                            Analisis data Budget vs Actual berikut:

                            {df.to_string(index=False)}

                            Total Budget: {total_budget:,.2f}
                            Total Actual: {total_actual:,.2f}
                            Total Variance: {total_variance:,.2f}

                            Buat analisis dengan struktur:
                            1. Executive Summary
                            2. Significant Budget Variances
                            3. Kategori dengan realisasi di atas anggaran
                            4. Kategori dengan realisasi di bawah anggaran
                            5. Kemungkinan penyebab selisih
                            6. Risiko keuangan
                            7. Rekomendasi jangka pendek dan panjang.

                            Bedakan fakta dalam data dengan dugaan penyebab.
                            Jangan mengarang informasi.
                            Perhatikan bahwa arti variance dapat berbeda
                            antara pendapatan dan pengeluaran.
                            """

                            with st.spinner("FINORA AI sedang menganalisis..."):
                                result = ask_ai(
                                    prompt,
                                    provider,
                                    model
                                )
                                st.markdown(result)

                        st.subheader("💬 Chat with FINORA AI")

                        if "budget_chat" not in st.session_state:
                            st.session_state.budget_chat = []

                        for message in st.session_state.budget_chat:
                            st.markdown(message)

                        with st.form("budget_chat_form"):
                            question = st.text_input(
                                "Tanyakan sesuatu tentang data anggaran:"
                            )
                            send = st.form_submit_button("Kirim")

                        if send and question:
                            prompt = f"""
                            Kamu adalah FINORA AI.
                            Jawab pertanyaan berdasarkan data berikut:

                            {df.to_string(index=False)}

                            Pertanyaan pengguna:
                            {question}

                            Berikan jawaban yang jelas dan berdasarkan data.
                            Jangan mengarang informasi yang tidak tersedia.
                            """

                            with st.spinner("FINORA AI sedang menjawab..."):
                                answer = ask_ai(
                                    prompt,
                                    provider,
                                    model
                                )

                            st.session_state.budget_chat.append(
                                f"👤 **You:** {question}"
                            )
                            st.session_state.budget_chat.append(
                                f"🤖 **FINORA AI:** {answer}"
                            )
                            st.rerun()

                        if st.button("🔄 Reset Chat"):
                            st.session_state.budget_chat = []
                            st.rerun()

            except Exception as error:
                st.error(f"Gagal membaca file: {error}")

    with tab2:
        st.subheader("Input Anggaran ke Database")

        with st.form("budget_form"):
            period = st.text_input(
                "Periode",
                placeholder="Contoh: 2026-11"
            )
            category = st.text_input("Kategori anggaran")
            budget_amount = st.number_input(
                "Jumlah anggaran (Rp)",
                min_value=0.0,
                step=10000.0
            )

            submitted = st.form_submit_button("Simpan Anggaran")

            if submitted:
                if not period or not category or budget_amount <= 0:
                    st.error("Lengkapi data anggaran.")
                else:
                    conn = get_connection()
                    conn.execute("""
                        INSERT INTO budgets
                        (period, category, budget_amount)
                        VALUES (?, ?, ?)
                    """, (period, category, budget_amount))
                    conn.commit()
                    conn.close()

                    st.success("Anggaran berhasil disimpan.")
                    st.rerun()

        budget_df = load_budgets()

        st.subheader("Daftar Anggaran")
        st.dataframe(budget_df, use_container_width=True)


# =========================================================
# 11. FINANCIAL COPILOT AI
# =========================================================

def financial_copilot():
    st.title("🤖 Financial Copilot AI")
    st.subheader("Scenario Planning & Strategic Insights")

    uploaded_file = st.file_uploader(
        "Upload Excel untuk analisis skenario",
        type=["xlsx", "xls"],
        key="copilot_excel"
    )

    if not uploaded_file:
        st.info(
            "Unggah Excel dengan kolom Category dan Base Forecast "
            "untuk memulai analisis skenario."
        )
        return

    try:
        df = pd.read_excel(uploaded_file)

        if not {"Category", "Base Forecast"}.issubset(df.columns):
            st.error(
                "File wajib memiliki kolom Category dan Base Forecast."
            )
            return

        df["Base Forecast"] = pd.to_numeric(
            df["Base Forecast"], errors="coerce"
        )

        if df["Base Forecast"].isna().any():
            st.error("Base Forecast harus berisi angka.")
            return

        df["Optimistic"] = df["Base Forecast"] * 1.15
        df["Pessimistic"] = df["Base Forecast"] * 0.90
        df["Worst Case"] = df["Base Forecast"] * 0.75

        left, right = st.columns([1.2, 1])

        with left:
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
                barmode="group",
                title="Financial Scenario Comparison"
            )

            st.plotly_chart(fig, use_container_width=True)

        with right:
            st.subheader("🤖 AI Financial Insights")

            provider = st.selectbox(
                "AI Provider",
                ["Gemini", "Groq"],
                key="copilot_provider"
            )

            model = (
                "gemini-2.5-flash"
                if provider == "Gemini"
                else "llama-3.3-70b-versatile"
            )

            if st.button("Generate Financial Insights"):
                prompt = f"""
                Kamu adalah Financial Copilot AI dari FINORA AI.

                Analisis skenario keuangan berikut:
                {df.to_string(index=False)}

                Jelaskan:
                1. Ringkasan kondisi keuangan.
                2. Perbandingan setiap skenario.
                3. Risiko keuangan.
                4. Dampak terhadap cash flow dan profitabilitas
                   jika data mendukung analisis tersebut.
                5. Rekomendasi jangka pendek.
                6. Rekomendasi jangka panjang.

                Angka skenario merupakan simulasi, bukan prediksi pasti.
                Jangan menyimpulkan EBIT, ESG, CAPEX, atau rasio lain
                jika data yang diperlukan tidak tersedia.
                """

                with st.spinner("AI sedang menganalisis..."):
                    st.markdown(
                        ask_ai(prompt, provider, model)
                    )

    except Exception as error:
        st.error(f"Terjadi kesalahan: {error}")


# =========================================================
# 12. AI AUDIT
# =========================================================

def ai_audit():
    st.title("🔍 AI Audit & Risk Detection")

    df = load_transactions()

    if df.empty:
        st.info("Belum ada transaksi untuk diaudit.")
        return

    st.subheader("Pemeriksaan Indikasi Risiko")

    duplicate = df[
        df.duplicated(
            subset=[
                "transaction_date",
                "description",
                "amount"
            ],
            keep=False
        )
    ]

    if duplicate.empty:
        st.success("Tidak ditemukan transaksi duplikat berdasarkan pemeriksaan sederhana.")
    else:
        st.warning("Terdapat transaksi dengan karakteristik duplikat.")
        st.dataframe(duplicate, use_container_width=True)

    threshold = st.number_input(
        "Batas nominal transaksi untuk pemeriksaan (Rp)",
        min_value=0.0,
        value=10000000.0,
        step=1000000.0
    )

    unusual = df[df["amount"] >= threshold]

    st.subheader("Transaksi Bernilai Besar")
    st.dataframe(unusual, use_container_width=True)

    st.caption(
        "Hasil pemeriksaan merupakan indikator awal untuk ditinjau auditor, "
        "bukan bukti kecurangan atau penyimpangan."
    )


# =========================================================
# 13. ANALYTICS & REPORTS
# =========================================================

def analytics_reports():
    st.title("📈 Analytics & Financial Reports")

    df = load_transactions()

    if df.empty:
        st.info("Belum tersedia data untuk dianalisis.")
        return

    df["transaction_date"] = pd.to_datetime(
        df["transaction_date"],
        errors="coerce"
    )

    df["Month"] = df["transaction_date"].dt.to_period("M").astype(str)

    monthly = (
        df.groupby(["Month", "transaction_type"])["amount"]
        .sum()
        .reset_index()
    )

    fig = px.bar(
        monthly,
        x="Month",
        y="amount",
        color="transaction_type",
        barmode="group",
        title="Tren Pendapatan dan Pengeluaran Bulanan"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Laporan Transaksi")
    st.dataframe(df, use_container_width=True)

    st.download_button(
        "Download Laporan Excel",
        data=to_excel_bytes(df),
        file_name="finora_report.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def to_excel_bytes(df):
    from io import BytesIO

    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Laporan")

    return output.getvalue()


# =========================================================
# 14. USER MANAGEMENT
# =========================================================

def user_management():
    st.title("👥 User Management")

    conn = get_connection()
    users = pd.read_sql_query(
        "SELECT id, username, role FROM users",
        conn
    )
    conn.close()

    st.subheader("Daftar Pengguna")
    st.dataframe(users, use_container_width=True)

    st.subheader("Tambah Pengguna")

    with st.form("admin_add_user"):
        username = st.text_input("Username pengguna")
        password = st.text_input("Password", type="password")
        role = st.selectbox(
            "Hak akses",
            ["Admin", "Finance", "Auditor", "Manager"]
        )

        submitted = st.form_submit_button("Tambah Pengguna")

        if submitted:
            if not username or len(password) < 8:
                st.error("Isi username dan password minimal 8 karakter.")
            elif register_user(username, password, role):
                st.success("Pengguna berhasil ditambahkan.")
                st.rerun()
            else:
                st.error("Username sudah digunakan.")


# =========================================================
# 15. MAIN APPLICATION
# =========================================================

def main():
    if "user" not in st.session_state:
        login_page()
        return

    user = st.session_state.user
    username = user["username"]
    role = user["role"]

    st.sidebar.title("📊 FINORA AI")
    st.sidebar.caption("Financial Management System")

    st.sidebar.write(f"Pengguna: **{username}**")
    st.sidebar.write(f"Role: **{role}**")

    menu_items = [
        "Dashboard",
        "Manajemen Keuangan",
        "Sistem Akuntansi",
        "Budgeting & Planning",
        "Financial Copilot AI",
        "AI Audit",
        "Analytics & Reports"
    ]

    if role == "Admin":
        menu_items.append("User Management")

    selected_menu = st.sidebar.radio(
        "Navigasi Menu",
        menu_items
    )

    if st.sidebar.button("Logout"):
        log_activity(username, "Logout")
        del st.session_state.user
        st.rerun()

    if selected_menu == "Dashboard":
        dashboard()

    elif selected_menu == "Manajemen Keuangan":
        financial_management(username)

    elif selected_menu == "Sistem Akuntansi":
        accounting_system(username)

    elif selected_menu == "Budgeting & Planning":
        budgeting_module()

    elif selected_menu == "Financial Copilot AI":
        financial_copilot()

    elif selected_menu == "AI Audit":
        ai_audit()

    elif selected_menu == "Analytics & Reports":
        analytics_reports()

    elif selected_menu == "User Management" and role == "Admin":
        user_management()


if __name__ == "__main__":
    main()
