
"""Streamlit interface for the credit application manager.

Responsibilities:
- Display an overview of all credit applications.
- Present summary statistics.
- Allow navigation to individual application details.
- Explain cases requiring manager decisions.

Manager decisions are outside the currently implemented happy path.
Process event logging remains internal.
"""

import streamlit as st

from config import REFERENT_APPROVAL_LIMIT
from models import (
    ApplicationStatus,
    CreditApplication,
    User,
    UserRole,
)
from services.application_service import list_applications
from ui.components import format_status, show_application_summary


MANAGER_SELECTED_CASE_KEY = "manager_selected_case"


def _format_amount(application: CreditApplication) -> str:
    """Format the requested amount for display."""
    amount = f"{application.requested_amount:,.2f}"
    return amount.replace(",", " ") + " €"


def _show_statistics(
    applications: list[CreditApplication],
) -> None:
    """Display a brief overview of application statuses."""
    total = len(applications)

    approved = sum(
        app.status == ApplicationStatus.APPROVED
        for app in applications
    )

    rejected = sum(
        app.status == ApplicationStatus.REJECTED
        for app in applications
    )

    in_progress = total - approved - rejected

    col1, col2, col3 = st.columns(3)

    col1.metric("Vse vloge", total)
    col2.metric("Odobrene", approved)
    col3.metric("V obravnavi", in_progress)


def _show_application_overview(
    applications: list[CreditApplication],
) -> None:
    """Display selectable credit applications."""
    _show_statistics(applications)

    st.subheader("Kreditne vloge")

    if not applications:
        st.info("Trenutno ni oddanih kreditnih vlog.")
        return

    for application in reversed(applications):
        with st.container(border=True):
            left, right = st.columns(
                [3, 1],
                vertical_alignment="center",
            )

            with left:
                st.markdown(
                    f"**{application.case_id} · "
                    f"{application.loan_purpose}**"
                )

                st.caption(
                    f"Stranka: {application.customer_id}  |  "
                    f"{_format_amount(application)}"
                )

                st.write(
                    "**Status:** "
                    f"{format_status(application.status.value)}"
                )

            with right:
                if st.button(
                    "Podrobnosti",
                    key=f"manager_open_{application.case_id}",
                    width="stretch",
                ):
                    st.session_state[MANAGER_SELECTED_CASE_KEY] = (
                        application.case_id
                    )
                    st.rerun()


def _show_application_details(
    application: CreditApplication,
) -> None:
    """Show one application and a way back to the overview."""
    if st.button(
        "← Nazaj na pregled vlog",
        key="manager_back_to_overview",
        width="content",
    ):
        st.session_state.pop(MANAGER_SELECTED_CASE_KEY, None)
        st.rerun()

    st.subheader(f"Podrobnosti vloge {application.case_id}")

    with st.container(border=True):
        show_application_summary(application)

    if application.status == ApplicationStatus.APPROVED:
        st.success("Kreditna vloga je odobrena.")

    elif application.status == ApplicationStatus.REJECTED:
        st.info("Kreditna vloga je zavrnjena.")

    elif (
        application.current_step == "approve_application"
        and application.requested_amount > REFERENT_APPROVAL_LIMIT
    ):
        st.warning(
            "Zaprošeni znesek presega pristojnost referenta. "
            "Odločitev vodje bo omogočena ob razširitvi procesa."
        )

    elif application.current_step == "approve_application":
        st.info(
            "Vloga je ocenjena in čaka na odločitev referenta."
        )

    elif application.assigned_referent is None:
        st.info("Vloga čaka na prevzem referenta.")

    else:
        st.info("Vloga je v obravnavi.")


def render_manager_view(user: User) -> None:
    """Render the manager's overview or selected application."""
    if user.role != UserRole.MANAGER:
        st.error("Ta stran je namenjena vodji.")
        return

    st.title("Pregled kreditnih vlog")
    st.caption(f"Prijavljeni vodja: {user.username}")

    # A different manager must start at the main overview.
    owner_key = "manager_selection_owner"

    if st.session_state.get(owner_key) != user.username:
        st.session_state[owner_key] = user.username
        st.session_state.pop(MANAGER_SELECTED_CASE_KEY, None)

    applications = list_applications()

    applications_by_id = {
        application.case_id: application
        for application in applications
    }

    selected_case_id = st.session_state.get(
        MANAGER_SELECTED_CASE_KEY
    )

    if selected_case_id in applications_by_id:
        _show_application_details(
            applications_by_id[selected_case_id]
        )
        return

    st.session_state.pop(MANAGER_SELECTED_CASE_KEY, None)
    _show_application_overview(applications)
