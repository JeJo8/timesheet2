import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Timesheet / Rota App v5", layout="wide")
SHOP_NAME = "Esquires Aylesbury Central"

DATA_FILE = "timesheet.csv"
EMP_FILE = "employees.csv"

# ---------------- FILE SETUP ----------------
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=["WeekStart", "Date", "Employee", "StartTime", "FinishTime", "BreakMinutes", "HoursWorked", "Notes"])
    df.to_csv(DATA_FILE, index=False)

if not os.path.exists(EMP_FILE):
    pd.DataFrame(columns=["Employee"]).to_csv(EMP_FILE, index=False)

df = pd.read_csv(DATA_FILE)
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

# ✅ Remove duplicates automatically
before = len(df)
df.drop_duplicates(subset=["Date", "Employee", "StartTime", "FinishTime"], keep="first", inplace=True)
after = len(df)
if before != after:
    df.to_csv(DATA_FILE, index=False)
    st.sidebar.warning(f"Removed {before - after} duplicate entries automatically.")

employees_df = pd.read_csv(EMP_FILE)
employees = employees_df["Employee"].dropna().tolist()

# ---------------- SIDEBAR LOGIN ----------------
st.sidebar.header("Access & Settings")
role = st.sidebar.selectbox("Role", ["Viewer", "Admin"])

def admin_login():
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if not st.session_state.admin_authenticated:
        pwd = st.sidebar.text_input("Enter Admin Password", type="password")
        if st.sidebar.button("Login"):
            if "ADMIN_PASSWORD" in st.secrets and pwd == st.secrets["ADMIN_PASSWORD"]:
                st.session_state.admin_authenticated = True
                st.sidebar.success("Authenticated ✅")
            else:
                st.sidebar.error("Incorrect password")
    return st.session_state.get("admin_authenticated", False)

is_admin = admin_login() if role == "Admin" else False

# Auto-break settings
week_start = st.sidebar.date_input("Week Start (Monday)", value=(datetime.today() - timedelta(days=datetime.today().weekday())).date())
auto_break_threshold = st.sidebar.number_input("Auto-break threshold (hours)", min_value=1.0, max_value=24.0, value=6.0)
auto_break_minutes = st.sidebar.number_input("Auto-break minutes", min_value=0, max_value=240, value=30)

st.title(f"⏱️ {SHOP_NAME} - Timesheet / Rota App v5")

# ---------------- EMPLOYEE MANAGEMENT ----------------
if is_admin:
    st.sidebar.markdown("### 👥 Employee Management")
    new_emp = st.sidebar.text_input("Add Employee Name")
    if st.sidebar.button("➕ Add Employee"):
        if new_emp and new_emp not in employees:
            employees_df = pd.concat([employees_df, pd.DataFrame([[new_emp]], columns=["Employee"])], ignore_index=True)
            employees_df.to_csv(EMP_FILE, index=False)
            st.sidebar.success(f"Added employee: {new_emp}")
        else:
            st.sidebar.warning("Invalid or duplicate name.")

    del_emp = st.sidebar.selectbox("🗑️ Delete Employee", [""] + employees)
    if st.sidebar.button("Delete Employee"):
        employees_df = employees_df[employees_df["Employee"] != del_emp]
        employees_df.to_csv(EMP_FILE, index=False)
        st.sidebar.success(f"Deleted employee: {del_emp}")
        employees = employees_df["Employee"].tolist()

# ---------------- MAIN NAVIGATION ----------------
tabs = st.tabs(["Timesheet", "Summaries", "Export / Import"])

# ---------------- TIMESHEET TAB ----------------
with tabs[0]:
    st.header("Timesheet Entries")

    # ADD ENTRY
    if not employees:
        st.warning("No employees found. Please add employees first (Admin only).")
    else:
        if is_admin:
            with st.form("add_entry_form", clear_on_submit=True):
                date = st.date_input("Date", value=pd.to_datetime(week_start))
                employee = st.selectbox("Employee", employees)
                start_time = st.time_input("Start Time", value=datetime.strptime("09:00", "%H:%M").time())
                end_time = st.time_input("Finish Time", value=datetime.strptime("17:00", "%H:%M").time())
                notes = st.text_area("Notes (optional)", max_chars=200)
                submitted = st.form_submit_button("Add Entry")

                if submitted:
                    start_dt = datetime.combine(pd.to_datetime(date), start_time)
                    end_dt = datetime.combine(pd.to_datetime(date), end_time)
                    if end_dt < start_dt:
                        end_dt += timedelta(days=1)
                    total_seconds = (end_dt - start_dt).total_seconds()
                    total_hours = total_seconds / 3600.0
                    break_minutes = int(auto_break_minutes) if total_hours >= auto_break_threshold else 0
                    worked_hours = max(0, (total_seconds - break_minutes * 60) / 3600.0)

                    # Prevent duplicates
                    duplicate_check = (
                        (df["Employee"] == employee) &
                        (df["Date"] == pd.to_datetime(date)) &
                        (df["StartTime"] == start_dt.strftime("%H:%M")) &
                        (df["FinishTime"] == end_dt.strftime("%H:%M"))
                    )
                    if duplicate_check.any():
                        st.warning("⚠️ Duplicate entry detected! Entry not saved.")
                    else:
                        new_row = {
                            "WeekStart": pd.to_datetime(week_start).strftime("%Y-%m-%d"),
                            "Date": pd.to_datetime(date).strftime("%Y-%m-%d"),
                            "Employee": employee,
                            "StartTime": start_dt.strftime("%H:%M"),
                            "FinishTime": end_dt.strftime("%H:%M"),
                            "BreakMinutes": break_minutes,
                            "HoursWorked": round(worked_hours, 2),
                            "Notes": notes
                        }
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        df.to_csv(DATA_FILE, index=False)
                        st.success(f"Added entry for {employee} ({worked_hours:.2f} hrs)")

        # EDIT / DELETE ENTRY
        if is_admin:
            st.markdown("### ✏️ Edit or 🗑️ Delete Entry")
            if df.empty:
                st.info("No entries available yet.")
            else:
                emp_to_edit = st.selectbox("Select Employee", sorted(df["Employee"].dropna().unique()), key="edit_emp")
                df_emp = df[df["Employee"] == emp_to_edit]

                if not df_emp.empty:
                    date_to_edit = st.selectbox("Select Date", sorted(df_emp["Date"].dt.strftime("%Y-%m-%d").unique()), key="edit_date")
                    match_entries = df_emp[df_emp["Date"].dt.strftime("%Y-%m-%d") == date_to_edit]

                    if len(match_entries) > 1:
                        entry_idx = st.selectbox(
                            "Multiple entries found — choose which one to edit or delete",
                            match_entries.index,
                            format_func=lambda x: f"{match_entries.loc[x, 'StartTime']} - {match_entries.loc[x, 'FinishTime']} ({match_entries.loc[x, 'Notes']})"
                        )
                    else:
                        entry_idx = match_entries.index[0]

                    entry = df.loc[entry_idx]
                    with st.form("edit_entry_form"):
                        st.write(f"**Editing entry for {emp_to_edit} on {date_to_edit}**")
                        col1, col2 = st.columns(2)
                        with col1:
                            new_start = st.time_input("Start Time", value=datetime.strptime(entry["StartTime"], "%H:%M").time())
                        with col2:
                            new_end = st.time_input("Finish Time", value=datetime.strptime(entry["FinishTime"], "%H:%M").time())
                        new_notes = st.text_area("Notes", value=str(entry.get("Notes", "")))
                        submitted_edit = st.form_submit_button("💾 Save Changes")
                        if submitted_edit:
                            start_dt = datetime.combine(pd.to_datetime(entry["Date"]), new_start)
                            end_dt = datetime.combine(pd.to_datetime(entry["Date"]), new_end)
                            if end_dt < start_dt:
                                end_dt += timedelta(days=1)
                            total_seconds = (end_dt - start_dt).total_seconds()
                            total_hours = total_seconds / 3600.0
                            break_minutes = int(auto_break_minutes) if total_hours >= auto_break_threshold else int(entry.get("BreakMinutes", 0))
                            worked_hours = max(0, (total_seconds - break_minutes * 60) / 3600.0)
                            df.at[entry_idx, "StartTime"] = start_dt.strftime("%H:%M")
                            df.at[entry_idx, "FinishTime"] = end_dt.strftime("%H:%M")
                            df.at[entry_idx, "BreakMinutes"] = break_minutes
                            df.at[entry_idx, "HoursWorked"] = round(worked_hours, 2)
                            df.at[entry_idx, "Notes"] = new_notes
                            df.to_csv(DATA_FILE, index=False)
                            st.success(f"✅ Updated entry for {emp_to_edit} on {date_to_edit}")

                    if st.button("❌ Delete This Entry", key="del_entry_btn"):
                        df.drop(entry_idx, inplace=True)
                        df.to_csv(DATA_FILE, index=False)
                        st.warning(f"🗑️ Deleted entry for {emp_to_edit} on {date_to_edit}")

                if st.button("🧹 Clean Duplicate Entries", key="clean_dupes_btn"):
                    before = len(df)
                    df.drop_duplicates(subset=["Date", "Employee", "StartTime", "FinishTime"], keep="first", inplace=True)
                    after = len(df)
                    df.to_csv(DATA_FILE, index=False)
                    st.success(f"Removed {before - after} duplicate entries.")

        # SEARCH & VIEW
        st.subheader("🔍 Search / View Entries")
        if df.empty:
            st.info("No entries yet.")
        else:
            search_query = st.text_input("Search (by employee, date, or notes):", placeholder="e.g. John or 2025-11-05 or 'delivery'")
            df_display = df.copy()
            if search_query.strip():
                q = search_query.lower()
                df_display = df_display[
                    df_display.apply(
                        lambda row:
                            q in str(row["Employee"]).lower()
                            or q in str(row["Date"]).lower()
                            or q in str(row["Notes"]).lower(),
                        axis=1
                    )
                ]
                st.info(f"Showing {len(df_display)} matching results for: '{search_query}'")

            if df_display.empty:
                st.warning("No entries found matching your search.")
            else:
                df_display_sorted = df_display.sort_values(["Employee", "Date"])
                st.dataframe(df_display_sorted)
                csv_search = df_display_sorted.to_csv(index=False).encode("utf-8")
                st.download_button("⬇️ Download Search Results", data=csv_search, file_name="search_results.csv")
            st.caption("Tip: Leave search box empty to view all entries.")

# ---------------- SUMMARIES TAB ----------------
with tabs[1]:
    st.header("Daily / Weekly / Monthly Summaries")
    col1, col2 = st.columns(2)
    with col1:
        date_from = st.date_input("From", value=pd.to_datetime(week_start))
    with col2:
        date_to = st.date_input("To", value=pd.to_datetime(week_start) + timedelta(days=27))

    df_range = df[(df["Date"] >= pd.to_datetime(date_from)) & (df["Date"] <= pd.to_datetime(date_to))].copy()
    if df_range.empty:
        st.info("No entries found in this period.")
    else:
        daily = df_range.groupby(["Date", "Employee"])["HoursWorked"].sum().reset_index()
        weekly = df_range.groupby([pd.Grouper(key="Date", freq="W-MON"), "Employee"])["HoursWorked"].sum().reset_index()
        monthly = df_range.groupby([pd.Grouper(key="Date", freq="M"), "Employee"])["HoursWorked"].sum().reset_index()
        st.subheader("📅 Daily Totals")
        st.dataframe(daily.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0))
        st.subheader("🗓 Weekly Totals")
        st.dataframe(weekly.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0))
        st.subheader("📆 Monthly Totals")
        st.dataframe(monthly.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0))

        def generate_pdf(data_d, data_w, data_m, shop_name):
            buffer = BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []
            elements.append(Paragraph(f"<b>{shop_name} — Timesheet Summary</b>", styles["Title"]))
            elements.append(Paragraph(f"Period: {date_from} to {date_to}", styles["Normal"]))
            elements.append(Spacer(1, 12))
            def make_table(df, title):
                elements.append(Paragraph(f"<b>{title}</b>", styles["Heading2"]))
                tbl_data = [df.columns.to_list()] + df.reset_index().values.tolist()
                t = Table(tbl_data, hAlign="LEFT")
                t.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]))
                elements.append(t)
                elements.append(Spacer(1, 12))
            make_table(data_d, "Daily Totals")
            make_table(data_w, "Weekly Totals")
            make_table(data_m, "Monthly Totals")
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
            doc.build(elements)
            pdf = buffer.getvalue()
            buffer.close()
            return pdf

        pdf_bytes = generate_pdf(
            daily.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0),
            weekly.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0),
            monthly.pivot(index="Date", columns="Employee", values="HoursWorked").fillna(0),
            SHOP_NAME
        )
        st.download_button("📄 Download Summary as PDF", data=pdf_bytes, file_name=f"timesheet_summary_{date_from}_{date_to}.pdf", mime="application/pdf")

# ---------------- EXPORT / IMPORT TAB ----------------
with tabs[2]:
    st.header("Export / Import")
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download All Timesheet Data", data=csv_data, file_name="timesheet_full.csv")
    uploaded = st.file_uploader("Upload CSV to append entries", type=["csv"])
    if uploaded:
        uploaded_df = pd.read_csv(uploaded)
        df = pd.concat([df, uploaded_df], ignore_index=True)
        df.drop_duplicates(subset=["Date", "Employee", "StartTime", "FinishTime"], keep="first", inplace=True)
        df.to_csv(DATA_FILE, index=False)
        st.success("Uploaded data appended successfully (duplicates removed).")
