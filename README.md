# discord-mitgliederverlauf

Zwei Analyse-Dashboards für den Discord-Server "Brian's DC", beide gehostet
über GitHub Pages aus diesem Repo (`main`-Branch, Root als Pages-Quelle):

| Dashboard | Pfad | Live-URL |
|---|---|---|
| Mitgliederverlauf | `index.html` (Root) | https://brianfna.github.io/discord-mitgliederverlauf/ |
| Aktivitäts-Rangliste | `aktivitaet/` | https://brianfna.github.io/discord-mitgliederverlauf/aktivitaet/ |

## 1. Mitgliederverlauf (`index.html`)

Interaktives HTML-Dashboard (D3.js) für den Mitgliederverlauf, gebaut aus
einem exportierten Carl-bot-Member-Log (Join/Leave-Events, 2021–2026).

- Eigenständig, kein Server nötig
- Features: zoombarer Zeitverlauf (Mausrad/Pinch/Buttons), Rollenfarben aus
  den Discord-Rolleneinstellungen, Fuzzy-Suche nach Nutzernamen (tippfehlertolerant)
- Datenquelle war eine manuell aus dem `#join-leave`-Log-Channel kopierte
  Textdatei (nicht Teil dieses Repos)
- Eine lokale Referenzkopie liegt außerhalb der Versionskontrolle in
  `member-dashboard/` (siehe `.gitignore`) — die auf GitHub gehostete
  Version ist immer `index.html` im Repo-Root

## 2. Aktivitäts-Rangliste (`aktivitaet/` + `activity-bot/`)

Bot + Website, die eine Rangliste zeigen: wer die meisten Nachrichten
geschrieben hat, wer am längsten im Voice-Chat war und wer wann dem Server
beigetreten ist. Die Website (`aktivitaet/`) wird über GitHub Pages gehostet
und **4× täglich automatisch** (00:00 / 06:00 / 12:00 / 18:00 UTC) vom Bot
mit frischen Daten aktualisiert und per Git gepusht.

Discord-Bot-Application ist bereits angelegt und eingeladen: `Bot_FNA#4474`.

### Dateien
- `activity-bot/bot.py` — dauerhaft laufender Bot. Loggt live
  Nachrichten-Metadaten (User, Channel, Zeitstempel, Zeichenlänge — **kein**
  Nachrichtentext), Voice-Sessions (Join/Leave-Zeitpunkte) und Mitglieder
  (Username, Avatar, Beitrittsdatum) in SQLite (`activity.db`). Exportiert
  und pusht außerdem automatisch 4×/Tag den aktuellen Stand nach
  `aktivitaet/data.json`.
- `activity-bot/backfill_messages.py` — einmaliges Skript, holt die
  **komplette bisherige** Nachrichten-Historie aller Text-Channels + Threads
  über die Discord-API nach
- `activity-bot/backfill_voice.py` — einmaliges Skript, rekonstruiert
  historische Voice-Sessions aus Carl-bots Log in `#voice` (Join/Leave-Paare
  → Sitzungsdauer), da Voice-Historie sich nicht direkt über die Discord-API
  abfragen lässt
- `activity-bot/backfill_joins.py` — einmaliges Skript, holt historische
  Beitrittsdaten aus Carl-bots Log in `#join-leave` nach, inkl. mittlerweile
  ausgetretener Mitglieder
- `activity-bot/export_stats.py` — aggregiert `activity.db` zu
  `aktivitaet/data.json` und pusht die Änderung per Git; wird von `bot.py`
  automatisch aufgerufen, kann aber auch manuell mit `python export_stats.py`
  ausgeführt werden
- `activity-bot/dump_channel_raw.py` — Debug-Skript, liest rohen Text+Embed-
  Inhalt eines einzelnen Channels aus, um Log-Formate anderer Bots zu prüfen
- `aktivitaet/` — die eigentliche Website (`index.html`, `style.css`,
  `script.js`, `data.json`). Statisch, kein Build-Schritt nötig, wird direkt
  über GitHub Pages ausgeliefert (Unterpfad des bestehenden Repos, berührt
  `index.html` im Root nicht).
- `aktivitaet/voicelog.js` + `aktivitaet/voicelog.json` — verstecktes
  Detail-Panel mit jeder einzelnen Voice-Session, aufrufbar durch Eintippen
  von **`voicelog`** irgendwo auf der Seite (außerhalb des Suchfelds), Escape
  oder Klick daneben schließt es wieder. Zwei Ansichten: "Pro Nutzer" (Jahr →
  Monat → Tag → Sessions für einen ausgewählten Nutzer) und "Pro Datum"
  (gleiche Baumstruktur, aber serverweit, mit Nutzer-Aufschlüsselung pro Tag).
  **Kein echter Zugriffsschutz** — nur UI-seitig versteckt, da die Seite rein
  statisch ist (`voicelog.json` bleibt über die URL direkt abrufbar für alle,
  die sie kennen/erraten). Der Auslöse-Text lässt sich in `voicelog.js`
  (Konstante `VLOG_SECRET`) ändern.
- `aktivitaet/join-chart.js` — zoombarer Mitgliederverlauf (D3, echte
  Mitgliederzahl über Zeit inkl. Austritte, nicht nur kumulierte Beitritte)
  oberhalb der Liste im "Beigetreten"-Tab, abgelöst vom früheren
  eigenständigen `member-dashboard/`-Chart, jetzt gespeist aus den live
  getrackten Bot-Daten (Tabelle `member_events`, per `on_member_join`/
  `on_member_remove` in `bot.py` sowie historisch aus `#join-leave`
  nachgeladen von `backfill_joins.py`) statt einer manuell kopierten
  Logdatei. Grüne Punkte = Beitritt, rote = Austritt.

Nutzer ohne Eintrag in der `members`-Tabelle (z. B. sehr alte Nachrichten/
Voice-Sessions von jemandem, der vor dem ersten Bot-Start bereits wieder
weg war) tauchen **nicht** als "Unbekannt" in den Ranglisten auf, sondern
werden beim Export komplett herausgefiltert — sie fließen aber weiterhin in
die Gesamtsummen (Nachrichten/Voice-Zeit gesamt) mit ein.

### Historische Daten einmalig nachladen

Die drei Backfill-Skripte holen alles nach, was vor dem ersten Start von
`bot.py` bereits passiert ist (Nachrichten komplett, Voice-Zeit + Beitritte
aus den bestehenden Carl-bot-Logs in `#voice` / `#join-leave`). **Reihenfolge
und Timing wichtig:**

```
python activity-bot/backfill_messages.py
python activity-bot/backfill_voice.py
python activity-bot/backfill_joins.py
python activity-bot/export_stats.py
```

- Nacheinander ausführen, nie parallel (ein Discord-Bot-Prozess pro Token
  gleichzeitig, siehe Sicherheitshinweise)
- Vor dem dauerhaften Start von `bot.py` einmalig laufen lassen, sonst
  können sich historische und live erfasste Voice-Sessions überschneiden
- Danach läuft `bot.py` normal weiter und trackt nur noch neue Ereignisse

### Setup

```
pip install -r activity-bot/requirements.txt
```

Bot-Token in `activity-bot/.env` eintragen (Vorlage: `.env.example`,
niemals ins Repo committen — bereits in `.gitignore`):

```
DISCORD_BOT_TOKEN=...
```

Im [Discord Developer Portal](https://discord.com/developers/applications)
beim Bot zusätzlich aktivieren:
- **MESSAGE CONTENT INTENT**
- **SERVER MEMBERS INTENT**

Bot starten (läuft dauerhaft, z. B. als Windows-Task/Service einrichten,
damit er nach einem Neustart automatisch wieder läuft):

```
python activity-bot/bot.py
```

Damit der automatische Export alle 6 Stunden auch wirklich gepusht wird,
muss `git push` in diesem Repo **ohne manuelle Eingabe** funktionieren
(gespeicherter Credential Helper oder SSH-Key ohne Passphrase-Abfrage) —
einmal `git push` von Hand testen, bevor der Bot dauerhaft läuft.

GitHub Pages ist bereits auf "Deploy from branch: main, Root" konfiguriert
(bedient `index.html`) — `aktivitaet/` wird dadurch automatisch mit
ausgeliefert, ohne dass die Pages-Einstellungen geändert werden müssen.

### Sicherheitshinweise

- Ausschließlich über die offizielle Bot-Application (`Bot_FNA#4474`)
  automatisieren — **niemals** über den persönlichen Hauptaccount
  (Self-Bots verstoßen gegen die Discord-ToS, Risiko: Sperre des
  Hauptaccounts statt nur des Bots)
- `discord.py` hält Rate-Limits automatisch ein
- Immer nur einen Prozess gleichzeitig mit demselben Token laufen lassen
- Token nicht in öffentliche Repos committen (z. B. `.gitignore` für
  jede Datei mit Token/`.env`)
