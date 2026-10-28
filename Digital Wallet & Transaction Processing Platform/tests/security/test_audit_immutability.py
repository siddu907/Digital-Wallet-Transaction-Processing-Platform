from tests.conftest import register_and_login


def test_audit_log_has_no_mutation_api(client):
    token = register_and_login(client, "audit-immutability@example.com")
    response = client.delete("/api/admin/audit-logs/any-id", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 405
