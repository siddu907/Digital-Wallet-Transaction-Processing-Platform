import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app import models  # noqa: F401

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture()
def client():
    Base.metadata.create_all(engine)

    def override_get_db():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def register_and_login(client, email):
    response = client.post("/api/auth/register", json={
        "email": email, "full_name": "Test Customer", "password": "SecureTest123!",
    })
    assert response.status_code == 201, response.text
    response = client.post("/api/auth/login", json={"email": email, "password": "SecureTest123!"})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]
