from webapps.portal import oracle_emp


def test_oracle_emp_profile_defaults_to_mpc(monkeypatch):
    monkeypatch.delenv("ORACLE_EMP_DB_PROFILE", raising=False)
    # 還原至一週前版本後，預設應回傳 "MPC"
    assert oracle_emp._oracle_emp_profile() == "MPC"


def test_oracle_emp_profile_honors_explicit_override(monkeypatch):
    monkeypatch.setenv("ORACLE_EMP_DB_PROFILE", "ERP_MPC")
    assert oracle_emp._oracle_emp_profile() == "ERP_MPC"
