"""Streamlit interface for credit application customers.

Responsibilities:
- Display the customer's own credit applications.
- Submit interactive PDF credit applications.
- Supplement existing applications with corrected PDFs.
- Show application details and user-friendly messages.

Business rules, PDF validation, and database operations
are handled by the service layer.
"""

from pathlib import Path

import streamlit as st

from config import MAX_PDF_SIZE_BYTES
from models import (
    ApplicationStatus,
    CreditApplication,
    User,
    UserRole,
)
from services.application_service import (
    list_applications,
    submit_application_supplement,
    submit_application_with_pdf,
)
from services.file_service import FileStorageError
from services.pdf_form_service import (
    PDFFormValidationError,
    read_credit_form,
)
from services.workflow_service import WorkflowError
from ui.components import format_status, show_application_summary


CUSTOMER_PAGE_KEY = "customer_current_page"
CUSTOMER_CASE_KEY = "customer_selected_case"

FORM_TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "forms"
    / "kreditna_vloga_predloga.pdf"
)


def _format_amount(application: CreditApplication) -> str:
    """Format the requested credit amount."""
    amount = f"{application.requested_amount:,.2f}"
    return amount.replace(",", " ") + " €"


def _navigate(page: str, case_id: str | None = None) -> None:
    """Navigate without modifying application data."""
    st.session_state[CUSTOMER_PAGE_KEY] = page

    if case_id is None:
        st.session_state.pop(CUSTOMER_CASE_KEY, None)
    else:
        st.session_state[CUSTOMER_CASE_KEY] = case_id

    st.rerun()


def _show_pdf_template() -> None:
    """Allow customers to download the interactive PDF template."""

    st.write(
        "Prenesite obrazec, izpolnite obvezna polja "
        "in shranite izpolnjen PDF."
    )

    try:
        template = FORM_TEMPLATE_PATH.read_bytes()
    except OSError:
        st.error("Predloga kreditne vloge trenutno ni na voljo.")
        return

    st.download_button(
        label="Prenesi obrazec kreditne vloge",
        data=template,
        file_name="kreditna_vloga.pdf",
        mime="application/pdf",
        key="download_credit_form_template",
        width="stretch",
    )


def _read_uploaded_form(uploaded_pdf):
    """Validate an uploaded PDF and return its extracted data."""

    if uploaded_pdf is None:
        st.error("Naložite izpolnjen PDF-obrazec.")
        return None

    if uploaded_pdf.size > MAX_PDF_SIZE_BYTES:
        st.error("PDF presega dovoljeno velikost 10 MiB.")
        return None

    if not uploaded_pdf.name.lower().endswith(".pdf"):
        st.error("Dovoljene so samo datoteke PDF.")
        return None

    try:
        return read_credit_form(uploaded_pdf.getvalue())
    except PDFFormValidationError as exc:
        st.error(f"PDF-obrazec ni pravilno izpolnjen: {exc}")
        return None


def _show_customer_overview(
    applications: list[CreditApplication],
) -> None:
    """Display applications belonging to the current customer."""

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

                if application.current_step == "submit_supplement":
                    st.warning("Potrebna je dopolnitev vloge.")

            with right:
                if st.button(
                    "Podrobnosti",
                    key=f"customer_open_{application.case_id}",
                    width="stretch",
                ):
                    _navigate("details", application.case_id)


def _show_supplement_form(
    application: CreditApplication,
    customer: User,
) -> None:
    """Allow the application owner to provide a corrected PDF."""

    st.subheader("Dopolnitev kreditne vloge")

    st.info(
        "Referent je zahteval dopolnitev. "
        "Popravite obrazec in naložite novo različico PDF-ja."
    )

    _show_pdf_template()

    with st.form(f"supplement_form_{application.case_id}"):
        uploaded_pdf = st.file_uploader(
            "Dopolnjen PDF-obrazec",
            type=["pdf"],
            key=f"supplement_pdf_{application.case_id}",
        )

        submitted = st.form_submit_button(
            "Oddaj dopolnitev",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    form_data = _read_uploaded_form(uploaded_pdf)

    if form_data is None:
        return

    try:
        updated = submit_application_supplement(
            case_id=application.case_id,
            customer=customer,
            pdf_filename=uploaded_pdf.name,
            pdf_content=uploaded_pdf.getvalue(),
        )

    except (
        ValueError,
        WorkflowError,
        PDFFormValidationError,
        FileStorageError,
    ) as exc:
        st.error(f"Dopolnitve ni mogoče oddati: {exc}")
        return

    except OSError:
        st.error("Pri shranjevanju dopolnitve je prišlo do napake.")
        return

    st.session_state["customer_supplement_confirmation"] = (
        customer.username,
        updated.case_id,
    )

    _navigate("details", updated.case_id)


def _show_application_details(
    application: CreditApplication,
    customer: User,
) -> None:
    """Display one application and its available customer actions."""

    if st.button(
        "← Nazaj na moje vloge",
        key="customer_back_from_details",
    ):
        _navigate("overview")

    st.subheader(f"Podrobnosti vloge {application.case_id}")

    with st.container(border=True):
        show_application_summary(application)

        if application.monthly_income is not None:
            st.write(
                "**Mesečni prihodek:** "
                f"{_format_decimal(application.monthly_income)} €"
            )

    if application.current_step == "submit_supplement":
        _show_supplement_form(application, customer)

    elif application.status == ApplicationStatus.APPROVED:
        st.success("Vaša kreditna vloga je odobrena.")

    elif application.status == ApplicationStatus.REJECTED:
        st.error("Vaša kreditna vloga je zavrnjena.")

    elif application.assigned_referent is None:
        st.info(
            "Vaša kreditna vloga je prejeta in čaka na obravnavo."
        )

    else:
        st.info(
            "Vašo kreditno vlogo obravnava pristojni referent."
        )


def _format_decimal(value) -> str:
    """Format a decimal amount for display."""

    return f"{value:,.2f}".replace(",", " ")


def _show_submission_form(customer: User) -> None:
    """Submit a new credit application using an interactive PDF."""

    if st.button(
        "← Nazaj na moje vloge",
        key="customer_back_from_form",
    ):
        _navigate("overview")

    st.subheader("Nova kreditna vloga")

    _show_pdf_template()

    with st.form(
        "credit_application_form",
        clear_on_submit=True,
    ):
        uploaded_pdf = st.file_uploader(
            "Izpolnjen PDF-obrazec",
            type=["pdf"],
            help="Obvezno. Največ 10 MiB.",
        )

        submitted = st.form_submit_button(
            "Oddaj kreditno vlogo",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return

    form_data = _read_uploaded_form(uploaded_pdf)

    if form_data is None:
        return

    try:
        application = submit_application_with_pdf(
            customer=customer,
            requested_amount=form_data.zaprosen_znesek,
            loan_purpose=form_data.namen_kredita,
            pdf_filename=uploaded_pdf.name,
            pdf_content=uploaded_pdf.getvalue(),
            monthly_income=form_data.mesecni_prihodek,
        )

    except (
        ValueError,
        WorkflowError,
        PDFFormValidationError,
        FileStorageError,
    ) as exc:
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

    _navigate("details", application.case_id)


def render_customer_view(user: User) -> None:
    """Render the customer overview, details, or submission page."""

    if user.role != UserRole.CUSTOMER:
        st.error("Ta stran je namenjena strankam.")
        return

    st.title("Moje kreditne vloge")
    st.caption(f"Prijavljena stranka: {user.username}")

    # Reset navigation when the identity changes.
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

    supplement_confirmation = st.session_state.pop(
        "customer_supplement_confirmation",
        None,
    )

    if supplement_confirmation is not None:
        username, case_id = supplement_confirmation

        if username == user.username:
            st.success(
                f"Dopolnitev vloge {case_id} je bila uspešno oddana."
            )

    applications = [
        application
        for application in list_applications()
        if application.customer_id == user.username
    ]

    page = st.session_state.get(CUSTOMER_PAGE_KEY, "overview")

    if page == "new":
        _show_submission_form(user)
        return

    if page == "details":
        selected_case_id = st.session_state.get(CUSTOMER_CASE_KEY)

        selected_application = next(
            (
                application
                for application in applications
                if application.case_id == selected_case_id
            ),
            None,
        )

        if selected_application is not None:
            _show_application_details(selected_application, user)
            return

        st.session_state[CUSTOMER_PAGE_KEY] = "overview"
        st.session_state.pop(CUSTOMER_CASE_KEY, None)

    _show_customer_overview(applications)
