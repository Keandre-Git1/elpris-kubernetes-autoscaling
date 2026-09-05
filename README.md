Flask-app

Om projektet
Detta är en individuell uppgift i Programmering 2 på Nackademin. Appen visar elpriser per timme baserat på användarens val av datum och region (prisklass).

Funktioner
- Formulär för år, månad, dag och prisklass
- Validering av datum (tidigast 2022-11-01, senast imorgon)
- Hämtar data från elprisetjustnu.se API
- Visar elpriser i tabell
- Visar elpriser som linjediagram
- 404-sida vid felaktiga länkar
- Test cases med Pytest

Installation
1. Skapa och aktivera ett virtuellt miljö (valfritt):
python -m venv venv
OBS! För Ubuntu och Debian behöver du installera python3-venv
    sudo apt update && sudo apt install python3-venv

source venv/bin/activate  # Mac/Linux 
venv\Scripts\activate     # Windows

2. Installera requirements:
pip install -r requirements.txt

3. Starta appen (app.py ligger i application/-mappen, ange sökvägen):
flask --app application/app run

4. Öppna i webbläsaren: `http://127.0.0.1:5000`

Health check
- `GET /health` returnerar `{"status": "ok"}` - används t.ex. som liveness/readiness-probe vid drift i Kubernetes.

Köra tester
pytest

Säkerhet
- Anrop mot elprisetjustnu.se görs med `requests` och normal SSL-certifikatverifiering (ingen `ssl._create_unverified_context()`).
- Felmeddelanden till användaren innehåller aldrig rå exception-text eller obehandlad användarinmatning (skyddar mot reflekterad XSS). Fulla stacktraces loggas internt via `logging`, inte till klienten.


Mappstruktur
├── application/
│   ├── app.py
│   ├── data/
│   ├── static/
│   │   ├── css/
│   │   ├── images/
│   │   └── js/
│   ├── templates/
│   │   ├── 404.html
│   │   ├── enter.html
│   │   ├── footer.html
│   │   ├── header.html
│   │   ├── layout.html
│   │   ├── main.html
│   │   └── post_enter.html
├── tests/
│   ├── test_api.py
│   └── test_endpoints.py
├── requirements.txt
├── README.md
