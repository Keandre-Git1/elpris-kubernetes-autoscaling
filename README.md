# Elpris-appen

## Om projektet
Detta är en gruppuppgift i Programmering 2 på Nackademin. Appen visar elpriser per timme baserat på användarens val av datum och region (prisklass). Detta projekt är en utökning på att kombinera containerisering och Kubernetes med hemsidan.

## Funktioner
- Formulär för år, månad, dag och prisklass
- Validering av datum (tidigast 2022-11-01, senast imorgon)
- Hämtar data från elprisetjustnu.se API, med cache för att minska antalet externa anrop
- Visar elpriser i tabell
- Visar elpriser som linjediagram
- 404-sida vid felaktiga länkar
- Health check-endpoint (`/health`) för drift/orkestrering
- Test cases med Pytest (mockar det externa API:et, kräver ingen körande server)

## Installation (utan Docker)

Detta är endast nödvändigt om du vill pröva Flask-webservern utan containerisering.

1. Skapa och aktivera en virtuell miljö (valfritt):
```
python -m venv venv
```
OBS! För Ubuntu och Debian behöver du installera python3-venv:
```
sudo apt update && sudo apt install python3-venv
```
```
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
```

2. Installera requirements:
```
pip install -r requirements.txt
```

3. Starta appen (app.py ligger i application/-mappen, ange sökvägen):
```
flask --app application/app run
```

4. Öppna i webbläsaren: `http://127.0.0.1:5000`

> **Notera:** detta är utvecklingsläget, via Flasks inbyggda dev-server (port 5000, standard). I container/produktion (se nedan) körs appen istället via gunicorn på port **2800** — se avsnittet Docker.

## Health check
`GET /health` returnerar `{"status": "ok"}` — används som liveness/readiness-probe vid drift i Kubernetes.

## Köra tester
```
pytest
```

## Säkerhet
- Anrop mot elprisetjustnu.se görs med `requests` och normal SSL-certifikatverifiering.
- Felmeddelanden till användaren innehåller aldrig rå exception-text eller obehandlad användarinmatning (skyddar mot reflekterad XSS). Fulla stacktraces loggas internt via `logging`, inte till klienten.
- Containern körs som en icke-root-användare (`appuser`), se Dockerfile.

## Förutsättningar (Docker & Kubernetes)

- [Docker](https://docs.docker.com/engine/install/) installerat och körbart utan `sudo` (se [post-install-steg](https://docs.docker.com/engine/install/linux-postinstall/) om `docker ps` ger `permission denied`)
- [minikube](https://minikube.sigs.k8s.io/docs/start/) installerat
- [kubectl](https://kubernetes.io/docs/tasks/tools/) installerat

## Docker

Appen körs i produktion via **gunicorn** (inte Flasks utvecklingsserver) i en containeriserad, icke-root miljö, byggd med en multi-stage Dockerfile för att hålla imagen liten.

Bygg imagen:
```
docker build -t elpris-app:latest .
```

Kör den lokalt:
```
docker run -p 2800:2800 elpris-app:latest
```

Testa:
```
curl http://127.0.0.1:2800/health
```

## Kubernetes

Manifest för drift i Kubernetes finns i `k8s/`:

- **`deployment.yaml`**: kör containern med definierade resursgränser (`requests`/`limits`) och liveness-/readiness-probes mot `/health`.
- **`service.yaml`**: exponerar appen inom (och, via NodePort, utanför) klustret.
- **`hpa.yaml`**: HorizontalPodAutoscaler: skalar mellan 1 och 5 repliker baserat på CPU-användning (mål: 50 % av `requests.cpu`).

### Köra lokalt med minikube

```
minikube start --driver=docker
minikube addons enable metrics-server
minikube image load elpris-app:latest

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

Verifiera:
```
kubectl get pods
kubectl get hpa
minikube service elpris-app-service --url
```

> **Känd begränsning:** cachen för elpriser är in-memory och delas inte mellan repliker, varje pod har sin egen cache. Vid horisontell skalning på riktigt (flera repliker samtidigt) skulle en delad cache (t.ex. Redis) behövas för att undvika redundanta anrop mot det externa API:et.

## Belastningstest och autoskalning

## Mappstruktur

```
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
├── k8s/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── hpa.yaml
├── tests/
│   ├── test_api.py
│   └── test_endpoints.py
├── Dockerfile
├── .dockerignore
├── .gitignore
├── requirements.txt
├── README.md
```
