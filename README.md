# Elpris-appen

## Om projektet

Det här är en gruppuppgift från gammal kurs (Programmering 2) på Nackademin. Här är grunden: en Flask-app där man kan välja datum och region och få tillbaka elpriset per timme, både som tabell och som graf.

Jag valde att bygga vidare på denna uppgift som ett sätt att öva på just auto scaling med kubernetes och containerisering med Docker. Så det som ligger i det här repot är egentligen två saker: en gammal gruppuppgift, och ett eget projekt ovanpå den.

## Funktioner

- Formulär för år, månad, dag och prisklass
- Datumvalidering (tidigast 2022-11-01, senast imorgon api:et har inte data längre bak eller fram i tiden)
- Hämtar elpriser från [elprisetjustnu.se](https://www.elprisetjustnu.se/elpris-api)
- Cachar svaren en timme för att inte slösa på deras resurser i onödan
- Visar priserna i en tabell och som linjediagram (Plotly)
- `/health`-endpoint, mest till för Kubernetes (se längre ner)
- Tester med Pytest som mockar det externa API:et så man slipper vara connected på nätet för att köra dem

## Köra appen lokalt (utan Docker)

Det här behövs bara om du vill testa Flask-servern direkt, utan container.

1. Virtuell miljö (valfritt men rekommenderas):
```
python -m venv venv
```
På Ubuntu/Debian kan du behöva installera venv-paketet separat:
```
sudo apt update && sudo apt install python3-venv
```
```
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
```

2. Beroenden:
```
pip install -r requirements.txt
```

3. Starta (app.py ligger under application/, så sökvägen behövs):
```
flask --app application/app run
```

4. Gå till `http://127.0.0.1:5000`

Värt att veta: det här är Flasks inbyggda utvecklingsserver, som körs på port 5000. I docker containern kör vi istället gunicorn på port 2800

## Tester

```
pytest
```

Testerna mockar anropet mot elprisetjustnu.se, så de kräver varken nätverk eller en körande server för att fungera.

## Säkerhet

Här nämns de sakerna jag själv hittade och fixade:

- Anrop mot elprisetjustnu.se görs med `requests` och vanlig SSL-verifiering.

- Containern kör som en icke-root-användare.


## Health check

`GET /health` svarar `{"status": "ok"}`. Lades till specifikt för att Kubernetes ska ha något att fråga när den vill veta om appen mår bra (mer om det under Kubernetes).


## Docker & Kubernetes förutsättningar

Om du vill testa containerdelen behöver du ha följande installerat:

- [Docker](https://docs.docker.com/engine/install/) (och kunna köra `docker`-kommandon utan `sudo` — se [den här guiden](https://docs.docker.com/engine/install/linux-postinstall/) om `docker ps` klagar på behörighet)
- [minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

## Docker

Appen körs via gunicorn i containern, inte Flasks dev-server. Dockerfilen är byggd i flera steg för att kunna hålla imagens storlek lågt och köra som en icke-root-användare.

```
docker build -t elpris-app:latest .
docker run -p 2800:2800 elpris-app:latest
```

Testa att den svarar:
```
curl http://127.0.0.1:2800/health
# Eller i en webbläsare
http://127.0.0.1:2800

```

## Kubernetes

Manifesten ligger i `k8s/`:

- `deployment.yaml` : kör containern, med satta CPU-användningsgränser och probes mot `/health`
- `service.yaml` : gör appen nåbar (NodePort, för att det ska gå att testa lokalt utan stora problem)
- `hpa.yaml` : min autoskalningsregeln: mellan 1 och 5 repliker, auto scalas upp ifall CPU:n går över 50 % av det som är satt i requests

Lokalt med minikube:

```
minikube start --driver=docker
minikube addons enable metrics-server
minikube image load elpris-app:latest

kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
```

Kolla att allt kommit upp:
```
kubectl get pods
kubectl get hpa
minikube service elpris-app-service --url
```

## Belastningstest och autoskalning

Jag körde ett lasttest med k6 (Grafana) mot `/api`, med samma datum/region i alla anrop. Man kanske undrar varför jag inte testade mot `/health` istället, anledningen är att `/health` bara returnerar en tom dictionary och inte gör något särskilt, så det säger mest att processen svarar, inte hur appen beter sig under riktig belastning. `/api` gör däremot riktig belastning med pandas (bygger tabellen med kr/kWh och tid) vid varje anrop.

Testet gick upp till 50 virtuella användare över en minut, denna last varade i två minuter och saktade ner efter.

### Resultat

Med bara en pod sköt CPU-användningen upp till 173 % direkt när lasten ökade. Vilket gjorde att pod 1 startades om av kubernetes vilket gav `connection refused` fel i k6 loggen.

Baserat på belastningen skalade den senare upp till 4 repliker (Pods), och sedan till 5 (maxvärdet i `hpa.yaml`) när CPU-användningen fortfarande låg på 226 %. Med lasten nu fördelad på grund av auto scaling på de fem poddarna så sjönk CPU-användningen snabbt, till 116 % och sedan ner mot 1 % när testet slutade.

Kort sagt: en ensam pod klarade inte belastningen och blev på kort tid instabil, första podden startades om men auto scalingen upptäckte det och löste det genom att lägga till fler repliker (Pods), och systemet stabiliserade sig därefter.

Loggutdrag (`kubectl get hpa -w`) under testet:
```
NAME             REFERENCE               TARGETS         MINPODS   MAXPODS   REPLICAS
elpris-app-hpa   Deployment/elpris-app   cpu: 1%/50%     1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 173%/50%   1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 173%/50%   1         5         4
elpris-app-hpa   Deployment/elpris-app   cpu: 226%/50%   1         5         4
elpris-app-hpa   Deployment/elpris-app   cpu: 226%/50%   1         5         5
elpris-app-hpa   Deployment/elpris-app   cpu: 116%/50%   1         5         5
elpris-app-hpa   Deployment/elpris-app   cpu: 1%/50%     1         5         5
```

### Köra testet själv

Kräver att klustret redan är igång (se Kubernetes avsnittet ovan) och att [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) är installerat.

Vill man se skalningen live medan testet kör, öppna två terminalfönster:

Terminal 1:

`kubectl get hpa -w`


Terminal 2:

`kubectl get pods -w`

Sen kör man testet.

Terminal 3:

```
export BASE_URL=$(minikube service elpris-app-service --url)
k6 run -e BASE_URL=$BASE_URL loadtest/loadtest.js
```

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
├── loadtest/
│   └── loadtest.js
├── tests/
│   ├── test_api.py
│   └── test_endpoints.py
├── Dockerfile
├── .dockerignore
├── .gitignore
├── requirements.txt
├── README.md
```
