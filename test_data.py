from app import create_app
from models import db, ClassGroup, Subject, Teacher, Room, TimeSlot, TeacherSubject, TeacherAvailability

def test_data():
    app = create_app()
    with app.app_context():
        print("--- CLASSES ---")
        for c in ClassGroup.query.all():
            print(f"Class: {c.name}, Strength: {c.student_strength}")
            
        print("\n--- ROOMS ---")
        for r in Room.query.all():
            print(f"Room: {r.name}, Capacity: {r.capacity}, Type: {r.room_type}")
            
        print("\n--- TEACHERS ---")
        for t in Teacher.query.all():
            print(f"Teacher: {t.name}, Max/Day: {t.max_lectures_per_day}")
            
        print("\n--- SUBJECTS ---")
        for s in Subject.query.all():
            print(f"Subject: {s.name}, Class ID: {s.class_id}, Hours/Week: {s.lectures_per_week}, Is Lab: {s.is_lab}")
            
        print("\n--- TEACHER SUBJECT MAPPINGS ---")
        for ts in TeacherSubject.query.all():
            t = Teacher.query.get(ts.teacher_id)
            s = Subject.query.get(ts.subject_id)
            print(f"Teacher {t.name} -> Subject {s.name} (Class {s.class_id})")

        print("\n--- ASSIGNMENT CHECKS ---")
        for s in Subject.query.all():
            mappings = TeacherSubject.query.filter_by(subject_id=s.id).count()
            if mappings == 0:
                print(f"WARNING: Subject '{s.name}' has no teachers assigned!")

if __name__ == "__main__":
    test_data()
