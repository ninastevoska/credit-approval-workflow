"""Streamlit interface for credit application referents.

Responsibilities:
- Display a selectable list of credit applications.
- Open application details only after selection.
- Display the attached PDF document.
- Offer actions allowed by the workflow service.
- Show user-friendly confirmation messages.

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


# Messages describe the result, not the internal workflow step.
SUCCESS_MESSAGES = {
    "claim_application": "Uspešno ste prevzeli kreditno vlogo.",
    "review_application": "Pregled kreditne vloge je zaključen.",
    "assess_creditworthiness": "Bonitetna ocena je shranjena.",
    "approve_application": "Kreditna vloga je odobrena.",
}


def _format_amount(application: CreditApplication) -> str:
    """Format the requested amount for the user interface."""
    return f"{application.requested_amount:,.2f}".replace(
        ",", " "
    ) + " €"


def _group_referent_applications(
    applications: list[CreditApplication],
    username: str,
) -> tuple[list[CreditApplication], list[CreditApplication]]:
    """Separate unassigned applications from this referent's cases.

    Applications assigned to other referents are excluded.
    """
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

    # Newest first; keep active cases before completed ones.
    new_applications.reverse()

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
    """Display a readable and color-coded application status."""
    if application.status == ApplicationStatus.APPROVED:
        st.badge("Odobrena", color="green")

    elif application.status == ApplicationStatus.REJECTED:
        st.badge("Zavrnjena", color="red")

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
) -> CreditApplication | None:
    """Display new applications and applications assigned to this referent."""
    st.subheader("Kreditne vloge")

    selection_key = "referent_selected_case"

    new_applications, my_applications = _group_referent_applications(
        applications,
        referent.username,
    )

    def show_case_card(application: CreditApplication) -> None:
        """Display one application with its status and open button."""
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
                    f"Znesek: {_format_amount(application)}"
                )

                _show_status_badge(application)

            with right:
                if st.button(
                    "Odpri vlogo",
                    key=f"open_referent_case_{application.case_id}",
                    width="stretch",
                ):
                    st.session_state[selection_key] = application.case_id
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

    return None



def _show_pdf(application: CreditApplication) -> None:
    """Provide the application document for inspection."""
    with st.expander("Dokazilo o prihodkih (PDF)"):
        try:
            pdf_bytes = read_pdf(application.pdf_path)
        except (FileStorageError, OSError):
            st.error("Dokument trenutno ni dostopen.")
            return

        st.download_button(
            "Prenesi dokument",
            data=pdf_bytes,
            file_name=f"{application.case_id}_dokazilo.pdf",
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
    """Execute one business action and refresh the application."""
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
    """Display available actions using the workflow rules."""
    st.subheader("Obravnava vloge")

    actions = get_available_actions(
        application=application,
        role=referent.role,
        username=referent.username,
    )

    if not actions:
        if application.current_step == "completed":
            st.success("Kreditna vloga je zaključena.")
        elif (
            application.assigned_referent is not None
            and application.assigned_referent != referent.username
        ):
            st.info(
                "Vlogo trenutno obravnava drug referent."
            )
        elif application.current_step == "approve_application":
            st.warning(
                "Vloge ni mogoče neposredno odobriti. "
                "Preverite znesek in bonitetno oceno. "
                "Za druge odločitve bo potrebna razširitev procesa."
            )
        else:
            st.info("Trenutno ni razpoložljivih dejanj.")
        return

    for action in actions:
        if action.step == "claim_application":
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
                    application, action.step, referent
                )

        elif action.step == "review_application":
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
                    application, action.step, referent
                )

        elif action.step == "assess_creditworthiness":
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
                    action.step,
                    referent,
                    credit_rating=rating,
                )

        elif action.step == "approve_application":
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
                    application, action.step, referent
                )



def render_referent_view(user: User) -> None:
    """Render the referent's application list or selected case."""
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
                step, "Spremembe so shranjene."
            )
            st.success(f"{case_id}: {message}")

    applications = list_applications()

    # Keep the selection specific to the currently logged-in user.
    owner_key = "referent_selection_owner"
    selection_key = "referent_selected_case"

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

    # If no case is selected, display the main overview.
    if selected_case_id not in applications_by_id:
        st.session_state.pop(selection_key, None)
        _show_application_list(applications, user)
        return

    # A case has been selected: display only its details.
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
        _show_pdf(selected)

    _show_actions(selected, user)
