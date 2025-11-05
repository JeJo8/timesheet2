import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import calendar

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Timesheet / Rota App v3", layout="wide")
SHOP_NAME = "My Shop"  # Change this to your business name

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
employees_df = pd.read_csv(EMP_FILE)
employees = employees_df["Employee"].dropna().tolist()

# ---------------- SIDEBAR & LOGIN ----------------
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

st.title("⏱️ Timesheet / Rota App v3")

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
        st.subheader("All Entries")
        st.dataframe(df.sort_values(["Employee", "Date"]))

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

        # PDF Export
        st.markdown("### 📄 Export Summary to PDF")

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

        st.download_button(
            "📄 Download Summary as PDF",
            data=pdf_bytes,
            file_name=f"timesheet_summary_{date_from}_{date_to}.pdf",
            mime="application/pdf"
        )

# ---------------- EXPORT / IMPORT TAB ----------------
with tabs[2]:
    st.header("Export / Import")
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download All Timesheet Data", data=csv_data, file_name="timesheet_full.csv")
    uploaded = st.file_uploader("Upload CSV to append entries", type=["csv"])
    if uploaded:
        uploaded_df = pd.read_csv(uploaded)
        df = pd.concat([df, uploaded_df], ignore_index=True)
        df.to_csv(DATA_FILE, index=False)
        st.success("Uploaded data appended successfully.")
