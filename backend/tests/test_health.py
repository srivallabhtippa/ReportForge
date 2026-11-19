def test_health_says_the_process_is_alive(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_proves_the_database_works(client):
    response = client.get("/health/db")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_does_not_leak_database_details(client):
    # The endpoint is public. Anyone can call it, so it must say nothing about the
    # database user, database name or version.
    text = client.get("/health/db").text.lower()

    assert "reportforge" not in text
    assert "postgres" not in text
