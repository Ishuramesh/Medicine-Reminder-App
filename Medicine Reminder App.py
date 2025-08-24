#!/usr/bin/env python3
"""
MediRemind – Step 1
A simple command‑line Medicine & Health Reminder database (no notifications yet).

What you can do in Step 1:
  • Add medicines with dose and one or more daily reminder times (HH:MM, 24‑hour)
  • Optional: start/end dates, notes
  • View all medicines (with times)
  • See today's schedule (sorted by time)
  • Update times for a medicine
  • Delete a medicine

Next steps (later): console/desktop notifications + refill tracking + web UI.
"""
from __future__ import annotations
import sqlite3
from datetime import datetime, date, timedelta
from typing import List, Optional
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "mediremind.db")

# ------------------------------- DB LAYER ---------------------------------- #

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dose TEXT,
                notes TEXT,
                start_date TEXT, -- ISO YYYY-MM-DD or NULL
                end_date   TEXT  -- ISO YYYY-MM-DD or NULL
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medicine_id INTEGER NOT NULL,
                time_hhmm TEXT NOT NULL, -- '08:00', '21:30'
                FOREIGN KEY(medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
            );
            """
        )


# ----------------------------- REPOSITORY ---------------------------------- #

def add_medicine(
    name: str,
    dose: Optional[str],
    times_hhmm: List[str],
    start_date_iso: Optional[str] = None,
    end_date_iso: Optional[str] = None,
    notes: Optional[str] = None,
) -> int:
    if not name.strip():
        raise ValueError("Medicine name cannot be empty.")
    times_hhmm = [t.strip() for t in times_hhmm if t.strip()]
    if not times_hhmm:
        raise ValueError("At least one time is required (HH:MM).")
    for t in times_hhmm:
        _validate_hhmm(t)
    if start_date_iso:
        _validate_date(start_date_iso)
    if end_date_iso:
        _validate_date(end_date_iso)

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO medicines(name, dose, notes, start_date, end_date) VALUES (?,?,?,?,?)",
            (name.strip(), _none_or_strip(dose), _none_or_strip(notes), start_date_iso, end_date_iso),
        )
        med_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO schedules(medicine_id, time_hhmm) VALUES (?,?)",
            [(med_id, t) for t in times_hhmm],
        )
    return med_id


def list_medicines() -> List[sqlite3.Row]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.name, m.dose, m.notes, m.start_date, m.end_date,
                   COALESCE(GROUP_CONCAT(s.time_hhmm, ', '), '') AS times
            FROM medicines m
            LEFT JOIN schedules s ON s.medicine_id = m.id
            GROUP BY m.id
            ORDER BY LOWER(m.name)
            """
        ).fetchall()
    return rows


def delete_medicine(med_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM medicines WHERE id = ?", (med_id,))
        return cur.rowcount > 0


def update_times(med_id: int, times_hhmm: List[str]) -> None:
    times_hhmm = [t.strip() for t in times_hhmm if t.strip()]
    if not times_hhmm:
        raise ValueError("Provide at least one time.")
    for t in times_hhmm:
        _validate_hhmm(t)
    with get_conn() as conn:
        conn.execute("DELETE FROM schedules WHERE medicine_id = ?", (med_id,))
        conn.executemany(
            "INSERT INTO schedules(medicine_id, time_hhmm) VALUES (?,?)",
            [(med_id, t) for t in times_hhmm],
        )


# ------------------------------ UTILITIES ---------------------------------- #

def _validate_hhmm(s: str) -> None:
    try:
        datetime.strptime(s, "%H:%M")
    except ValueError:
        raise ValueError(f"Invalid time '{s}'. Use HH:MM in 24-hour format (e.g., 08:00, 21:30)")


def _validate_date(s: str) -> None:
    try:
        datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Invalid date '{s}'. Use YYYY-MM-DD (e.g., 2025-08-24)")


def _none_or_strip(x: Optional[str]) -> Optional[str]:
    return x.strip() if isinstance(x, str) and x.strip() else None


def today_schedule() -> List[dict]:
    """Return a sorted list of today's due times with medicine name/dose."""
    today = date.today()
    items: List[dict] = []
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.name, m.dose, m.start_date, m.end_date, s.time_hhmm
            FROM medicines m
            JOIN schedules s ON s.medicine_id = m.id
            ORDER BY s.time_hhmm
            """
        ).fetchall()
    for r in rows:
        # Respect optional start/end dates
        if r["start_date"] and today < datetime.strptime(r["start_date"], "%Y-%m-%d").date():
            continue
        if r["end_date"] and today > datetime.strptime(r["end_date"], "%Y-%m-%d").date():
            continue
        due_dt = datetime.combine(today, datetime.strptime(r["time_hhmm"], "%H:%M").time())
        items.append(
            {
                "at": due_dt,
                "medicine": r["name"],
                "dose": r["dose"] or "",
                "time": r["time_hhmm"],
            }
        )
    items.sort(key=lambda x: x["at"])  # already sorted but keep safe
    return items


# ------------------------------ CLI LAYER ---------------------------------- #

def clear():
    os.system("cls" if os.name == "nt" else "clear")


def pause(msg: str = "Press Enter to continue…"):
    input(msg)


def menu_loop():
    init_db()
    while True:
        clear()
        print("🩺 MediRemind – Medicine & Health Reminder (Step 1)")
        print("=" * 60)
        print("1) Add medicine")
        print("2) View medicines")
        print("3) See today's schedule")
        print("4) Update times for a medicine")
        print("5) Delete a medicine")
        print("0) Exit")
        choice = input("\nChoose an option: ").strip()
        try:
            if choice == "1":
                handle_add()
            elif choice == "2":
                handle_view()
            elif choice == "3":
                handle_today()
            elif choice == "4":
                handle_update_times()
            elif choice == "5":
                handle_delete()
            elif choice == "0":
                print("Goodbye! ✨")
                break
            else:
                print("Invalid choice. Try again.")
                pause()
        except Exception as e:
            print(f"\n⚠️  Error: {e}")
            pause()


def handle_add():
    clear()
    print("➕ Add Medicine")
    print("-" * 60)
    name = input("Name (e.g., Paracetamol): ").strip()
    dose = input("Dose/Strength (e.g., 500 mg) [optional]: ").strip() or None
    times_str = input("Daily times (comma‑separated HH:MM, e.g., 08:00,14:00,20:00): ").strip()
    start_date = input("Start date YYYY-MM-DD [optional]: ").strip() or None
    end_date = input("End date YYYY-MM-DD [optional]: ").strip() or None
    notes = input("Notes [optional]: ").strip() or None

    times = [t.strip() for t in times_str.split(',')]
    med_id = add_medicine(name, dose, times, start_date, end_date, notes)
    print(f"\n✅ Added '{name}' (id={med_id}) with times: {', '.join(times)}")
    pause()


def handle_view():
    clear()
    print("📋 Medicines")
    print("-" * 60)
    rows = list_medicines()
    if not rows:
        print("No medicines yet. Add one from the menu.")
    else:
        for r in rows:
            print(f"#{r['id']}: {r['name']}  | Dose: {r['dose'] or '-'}")
            print(f"   Times: {r['times'] or '-'}")
            sd = r['start_date'] or '-'
            ed = r['end_date'] or '-'
            if r['notes']:
                print(f"   Notes: {r['notes']}")
            print(f"   Start: {sd}   End: {ed}")
            print("-" * 60)
    pause()


def handle_today():
    clear()
    print("🗓️  Today's Schedule")
    print("-" * 60)
    items = today_schedule()
    if not items:
        print("Nothing scheduled for today.")
    else:
        now = datetime.now()
        for it in items:
            status = "DONE" if it["at"] < now else "DUE"
            print(f"{it['time']}  | {it['medicine']}  {it['dose']}  [{status}]")
    pause()


def handle_update_times():
    clear()
    rows = list_medicines()
    if not rows:
        print("No medicines to update.")
        pause()
        return
    print("⏰ Update Times")
    print("-" * 60)
    for r in rows:
        print(f"#{r['id']}: {r['name']}  (current: {r['times'] or '-'})")
    med_id = int(input("Enter medicine id to update: ").strip())
    times_str = input("New daily times (comma‑separated HH:MM): ").strip()
    times = [t.strip() for t in times_str.split(',')]
    update_times(med_id, times)
    print("\n✅ Times updated.")
    pause()


def handle_delete():
    clear()
    rows = list_medicines()
    if not rows:
        print("No medicines to delete.")
        pause()
        return
    print("🗑️  Delete Medicine")
    print("-" * 60)
    for r in rows:
        print(f"#{r['id']}: {r['name']}  (times: {r['times'] or '-'})")
    med_id = int(input("Enter medicine id to delete: ").strip())
    if delete_medicine(med_id):
        print("\n✅ Deleted.")
    else:
        print("\nNot found.")
    pause()


if __name__ == "__main__":
    init_db()
    menu_loop()
