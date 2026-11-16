
# =========================================================
# AI AUDIT - EXCEL AUDIT ENGINE
# =========================================================

def ai_audit():

    st.markdown("""
    <div class="finora-header">
        <h2>🔍 FINORA AI Audit Center</h2>
        <p>Automated Financial Data Audit, Risk Detection & Recommendations</p>
    </div>
    """, unsafe_allow_html=True)

    st.write(
        "Unggah file Excel keuangan untuk menjalankan pemeriksaan "
        "data secara otomatis dan menghasilkan laporan audit."
    )

    uploaded_file = st.file_uploader(
        "📂 Upload File Excel untuk Audit",
        type=["xlsx", "xls"],
        key="audit_excel"
    )

    if not uploaded_file:
        st.info(
            "Silakan unggah file Excel yang berisi data transaksi, "
            "jurnal, anggaran, atau laporan keuangan."
        )
        return

    try:
        excel = pd.ExcelFile(uploaded_file)

        sheet_name = st.selectbox(
            "Pilih Sheet yang akan diperiksa",
            excel.sheet_names
        )

        df = pd.read_excel(
            uploaded_file,
            sheet_name=sheet_name
        )

        if df.empty:
            st.error("Sheet yang dipilih tidak memiliki data.")
            return

        st.subheader("📋 Data yang Akan Diaudit")
        st.write(f"Jumlah baris: **{len(df):,}**")
        st.write(f"Jumlah kolom: **{len(df.columns):,}**")
        st.dataframe(df.head(100), use_container_width=True)

        if len(df) > 100:
            st.caption(
                "Pratinjau menampilkan 100 baris pertama. "
                "Pemeriksaan otomatis tetap dilakukan pada seluruh baris."
            )

        # -------------------------------------------------
        # 1. NORMALISASI NAMA KOLOM
        # -------------------------------------------------

        audit_df = df.copy()

        audit_df.columns = [
            str(col).strip() for col in audit_df.columns
        ]

        normalized = {
            str(col).strip().lower(): col
            for col in audit_df.columns
        }

        findings = []

        def add_finding(category, risk, count, description, recommendation):
            findings.append({
                "Kategori": category,
                "Tingkat Risiko": risk,
                "Jumlah Temuan": int(count),
                "Deskripsi": description,
                "Rekomendasi": recommendation
            })

        # -------------------------------------------------
        # 2. PEMERIKSAAN DATA KOSONG
        # -------------------------------------------------

        missing_cells = int(audit_df.isna().sum().sum())

        if missing_cells > 0:
            add_finding(
                "Data Tidak Lengkap",
                "Sedang",
                missing_cells,
                "Ditemukan sel kosong pada data yang diunggah.",
                "Periksa dokumen sumber dan lengkapi data "
                "yang belum tersedia."
            )
        else:
            add_finding(
                "Data Tidak Lengkap",
                "Rendah",
                0,
                "Tidak ditemukan sel kosong.",
                "Pertahankan kelengkapan pencatatan."
            )

        # -------------------------------------------------
        # 3. PEMERIKSAAN DUPLIKASI
        # -------------------------------------------------

        duplicate_rows = audit_df[
            audit_df.duplicated(keep=False)
        ]

        duplicate_count = int(
            audit_df.duplicated().sum()
        )

        add_finding(
            "Transaksi Duplikat",
            "Tinggi" if duplicate_count > 0 else "Rendah",
            duplicate_count,
            (
                "Ditemukan baris yang sama persis."
                if duplicate_count > 0
                else "Tidak ditemukan baris duplikat yang sama persis."
            ),
            "Cocokkan transaksi yang terindikasi duplikat "
            "dengan bukti transaksi sebelum melakukan koreksi."
        )

        # -------------------------------------------------
        # 4. PEMERIKSAAN KOLOM NOMINAL
        # -------------------------------------------------

        amount_columns = []

        for col in audit_df.columns:
            col_lower = str(col).strip().lower()

            if any(word in col_lower for word in [
                "amount", "nominal", "jumlah",
                "debit", "credit", "kredit",
                "budget", "actual", "realisasi",
                "saldo", "nilai"
            ]):
                converted = pd.to_numeric(
                    audit_df[col], errors="coerce"
                )

                if converted.notna().any():
                    audit_df[col] = converted
                    amount_columns.append(col)

        negative_count = 0
        negative_details = []

        for col in amount_columns:
            negative_mask = audit_df[col] < 0
            count = int(negative_mask.sum())

            if count > 0:
                negative_count += count
                negative_details.append(
                    f"{col}: {count} nilai negatif"
                )

        add_finding(
            "Nominal Negatif",
            "Sedang" if negative_count > 0 else "Rendah",
            negative_count,
            (
                "; ".join(negative_details)
                if negative_details
                else "Tidak ditemukan nominal negatif pada kolom numerik terdeteksi."
            ),
            "Periksa apakah nilai negatif merupakan koreksi, retur, "
            "pembalikan transaksi, atau kesalahan input."
        )

        # -------------------------------------------------
        # 5. PEMERIKSAAN NILAI EKSTREM (IQR)
        # -------------------------------------------------

        outlier_total = 0
        outlier_details = []

        for col in amount_columns:
            values = audit_df[col].dropna()

            if len(values) < 4 or values.nunique() < 2:
                continue

            q1 = values.quantile(0.25)
            q3 = values.quantile(0.75)
            iqr = q3 - q1

            if iqr == 0:
                continue

            lower = q1 - (1.5 * iqr)
            upper = q3 + (1.5 * iqr)

            mask = (
                (audit_df[col] < lower)
                | (audit_df[col] > upper)
            )

            count = int(mask.sum())

            if count > 0:
                outlier_total += count
                outlier_details.append(
                    f"{col}: {count} nilai ekstrem"
                )

        add_finding(
            "Nilai Ekstrem",
            "Sedang" if outlier_total > 0 else "Rendah",
            outlier_total,
            (
                "; ".join(outlier_details)
                if outlier_details
                else "Tidak ditemukan nilai ekstrem berdasarkan metode IQR."
            ),
            "Telusuri nilai ekstrem dengan invoice, kuitansi, "
            "otorisasi, dan transaksi pembanding. Nilai ekstrem "
            "belum tentu merupakan kesalahan."
        )

        # -------------------------------------------------
        # 6. PEMERIKSAAN TANGGAL
        # -------------------------------------------------

        date_columns = [
            col for col in audit_df.columns
            if any(word in str(col).lower() for word in [
                "date", "tanggal", "tgl"
            ])
        ]

        invalid_dates = 0

        for col in date_columns:
            original_nonempty = audit_df[col].notna()

            parsed = pd.to_datetime(
                audit_df[col],
                errors="coerce"
            )

            invalid_dates += int(
                (original_nonempty & parsed.isna()).sum()
            )

        add_finding(
            "Format Tanggal",
            "Sedang" if invalid_dates > 0 else "Rendah",
            invalid_dates,
            (
                f"Ditemukan {invalid_dates} tanggal yang tidak dapat dibaca."
                if invalid_dates > 0
                else "Tidak ditemukan tanggal tidak valid pada kolom tanggal terdeteksi."
            ),
            "Cocokkan tanggal dengan dokumen sumber dan "
            "gunakan format tanggal yang konsisten."
        )

        # -------------------------------------------------
        # 7. PEMERIKSAAN DEBIT DAN KREDIT
        # -------------------------------------------------

        debit_col = normalized.get("debit")
        credit_col = normalized.get("credit")

        if credit_col is None:
            credit_col = normalized.get("kredit")

        if debit_col and credit_col:
            debit_values = pd.to_numeric(
                audit_df[debit_col], errors="coerce"
            ).fillna(0)

            credit_values = pd.to_numeric(
                audit_df[credit_col], errors="coerce"
            ).fillna(0)

            total_debit = debit_values.sum()
            total_credit = credit_values.sum()
            difference = total_debit - total_credit

            if abs(difference) > 0.01:
                add_finding(
                    "Keseimbangan Debit Kredit",
                    "Tinggi",
                    1,
                    f"Total debit dan kredit berbeda sebesar {difference:,.2f}.",
                    "Periksa jurnal yang belum memiliki pasangan debit "
                    "atau kredit dan lakukan rekonsiliasi."
                )
            else:
                add_finding(
                    "Keseimbangan Debit Kredit",
                    "Rendah",
                    0,
                    "Total debit dan kredit seimbang.",
                    "Pertahankan proses pemeriksaan keseimbangan jurnal."
                )
        else:
            total_debit = None
            total_credit = None
            st.info(
                "Pemeriksaan debit-kredit tidak dijalankan karena "
                "kolom Debit dan Kredit tidak ditemukan bersamaan."
            )

        # -------------------------------------------------
        # 8. PEMERIKSAAN BUDGET VS ACTUAL
        # -------------------------------------------------

        budget_col = normalized.get("budget")
        actual_col = normalized.get("actual")

        if budget_col and actual_col:
            budget_values = pd.to_numeric(
                audit_df[budget_col], errors="coerce"
            )

            actual_values = pd.to_numeric(
                audit_df[actual_col], errors="coerce"
            )

            audit_df["Audit Variance"] = (
                actual_values - budget_values
            )

            audit_df["Audit Variance %"] = (
                audit_df["Audit Variance"]
                / budget_values.replace(0, float("nan"))
            ) * 100

            overspending = int(
                (actual_values > budget_values).sum()
            )

            add_finding(
                "Realisasi Melebihi Anggaran",
                "Tinggi" if overspending > 0 else "Rendah",
                overspending,
                (
                    f"{overspending} baris memiliki realisasi "
                    "lebih besar daripada anggaran."
                ),
                "Periksa penyebab selisih, persetujuan perubahan "
                "anggaran, dan bukti pengeluaran."
            )

            st.subheader("📊 Analisis Budget vs Actual")

            total_budget = budget_values.sum()
            total_actual = actual_values.sum()
            total_variance = total_actual - total_budget

            c1, c2, c3 = st.columns(3)
            c1.metric("Total Budget", money(total_budget))
            c2.metric("Total Actual", money(total_actual))
            c3.metric("Variance", money(total_variance))

        # -------------------------------------------------
        # 9. RINGKASAN HASIL AUDIT
        # -------------------------------------------------

        findings_df = pd.DataFrame(findings)

        high_count = int(
            (findings_df["Tingkat Risiko"] == "Tinggi").sum()
        )

        medium_count = int(
            (findings_df["Tingkat Risiko"] == "Sedang").sum()
        )

        low_count = int(
            (findings_df["Tingkat Risiko"] == "Rendah").sum()
        )

        st.divider()
        st.subheader("📌 Ringkasan Hasil Pemeriksaan")

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Jumlah Baris", f"{len(audit_df):,}")
        c2.metric("Risiko Tinggi", high_count)
        c3.metric("Risiko Sedang", medium_count)
        c4.metric("Risiko Rendah", low_count)

        st.subheader("📋 Daftar Temuan Audit")
        st.dataframe(
            findings_df,
            use_container_width=True,
            hide_index=True
        )

        # -------------------------------------------------
        # 10. DETAIL TRANSAKSI YANG TERINDIKASI
        # -------------------------------------------------

        st.subheader("🔎 Detail Data yang Perlu Ditinjau")

        if not duplicate_rows.empty:
            with st.expander("Lihat transaksi duplikat"):
                st.dataframe(
                    duplicate_rows,
                    use_container_width=True
                )

        if negative_count > 0:
            with st.expander("Lihat nominal negatif"):
                negative_mask = pd.Series(
                    False, index=audit_df.index
                )

                for col in amount_columns:
                    negative_mask |= audit_df[col] < 0

                st.dataframe(
                    audit_df[negative_mask],
                    use_container_width=True
                )

        # -------------------------------------------------
        # 11. AI AUDIT ANALYSIS
        # -------------------------------------------------

        st.divider()
        st.subheader("🤖 AI Audit Analysis & Recommendations")

        provider = st.selectbox(
            "Pilih AI Provider",
            ["Gemini", "Groq"],
            key="audit_provider"
        )

        if provider == "Gemini":
            model = "gemini-2.5-flash"
        else:
            model = "llama-3.3-70b-versatile"

        if st.button("🚀 Jalankan Analisis AI Audit"):

            audit_summary = findings_df.to_string(index=False)

            data_preview = audit_df.head(100).to_string(
                index=False
            )

            prompt = f"""
            Kamu adalah FINORA AI, asisten audit keuangan profesional.

            Lakukan analisis atas hasil pemeriksaan data berikut.

            JUMLAH BARIS DATA:
            {len(audit_df)}

            TEMUAN OTOMATIS:
            {audit_summary}

            DATA PREVIEW:
            {data_preview}

            Susun laporan dengan bagian:

            1. Ringkasan Eksekutif Audit
            2. Ruang Lingkup dan Keterbatasan Pemeriksaan
            3. Temuan Audit Berdasarkan Tingkat Risiko
            4. Analisis Penyebab yang Mungkin
            5. Dampak atau Risiko Keuangan
            6. Rekomendasi Perbaikan
            7. Prioritas Tindak Lanjut
            8. Kesimpulan Audit

            Ketentuan:
            - Bedakan fakta data dan dugaan penyebab.
            - Jangan menyatakan kecurangan sebagai fakta.
            - Jangan mengarang bukti atau dokumen.
            - Jelaskan jika data tidak cukup untuk menyimpulkan.
            - Berikan rekomendasi yang dapat dilaksanakan.
            - Gunakan bahasa Indonesia profesional.
            """

            with st.spinner(
                "FINORA AI sedang menganalisis hasil pemeriksaan..."
            ):
                ai_report = ask_ai(
                    prompt,
                    provider,
                    model
                )

            st.session_state.audit_ai_report = ai_report

        if "audit_ai_report" in st.session_state:
            st.markdown(
                st.session_state.audit_ai_report
            )

        # -------------------------------------------------
        # 12. DOWNLOAD LAPORAN AUDIT EXCEL
        # -------------------------------------------------

        from io import BytesIO

        output = BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            audit_df.to_excel(
                writer,
                sheet_name="Data Pemeriksaan",
                index=False
            )

            findings_df.to_excel(
                writer,
                sheet_name="Temuan Audit",
                index=False
            )

            if not duplicate_rows.empty:
                duplicate_rows.to_excel(
                    writer,
                    sheet_name="Data Duplikat",
                    index=False
                )

        st.download_button(
            "📥 Download Laporan Audit Excel",
            data=output.getvalue(),
            file_name="FINORA_AI_Audit_Report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as error:
        st.error(f"Terjadi kesalahan saat audit: {error}")
