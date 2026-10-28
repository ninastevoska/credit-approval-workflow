"""Reusable Streamlit interface components.

Responsibilities:
- Select the current user and their role.
- Display credit application information.
- Display the event history of an application.

"""

import streamlit as st

from models import CreditApplication, ProcessEvent, User, UserRole


ROLE_LABELS = {
    UserRole.CUSTOMER: "Stranka",
    UserRole.REFERENT: "Referent",
    UserRole.MANAGER: "Vodja",
}


STATUS_LABELS = {
    "oddana": "Oddana",
    "preverjena": "Preverjena",
    "v_pregledu": "V pregledu",
    "v_dopolnitvi": "V dopolnitvi",
    "dopolnjena": "Dopolnjena",
    "ocenjena": "Ocenjena",
    "pri_vodji": "Pri vodji",
    "odlocitev_sprejeta": "Odločitev sprejeta",
    "odobrena": "Odobrena",
    "zavrnjena": "Zavrnjena",
}


def format_status(status: str) -> str:
    """Return a readable Slovenian label for a process status."""
    return STATUS_LABELS.get(status, status)


def _logout() -> None:
    """End the current UI session and reset user-related state.

    The database and saved applications are not affected.
    """
    keys_to_clear = (
        "active_user",
        "login_username",
        "login_role",
        "selected_role",
        "selected_username",
        "customer_submission_confirmation",
        "referent_action_confirmation",
        "referent_selected_case",
        "manager_selected_case",
    )

    for key in keys_to_clear:
        st.session_state.pop(key, None)



def select_user() -> User | None:
    """Manage a simple login/logout interface in the sidebar.

    Authentication is simulated as required by Assignment 4:
    users select their own identity and role, without passwords.

    Once logged in, the selected identity remains fixed until
    the user explicitly logs out.
    """
    with st.sidebar:
        st.header("Uporabnik")

        # Check whether this Streamlit session has a logged-in user.
        active_user = st.session_state.get("active_user")

        if active_user is not None:
            st.write(f"**{active_user.username}**")
            st.caption(ROLE_LABELS[active_user.role])

            st.button(
                "Odjavi se",
                on_click=_logout,
                width="content",
                key="logout_button",
            )

            return active_user

        # The login form is displayed only when no user is active.
        with st.form("login_form"):
            role = st.selectbox(
                "Vloga",
                options=list(ROLE_LABELS.keys()),
                format_func=lambda value: ROLE_LABELS[value],
                key="login_role",
            )

            username = st.text_input(
                "Uporabniško ime",
                placeholder="npr. miha.p",
                key="login_username",
            )

            submitted = st.form_submit_button(
                "Prijavi se",
                type="primary",
                width="stretch",
            )

        if submitted:
            username = username.strip()

            if not username:
                st.error("Vnesi uporabniško ime.")
                return None

            st.session_state["active_user"] = User(
                username=username,
                role=role,
            )

            st.rerun()

        st.caption(
            "Za prijavo izberi vlogo in vnesi uporabniško ime."
        )

    return None



def show_application_summary(application: CreditApplication) -> None:
    """Display the main attributes of a credit application."""
    st.subheader(f"Kreditna vloga {application.case_id}")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Zaprošeni znesek",
            f"{application.requested_amount:,.2f} €",
        )

    with col2:
        st.metric(
            "Status",
            format_status(application.status.value),
        )

    with col3:
        st.metric(
            "Bonitetna ocena",
            (
                application.credit_rating.value
                if application.credit_rating is not None
                else "Ni določena"
            ),
        )

    st.write(f"**Stranka:** {application.customer_id}")
    st.write(f"**Namen kredita:** {application.loan_purpose}")

    st.write(
        "**Dodeljeni referent:** "
        f"{application.assigned_referent or 'Še ni dodeljen'}"
    )

    st.caption(
        "Datum oddaje: "
        f"{application.created_at.strftime('%d. %m. %Y %H:%M:%S')}"
    )


def show_event_history(events: list[ProcessEvent]) -> None:
    """Display the chronological activity history of one case."""
    st.subheader("Zgodovina aktivnosti")

    if not events:
        st.info("Za to kreditno vlogo še ni zabeleženih dogodkov.")
        return

    rows = []

    for event in events:
        rows.append(
            {
                "Čas": event.timestamp.strftime(
                    "%d. %m. %Y %H:%M:%S"
                ),
                "Aktivnost": event.activity,
                "Izvajalec": event.resource,
                "Vloga": event.role.value,
                "Status": format_status(event.status.value),
                "Boniteta": (
                    event.bonitetna_ocena.value
                    if event.bonitetna_ocena is not None
                    else "—"
                ),
            }
        )

    st.dataframe(
        rows,
        width="stretch",
        hide_index=True,
    )
