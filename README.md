# Elpris-appen

## Om projektet

Grunden är en gruppuppgift från kursen Programmering 2 på Nackademin: en Flask-app där man kan välja datum och region och få tillbaka elpriset per timme, både som tabell och som graf.

Jag valde att bygga vidare på uppgiften för att öva på containerisering med Docker och autoskalning med Kubernetes. Så det som ligger i det här repot är egentligen två saker: en gammal gruppuppgift, och ett eget projekt ovanpå den.

## Funktioner

- Formulär för år, månad, dag och prisklass
- Datumvalidering (tidigast 2022-11-01, senast imorgon, eftersom API:et inte har data längre bak eller fram i tiden)
- Hämtar elpriser från [elprisetjustnu.se](https://www.elprisetjustnu.se/elpris-api)
- Cachar svaren en timme för att inte slösa på deras resurser i onödan
- Visar priserna i en tabell och som linjediagram (Plotly)
- `/api`-endpoint som hämtar priserna och bygger tabellen med pandas (det är den lasttestet går mot)
- `/health`-endpoint, mest till för Kubernetes (se längre ner)
- Tester med Pytest som mockar det externa API:et, så man slipper vara uppkopplad för att köra dem

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

Värt att veta: det här är Flasks inbyggda utvecklingsserver, som körs på port 5000. I Docker-containern körs istället gunicorn på port 2800.

## Tester

```
pytest
```

Testerna mockar anropet mot elprisetjustnu.se, så de kräver varken nätverk eller en körande server för att fungera.

## Säkerhet

- Anrop mot elprisetjustnu.se görs med `requests` med SSL-verifiering påslagen.
- Containern kör som en icke-root-användare.

## Health check

`GET /health` svarar `{"status": "ok"}`. Den lades till för att Kubernetes ska ha något att fråga när den vill veta om appen mår bra (mer om det under Kubernetes).

## Docker & Kubernetes förutsättningar

Om du vill testa containerdelen behöver du ha följande installerat:

- [Docker](https://docs.docker.com/engine/install/) (och kunna köra `docker`-kommandon utan `sudo` — se [den här guiden](https://docs.docker.com/engine/install/linux-postinstall/) om `docker ps` klagar på behörighet)
- [minikube](https://minikube.sigs.k8s.io/docs/start/)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)

## Docker

Appen körs via gunicorn i containern, inte Flasks dev-server. Dockerfilen är byggd i flera steg för att hålla imagen liten, och appen körs som en icke-root-användare.

```
docker build -t elpris-app:latest .
docker run -p 2800:2800 elpris-app:latest
```

Testa att den svarar:
```
curl http://127.0.0.1:2800/health
# Eller i en webbläsare:
http://127.0.0.1:2800
```

## Kubernetes

Manifesten ligger i `k8s/`:

- `deployment.yaml`: kör containern med CPU- och minnesgränser (requests 100m CPU / 128Mi, limits 250m CPU / 256Mi) och liveness-/readiness-probes mot `/health` på port 2800
- `service.yaml`: gör appen nåbar via NodePort, så att det går att testa lokalt utan krångel
- `hpa.yaml`: autoskalningsregeln. Mellan 1 och 5 repliker, med målet att den genomsnittliga CPU-användningen ska ligga på 50 % av `requests.cpu`

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

> **Känd begränsning:** cachen för elpriser ligger i minnet och delas inte mellan repliker, så varje pod har sin egen cache. Med flera repliker anropar varje pod det externa API:et separat. En delad cache (t.ex. Redis) skulle lösa det.

## Belastningstest och autoskalning

Jag körde ett lasttest med k6 (Grafana) mot `/api`, med samma datum och region i alla anrop. Varför inte mot `/health`? Den returnerar bara `{"status": "ok"}` och gör inget arbete, så den visar bara att processen svarar. `/api` bygger tabellen med pandas vid varje anrop, även när priserna redan ligger i cachen, så den belastar CPU:n på riktigt, om än lätt.

Testet pågick i 3,5 minuter och rampade upp till 50 virtuella användare. Varje virtuell användare gör ett anrop och väntar sedan en halv sekund, vilket ger upp till runt 100 anrop per sekund.

### Resultat

Sammanfattning från k6:

| Mått | Värde |
|---|---|
| Antal anrop | 16 102 |
| Misslyckade anrop (`http_req_failed`) | 0,00 % |
| Svarstid, median | 2,57 ms |
| Svarstid, p95 | 4,26 ms |
| Svarstid, max | 81,8 ms |

Med en pod steg CPU-användningen till 166 % av CPU-requesten (100m), alltså ungefär 166m. HPA räknar ut antalet repliker som `ceil(repliker × aktuell användning / mål)`, här `ceil(1 × 166 / 50) = 4`, och skalade därför direkt från 1 till 4. De nya poddarna var redo efter ungefär 6 sekunder. Med 4 poddar sjönk snittet till 101 % och sedan 60 %, fortfarande över målet, så HPA lade till en femte. När lasten rampade ner sjönk CPU till 1 %.

Ingen pod startades om under testet, och `kubectl get events` visade inga misslyckade liveness- eller readiness-probes och inga OOMKilled. När lasten är borta väntar HPA som standard 5 minuter och skalar sedan ner till 1 replik, vilket syns som `Killing`-händelser i `kubectl get events`.

Loggutdrag (`kubectl get hpa -w`) under testet:
```
NAME             REFERENCE               TARGETS              MINPODS   MAXPODS   REPLICAS
elpris-app-hpa   Deployment/elpris-app   cpu: <unknown>/50%   1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 1%/50%          1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 10%/50%         1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 166%/50%        1         5         1
elpris-app-hpa   Deployment/elpris-app   cpu: 166%/50%        1         5         4
elpris-app-hpa   Deployment/elpris-app   cpu: 101%/50%        1         5         4
elpris-app-hpa   Deployment/elpris-app   cpu: 60%/50%         1         5         4
elpris-app-hpa   Deployment/elpris-app   cpu: 60%/50%         1         5         5
elpris-app-hpa   Deployment/elpris-app   cpu: 3%/50%          1         5         5
elpris-app-hpa   Deployment/elpris-app   cpu: 1%/50%          1         5         5
```

### Vad resultatet faktiskt visar

Autoskalningen fungerar som den ska: HPA skalade upp exakt enligt formeln, de nya poddarna kom upp på några sekunder och inga anrop misslyckades.

Men det betyder inte att appen *behövde* fem poddar. När HPA skalade upp använde den enda podden ungefär 166m CPU, vilket är under limiten på 250m, så den var inte strypt, och inga anrop misslyckades i någon fas av testet. HPA skalade för att jag satt målet till 50 % av en låg request på 100m. Det är ett val av hur mycket marginal man vill ha, inte ett bevis på att en pod är för lite. Det här testet visar inte var en ensam pod faktiskt slutar räcka.

### Tidigare körning

Min första körning gav ett annat resultat: CPU låg på 226 % med 4 poddar och 116 % med 5, en pod startades om och k6 loggade `connection refused`. Den körningen saknar k6-sammanfattning och händelselogg, så jag kan inte säga varför. I senare körningar med samma manifest har ingen pod startats om.

### Vad jag lärde mig

- Att HPA skalar upp betyder inte automatiskt att appen behövde det. Det avgörs av var man sätter `requests` och målvärdet.
- En körning räcker inte. Första körningen gav en omstart som inte gick att återskapa, och utan k6-sammanfattning och `kubectl get events` gick orsaken inte att ta reda på i efterhand. Nu sparar jag båda varje gång.
- Nästa steg är att öka lasten stegvis tills svarstiderna eller felen börjar stiga, för att hitta var en pod faktiskt tar slut och om `maxReplicas: 5` räcker då.

### Köra testet själv

Kräver att klustret redan är igång (se Kubernetes-avsnittet ovan) och att [k6](https://grafana.com/docs/k6/latest/set-up/install-k6/) är installerat.

Öppna tre terminalfönster för att se skalningen live medan testet kör.

Terminal 1:
```
kubectl get hpa -w
```

Terminal 2:
```
kubectl get pods -w
```

Terminal 3 (kör testet och sparar sammanfattningen):
```
export BASE_URL=$(minikube service elpris-app-service --url)
k6 run -e BASE_URL=$BASE_URL loadtest/loadtest.js | tee k6-resultat.txt
```

Efteråt kan man se om någon pod startats om eller fått problem med sina probes:
```
kubectl get events --sort-by=.lastTimestamp | grep -iE "unhealthy|probe|killing|oom"
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
