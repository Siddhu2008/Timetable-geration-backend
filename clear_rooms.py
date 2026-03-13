"""Clean up any debug/test rooms left from testing."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import create_app
from models import db, Room

app = create_app()
with app.app_context():
    all_rooms = Room.query.all()
    print(f"Rooms in DB: {[(r.name, r.room_type) for r in all_rooms]}")
    Room.query.delete()
    db.session.commit()
    print("Cleared all rooms. You can now do a fresh bulk upload!")
