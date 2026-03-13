import random
from collections import defaultdict
from models import (
    db, ClassGroup, Room, Subject, SubjectClass, Teacher, 
    TeacherAvailability, TeacherSubject, TimeSlot, 
    TimetableEntry, TimetableVersion
)


class ScheduleItem:
    """Represents one lecture that needs to be scheduled: a subject FOR a specific class."""
    def __init__(self, subject, class_id):
        self.id = subject.id
        self.name = subject.name
        self.class_id = class_id
        self.lectures_per_week = subject.lectures_per_week
        self.priority_morning = subject.priority_morning
        self.is_lab = subject.is_lab


class TimetableGenerator:
    def __init__(self, version_name="Generated Timetable", created_by=None):
        self.version_name = version_name
        self.created_by = created_by
        self.classes = []
        self.subjects = []
        self.teachers = []
        self.rooms = []
        self.slots = []
        
        # State for backtracking
        self.teacher_schedule = {}  # (teacher_id, slot_id) -> bool (blocks ACROSS all classes)
        self.room_schedule = {}     # (room_id, slot_id) -> bool
        self.class_schedule = {}    # (class_id, slot_id) -> bool
        self.subject_counts = {}    # (class_id, subject_id, day) -> int
        self.teacher_daily_load = {}  # (teacher_id, day) -> int
        
        # For continuous scheduling: track how many slots a class has on each day
        self.class_day_load = {}  # (class_id, day) -> int
        
        self.backtrack_limit = 100000
        self.backtracks = 0
        
        self.timetable = []

    def _load_data(self):
        self.classes = ClassGroup.query.all()
        self.subjects = Subject.query.all()
        self.teachers = Teacher.query.all()
        self.rooms = Room.query.all()
        self.slots = TimeSlot.query.filter_by(is_break=False).order_by(
            TimeSlot.day_of_week, TimeSlot.slot_order
        ).all()
        
        # Pre-load teacher → subject mappings
        self.teacher_subjects = defaultdict(list)
        for ts in TeacherSubject.query.all():
            self.teacher_subjects[ts.subject_id].append(ts.teacher_id)
        
        # Pre-load subject → class linkings from SubjectClass junction table
        self.subject_class_links = defaultdict(list)  # subject_id -> [class_id, ...]
        for sc in SubjectClass.query.all():
            self.subject_class_links[sc.subject_id].append(sc.class_id)

        # Fallback: if no SubjectClass entries exist but Subject has class_id (legacy)
        for subj in self.subjects:
            if subj.class_id and not self.subject_class_links[subj.id]:
                self.subject_class_links[subj.id].append(subj.class_id)

        # Teacher availability
        self.teacher_avail = defaultdict(lambda: True)
        for avail in TeacherAvailability.query.all():
            self.teacher_avail[(avail.teacher_id, avail.time_slot_id)] = avail.is_available

    def _build_items(self):
        """Build a flat list of ScheduleItem: one per lecture per (subject, class) pair."""
        items = []
        for subj in self.subjects:
            class_ids = self.subject_class_links.get(subj.id, [])
            for class_id in class_ids:
                for _ in range(subj.lectures_per_week):
                    items.append(ScheduleItem(subj, class_id))
        return items

    def _sort_items(self, items):
        """
        Sort by difficulty (descending) — hardest to schedule first:
        1. Lab subjects (require specific rooms)
        2. Fewer teachers available
        3. More lectures per week
        """
        def difficulty_score(item):
            num_teachers = len(self.teacher_subjects[item.id])
            lab_score = 10 if item.is_lab else 0
            teacher_score = 5 / max(1, num_teachers)
            hour_score = item.lectures_per_week
            return lab_score + teacher_score + hour_score

        return sorted(items, key=difficulty_score, reverse=True)

    def _score_slot_for_continuity(self, item, slot):
        """
        Higher score = slot is better for continuous scheduling.
        We prefer slots on days where the class already has lectures (cluster per day).
        But we cap how many lectures per day to avoid overloading.
        """
        day_load = self.class_day_load.get((item.class_id, slot.day_of_week), 0)
        max_per_day = 3  # max lectures per class per day for balance
        if day_load >= max_per_day:
            return -1  # penalty: this day already has enough for this class
        # Prefer days with existing load (making it continuous) but not if already maxed
        return day_load  # 0 = new day, 1+ = already has some → prefer higher

    def is_valid(self, item, teacher_id, room, slot):
        # HARD: Teacher teaching another class at same time (key constraint)
        if (teacher_id, slot.id) in self.teacher_schedule:
            return False, "Teacher clash (teaching another class this slot)"

        # HARD: Room double-booked
        if (room.id, slot.id) in self.room_schedule:
            return False, "Room clash"

        # HARD: Class already has a lecture this slot
        if (item.class_id, slot.id) in self.class_schedule:
            return False, "Class clash"

        # HARD: Teacher unavailable
        if not self.teacher_avail[(teacher_id, slot.id)]:
            return False, "Teacher unavailable"

        # HARD: Room capacity
        class_group = next((c for c in self.classes if c.id == item.class_id), None)
        if class_group and room.capacity < class_group.student_strength:
            return False, "Room capacity too small"

        # HARD: Room type mismatch (lab vs classroom)
        expected_type = "lab" if item.is_lab else "classroom"
        if room.room_type != expected_type:
            return False, "Room type mismatch"

        # SOFT: Avoid teaching same subject more than once in a day
        if self.subject_counts.get((item.class_id, item.id, slot.day_of_week), 0) >= 1:
            if item.lectures_per_week <= 5:
                return False, "Subject already taught this day"

        # SOFT: Teacher daily load
        curr_load = self.teacher_daily_load.get((teacher_id, slot.day_of_week), 0)
        teacher = next((t for t in self.teachers if t.id == teacher_id), None)
        if teacher and curr_load >= teacher.max_lectures_per_day:
            return False, "Teacher daily load exceeded"

        # SOFT: Continuity check — avoid too many lectures for same class on same day
        if self._score_slot_for_continuity(item, slot) < 0:
            return False, "Class day load exceeded"

        return True, ""

    def backtrack(self, items, index=0):
        if self.backtracks >= self.backtrack_limit:
            return False

        if index == len(items):
            return True

        item = items[index]
        possible_teachers = self.teacher_subjects.get(item.id, [])
        if not possible_teachers:
            # No teacher assigned — skip this item instead of failing everything
            print(f"  [WARN] No teacher for subject '{item.name}' class {item.class_id} — skipping.")
            return self.backtrack(items, index + 1)

        # Sort slots: priority morning subjects first; then score by continuity
        def slot_sort_key(s):
            continuity = self._score_slot_for_continuity(item, s)
            morning_bonus = -s.slot_order if item.priority_morning else 0
            return (-continuity, morning_bonus, s.slot_order)

        sorted_slots = sorted(self.slots, key=slot_sort_key)

        for slot in sorted_slots:
            for teacher_id in possible_teachers:
                valid_rooms = [
                    r for r in self.rooms
                    if r.room_type == ("lab" if item.is_lab else "classroom")
                    and r.capacity >= next(
                        (c.student_strength for c in self.classes if c.id == item.class_id), 0
                    )
                ]
                random.shuffle(valid_rooms)

                for room in valid_rooms:
                    valid, reason = self.is_valid(item, teacher_id, room, slot)
                    if valid:
                        # Assign
                        entry = {
                            "class_id": item.class_id,
                            "subject_id": item.id,
                            "teacher_id": teacher_id,
                            "room_id": room.id,
                            "time_slot_id": slot.id,
                            "day": slot.day_of_week,
                            "item_name": item.name,
                        }
                        self.timetable.append(entry)
                        self.teacher_schedule[(teacher_id, slot.id)] = True
                        self.room_schedule[(room.id, slot.id)] = True
                        self.class_schedule[(item.class_id, slot.id)] = True
                        key_sc = (item.class_id, item.id, slot.day_of_week)
                        self.subject_counts[key_sc] = self.subject_counts.get(key_sc, 0) + 1
                        self.teacher_daily_load[(teacher_id, slot.day_of_week)] = (
                            self.teacher_daily_load.get((teacher_id, slot.day_of_week), 0) + 1
                        )
                        self.class_day_load[(item.class_id, slot.day_of_week)] = (
                            self.class_day_load.get((item.class_id, slot.day_of_week), 0) + 1
                        )

                        self.backtracks += 1
                        if self.backtrack(items, index + 1):
                            return True

                        # Unassign (backtrack)
                        self.timetable.pop()
                        del self.teacher_schedule[(teacher_id, slot.id)]
                        del self.room_schedule[(room.id, slot.id)]
                        del self.class_schedule[(item.class_id, slot.id)]
                        self.subject_counts[key_sc] -= 1
                        self.teacher_daily_load[(teacher_id, slot.day_of_week)] -= 1
                        self.class_day_load[(item.class_id, slot.day_of_week)] -= 1

        return False

    def generate(self):
        self._load_data()

        items = self._build_items()
        items = self._sort_items(items)
        print(f"Starting Verification...")
        print(f"Data context: {len(self.classes)} Classes, {len(self.subjects)} Subjects, "
              f"{len(self.teachers)} Teachers, {len(self.rooms)} Rooms, {len(self.slots)} Slots")
        print(f"Total lecture slots to schedule: {len(items)}")

        # Reset state
        self.teacher_schedule = {}
        self.room_schedule = {}
        self.class_schedule = {}
        self.subject_counts = {}
        self.teacher_daily_load = {}
        self.class_day_load = {}
        self.timetable = []
        self.backtracks = 0

        success = self.backtrack(items)
        print(f"Total backtracks: {self.backtracks}")

        if success:
            print("Successfully scheduled all items!")
            version = TimetableVersion(
                name=self.version_name,
                created_by=self.created_by,
                is_active=False,
                score=100.0,
            )
            db.session.add(version)
            db.session.flush()

            for t in self.timetable:
                entry = TimetableEntry(
                    version_id=version.id,
                    class_id=t["class_id"],
                    subject_id=t["subject_id"],
                    teacher_id=t["teacher_id"],
                    room_id=t["room_id"],
                    time_slot_id=t["time_slot_id"],
                )
                db.session.add(entry)

            db.session.commit()
            return version
        else:
            placed = len(self.timetable)
            total = len(items)
            print(f"Failed to schedule. Managed to place {placed} out of {total} items.")
            if self.timetable:
                last = self.timetable[-1]
                print(f"Last placed: {last.get('item_name')} for class {last.get('class_id')}")
            print("Generation failed. Check teacher assignments, room types, and available slots.")
            return None
