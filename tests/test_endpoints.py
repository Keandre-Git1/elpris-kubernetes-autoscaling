from application.app import app


def test_main_page_loads():
    """Startsidan ska svara 200. Ingen körande server krävs - test_client()
    kör requesten direkt mot appen i minnet, vilket gör testet CI-vänligt."""
    test_app = app.test_client()
    response = test_app.get("/")
    assert response.status_code == 200


def test_input_page_has_submit_button():
    test_app = app.test_client()
    response = test_app.get("/input")
    assert response.status_code == 200
    assert "Skicka" in response.data.decode("utf-8")


def test_health_endpoint():
    test_app = app.test_client()
    response = test_app.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_unknown_route_returns_404():
    test_app = app.test_client()
    response = test_app.get("/finns-inte")
    assert response.status_code == 404
