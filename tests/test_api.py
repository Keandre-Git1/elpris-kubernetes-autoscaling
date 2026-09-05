import datetime

import pandas as pd
import pytest

import application.app as app_module
from application.app import app

# Exempel-svar som elprisetjustnu.se skulle kunna returnera för en dag.
FAKE_API_RESPONSE = pd.DataFrame(
    [
        {"SEK_per_kWh": 0.5, "time_start": "2023-12-01T00:00:00+01:00", "time_end": "2023-12-01T01:00:00+01:00"},
        {"SEK_per_kWh": 0.6, "time_start": "2023-12-01T01:00:00+01:00", "time_end": "2023-12-01T02:00:00+01:00"},
    ]
)


@pytest.fixture
def mock_price_fetch(monkeypatch):
    """Ersätter det riktiga nätverksanropet mot elprisetjustnu.se med testdata.

    Utan detta skulle testerna göra riktiga HTTP-anrop mot en tredjeparts-API
    varje gång pytest körs - långsamt, flakigt och kan trigga rate limiting,
    särskilt i CI. Enhetstester ska inte bero på att en extern tjänst är uppe.
    """
    monkeypatch.setattr(app_module, "_hamta_priser", lambda år, månad, dag, prisklass: FAKE_API_RESPONSE.copy())


# Testar elpris-api:et med giltig region och datum
def test_elpris_valid_input(mock_price_fetch):
    test_app = app.test_client()
    response = test_app.post("/api", data={
        "år": "2023",
        "månad": "12",
        "dag": "01",
        "prisklass": "SE3"
    })
    assert response.status_code == 200
    assert "Elpriset för" in response.data.decode("utf-8")


# Testar elpris-api:et med för gammalt datum
def test_elpris_too_old_date():
    test_app = app.test_client()
    response = test_app.post("/api", data={
        "år": "2022",
        "månad": "10",
        "dag": "31",
        "prisklass": "SE3"
    })
    assert response.status_code == 200
    assert "Datumet får endast vara" in response.data.decode("utf-8")


# Testar elpris-api:et med datum för långt fram i tiden.
# OBS: datumet räknas ut relativt "idag" istället för att hårdkodas (t.ex.
# "2025-12-31"). Ett hårdkodat framtidsdatum blir förr eller senare ett datum
# i det förflutna och testet slutar testa det avsedda scenariot - exakt det
# som hände här när klockan passerade 2025-12-31.
def test_elpris_too_future_date():
    future_date = datetime.date.today() + datetime.timedelta(days=30)
    test_app = app.test_client()
    response = test_app.post("/api", data={
        "år": str(future_date.year),
        "månad": str(future_date.month),
        "dag": str(future_date.day),
        "prisklass": "SE3"
    })
    assert response.status_code == 200
    assert "Datumet får endast vara" in response.data.decode("utf-8")


# Testar elpris-api:et med ogiltigt dagformat
def test_elpris_invalid_day_format():
    test_app = app.test_client()
    response = test_app.post("/api", data={
        "år": "2023",
        "månad": "12",
        "dag": "abc",
        "prisklass": "SE3"
    })
    assert response.status_code == 200
    assert "Försök igen!" in response.data.decode("utf-8")


# Testar elpris-api:et med ogiltig regionkod
def test_elpris_icke_tillganglig_region():
    test_app = app.test_client()
    response = test_app.post("/api", data={
        "år": "2023",
        "månad": "12",
        "dag": "01",
        "prisklass": "SE5"  # ogiltig region
    })
    assert response.status_code == 200
    assert "Ogiltig region" in response.data.decode("utf-8")


# Reflekterad XSS-regression: användarinmatning som hamnar i ett felmeddelande
# ska aldrig renderas som rå HTML (se historik: {{ e|safe }} i templates).
def test_elpris_invalid_day_is_not_reflected_as_html():
    test_app = app.test_client()
    payload = "<script>alert(1)</script>"
    response = test_app.post("/api", data={
        "år": "2023",
        "månad": "12",
        "dag": payload,
        "prisklass": "SE3"
    })
    assert response.status_code == 200
    assert payload not in response.data.decode("utf-8")


# Testar graf-endpoint utan parametrar
def test_graf_missing_info():
    test_app = app.test_client()
    response = test_app.get("/graf")
    assert response.status_code == 400
