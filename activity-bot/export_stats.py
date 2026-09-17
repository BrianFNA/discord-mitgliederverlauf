"""
Exportiert die gesammelten Aktivitätsdaten aus activity.db als JSON für die
Website (docs/data.json) und veröffentlicht sie per Git-Push.

Eigenständig nutzbar:  python export_stats.py
Wird außerdem von bot.py importiert und alle 6 Stunden automatisch aufgerufen.
"""

import datetime
import json
import os
import subprocess
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "activity.db")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(REPO_ROOT, "aktivitaet", "data.json")
VOICELOG_OUT_PATH = os.path.join(REPO_ROOT, "aktivitaet", "voicelog.json")


def fetch_all(con, query):
    cur = con.cursor()
    cur.execute(query)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def build_export():
    con = sqlite3.connect(DB_PATH)

    members = fetch_all(con, "SELECT * FROM members")
    msg_counts = fetch_all(
        con, "SELECT user_id, COUNT(*) AS cnt FROM messages GROUP BY user_id"
    )
    voice_totals = fetch_all(
        con, "SELECT user_id, SUM(duration_seconds) AS secs FROM voice_sessions GROUP BY user_id"
    )
    con.close()

    member_map = {m["user_id"]: m for m in members}
    msg_map = {r["user_id"]: r["cnt"] for r in msg_counts}
    voice_map = {r["user_id"]: r["secs"] for r in voice_totals}

    # Nur bekannte Mitglieder (mit Eintrag in der members-Tabelle) - Nachrichten/
    # Voice-Sessions von User-IDs ohne Mitgliedsdatensatz ("Unbekannt") werden
    # nicht als eigene Zeile aufgeführt, fließen aber weiter in die Gesamt-
    # summen (total_messages/total_voice_seconds) ein.
    users = []
    for uid, m in member_map.items():
        users.append({
            "user_id": uid,
            "username": m.get("username", "Unbekannt"),
            "avatar_url": m.get("avatar_url"),
            "message_count": msg_map.get(uid, 0),
            "voice_seconds": voice_map.get(uid, 0),
            "joined_at": m.get("joined_at"),
        })

    export = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "total_messages": sum(msg_map.values()),
        "total_voice_seconds": sum(voice_map.values()),
        "member_count": len(members),
        "users": users,
    }

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

    print(f"Export geschrieben nach {OUT_PATH} ({len(users)} User erfasst).")
    return export


def build_voicelog():
    """Exportiert jede einzelne Voice-Session (für das versteckte Voice-Log-Panel)."""
    con = sqlite3.connect(DB_PATH)
    members = fetch_all(con, "SELECT user_id, username, avatar_url FROM members")
    sessions = fetch_all(
        con,
        "SELECT user_id, channel_name, joined_at, left_at, duration_seconds "
        "FROM voice_sessions ORDER BY joined_at ASC"
    )
    con.close()

    # Nur bekannte Mitglieder - Sessions von User-IDs ohne Mitgliedsdatensatz
    # ("Unbekannt") werden komplett verworfen, nicht nur unbenannt angezeigt.
    users = {m["user_id"]: {"username": m["username"], "avatar_url": m["avatar_url"]} for m in members}
    sessions = [s for s in sessions if s["user_id"] in users]

    voicelog = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "users": users,
        "sessions": sessions,
    }

    os.makedirs(os.path.dirname(VOICELOG_OUT_PATH), exist_ok=True)
    with open(VOICELOG_OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(voicelog, f, ensure_ascii=False, indent=2)

    print(f"Voice-Log geschrieben nach {VOICELOG_OUT_PATH} ({len(sessions)} Sessions).")
    return voicelog


def push_to_github():
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    try:
        subprocess.run(
            ["git", "add", "aktivitaet/data.json", "aktivitaet/voicelog.json"],
            cwd=REPO_ROOT, check=True, capture_output=True, text=True,
        )
        commit = subprocess.run(
            ["git", "commit", "-m", f"Aktivitäts-Update {timestamp}"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if commit.returncode != 0 and "nothing to commit" not in commit.stdout:
            print(f"git commit: {commit.stdout}{commit.stderr}")
            return
        push = subprocess.run(
            ["git", "push"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if push.returncode != 0:
            print(f"git push fehlgeschlagen: {push.stderr}")
        else:
            print("Erfolgreich zu GitHub gepusht.")
    except subprocess.CalledProcessError as e:
        print(f"Git-Fehler: {e.stderr}")


if __name__ == "__main__":
    build_export()
    build_voicelog()
