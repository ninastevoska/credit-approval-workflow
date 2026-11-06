"""Streamlit interface for credit application referents.

Responsibilities:
- Display new and assigned credit applications.
- Show application details and uploaded PDF documents.
- Offer only permitted workflow actions.
- Support approval, rejection, and supplementation requests.
"""

import streamlit as st

from models import (
    ApplicationStatus,
    CreditApplication,
    CreditRating,
    User,
    UserRole,
)
from services.application_service import (
    list_applications,
    perform_action,
)
from services.file_service import FileStorageError, read_pdf
from services.workflow_service import (
    WorkflowError,
    get_available_actions,
)
from ui.components import format_status, show_application_summary


SUCCESS_MESSAGES = {
    "claim_application": "Uspešno ste prevzeli kreditno vlogo.",
    "review_application": "Pregled kreditne vloge je zaključen.",
    "assess_creditworthiness": "Bonitetna ocena je shranjena.",
    "approve_application": "Kreditna vloga je odobrena.",
    "reject_application": "Kreditna vloga je zavrnjena.",
    "request_completion": "Zahteva za dopolnitev je zabeležena.",
}


def _format_amount(value) -> str:
    """Format a monetary value for display."""
    return f"{value:,.2f}".replace(",", " ") + " €"


def _group_referent_applications(
    applications: list[CreditApplication],
    username: str,
) -> tuple[list[CreditApplication], list[CreditApplication]]:
    """Separate new cases from cases assigned to the referent."""

    new_applications = [
        application
        for application in applications
        if application.assigned_referent is None
        and application.status == ApplicationStatus.VERIFIED
    ]

    my_applications = [
        application
        for application in applications
        if application.assigned_referent == username
    ]

    new_applications.reverse()

    # Show active cases before completed ones.
    my_applications.sort(
        key=lambda application: (
            application.status in {
                ApplicationStatus.APPROVED,
                ApplicationStatus.REJECTED,
            },
            -application.created_at.timestamp(),
        )
    )

    return new_applications, my_applications


def _show_status_badge(application: CreditApplication) -> None:
    """Display a readable, color-coded application status."""

    if application.status == ApplicationStatus.APPROVED:
        st.badge("Odobrena", color="green")

    elif application.status == ApplicationStatus.REJECTED:
        st.badge("Zavrnjena", color="red")

    elif application.current_step == "submit_supplement":
        st.badge("Čaka na dopolnitev", color="orange")

    elif application.assigned_referent is None:
        st.badge("Nova", color="blue")

    else:
        st.badge(
            format_status(application.status.value),
            color="orange",
        )


def _show_application_list(
    applications: list[CreditApplication],
    referent: User,
) -> None:
    """Display selectable lists of applications."""

    st.subheader("Kreditne vloge")

    new_applications, my_applications = _group_referent_applications(
        applications,
        referent.username,
    )

    def show_case_card(application: CreditApplication) -> None:
        """Display one credit application card."""

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
                    f"Stranka: {application.customer_id} | "
                    f"Znesek: {_format_amount(application.requested_amount)}"
                )

                _show_status_badge(application)

            with right:
                if st.button(
                    "Odpri vlogo",
                    key=f"open_referent_case_{application.case_id}",
                    width="stretch",
                ):
                    st.session_state["referent_selected_case"] = (
                        application.case_id
                    )
                    st.rerun()

    st.markdown("### Nove vloge")
    st.caption(f"Čakajo na prevzem: {len(new_applications)}")

    if new_applications:
        for application in new_applications:
            show_case_card(application)
    else:
        st.info("Trenutno ni novih kreditnih vlog.")

    st.markdown("### Moje vloge")
    st.caption(f"Skupaj: {len(my_applications)}")

    if my_applications:
        for application in my_applications:
            show_case_card(application)
    else:
        st.info("Trenutno nimate dodeljenih kreditnih vlog.")


def _show_pdf(application: CreditApplication) -> None:
    """Provide the current application PDF for inspection."""

    with st.expander("Kreditna vloga (PDF)"):
        try:
            pdf_bytes = read_pdf(application.pdf_path)

        except (FileStorageError, OSError):
            st.error("Dokument trenutno ni dostopen.")
            return

        st.download_button(
            "Prenesi PDF-obrazec",
            data=pdf_bytes,
            file_name=f"{application.case_id}_vloga.pdf",
            mime="application/pdf",
            key=f"download_pdf_{application.case_id}",
            width="stretch",
        )


def _perform_referent_action(
    application: CreditApplication,
    step: str,
    referent: User,
    credit_rating: CreditRating | None = None,
) -> None:
    """Execute an allowed action and refresh the interface."""

    try:
        perform_action(
            case_id=application.case_id,
            step=step,
            actor=referent,
            credit_rating=credit_rating,
        )

    except (WorkflowError, ValueError) as exc:
        st.error(f"Zahteve ni mogoče izvesti: {exc}")
        return

    except OSError:
        st.error("Pri shranjevanju je prišlo do napake.")
        return

    st.session_state["referent_action_confirmation"] = (
        referent.username,
        application.case_id,
        step,
    )

    st.rerun()


def _show_actions(
    application: CreditApplication,
    referent: User,
) -> None:
    """Display the workflow actions available to this referent."""

    st.subheader("Obravnava vloge")

    actions = get_available_actions(
        application=application,
        role=referent.role,
        username=referent.username,
    )

    if not actions:
        if application.current_step == "completed":
            st.success("Kreditna vloga je zaključena.")

        elif application.current_step == "submit_supplement":
            st.info(
                "Vloga čaka na dopolnitev stranke. "
                "Po oddaji dopolnitve jo boste lahko ponovno pregledali."
            )

        else:
            st.info("Trenutno ni razpoložljivih dejanj.")

        return

    # Use workflow rules rather than hard-coded status checks.
    allowed_steps = {action.step for action in actions}

    if "claim_application" in allowed_steps:
        st.write(
            "Ta vloga še ni dodeljena. "
            "Prevzemite jo, če jo želite obravnavati."
        )

        if st.button(
            "Prevzemi vlogo",
            type="primary",
            key=f"claim_{application.case_id}",
            width="stretch",
        ):
            _perform_referent_action(
                application,
                "claim_application",
                referent,
            )

    if "review_application" in allowed_steps:
        st.write(
            "Preglejte podatke kreditne vloge in "
            "priloženo dokumentacijo."
        )

        if st.button(
            "Zaključi pregled",
            type="primary",
            key=f"review_{application.case_id}",
            width="stretch",
        ):
            _perform_referent_action(
                application,
                "review_application",
                referent,
            )

    if "assess_creditworthiness" in allowed_steps:
        with st.form(f"assessment_{application.case_id}"):
            rating = st.selectbox(
                "Bonitetna ocena",
                options=list(CreditRating),
                format_func=lambda value: value.value,
            )

            submitted = st.form_submit_button(
                "Shrani bonitetno oceno",
                type="primary",
                width="stretch",
            )

        if submitted:
            _perform_referent_action(
                application,
                "assess_creditworthiness",
                referent,
                credit_rating=rating,
            )

    if "request_completion" in allowed_steps:
        st.markdown("#### Dopolnitev dokumentacije")
        st.write(
            "Če dokumentacija ni ustrezna, lahko zahtevate "
            "dopolnitev. Stranka bo lahko naložila popravljen PDF."
        )

        if st.button(
            "Zahtevaj dopolnitev",
            key=f"request_completion_{application.case_id}",
            width="stretch",
        ):
            _perform_referent_action(
                application,
                "request_completion",
                referent,
            )

    if "approve_application" in allowed_steps:
        st.markdown("#### Odločitev o vlogi")
        st.write(
            "Vloga je pregledana in ocenjena. "
            "S potrditvijo bo odločitev dokončna."
        )

        if st.button(
            "Odobri kreditno vlogo",
            type="primary",
            key=f"approve_{application.case_id}",
            width="stretch",
        ):
            _perform_referent_action(
                application,
                "approve_application",
                referent,
            )

    if "reject_application" in allowed_steps:
        st.markdown("#### Zavrnitev kreditne vloge")

        if st.button(
            "Zavrni kreditno vlogo",
            key=f"reject_{application.case_id}",
            width="stretch",
        ):
            _perform_referent_action(
                application,
                "reject_application",
                referent,
            )


def render_referent_view(user: User) -> None:
    """Render the referent's application overview or selected case."""

    if user.role != UserRole.REFERENT:
        st.error("Ta stran je namenjena referentom.")
        return

    st.title("Obravnava kreditnih vlog")
    st.caption(f"Prijavljeni referent: {user.username}")

    confirmation = st.session_state.pop(
        "referent_action_confirmation",
        None,
    )

    if confirmation is not None:
        username, case_id, step = confirmation

        if username == user.username:
            message = SUCCESS_MESSAGES.get(
                step,
                "Spremembe so shranjene.",
            )
            st.success(f"{case_id}: {message}")

    applications = list_applications()

    owner_key = "referent_selection_owner"
    selection_key = "referent_selected_case"

    # Reset the selection when switching referents.
    if st.session_state.get(owner_key) != user.username:
        st.session_state[owner_key] = user.username
        st.session_state.pop(selection_key, None)

    new_applications, my_applications = _group_referent_applications(
        applications,
        user.username,
    )

    applications_by_id = {
        application.case_id: application
        for application in new_applications + my_applications
    }

    selected_case_id = st.session_state.get(selection_key)

    if selected_case_id not in applications_by_id:
        st.session_state.pop(selection_key, None)
        _show_application_list(applications, user)
        return

    selected = applications_by_id[selected_case_id]

    if st.button(
        "← Nazaj na pregled vlog",
        key="back_to_referent_overview",
        width="content",
    ):
        st.session_state.pop(selection_key, None)
        st.rerun()

    st.subheader(f"Kreditna vloga {selected.case_id}")

    with st.container(border=True):
        show_application_summary(selected)

        if selected.monthly_income is not None:
            st.write(
                "**Mesečni prihodek:** "
                f"{_format_amount(selected.monthly_income)}"
            )

        _show_pdf(selected)

    _show_actions(selected, user)
