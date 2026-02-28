import random
from collections import defaultdict
from typing import Dict, List, Tuple
from models import (
    db,
    ClassGroup,
    ConflictLog,
    Room,
    Subject,
    Teacher,
    TeacherAvailability,
    TeacherSubject,
    TimeSlot,
    TimetableEntry,
    TimetableVersion,
)


def _load_availability() -> Dict[Tuple[int, int], bool]:
    out = defaultdict(lambda: True)
    for row in TeacherAvailability.query.all():
        out[(row.teacher_id, row.time_slot_id)] = row.is_available
    return out


def detect_conflicts(version_id: int) -> List[dict]:
    entries = TimetableEntry.query.filter_by(version_id=version_id).all()
    conflicts = []
    seen_teacher = set()
    seen_room = set()
    seen_class = set()
    daily_subject = set()
    teacher_daily_count = defaultdict(int)

    slots = {s.id: s for s in TimeSlot.query.all()}
    teachers = {t.id: t for t in Teacher.query.all()}
    classes = {c.id: c for c in ClassGroup.query.all()}
    rooms = {r.id: r for r in Room.query.all()}

    for e in entries:
        key_teacher = (e.teacher_id, e.time_slot_id)
        key_room = (e.room_id, e.time_slot_id)
        key_class = (e.class_id, e.time_slot_id)
        day_key = (e.class_id, slots[e.time_slot_id].day_of_week, e.subject_id)
        teacher_day = (e.teacher_id, slots[e.time_slot_id].day_of_week)

        if key_teacher in seen_teacher:
            conflicts.append({"type": "teacher_clash", "message": f"Teacher clash at slot {e.time_slot_id}"})
        if key_room in seen_room:
            conflicts.append({"type": "room_clash", "message": f"Room clash at slot {e.time_slot_id}"})
        if key_class in seen_class:
            conflicts.append({"type": "class_clash", "message": f"Class clash at slot {e.time_slot_id}"})
        if day_key in daily_subject:
            conflicts.append({"type": "subject_repeat", "message": f"Subject repetition for class {e.class_id}"})
        if rooms[e.room_id].capacity < classes[e.class_id].student_strength:
            conflicts.append(
                {
                    "type": "room_capacity_mismatch",
                    "message": f"Room {e.room_id} capacity is less than class {e.class_id} strength",
                }
            )

        teacher_daily_count[teacher_day] += 1
        max_daily = teachers[e.teacher_id].max_lectures_per_day
        if teacher_daily_count[teacher_day] > max_daily:
            conflicts.append({"type": "teacher_overload", "message": f"Teacher {e.teacher_id} overloaded on {teacher_day[1]}"})

        seen_teacher.add(key_teacher)
        seen_room.add(key_room)
        seen_class.add(key_class)
        daily_subject.add(day_key)

    return conflicts


def _score_schedule(version_id: int) -> float:
    entries = TimetableEntry.query.filter_by(version_id=version_id).all()
    slots = {s.id: s for s in TimeSlot.query.all()}
    subjects = {s.id: s for s in Subject.query.all()}
    score = 100.0

    for e in entries:
        sub = subjects[e.subject_id]
        slot = slots[e.time_slot_id]
        if sub.priority_morning and slot.slot_order > 2:
            score -= 0.4
    conflicts = detect_conflicts(version_id)
    score -= len(conflicts) * 10
    return max(0.0, round(score, 2))


def generate_timetable(created_by: int, num_versions: int = 3, max_retries: int = 500) -> List[TimetableVersion]:
    import random
    classes = ClassGroup.query.all()
    subjects = Subject.query.all()
    slots = TimeSlot.query.filter_by(is_break=False).order_by(TimeSlot.day_of_week, TimeSlot.slot_order).all()
    days_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    
    teacher_subject = TeacherSubject.query.all()
    t_map = {ts.subject_id: ts.teacher_id for ts in teacher_subject}
    
    rooms = Room.query.all()
    classrooms = [r for r in rooms if r.room_type == "classroom"]
    lab_rooms = [r for r in rooms if r.room_type == "lab"]
    
    generated_versions: List[TimetableVersion] = []
    
    for index in range(num_versions):
        class_items = []
        for c in classes:
            c_subs = [s for s in subjects if s.class_id == c.id]
            t_items = []
            l_items = []
            for s in c_subs:
                if s.is_lab:
                    for _ in range(s.lectures_per_week // 2):
                        l_items.append({"class_id": c.id, "subject_id": s.id, "type": "L"})
                else:
                    for _ in range(s.lectures_per_week):
                        t_items.append({"class_id": c.id, "subject_id": s.id, "type": "T"})
            class_items.extend(l_items)
            class_items.extend(t_items)
            
        random.shuffle(class_items)
        class_items.sort(key=lambda x: x["type"], reverse=True)
        
        class_grids = {}
        for c in classes:
            days_shuffled = list(days_order)
            random.shuffle(days_shuffled)
            c_grid = {}
            for i, d in enumerate(days_shuffled):
                if i < 3:
                    # Heavy day: 2 lab blocks + 3 theory slots
                    # Slot orders: 1-3 (pre-lunch), 5-6 (post-lunch), 8-9 (afternoon)
                    # Lab pairs: (1,2) and (5,6)  — both in non-break territory
                    # Remaining theory slots: 3, 8, 9
                    c_grid[d] = [
                        {"slots": [1, 2], "type": "L", "item": None},   # Lab 1 (09:00–11:00)
                        {"slots": [5, 6], "type": "L", "item": None},   # Lab 2 (12:30–14:30)
                        {"slots": [3],    "type": "T", "item": None},   # Theory (11:00–12:00)
                        {"slots": [8],    "type": "T", "item": None},   # Theory (14:45–15:45)
                        {"slots": [9],    "type": "T", "item": None},   # Theory (15:45–16:45)
                    ]
                else:
                    # Light day: 1 lab block + 3 theory slots
                    c_grid[d] = [
                        {"slots": [1, 2], "type": "L", "item": None},   # Lab (09:00–11:00)
                        {"slots": [3],    "type": "T", "item": None},   # Theory (11:00–12:00)
                        {"slots": [5],    "type": "T", "item": None},   # Theory (12:30–13:30)
                        {"slots": [6],    "type": "T", "item": None},   # Theory (13:30–14:30)
                    ]
            class_grids[c.id] = c_grid
            
        empty_blocks = []
        for c_id, grid in class_grids.items():
            for day, blocks in grid.items():
                for b in blocks:
                    empty_blocks.append({"class_id": c_id, "day": day, "block": b})
                    
        slot_map = {}
        for s in slots:
            slot_map[(s.day_of_week, s.slot_order)] = s.id
            
        teacher_busy = set()
        room_busy = set()
        
        def place_item(item_idx):
            if item_idx == len(class_items):
                return True
                
            item = class_items[item_idx]
            teacher_id = t_map.get(item["subject_id"])
            if not teacher_id: return False
            c_id = item["class_id"]
            
            valid_blocks = [b for b in empty_blocks if b["class_id"] == c_id and b["block"]["type"] == item["type"] and b["block"]["item"] is None]
            random.shuffle(valid_blocks)
            
            for vb in valid_blocks:
                day = vb["day"]
                block = vb["block"]
                
                daily_subs = [b["item"]["subject_id"] for b in class_grids[c_id][day] if b["item"] is not None]
                if item["subject_id"] in daily_subs:
                    continue
                
                t_conflict = False
                for s_idx in block["slots"]:
                    ts_id = slot_map.get((day, s_idx))
                    if not ts_id or (teacher_id, ts_id) in teacher_busy:
                        t_conflict = True
                        break
                if t_conflict:
                    continue
                    
                r_group = classrooms if item["type"] == "T" else lab_rooms
                shuffled_rooms = r_group[:]
                random.shuffle(shuffled_rooms)
                room_id = None
                for r in shuffled_rooms:
                    r_conflict = False
                    for s_idx in block["slots"]:
                        ts_id = slot_map.get((day, s_idx))
                        if not ts_id or (r.id, ts_id) in room_busy:
                            r_conflict = True
                            break
                    if not r_conflict:
                        room_id = r.id
                        break
                        
                if not room_id:
                    continue
                    
                block["item"] = {"subject_id": item["subject_id"], "teacher_id": teacher_id, "room_id": room_id}
                added_teacher = []
                added_room = []
                for s_idx in block["slots"]:
                    ts_id = slot_map[(day, s_idx)]
                    teacher_busy.add((teacher_id, ts_id))
                    room_busy.add((room_id, ts_id))
                    added_teacher.append((teacher_id, ts_id))
                    added_room.append((room_id, ts_id))
                    
                if place_item(item_idx + 1):
                    return True
                    
                block["item"] = None
                for tk in added_teacher: teacher_busy.remove(tk)
                for rk in added_room: room_busy.remove(rk)
                    
            return False

        success = place_item(0)
        
        version = TimetableVersion(name=f"Auto Formatted {index + 1}", created_by=created_by, is_active=False)
        db.session.add(version)
        db.session.flush()

        if success:
            for eb in empty_blocks:
                c_id = eb["class_id"]
                day = eb["day"]
                block = eb["block"]
                item = block["item"]
                
                for s_idx in block["slots"]:
                    ts_id = slot_map[(day, s_idx)]
                    db.session.add(TimetableEntry(
                        version_id=version.id,
                        class_id=c_id,
                        subject_id=item["subject_id"],
                        teacher_id=item["teacher_id"],
                        room_id=item["room_id"],
                        time_slot_id=ts_id
                    ))
            
            db.session.add(ConflictLog(version_id=version.id, conflict_type="Success", message="Contiguous Generation Successful"))
            version.score = 100.0
            generated_versions.append(version)
            db.session.commit()
        else:
            db.session.add(ConflictLog(version_id=version.id, conflict_type="generation_failed", message="Constraints too strict to find contiguous solution."))
            version.score = 0
            generated_versions.append(version)
            db.session.commit()
            
    if generated_versions:
        best = max(generated_versions, key=lambda v: v.score)
        TimetableVersion.query.update({"is_active": False})
        best.is_active = True
        db.session.commit()
            
    return generated_versions
