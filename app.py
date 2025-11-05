import streamlit as st
import pandas as pd
import os
from datetime import datetime, timedelta
import calendar

st.set_page_config(page_title="Timesheet / Rota App v2", layout="wide")

DATA_FILE = "timesheet.csv"

# Initialize data file
if not os.path.exists(DATA_FILE):
    df = pd.DataFrame(columns=["WeekStart","Date","Employee","StartTime","FinishTime","BreakMinutes","HoursWorked","Notes"])
    df.to_csv(DATA_FILE, index=False)

# Load data
df = pd.read_csv(DATA_FILE)
df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

# ------------------
# Authentication / Roles
# ------------------
st.sidebar.header("Access & Settings")

role = st.sidebar.selectbox("Role", ["Viewer", "Admin"])

# Admin authentication via Streamlit secrets
def admin_login():
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    if not st.session_state.admin_authenticated:
        pwd = st.sidebar.text_input("Enter Admin password", type="password")
        if st.sidebar.button("Login as Admin"):
            # check secret
            try:
                secret = st.secrets["ADMIN_PASSWORD"]
            except Exception:
                st.sidebar.error("Admin password not configured in Streamlit secrets. Contact owner.")
                return False
            if pwd == secret:
                st.session_state.admin_authenticated = True
                st.sidebar.success("Authenticated as Admin")
            else:
                st.sidebar.error("Incorrect password")
    return st.session_state.get("admin_authenticated", False)

is_admin = False
if role == "Admin":
    is_admin = admin_login()
else:
    is_admin = False

# Settings for auto-break
default_week_start = (pd.Timestamp.today() - pd.Timedelta(days=pd.Timestamp.today().weekday())).date()
week_start = st.sidebar.date_input("Week start (Monday)", value=default_week_start)
auto_break_threshold = st.sidebar.number_input("Auto-break threshold (hours)", min_value=1.0, max_value=24.0, value=6.0, step=0.5)
auto_break_minutes = st.sidebar.number_input("Auto-break minutes when over threshold", min_value=0, max_value=240, value=30, step=5)

st.title("⏱️ Timesheet / Rota App v2")

# Filter data for selected week/month
week_end = pd.to_datetime(week_start) + pd.Timedelta(days=6)
df_week = df[(df["Date"] >= pd.to_datetime(week_start)) & (df["Date"] <= week_end)].copy()

# Top-level navigation
tab = st.tabs(["Timesheet", "Summaries", "Export/Import"])

# ------------------
# TIMESHEET TAB
# ------------------
with tab[0]:
    st.header("Timesheet Entries")
    # Category: filter by employee or show all
    employees = sorted(df["Employee"].dropna().unique().tolist())
    emp_filter = st.selectbox("Filter by Employee", ["All"] + employees)
    if emp_filter != "All":
        df_display = df[df["Employee"] == emp_filter].copy()
    else:
        df_display = df.copy()
    st.subheader("All entries")
    if df_display.empty:
        st.info("No entries yet.")
    else:
        # show full table with dates formatted
        disp = df_display.copy()
        disp["Date"] = pd.to_datetime(disp["Date"]).dt.strftime("%Y-%m-%d")
        st.dataframe(disp.sort_values(["Employee","Date"]))
    st.markdown("---")
    # Add / Edit / Delete (Admin only)
    if is_admin:
        st.subheader("Add / Edit / Delete Entries (Admin)")
        action = st.radio("Action", ["Add Entry", "Edit Entry", "Delete Entry"], horizontal=True)
        if action == "Add Entry":
            with st.form("add_form", clear_on_submit=True):
                date = st.date_input("Date", value=pd.to_datetime(week_start))
                employee = st.text_input("Employee Name")
                col1, col2 = st.columns(2)
                with col1:
                    start_time = st.time_input("Start Time", value=datetime.strptime("09:00","%H:%M").time())
                with col2:
                    end_time = st.time_input("Finish Time", value=datetime.strptime("17:00","%H:%M").time())
                notes = st.text_area("Notes (optional)", max_chars=400)
                use_auto_break = st.checkbox("Auto-detect break based on hours threshold", value=True)
                submitted = st.form_submit_button("Add Entry")
                if submitted:
                    if not employee:
                        st.warning("Please enter employee name")
                    else:
                        start_dt = datetime.combine(pd.to_datetime(date), start_time)
                        end_dt = datetime.combine(pd.to_datetime(date), end_time)
                        if end_dt < start_dt:
                            end_dt += pd.Timedelta(days=1)
                        total_seconds = (end_dt - start_dt).total_seconds()
                        total_hours = total_seconds / 3600.0
                        break_minutes = int(auto_break_minutes) if (use_auto_break and total_hours >= float(auto_break_threshold)) else 0
                        worked_hours = max(0, (total_seconds - break_minutes*60) / 3600.0)
                        new_row = {
                            "WeekStart": pd.to_datetime(week_start).strftime("%Y-%m-%d"),
                            "Date": pd.to_datetime(date).strftime("%Y-%m-%d"),
                            "Employee": employee,
                            "StartTime": start_dt.strftime("%H:%M"),
                            "FinishTime": end_dt.strftime("%H:%M"),
                            "BreakMinutes": break_minutes,
                            "HoursWorked": round(worked_hours,2),
                            "Notes": notes
                        }
                        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                        df.to_csv(DATA_FILE, index=False)
                        st.success(f"Added entry for {employee} on {date} — {worked_hours:.2f} hours (break {break_minutes} min)")
        elif action == "Edit Entry":
            st.info("Select an entry to edit (by Employee + Date)")
            if df.empty:
                st.info("No entries available to edit.")
            else:
                sel_emp = st.selectbox("Employee", [""]+employees)
                dates_for_emp = sorted(df[df["Employee"]==sel_emp]["Date"].dropna().unique().tolist())
                sel_date = st.selectbox("Date", [""]+dates_for_emp)
                if sel_emp and sel_date:
                    entry_idx = df[(df["Employee"]==sel_emp) & (pd.to_datetime(df["Date"]).dt.strftime('%Y-%m-%d')==pd.to_datetime(sel_date).strftime('%Y-%m-%d'))].index
                    if len(entry_idx)==0:
                        st.warning("No matching entry found.")
                    else:
                        i = entry_idx[0]
                        row = df.loc[i]
                        with st.form("edit_form"):
                            new_start = st.time_input("Start Time", value=datetime.strptime(row["StartTime"],"%H:%M").time())
                            new_end = st.time_input("Finish Time", value=datetime.strptime(row["FinishTime"],"%H:%M").time())
                            new_notes = st.text_area("Notes", value=str(row.get("Notes","")))
                            submit_edit = st.form_submit_button("Save Changes")
                            if submit_edit:
                                start_dt = datetime.combine(pd.to_datetime(row["Date"]), new_start)
                                end_dt = datetime.combine(pd.to_datetime(row["Date"]), new_end)
                                if end_dt < start_dt:
                                    end_dt += pd.Timedelta(days=1)
                                total_seconds = (end_dt - start_dt).total_seconds()
                                total_hours = total_seconds / 3600.0
                                break_minutes = int(auto_break_minutes) if total_hours >= float(auto_break_threshold) else int(row.get("BreakMinutes",0))
                                worked_hours = max(0, (total_seconds - break_minutes*60) / 3600.0)
                                df.at[i,"StartTime"] = start_dt.strftime("%H:%M")
                                df.at[i,"FinishTime"] = end_dt.strftime("%H:%M")
                                df.at[i,"BreakMinutes"] = break_minutes
                                df.at[i,"HoursWorked"] = round(worked_hours,2)
                                df.at[i,"Notes"] = new_notes
                                df.to_csv(DATA_FILE,index=False)
                                st.success("Entry updated.")
        else:  # Delete
            st.info("Select an entry to delete")
            if df.empty:
                st.info("No entries to delete.")
            else:
                sel_emp = st.selectbox("Employee to delete", [""]+employees, key="del_emp")
                dates_for_emp = sorted(df[df["Employee"]==sel_emp]["Date"].dropna().unique().tolist())
                sel_date = st.selectbox("Date to delete", [""]+dates_for_emp, key="del_date")
                if sel_emp and sel_date:
                    idxs = df[(df["Employee"]==sel_emp) & (pd.to_datetime(df["Date"]).dt.strftime('%Y-%m-%d')==pd.to_datetime(sel_date).strftime('%Y-%m-%d'))].index
                    if len(idxs)==0:
                        st.warning("No matching entry found.")
                    else:
                        if st.button("Delete Entry"):
                            df.drop(idxs, inplace=True)
                            df.to_csv(DATA_FILE,index=False)
                            st.success("Entry deleted.")

    else:
        st.info("Admin login required to add/edit/delete entries. Select 'Admin' role in the sidebar.")

# ------------------
# SUMMARIES TAB
# ------------------
with tab[1]:
    st.header("Summaries & Reports")
    # Date range controls
    col_a, col_b = st.columns(2)
    with col_a:
        date_from = st.date_input("From", value=(pd.to_datetime(week_start) - pd.Timedelta(days=7)).date())
    with col_b:
        date_to = st.date_input("To", value=(pd.to_datetime(week_start) + pd.Timedelta(days=27)).date())

    # Ensure date order
    if pd.to_datetime(date_from) > pd.to_datetime(date_to):
        st.error("From date must be before To date.")
    else:
        df_range = df[(df["Date"] >= pd.to_datetime(date_from)) & (df["Date"] <= pd.to_datetime(date_to))].copy()
        if df_range.empty:
            st.info("No entries in selected date range.")
        else:
            # Daily totals across all employees
            daily = df_range.groupby("Date")["HoursWorked"].sum().reset_index()
            daily["Date"] = pd.to_datetime(daily["Date"])
            st.subheader("Daily total hours (all employees)")
            st.bar_chart(daily.set_index("Date")["HoursWorked"])

            # Weekly totals per employee
            df_range["Week"] = pd.to_datetime(df_range["Date"]).dt.to_period("W").apply(lambda r: r.start_time)
            weekly = df_range.groupby(["Week","Employee"])["HoursWorked"].sum().reset_index()
            st.subheader("Weekly hours per employee (table)")
            st.dataframe(weekly.pivot(index="Week", columns="Employee", values="HoursWorked").fillna(0))

            # Monthly totals per employee
            df_range["Month"] = pd.to_datetime(df_range["Date"]).dt.to_period("M").apply(lambda r: r.start_time)
            monthly = df_range.groupby(["Month","Employee"])["HoursWorked"].sum().reset_index()
            st.subheader("Monthly hours per employee (table)")
            st.dataframe(monthly.pivot(index="Month", columns="Employee", values="HoursWorked").fillna(0))

            # Per-employee summary
            st.subheader("Totals by employee")
            totals_emp = df_range.groupby("Employee")["HoursWorked"].sum().reset_index().rename(columns={"HoursWorked":"TotalHours"})
            st.dataframe(totals_emp)

# ------------------
# EXPORT / IMPORT TAB
# ------------------
with tab[2]:
    st.header("Export / Import")
    st.subheader("Download weekly CSV")
    if df_week.empty:
        st.info("No entries for this week.")
    else:
        csv = df_week.to_csv(index=False).encode("utf-8")
        st.download_button("Download week CSV", data=csv, file_name=f"timesheet_week_{str(week_start)}.csv")
    st.subheader("Upload CSV to append entries (must match columns)")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        uploaded_df = pd.read_csv(uploaded)
        required_cols = set(["WeekStart","Date","Employee","StartTime","FinishTime","BreakMinutes","HoursWorked","Notes"])
        if required_cols.issubset(set(uploaded_df.columns)):
            df = pd.concat([df, uploaded_df], ignore_index=True)
            df.to_csv(DATA_FILE, index=False)
            st.success("Uploaded and appended entries")
        else:
            st.error("CSV missing required columns. See template.")
    st.markdown("Download full master CSV:")
    full_csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download full timesheet CSV", data=full_csv, file_name="timesheet_all.csv")

st.sidebar.markdown("---")
st.sidebar.info("Notes:\n- Admin role required to modify entries.\n- Use the summaries tab to view daily/weekly/monthly totals.")