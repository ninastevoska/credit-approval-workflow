"""Streamlit interface for credit application customers.

Responsibilities:
- Display the customer's own credit applications.
- Allow explicit navigation between overview and details.
- Provide a form for submitting a new credit application.
- Show user-friendly confirmation and error messages.

Workflow execution, event logging, and PDF storage are handled
by the service layer, not by this module.
"""

from decimal import Decimal

import streamlit as st

from config import MAX_PDF_SIZE_BYTES
from models import CreditApplication, User, UserRole
from services.application_service import (
    list_applications,
    submit_application_with_pdf,
)
from services.file_service import FileStorageError
from services.workflow_service import WorkflowError
from ui.components import format_status, show_application_summary


CUSTOMER_PAGE_KEY = "customer_current_page"
CUSTOMER_CASE_KEY = "customer_selected_case"


def _format_amount(application: CreditApplication) -> str:
    """Format the requested credit amount."""
    amount = f"{application.requested_amount:,.2f}"
    return amount.replace(",", " ") + " €"


def _navigate(page: str, case_id: str | None = None) -> None:
    """Change the customer page without modifying process data."""
    st.session_state[CUSTOMER_PAGE_KEY] = page

    if case_id is None:
        st.session_state.pop(CUSTOMER_CASE_KEY, None)
    else:
        st.session_state[CUSTOMER_CASE_KEY] = case_id

    st.rerun()


def _show_customer_overview(
    applications: list[CreditApplication],
) -> None:
    """Display the customer's applications and navigation options."""
    st.subheader("Moje kreditne vloge")

    if st.button(
        "Nova kreditna vloga",
        type="primary",
        key="customer_new_application",
    ):
        _navigate("new")

    if not applications:
        st.info("Trenutno še nimate oddanih kreditnih vlog.")
        return

    # Display the newest applications first.
    for application in reversed(applications):
        with st.container(border=True):
            left, right = st.columns(
                [3, 1],
                vertical_alignment="center",
            )

            with left:
                st.markdown(f"**{application.case_id}**")
                st.write(application.loan_purpose)

                st.caption(
                    f"{_format_amount(application)}  |  "
                    f"{format_status(application.status.value)}"
                )

            with right:
                if st.button(
                    "Podrobnosti",
                    key=f"customer_open_{application.case_id}",
                    width="stretch",
                ):
                    _navigate("details", application.case_id)


def _show_application_details(
    application: CreditApplication,
) -> None:
    """Display the selected application without the technical event log."""
    if st.button(
        "← Nazaj na moje vloge",
        key="customer_back_from_details",
    ):
        _navigate("overview")

    st.subheader(f"Podrobnosti vloge {application.case_id}")

    with st.container(border=True):
        show_application_summary(application)

    if application.current_step == "completed":
        st.success("Vaša kreditna vloga je odobrena.")

    elif application.assigned_referent is None:
        st.info(
            "Vaša kreditna vloga je prejeta in čaka na obravnavo."
        )

    else:
        st.info(
            "Vašo kreditno vlogo obravnava pristojni referent."
        )


def _show_submission_form(customer: User) -> None:
    """Display and process the new credit application form."""
    if st.button(
        "← Nazaj na moje vloge",
        key="customer_back_from_form",
    ):
        _navigate("overview")

    st.subheader("Nova kreditna vloga")
    st.write(
        "Izpolnite podatke in priložite dokazilo o prihodkih."
    )

    with st.form(
        "credit_application_form",
        clear_on_submit=True,
    ):
        amount = st.number_input(
            "Zaprošeni znesek (€)",
            min_value=1.0,
            value=1000.0,
            step=100.0,
            format="%.2f",
        )

        purpose = st.text_area(
            "Namen kredita",
            placeholder="Opišite namen kredita.",
            max_chars=500,
        )

        uploaded_pdf = st.file_uploader(
            "Dokazilo o prihodkih (PDF)",
            type=["pdf"],
            help="Obvezna priloga. Največ 10 MiB.",
        )

        submitted = st.form_submit_button(
            "Oddaj kreditno vlogo",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    if not purpose.strip():
        st.error("Vnesite namen kredita.")
        return

    if uploaded_pdf is None:
        st.error("Priložite dokazilo o prihodkih v obliki PDF.")
        return

    # Validate size before passing the content to the service.
    if uploaded_pdf.size > MAX_PDF_SIZE_BYTES:
        st.error("Datoteka presega dovoljeno velikost 10 MiB.")
        return

    try:
        application = submit_application_with_pdf(
            customer=customer,
            requested_amount=Decimal(str(amount)),
            loan_purpose=purpose.strip(),
            pdf_filename=uploaded_pdf.name,
            pdf_content=uploaded_pdf.getvalue(),
        )

    except (ValueError, WorkflowError, FileStorageError) as exc:
        st.error(f"Kreditne vloge ni mogoče oddati: {exc}")
        return

    except OSError:
        st.error(
            "Pri shranjevanju je prišlo do težave. "
            "Poskusite ponovno."
        )
        return

    st.session_state["customer_submission_confirmation"] = (
        customer.username,
        application.case_id,
    )

    # Open the newly submitted application automatically.
    _navigate("details", application.case_id)


def render_customer_view(user: User) -> None:
    """Render the customer overview, details, or submission form."""
    if user.role != UserRole.CUSTOMER:
        st.error("Ta stran je namenjena strankam.")
        return

    st.title("Moje kreditne vloge")
    st.caption(f"Prijavljena stranka: {user.username}")

    # Clear customer navigation when the logged-in identity changes.
    owner_key = "customer_page_owner"

    if st.session_state.get(owner_key) != user.username:
        st.session_state[owner_key] = user.username
        st.session_state[CUSTOMER_PAGE_KEY] = "overview"
        st.session_state.pop(CUSTOMER_CASE_KEY, None)

    confirmation = st.session_state.pop(
        "customer_submission_confirmation",
        None,
    )

    if confirmation is not None:
        username, case_id = confirmation

        if username == user.username:
            st.success(
                f"Kreditna vloga {case_id} je bila uspešno oddana."
            )

    applications = [
        application
        for application in list_applications()
        if application.customer_id == user.username
    ]

    page = st.session_state.get(
        CUSTOMER_PAGE_KEY,
        "overview",
    )

    if page == "new":
        _show_submission_form(user)
        return

    if page == "details":
        selected_case_id = st.session_state.get(
            CUSTOMER_CASE_KEY
        )

        selected_application = next(
            (
                application
                for application in applications
                if application.case_id == selected_case_id
            ),
            None,
        )

        if selected_application is not None:
            _show_application_details(selected_application)
            return

        # Return to overview if the selected case is not available.
        st.session_state[CUSTOMER_PAGE_KEY] = "overview"
        st.session_state.pop(CUSTOMER_CASE_KEY, None)

    _show_customer_overview(applications)
