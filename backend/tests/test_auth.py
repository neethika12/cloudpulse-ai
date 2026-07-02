def test_signup_and_me(client):
    signup_res = client.post(
        "/api/auth/signup",
        json={"email": "test@example.com", "password": "supersecret123", "full_name": "Test User"},
    )
    assert signup_res.status_code == 200
    token = signup_res.json()["access_token"]

    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    body = me_res.json()
    assert body["email"] == "test@example.com"
    assert body["full_name"] == "Test User"


def test_signup_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    res = client.post("/api/auth/signup", json={"email": "dup@example.com", "password": "password123"})
    assert res.status_code == 400


def test_login_success_and_failure(client):
    client.post("/api/auth/signup", json={"email": "login@example.com", "password": "correcthorse"})

    good = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "correcthorse"}
    )
    assert good.status_code == 200
    assert "access_token" in good.json()

    bad = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "wrongpassword"}
    )
    assert bad.status_code == 401


def test_me_requires_token(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401
