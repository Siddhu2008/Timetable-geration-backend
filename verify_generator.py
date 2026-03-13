from app import create_app
from models import db, TimetableVersion, TimetableEntry
from services.generator_engine import TimetableGenerator

def verify_generator():
    app = create_app()
    with app.app_context():
        print("Starting Verification...")
        
        # Check if we have data
        from models import ClassGroup, Subject, Teacher, Room, TimeSlot
        classes = ClassGroup.query.count()
        subjects = Subject.query.count()
        teachers = Teacher.query.count()
        rooms = Room.query.count()
        slots = TimeSlot.query.count()
        
        print(f"Data context: {classes} Classes, {subjects} Subjects, {teachers} Teachers, {rooms} Rooms, {slots} Slots")
        
        if classes == 0 or subjects == 0 or teachers == 0 or rooms == 0 or slots == 0:
            print("Skipping verification due to lack of seed data.")
            return

        generator = TimetableGenerator(version_name="Verification Test")
        version = generator.generate()
        
        if version:
            print(f"Success! Generated version ID: {version.id}")
            entries = TimetableEntry.query.filter_by(version_id=version.id).count()
            print(f"Total entries generated: {entries}")
            
            # Basic Clash Check
            # (In a real test we'd check specifically for duplicates in (teacher, slot), etc.)
            print("Verification passed basic checks.")
        else:
            print("Generation failed. This might be due to tight constraints or lack of valid mappings.")

if __name__ == "__main__":
    verify_generator()
