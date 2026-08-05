# Bologna FC calendars

Automatically generated, subscribable iCalendar feeds for Bologna FC fixtures.

## Feeds

After publishing this repository on GitHub, subscribe in Apple Calendar using:

- `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-serie-a.ics`
- `https://raw.githubusercontent.com/<OWNER>/<REPOSITORY>/main/calendar/bologna-coppa-italia.ics`

In Apple Calendar, choose **File → New Calendar Subscription**, paste one URL, and set auto-refresh to the frequency you prefer.

## What each event contains

Each event has the fixture as its title and this Italian description:

- competition and season;
- matchday or knockout round;
- stadium;
- official TV broadcaster when published;
- kick-off time converted to `Europe/Helsinki`.

Every fixture has a 30-minute display reminder. The event's real time zone is also `Europe/Helsinki`, including EET/EEST daylight-saving changes.

## Design

`LegaSdpProvider` reads the public structured fixture service used by Lega Serie A. It discovers competition and season identifiers at runtime, then filters fixtures by Bologna. This avoids HTML scraping for the authoritative schedule.

The framework is configuration-driven: `configs/calendars.json` defines each competition and output file. Adding a competition requires adding an entry, not duplicating calendar logic. Source IDs become UIDs, which prevents duplicates and allows a rescheduled fixture to update in subscribers rather than be duplicated.

The provider looks for broadcaster fields in the official fixture record. If a broadcaster is not yet published, the calendar says `Da definire`; it never guesses. Coppa Italia broadcasts can use channels other than DAZN or Sky, and the source value is preserved as-is.

The club season page is deliberately not the primary source: it is useful as a human-readable cross-check but does not offer a stable, complete broadcaster interface. The official Lega structured feed remains the durable source for both Serie A and Coppa Italia.

## Local use

Requires Python 3.11 or newer.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m bolo_calendar.cli
```

On Windows PowerShell, replace `.venv/bin/pip` with `.venv\\Scripts\\pip` and prefix commands with `$env:PYTHONPATH='src';`.

## GitHub Actions

The workflow runs every six hours and can also be started manually from the **Actions** tab. It runs the tests, regenerates both feeds, and commits only the `calendar/` files whose bytes differ. Set the repository workflow permission to **Read and write permissions** under **Settings → Actions → General**.

If an upstream request fails or returns invalid JSON, the job fails before writing any calendar. An empty Coppa Italia calendar is allowed before Bologna has a scheduled tie; a successful future run will populate the same subscribed feed.
