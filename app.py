"""Main entry point for the credit application Streamlit app.

Responsibilities:
- Configure the application page.
- Initialize the SQLite database.
- Select a user and role.
- Route the user to the corresponding interface.
- Provide CSV event-log export.

Business operations are implemented in the service layer.
"""

import streamlit as st

from config import EVENT_LOG_EXPORT_PATH
from database import get_connection, initialize_database
from models import UserRole
from services.event_service import export_event_log
from ui.components import select_user
from ui.customer_view import render_customer_view
from ui.manager_view import render_manager_view
from ui.referent_view import render_referent_view


def show_event_log_export() -> None:
    """Provide a downloadable CSV containing all recorded events."""
    with st.sidebar:
        st.divider()
        st.subheader("Dnevnik dogodkov")

        # Generate an up-to-date export from the SQLite database.
        with get_connection() as connection:
            export_path = export_event_log(
                connection,
                EVENT_LOG_EXPORT_PATH,
            )

        csv_data = export_path.read_bytes()

        st.download_button(
            label="Prenesi dnevnik.csv",
            data=csv_data,
            file_name="dnevnik.csv",
            mime="text/csv",
            width="stretch",
        )

        st.caption(
            "Izvoz vsebuje vse dogodke, razvrščene "
            "po case_id in časovnem žigu."
        )


def main() -> None:
    """Initialize and render the Streamlit application."""
    st.set_page_config(
        page_title="Kreditne vloge – IUP",
        page_icon="📋",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    initialize_database()

    user = select_user()

    if user is None:
        st.title("Sistem za obravnavo kreditnih vlog")
        st.info(
            "Za začetek v stranskem meniju izberi vlogo "
            "in vnesi uporabniško ime."
        )
        st.stop()

    if user.role == UserRole.CUSTOMER:
        render_customer_view(user)

    elif user.role == UserRole.REFERENT:
        render_referent_view(user)

    elif user.role == UserRole.MANAGER:
        render_manager_view(user)

    # The manager can export the complete process event log.
    if user.role == UserRole.MANAGER:
        show_event_log_export()


if __name__ == "__main__":
    main()
