"""
admin.py — Page d'administration des utilisateurs.

Accessible uniquement aux administrateurs.
"""

import streamlit as st
from core.auth import list_users, create_user, update_user_role, delete_user, change_password

st.set_page_config(
    page_title="🔧 Administration",
    page_icon="🔧",
    layout="wide",
)

# Auth gate
user = st.session_state.get("user")
if user is None:
    st.warning("Veuillez vous connecter depuis la page principale.")
    st.stop()
if user.role != "admin":
    st.error("Accès réservé aux administrateurs.")
    st.stop()

st.markdown("### 🔧 Administration des utilisateurs")
st.caption(f"Connecté en tant que : **{user.display_name}** ({user.role})")

# Liste des utilisateurs
st.markdown("#### Utilisateurs existants")
users = list_users()

if users:
    for u in users:
        col_info, col_role, col_actions = st.columns([3, 2, 2])
        with col_info:
            st.markdown(f"**{u.display_name}** (`{u.username}`) — créé le {u.created_at[:10]}")
        with col_role:
            role_map = {"admin": "🔴 Admin", "formateur": "🟡 Formateur", "utilisateur": "🟢 Utilisateur"}
            st.markdown(role_map.get(u.role, u.role))
        with col_actions:
            if u.username != "admin":
                col_a, col_b = st.columns(2)
                with col_a:
                    new_role = st.selectbox(
                        "Rôle",
                        ["admin", "formateur", "utilisateur"],
                        index=["admin", "formateur", "utilisateur"].index(u.role),
                        key=f"role_{u.username}",
                        label_visibility="collapsed",
                    )
                    if new_role != u.role:
                        if st.button("✅", key=f"save_role_{u.username}", help="Appliquer"):
                            update_user_role(u.username, new_role)
                            st.rerun()
                with col_b:
                    if st.button("🗑️", key=f"del_{u.username}", help="Supprimer"):
                        delete_user(u.username)
                        st.rerun()
        st.divider()

# Créer un utilisateur
st.markdown("#### Créer un utilisateur")
with st.form("create_user_form"):
    col1, col2 = st.columns(2)
    with col1:
        new_username = st.text_input("Nom d'utilisateur")
        new_display = st.text_input("Nom complet")
    with col2:
        new_password = st.text_input("Mot de passe", type="password")
        new_role = st.selectbox("Rôle", ["formateur", "utilisateur", "admin"])

    if st.form_submit_button("Créer l'utilisateur"):
        if not new_username or not new_password or not new_display:
            st.error("Tous les champs sont requis.")
        else:
            result = create_user(new_username, new_display, new_role, new_password)
            if result:
                st.success(f"Utilisateur **{new_username}** créé avec le rôle **{new_role}**.")
                st.rerun()
            else:
                st.error(f"Le nom d'utilisateur **{new_username}** existe déjà.")

# Changer un mot de passe
st.markdown("#### Changer un mot de passe")
with st.form("change_password_form"):
    target_user = st.selectbox("Utilisateur", [u.username for u in users], key="pwd_target")
    new_pwd = st.text_input("Nouveau mot de passe", type="password", key="new_pwd")
    if st.form_submit_button("Changer le mot de passe"):
        if not new_pwd:
            st.error("Le mot de passe ne peut pas être vide.")
        else:
            change_password(target_user, new_pwd)
            st.success(f"Mot de passe de **{target_user}** mis à jour.")
