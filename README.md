# Raspberry Pi IoT Monitor

Raspberry Pi lämpötila- ja kosteusmittauksille. Projektin voi käynnistää ensin paikallisesti ilman oikeaa anturia; sen jälkeen sen voi yhdistää Azure IoT Hubiin ja Azure SQL Databaseen.

## Ominaisuudet

- Raspberry Pi -lähettäjä: lähettää simuloituja lämpötila- ja kosteusmittauksia Azure IoT Hubiin.
- Azure Function: lukee IoT Hubin sisäänrakennetusta Event Hubs -yhteensopivasta päätepisteestä ja tallentaa mittaukset SQL-tietokantaan.
- Flask-verkkosivu: näyttää viimeisimmät mittaukset, sallii manuaalisen mittauksen kirjaamisen ja laitteen asetusten muokkaamisen.
- Paikallinen SQLite-tila verkkosivulle, jotta käyttöliittymää voi kokeilla ilman Azurea.


>Älä julkaise verkkosovellusta internetiin ennen kuin App Service Authentication / Microsoft Entra ID -kirjautuminen on otettu käyttöön. Esimerkin paikallinen tila ei ole tuotantokäyttöön. Azure-resurssien salaisuuksia ei pidä koskaan lisätä GitHubiin.

## Arkkitehtuuri

```text
Raspberry Pi (Python)
       |
       | MQTT/HTTPS laitteen SDK:n kautta
       v
Azure IoT Hub
       |
       | Event Hubs -yhteensopiva sisäänrakennettu päätepiste
       v
Azure Function  ------> Azure SQL Database
                              ^
                              |
                      Flask / Azure App Service
```

## Hakemistorakenne

```text
device/                 Raspberry Pi -lähettäjä
backend/                Azure Function
web/                    Flask-käyttöliittymä
database/schema.sql     SQL-taulut ja esimerkkilaite
tests/                  Perustestit

```

## 1. Verkkosivu

Python 3.11:n tai uudempi


Windows PowerShell:

```powershell
cd web
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Avaa `http://127.0.0.1:5000`. SQLite-tietokanta luodaan automaattisesti tiedostoon `web/iotmonitor.db`, ja esimerkkilaite lisätään ensimmäisellä käynnistyksellä.

Paikallinen tila käyttää SQLitea. Azure SQL -tilaan siirrytään asettamalla `SQL_CONNECTION_STRING` ja asentamalla Microsoft ODBC Driver 18 for SQL Server. Katso ympäristömuuttujat kohdasta `web/.env.example`.

## 2. Azure-resurssit


1. Resource Group
2. Azure IoT Hub
3. IoT Hub -laite, `raspberrypi-01`
4. Azure SQL Server ja tietokanta `iotmonitor`
5. Function App (Python-versio, joka vastaa projektin runtimea)
6. App Service verkkosovellukselle

Budjetti 45€/kuukausi

### SQL-tietokanta

Suorita Azure SQL Query Editorissa tai SQL Server -työkalussa tiedosto `database/schema.sql`.

### IoT Hubin viestit Functionille

Function käyttää IoT Hubin sisäänrakennettua Event Hubs -yhteensopivaa päätepistettä. Hae IoT Hubin **Built-in endpoints** -asetuksista Event Hub -yhteensopiva päätepiste ja luo sitä varten rajatun oikeuden omaava yhteysmerkkijono. Tallenna se Function Appin sovellusasetukseen:

- `IOTHUB_EVENTHUB_CONNECTION`

Älä käytä laitteen device connection stringiä tässä asetuksessa. Functionin pitää käyttää hubin sisäänrakennetun päätepisteen yhteyttä ja sillä pitää olla lukemiseen tarvittavat oikeudet.

Aseta Function Appin sovellusasetukset:

- `FUNCTIONS_WORKER_RUNTIME=python`
- `IOTHUB_EVENTHUB_CONNECTION=...`
- `SQL_CONNECTION_STRING=...`

Tallenna salaisuudet vain Azure App Settingsiin tai Key Vaultiin, älä lähdekoodiin.

> Azure Functions -ympäristön on tuettava `pyodbc`-kirjastoa ja Microsoft ODBC Driver 18:aa. Varmista ajonaikaisen ympäristön yhteensopivuus ennen käyttöönottoa. Jos valittu hosting-ympäristö ei sisällä ajuria, käytä ajurin sisältävää konttia tai vaihda tietokantayhteysratkaisua.

## 3. Raspberry Pi

Raspberry Piissä:

```bash
cd device
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Aseta laitteen yhteysmerkkijono ympäristömuuttujaksi (älä tallenna sitä GitHubiin):

```bash
export IOTHUB_DEVICE_CONNECTION_STRING='HostName=...;DeviceId=raspberrypi-01;SharedAccessKey=...'
export DEVICE_ID='raspberrypi-01'
export SAMPLE_INTERVAL_SECONDS='60'
python send_telemetry.py
```

Ohjelma lähettää aluksi simuloituja arvoja. Kun anturi on hankittu, vaihda `read_sensor()`-funktion toteutus esimerkiksi BME280-anturin lukemiseen. Pidä yhteysmerkkijono poissa lokista ja versionhallinnasta.

## 4. Verkkosivu Azure App Serviceen

Aseta App Servicen sovellusasetukset:

- `APP_ENV=production`
- `AUTH_ENABLED=true`
- `SQL_CONNECTION_STRING=...`
- `DEVICE_ID=raspberrypi-01`
- `SECRET_KEY` satunnaiseksi pitkäksi salaisuudeksi

Ota App Servicessä käyttöön **Authentication** ja Microsoft Entra ID -kirjautuminen ja vaadi kirjautuminen kaikille reiteille. `AUTH_ENABLED=true` on sovelluksen lisätarkistus; se ei korvaa App Servicen alustatason kirjautumisasetuksia. Älä jätä julkista anonyymikäyttöä päälle.

Käynnistyskomento App Serviceen (Linux) on yleensä:

```bash
gunicorn --bind 0.0.0.0:8000 app:app
```

Sijoita `web/`-hakemisto julkaistavan sovelluksen juureen tai säädä julkaisun työskentelyhakemisto sen mukaan.



## Mitä ei vielä ole toteutettu

- BME280-anturin todellinen luku; oletuksena lähetetään simuloituja arvoja.
- Azure IoT Hub device twin -tuki. Verkkosivun näytteenottoväli tallentuu tietokantaan, mutta se ei vielä muuta Raspberry Piin käynnissä olevaa mittausväliä.
- Mittausten automaattinen poistaminen `RetentionDays`-asetuksen perusteella.
- Tuotantotason käyttäjäroolit, auditointi ja CSRF-suojaus.
