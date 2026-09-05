import datetime
import logging
import time

import pandas as pd
import plotly.express as px
import requests
from flask import Flask, render_template, request

app = Flask(__name__)

# Loggar internt istället för att läcka exception-text till användaren.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MIN_DATE = datetime.date(2022, 11, 1)
API_TIMEOUT_SECONDS = 5
CACHE_TTL_SECONDS = 60 * 60  # 1 timme – historiska/dagens priser ändras inte i efterhand

_price_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}


def _hamta_priser(år: int, månad: int, dag: int, prisklass: str) -> pd.DataFrame:
    """Hämtar elpriser från elprisetjustnu.se, med enkel TTL-cache.

    Höjer requests.RequestException/ValueError vid fel – anroparen ansvarar
    för att fånga och hantera det på ett sätt som inte läcker interna
    detaljer till användaren.
    """
    cache_key = (år, månad, dag, prisklass)
    cached = _price_cache.get(cache_key)
    if cached is not None:
        timestamp, df_cached = cached
        if time.time() - timestamp < CACHE_TTL_SECONDS:
            return df_cached.copy()

    url = f"https://www.elprisetjustnu.se/api/v1/prices/{år}/{månad:02d}-{dag:02d}_{prisklass}.json"
    response = requests.get(url, timeout=API_TIMEOUT_SECONDS)
    response.raise_for_status()  # ger tydligt fel vid t.ex. 404 (ogiltig region/datum)

    df = pd.DataFrame(response.json())
    _price_cache[cache_key] = (time.time(), df.copy())
    return df


def _validera_datum(år: int, månad: int, dag: int) -> str | None:
    """Returnerar felmeddelande (str) om datumet är ogiltigt, annars None."""
    raw_date = datetime.date(år, månad, dag)
    max_date = (datetime.datetime.today() + datetime.timedelta(days=1)).date()
    if raw_date < MIN_DATE or max_date < raw_date:
        return "Datumet får endast vara mellan den 1 november 2022 till en dag efter idag."
    return None


@app.route("/")
def app_main():
    return render_template("main.html")


@app.route("/input")
def app_enterdata():
    return render_template("enter.html")


@app.route("/health")
def health():
    """Liveness/readiness-endpoint för t.ex. Kubernetes probes."""
    return {"status": "ok"}, 200


@app.errorhandler(404)
def page_not_found(e):
    """Tar användaren till 404-sidan ifall sökfältet är felaktigt."""
    return render_template("404.html", e="Sidan kunde inte hittas."), 404


@app.post("/api")
def app_api():
    """Användaren fyller i region och datum för att få en överblick på elpriset."""
    try:
        prisklass = request.form["prisklass"]
        if prisklass not in {"SE1", "SE2", "SE3", "SE4"}:
            return render_template("enter.html", e="Ogiltig region vald.")

        år = int(request.form["år"])
        månad = int(request.form["månad"])
        dag = int(request.form["dag"])
    except (KeyError, ValueError):
        # Fångar felaktig/manipulerad formulärdata (t.ex. bokstäver i dag-fältet)
        # utan att läcka Python-interna feltexter till klienten.
        logger.info("Ogiltig formulärdata mottagen på /api")
        return render_template("enter.html", e="Försök igen! Kontrollera att alla fält är korrekt ifyllda.")

    try:
        datumfel = _validera_datum(år, månad, dag)
        if datumfel:
            return render_template("enter.html", e=datumfel)

        col = _hamta_priser(år, månad, dag, prisklass)
        data_table = col[["SEK_per_kWh", "time_start", "time_end"]]
        df = pd.DataFrame(round(data_table, 5))
        df["time_start"] = pd.to_datetime(df["time_start"]).dt.strftime("%H:%M")
        df["time_end"] = pd.to_datetime(df["time_end"]).dt.strftime("%H:%M")

        return render_template("post_enter.html", df=df, år=år, månad=månad, dag=dag, prisklass=prisklass)
    except ValueError:
        # T.ex. datetime.date(2023, 2, 30) -> "day is out of range for month"
        logger.info("Ogiltigt datum mottaget på /api: %s-%s-%s", år, månad, dag)
        return render_template("enter.html", e="Ogiltigt datum. Kontrollera år, månad och dag.")
    except requests.RequestException:
        logger.exception("Fel vid hämtning från elprisetjustnu.se")
        return render_template("enter.html", e="Kunde inte hämta elpriser just nu. Försök igen om en stund.")
    except Exception:
        # Sista skyddsnät – logga fullt stacktrace internt, visa aldrig detaljer för användaren.
        logger.exception("Oväntat fel på /api")
        return render_template("enter.html", e="Något gick fel. Försök igen.")


@app.route("/graf")
def graf():
    """Tar användarens valda datum och prisklass för att skapa ett linjediagram."""
    try:
        prisklass = request.args.get("prisklass")
        if prisklass not in {"SE1", "SE2", "SE3", "SE4"}:
            return render_template("404.html", e="Ogiltig region."), 400

        år = int(request.args.get("år"))
        månad = int(request.args.get("månad"))
        dag = int(request.args.get("dag"))

        col = _hamta_priser(år, månad, dag, prisklass)
        df = col[["SEK_per_kWh", "time_start"]].copy()
        df["time_start"] = pd.to_datetime(df["time_start"]).dt.strftime("%H:%M")

        fig = px.line(
            df,
            x="time_start",
            y="SEK_per_kWh",
            title=f"Elpriset på datumet {dag}-{månad}-{år} / Dag-Mån-År",
        )
        return fig.to_html(full_html=True)
    except (TypeError, ValueError):
        logger.info("Ogiltiga parametrar mottagna på /graf")
        return render_template("404.html", e="Ogiltiga eller saknade parametrar."), 400
    except requests.RequestException:
        logger.exception("Fel vid hämtning från elprisetjustnu.se")
        return render_template("404.html", e="Kunde inte hämta elpriser just nu."), 502
    except Exception:
        logger.exception("Oväntat fel på /graf")
        return render_template("404.html", e="Något gick fel."), 500


if __name__ == "__main__":
    app.run(debug=False)
