# Calendari Bologna FC / Bologna FC calendars

## Italiano

Calendari iCalendar (`.ics`) aggiornati automaticamente per Bologna FC, Virtus Bologna, Formula 1 e le squadre italiane nelle competizioni UEFA. I feed sono pensati per essere sottoscritti in Apple Calendar, Google Calendar e in qualunque app compatibile con lo standard iCalendar.

### Feed disponibili

Dopo aver pubblicato il repository su GitHub, sostituisci `<OWNER>` e `<REPOSITORY>` negli indirizzi seguenti:

- Serie A: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-serie-a.ics`
- Coppa Italia: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-coppa-italia.ics`
- Virtus Bologna EuroLeague: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/virtus-bologna-euroleague.ics`
- Formula 1: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/formula-1.ics`
- Squadre italiane — UEFA Champions League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-champions-league.ics`
- Squadre italiane — UEFA Europa League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-europa-league.ics`
- Squadre italiane — UEFA Conference League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-conference-league.ics`

In Apple Calendar scegli **File → Nuova sottoscrizione calendario**, incolla uno degli indirizzi e scegli la frequenza di aggiornamento desiderata.

### Contenuto degli eventi

Ogni evento ha come titolo la partita, per esempio `Bologna – Milan`, e contiene:

- 🏆 competizione e stagione;
- 📅 giornata di Serie A, ad esempio `12ª giornata`, oppure turno di Coppa Italia, ad esempio `Quarti di finale`;
- 🏟️ stadio;
- 📺 diretta TV ufficiale, quando pubblicata: `⬛ DAZN`, `⬛ DAZN | 🔵 SKY` oppure l'emittente della Coppa Italia;
- 🕘 orario convertito in `Europe/Helsinki`.

Ogni partita include anche un promemoria 30 minuti prima del calcio d'inizio. Il calendario gestisce automaticamente il passaggio tra EET ed EEST.

### Come funziona

Il progetto interroga il servizio dati strutturato di Lega Serie A, individua automaticamente la stagione attiva e filtra le partite del Bologna. Per la Serie A, il numero della giornata viene letto dai metadati ufficiali della partita; per la Coppa Italia viene mantenuto il nome del turno.

La configurazione in `configs/calendars.json` definisce le competizioni e i file generati. Gli identificativi ufficiali delle partite diventano UID iCalendar stabili: una partita rinviata viene aggiornata, non duplicata.

Quando l'emittente non è ancora stata comunicata ufficialmente, il feed mostra `Da definire` senza fare supposizioni.

I feed Virtus mostrano competizione, `Matchday` e orario (senza TV o impianto). Formula 1 mostra il nome ufficiale del Gran Premio, città e Paese. I tre feed UEFA filtrano automaticamente le squadre con federazione italiana e mostrano turno, città e stadio; se UEFA non ha ancora assegnato l'impianto, il feed indica `Venue to be confirmed`.

### Esecuzione locale

Richiede Python 3.11 o successivo.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m bolo_calendar.cli
```

In Windows PowerShell, sostituisci `.venv/bin/pip` con `.venv\\Scripts\\pip` e aggiungi `$env:PYTHONPATH='src';` prima dei comandi Python.

### Aggiornamento automatico

GitHub Actions esegue l'aggiornamento ogni sei ore e può essere avviato manualmente dalla scheda **Actions**. I test vengono eseguiti prima della generazione e viene creato un commit soltanto se almeno un file in `calendar/` è davvero cambiato.

In **Settings → Actions → General**, imposta **Workflow permissions** su **Read and write permissions**. In caso di errore della fonte dati, il workflow si interrompe prima di modificare i calendari esistenti.

---

## English

Automatically updated iCalendar (`.ics`) feeds for Bologna FC, Virtus Bologna, Formula 1, and Italian teams in UEFA competitions. The feeds can be subscribed to in Apple Calendar, Google Calendar, and any iCalendar-compatible app.

### Available feeds

After publishing the repository on GitHub, replace `<OWNER>` and `<REPOSITORY>` in these URLs:

- Serie A: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-serie-a.ics`
- Coppa Italia: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-coppa-italia.ics`
- Virtus Bologna EuroLeague: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/virtus-bologna-euroleague.ics`
- Formula 1: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/formula-1.ics`
- Italian teams — UEFA Champions League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-champions-league.ics`
- Italian teams — UEFA Europa League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-europa-league.ics`
- Italian teams — UEFA Conference League: `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/italian-teams-conference-league.ics`

In Apple Calendar, choose **File → New Calendar Subscription**, paste a URL, and select your preferred refresh frequency.

### Event details

Every event is titled with the fixture, for example `Bologna – Milan`, and includes:

- 🏆 competition and season;
- 📅 the Serie A matchday, such as `12ª giornata`, or a Coppa Italia round, such as `Quarti di finale`;
- 🏟️ stadium;
- 📺 official TV coverage once announced: `⬛ DAZN`, `⬛ DAZN | 🔵 SKY`, or the applicable Coppa Italia broadcaster;
- 🕘 kick-off time converted to `Europe/Helsinki`.

Each fixture also has a 30-minute reminder. The calendar automatically handles EET/EEST daylight-saving changes.

### How it works

The project reads Lega Serie A's structured fixture service, automatically finds the active season, and filters Bologna fixtures. For Serie A, it reads the matchday number from official match metadata; for Coppa Italia, it retains the published round name.

`configs/calendars.json` defines competitions and generated files. Official match IDs become stable iCalendar UIDs, so a postponed match updates instead of being duplicated.

If a broadcaster has not yet been officially announced, the feed shows `Da definire` and does not guess.

Virtus feeds show the competition, `Matchday`, and kickoff only (no TV or venue). Formula 1 shows the official Grand Prix name, city, and country. The three UEFA feeds automatically filter teams with an Italian association and show the round, city, and stadium; if UEFA has not assigned a venue yet, the feed says `Venue to be confirmed`.

### Run locally

Python 3.11 or later is required.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m bolo_calendar.cli
```

On Windows PowerShell, replace `.venv/bin/pip` with `.venv\\Scripts\\pip` and prefix Python commands with `$env:PYTHONPATH='src';`.

### Automatic updates

GitHub Actions runs every six hours and can also be launched manually from the **Actions** tab. It runs the tests before generation and commits only when a file in `calendar/` actually changes.

Set **Settings → Actions → General → Workflow permissions** to **Read and write permissions**. If the upstream service fails, the workflow stops before modifying existing calendars.
