import streamlit as st
import requests
from typing import Optional


st.set_page_config(page_title="AI Gateway — Demo", layout="wide")

if "token" not in st.session_state:
    st.session_state.token = None
if "username" not in st.session_state:
    st.session_state.username = None
if "base_url" not in st.session_state:
    st.session_state.base_url = "http://localhost:8000"
if "base_url_input" not in st.session_state:
    # initialize the input key so direct script runs don't fail
    st.session_state.base_url_input = st.session_state.base_url


def login(base_url: str, username: str, password: str) -> Optional[str]:
    try:
        resp = requests.post(
            f"{base_url.rstrip('/')}/token",
            data={"username": username, "password": password},
            timeout=10,
        )
    except Exception as e:
        st.error(f"Network error: {e}")
        return None

    if resp.status_code == 200:
        data = resp.json()
        return data.get("access_token")
    else:
        try:
            err = resp.json()
        except Exception:
            err = resp.text
        st.error(f"Login failed: {err}")
        return None


def get_me(base_url: str, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base_url.rstrip('/')}/users/me/", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        return None
    return None


def fetch_audit_logs(base_url: str, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base_url.rstrip('/')}/audit_logs", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            try:
                st.error(r.json())
            except Exception:
                st.error(r.text)
            return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None


def fetch_policies(base_url: str, token: str):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.get(f"{base_url.rstrip('/')}/admin/policies", headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
        else:
            try:
                st.error(r.json())
            except Exception:
                st.error(r.text)
            return None
    except Exception as e:
        st.error(f"Network error: {e}")
        return None


def create_policy_api(base_url: str, token: str, payload: dict):
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{base_url.rstrip('/')}/admin/policies", json=payload, headers=headers, timeout=10)
        return r
    except Exception as e:
        st.error(f"Network error: {e}")
        return None


def delete_policy_api(base_url: str, token: str, policy_id: int):
    headers = {"Authorization": f"Bearer {token}"}
    try:
        r = requests.delete(f"{base_url.rstrip('/')}/admin/policies/{policy_id}", headers=headers, timeout=10)
        return r
    except Exception as e:
        st.error(f"Network error: {e}")
        return None


def send_prompt(base_url: str, token: str, prompt: str, model: Optional[str] = None):
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"prompt": prompt}
    if model:
        payload["model"] = model
    try:
        r = requests.post(f"{base_url.rstrip('/')}/prompt", json=payload, headers=headers, timeout=60)
    except Exception as e:
        st.error(f"Network error: {e}")
        return None
    if r.status_code == 200:
        return r.json()
    else:
        try:
            st.error(r.json())
        except Exception:
            st.error(r.text)
        return None


with st.sidebar:
    st.title("AI Gateway Demo")
    st.text_input("Backend base URL", value=st.session_state.base_url, key="base_url_input")
    # propagate the input to the canonical `base_url` value
    st.session_state.base_url = st.session_state.get("base_url_input", st.session_state.base_url)
    st.markdown("---")
    if st.session_state.token:
        st.write(f"Logged in as **{st.session_state.username}**")
        # fetch current user info once
        if "me" not in st.session_state:
            st.session_state.me = get_me(st.session_state.base_url, st.session_state.token)
        me = st.session_state.get("me")
        if me and me.get("role") == "admin":
            if st.button("Fetch audit logs"):
                logs = fetch_audit_logs(st.session_state.base_url, st.session_state.token)
                if logs is not None:
                    st.subheader("Audit logs")
                    try:
                        import pandas as pd
                        df = pd.DataFrame(logs)
                        st.dataframe(df)
                    except Exception:
                        st.write(logs)
            # Policy management UI
            with st.expander("Policy management"):
                st.markdown("Create a new policy rule:")
                col_a, col_b = st.columns(2)
                with col_a:
                    effect = st.selectbox("Effect", options=["deny", "allow"], index=0, key="policy_effect")
                    resource = st.text_input("Resource (e.g. prompt)", value="prompt", key="policy_resource")
                    action = st.text_input("Action (e.g. create)", value="create", key="policy_action")
                with col_b:
                    target_role = st.text_input("Target role (optional)", value="", key="policy_target_role")
                    target_department = st.text_input("Target department (optional)", value="", key="policy_target_dept")
                    if st.button("Create policy"):
                        payload = {
                            "effect": effect,
                            "resource": resource or None,
                            "action": action or None,
                            "target_role": target_role or None,
                            "target_department": target_department or None,
                        }
                        resp = create_policy_api(st.session_state.base_url, st.session_state.token, payload)
                        if resp is not None and resp.status_code == 200:
                            st.success("Policy created")
                            st.rerun()
                        else:
                            st.error(f"Could not create policy: {getattr(resp, 'text', str(resp))}")

                st.markdown("Existing policies:")
                policies = fetch_policies(st.session_state.base_url, st.session_state.token)
                if policies:
                    for p in policies:
                        c1, c2, c3, c4 = st.columns([1, 2, 2, 1])
                        c1.write(p.get("id"))
                        c2.write(f"{p.get('effect')} {p.get('resource') or '*'}:{p.get('action') or '*'}")
                        c3.write(f"role={p.get('target_role')}, dept={p.get('target_department')}")
                        if c4.button("Delete", key=f"del_{p.get('id')}"):
                            dresp = delete_policy_api(st.session_state.base_url, st.session_state.token, p.get('id'))
                            if dresp is not None and dresp.status_code == 200:
                                st.success("Deleted")
                                st.rerun()
                            else:
                                st.error(f"Delete failed: {getattr(dresp, 'text', str(dresp))}")
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.username = None
            st.rerun()
    else:
        st.subheader("Login")
        user = st.text_input("Username", key="username_input")
        pwd = st.text_input("Password", type="password", key="password_input")
        if st.button("Login"):
            token = login(st.session_state.base_url, user, pwd)
            if token:
                st.session_state.token = token
                st.session_state.username = user
                st.success("Logged in")
                st.rerun()


st.title("Prompt playground")

col1, col2 = st.columns([3, 1])

with col1:
    prompt = st.text_area("Prompt", height=300, key="prompt_input")
    model = st.selectbox("Model", options=["gpt-3.5-turbo", "gpt-4"], index=0)
    submit = st.button("Send prompt")

with col2:
    st.markdown("### Info")
    if st.session_state.token:
        st.markdown(f"**User:** {st.session_state.username}")
    else:
        st.markdown("Not logged in — responses will be rejected by the backend")
    st.markdown("---")
    st.markdown("### Last result")
    if "last_result" in st.session_state and st.session_state.last_result:
        res = st.session_state.last_result
        st.markdown(f"**Model:** {res.get('model')}")
        st.markdown(f"**Tokens used:** {res.get('tokens_used')}")
        st.markdown(f"**Cost (USD):** ${res.get('cost_usd', 0):.6f}")


if submit:
    if not prompt.strip():
        st.warning("Please enter a prompt before submitting.")
    elif not st.session_state.token:
        st.warning("Please login first using the sidebar.")
    else:
        with st.spinner("Sending prompt to backend..."):
            result = send_prompt(st.session_state.base_url, st.session_state.token, prompt, model)
        if result:
            st.session_state.last_result = result
            # Response preview area
            st.subheader("Response preview")
            llm_text = result.get("llm_response") or result.get("response") or result.get("message")
            st.text_area("LLM response", value=llm_text, height=300)

            # Show metadata
            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            c1.metric("Tokens used", value=result.get("tokens_used", "-"))
            c2.metric("Cost (USD)", value=f"${result.get('cost_usd', 0):.6f}")
            c3.text("Model:\n" + str(result.get("model", "-")))
