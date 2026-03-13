"""
Quick debug script to test bulk import parsing logic.
Run: .\ven\Scripts\python.exe debug_bulk.py
"""
import sys
import os
import csv
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Simulate _read_rows_from_upload on a sample CSV
CSV_CONTENT = "name,capacity,room_type\nA-101,60,classroom\nLab-1,40,lab\n"

def normalize_key(k):
    return str(k).strip().lower().replace(" ", "_") if k else ""

def read_csv_rows(text):
    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        normalized_row = {normalize_key(k): v for k, v in row.items()}
        out.append(normalized_row)
    return out

rows = read_csv_rows(CSV_CONTENT)
print(f"Rows parsed: {len(rows)}")
for row in rows:
    print(row)

# Now test with a real file
test_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rooms_sample.csv")
if os.path.exists(test_file):
    print(f"\nParsing real file: {test_file}")
    with open(test_file, "r", encoding="utf-8-sig") as f:
        rows = read_csv_rows(f.read())
    print(f"Rows parsed from file: {len(rows)}")
    for row in rows:
        print(row)
else:
    print(f"\nTest file not found: {test_file}")

# Now try importing via app context
print("\n--- Testing actual import via app context ---")
from app import create_app
from models import db, Room

app = create_app()
with app.app_context():
    # Count rooms first
    before = Room.query.count()
    print(f"Rooms before: {before}")
    
    rows_to_import = [
        {"name": "Debug-Room-A", "capacity": "60", "room_type": "classroom"},
        {"name": "Debug-Room-B", "capacity": "40", "room_type": "lab"},
    ]
    
    existing = {r.name.strip().lower() for r in Room.query.all()}
    created = 0
    for row in rows_to_import:
        name = str(row.get("name") or "").strip()
        if not name or name.lower() in existing:
            print(f"  Skipping: {row}")
            continue
        try:
            capacity = int(float(row.get("capacity", 0) or 0))
        except ValueError:
            capacity = 0
        room_type = str(row.get("room_type", "classroom") or "classroom").strip().lower()
        db.session.add(Room(name=name, capacity=capacity, room_type=room_type))
        existing.add(name.lower())
        created += 1
    
    db.session.commit()
    after = Room.query.count()
    print(f"Rooms after: {after} (created: {created})")
    
    # Clean up debug rooms
    Room.query.filter(Room.name.like("Debug-Room-%")).delete()
    db.session.commit()
    print("Cleaned up debug rooms.")
