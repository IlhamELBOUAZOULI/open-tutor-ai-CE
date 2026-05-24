"""
Teacher router — assignments, submissions, classroom code system, settings.
All teacher endpoints require teacher or admin role.
Student endpoints (join, view) require any verified user.
"""

import os
import random
import string
import uuid
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

SUBMISSION_FILES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "submission_files"
)
os.makedirs(SUBMISSION_FILES_DIR, exist_ok=True)

import open_webui.utils.auth as auth
from open_webui.internal.db import get_session as get_db
from open_webui.models.users import Users

from open_tutorai.models.database import (
    Assignment, Submission,
    TeacherClassroom, ClassroomEnrollment, TeacherSettings,
    ClassroomKnowledge,
)

router = APIRouter()


# ─────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────

def get_teacher_or_admin(user=Depends(auth.get_verified_user)):
    if user.role not in {"teacher", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only teachers and admins can access this.",
        )
    return user


def get_user_flexible(
    token: Optional[str] = None,
    authorization: Optional[str] = None,
    db: Session = Depends(get_db),
):
    jwt_token = token
    if not jwt_token and authorization and authorization.startswith("Bearer "):
        jwt_token = authorization[7:]
    if not jwt_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = auth.decode_token(jwt_token)
        user_id = payload.get("id") if payload else None
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        u = Users.get_user_by_id(user_id)
        if not u:
            raise HTTPException(status_code=401, detail="User not found")
        return u
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def _generate_class_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    return "".join(random.choices(chars, k=length))


def _ensure_unique_code(db: Session, length: int = 6) -> str:
    for _ in range(50):
        code = _generate_class_code(length)
        existing = db.query(TeacherClassroom).filter(
            TeacherClassroom.class_code == code
        ).first()
        if not existing:
            return code
    raise HTTPException(status_code=500, detail="Could not generate unique class code.")


# ─────────────────────────────────────────
# Pydantic schemas
# ─────────────────────────────────────────

class AssignmentCreate(BaseModel):
    title       : str
    description : Optional[str] = None
    course      : Optional[str] = None
    course_id   : Optional[str] = None
    course_color: Optional[str] = "from-indigo-500 to-indigo-600"
    due_date    : str
    due_time    : Optional[str] = "23:59"
    points      : Optional[int] = 100


class AssignmentUpdate(BaseModel):
    title       : Optional[str] = None
    description : Optional[str] = None
    course      : Optional[str] = None
    course_id   : Optional[str] = None
    course_color: Optional[str] = None
    due_date    : Optional[str] = None
    due_time    : Optional[str] = None
    points      : Optional[int] = None
    status      : Optional[str] = None


class AssignmentResponse(BaseModel):
    id              : str
    teacher_id      : str
    title           : str
    description     : Optional[str]
    course          : Optional[str]
    course_id       : Optional[str]
    course_color    : Optional[str]
    due_date        : str
    due_time        : str
    points          : int
    status          : str
    submission_count: int = 0
    created_at      : Optional[str]
    updated_at      : Optional[str]

    class Config:
        from_attributes = True


class SubmissionGrade(BaseModel):
    grade   : Optional[str] = None
    feedback: Optional[str] = None


class SubmissionResponse(BaseModel):
    id          : str
    assignment_id: str
    student_id  : str
    student_name : Optional[str]
    student_email: Optional[str]
    content     : Optional[str]
    file_ids    : Optional[List[Any]]
    status      : str
    grade       : Optional[str]
    feedback    : Optional[str]
    submitted_at: Optional[str]
    graded_at   : Optional[str]

    class Config:
        from_attributes = True


class StudentResponse(BaseModel):
    id               : str
    name             : str
    email            : str
    role             : str
    profile_image_url: Optional[str] = None
    last_active_at   : Optional[int] = None
    created_at       : Optional[int] = None


class ClassroomResponse(BaseModel):
    id          : str
    teacher_id  : str
    class_code  : str
    name        : Optional[str]
    teacher_name: Optional[str] = None
    student_count: int = 0
    created_at  : Optional[str]

    class Config:
        from_attributes = True


class JoinClassroomRequest(BaseModel):
    code: str


class JoinClassroomResponse(BaseModel):
    message  : str
    classroom: ClassroomResponse


class StudentClassroomResponse(BaseModel):
    id              : str
    class_code      : str
    teacher_name    : str
    teacher_email   : Optional[str] = None
    name            : Optional[str] = None
    assignment_count: int = 0
    enrolled_at     : Optional[str] = None


class SettingsResponse(BaseModel):
    language             : str
    timezone             : str
    notifications_enabled: bool
    email_notifications  : bool
    theme                : str

    class Config:
        from_attributes = True


class SettingsUpdate(BaseModel):
    language             : Optional[str]  = None
    timezone             : Optional[str]  = None
    notifications_enabled: Optional[bool] = None
    email_notifications  : Optional[bool] = None
    theme                : Optional[str]  = None


class SharedCourseItem(BaseModel):
    knowledge_id  : str
    knowledge_name: Optional[str] = None
    shared_at     : Optional[str] = None

    class Config:
        from_attributes = True


class ShareCourseRequest(BaseModel):
    knowledge_id  : str
    knowledge_name: Optional[str] = None


# ─────────────────────────────────────────
# Helpers internes
# ─────────────────────────────────────────

def _assignment_to_response(a: Assignment, db: Session) -> AssignmentResponse:
    sub_count = db.query(Submission).filter(
        Submission.assignment_id == a.id
    ).count()
    return AssignmentResponse(
        id=a.id,
        teacher_id=a.teacher_id,
        title=a.title,
        description=a.description,
        course=a.course,
        course_id=a.course_id,
        course_color=a.course_color or "from-indigo-500 to-indigo-600",
        due_date=a.due_date,
        due_time=a.due_time or "23:59",
        points=a.points or 100,
        status=a.status or "active",
        submission_count=sub_count,
        created_at=a.created_at.isoformat() if a.created_at else None,
        updated_at=a.updated_at.isoformat() if a.updated_at else None,
    )


def _classroom_to_response(c: TeacherClassroom, db: Session) -> ClassroomResponse:
    student_count = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == c.id
    ).count()
    teacher = Users.get_user_by_id(c.teacher_id)
    return ClassroomResponse(
        id=c.id,
        teacher_id=c.teacher_id,
        class_code=c.class_code,
        name=c.name,
        teacher_name=teacher.name if teacher else None,
        student_count=student_count,
        created_at=c.created_at.isoformat() if c.created_at else None,
    )


def _sub_to_response(s: Submission) -> SubmissionResponse:
    return SubmissionResponse(
        id=s.id,
        assignment_id=s.assignment_id,
        student_id=s.student_id,
        student_name=s.student_name,
        student_email=s.student_email,
        content=s.content,
        file_ids=s.file_ids or [],
        status=s.status,
        grade=s.grade,
        feedback=s.feedback,
        submitted_at=s.submitted_at.isoformat() if s.submitted_at else None,
        graded_at=s.graded_at.isoformat() if s.graded_at else None,
    )


# ─────────────────────────────────────────
# Étudiants
# ─────────────────────────────────────────

@router.get("/students", response_model=List[StudentResponse])
async def get_students(user=Depends(get_teacher_or_admin)):
    try:
        return [
            StudentResponse(
                id=u.id, name=u.name, email=u.email, role=u.role,
                profile_image_url=getattr(u, "profile_image_url", None),
                last_active_at=getattr(u, "last_active_at", None),
                created_at=getattr(u, "created_at", None),
            )
            for u in Users.get_users()
            if u.role == "user"
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────
# Assignments — CRUD
# ─────────────────────────────────────────

@router.get("/assignments", response_model=List[AssignmentResponse])
async def list_assignments(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    assignments = (
        db.query(Assignment)
        .filter(Assignment.teacher_id == user.id)
        .order_by(Assignment.created_at.desc())
        .all()
    )
    return [_assignment_to_response(a, db) for a in assignments]


@router.post("/assignments", response_model=AssignmentResponse, status_code=201)
async def create_assignment(
    form: AssignmentCreate,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    a = Assignment(
        id=str(uuid.uuid4()),
        teacher_id=user.id,
        title=form.title,
        description=form.description,
        course=form.course,
        course_id=form.course_id,
        course_color=form.course_color,
        due_date=form.due_date,
        due_time=form.due_time or "23:59",
        points=form.points or 100,
        status="active",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _assignment_to_response(a, db)


@router.put("/assignments/{assignment_id}", response_model=AssignmentResponse)
async def update_assignment(
    assignment_id: str,
    form: AssignmentUpdate,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    for field, value in form.dict(exclude_unset=True).items():
        setattr(a, field, value)
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(a)
    return _assignment_to_response(a, db)


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: str,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(a)
    db.commit()
    return {"message": "Assignment deleted"}


# ─────────────────────────────────────────
# Submissions — teacher
# ─────────────────────────────────────────

@router.get("/assignments/{assignment_id}/submissions", response_model=List[SubmissionResponse])
async def get_submissions(
    assignment_id: str,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    a = db.query(Assignment).filter(
        Assignment.id == assignment_id,
        Assignment.teacher_id == user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")
    subs = (
        db.query(Submission)
        .filter(Submission.assignment_id == assignment_id)
        .order_by(Submission.submitted_at.desc())
        .all()
    )
    return [_sub_to_response(s) for s in subs]


@router.put("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(
    submission_id: str,
    form: SubmissionGrade,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    s = db.query(Submission).filter(Submission.id == submission_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Submission not found")
    a = db.query(Assignment).filter(
        Assignment.id == s.assignment_id,
        Assignment.teacher_id == user.id,
    ).first()
    if not a:
        raise HTTPException(status_code=403, detail="Not your assignment")
    s.grade     = form.grade
    s.feedback  = form.feedback
    s.status    = "graded"
    s.graded_at = datetime.utcnow()
    db.commit()
    db.refresh(s)
    return _sub_to_response(s)


# ─────────────────────────────────────────
# Submissions — étudiant soumet
# ─────────────────────────────────────────

@router.post("/submissions", response_model=SubmissionResponse, status_code=201)
async def create_submission(
    assignment_id: str                  = Form(...),
    content      : Optional[str]        = Form(None),
    files        : List[UploadFile]     = File(default=[]),
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    a = db.query(Assignment).filter(Assignment.id == assignment_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Assignment not found")

    existing = db.query(Submission).filter(
        Submission.assignment_id == assignment_id,
        Submission.student_id    == user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Vous avez déjà soumis ce devoir")

    try:
        due = datetime.strptime(f"{a.due_date}T{a.due_time}", "%Y-%m-%dT%H:%M")
        sub_status = "late" if datetime.utcnow() > due else "submitted"
    except Exception:
        sub_status = "submitted"

    file_metadata = []
    for upload in files:
        if not upload.filename:
            continue
        file_id   = str(uuid.uuid4())
        safe_name = upload.filename.replace("/", "_").replace("\\", "_")
        dest_path = os.path.join(SUBMISSION_FILES_DIR, f"{file_id}_{safe_name}")
        file_bytes = await upload.read()
        with open(dest_path, "wb") as fp:
            fp.write(file_bytes)
        file_metadata.append({
            "id"          : file_id,
            "name"        : upload.filename,
            "size"        : len(file_bytes),
            "content_type": upload.content_type or "application/octet-stream",
            "path"        : dest_path,
        })

    s = Submission(
        id=str(uuid.uuid4()),
        assignment_id=assignment_id,
        student_id=user.id,
        student_name=user.name,
        student_email=user.email,
        content=content or "",
        file_ids=file_metadata,
        status=sub_status,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return _sub_to_response(s)


@router.get("/submission-files/{file_id}")
async def download_submission_file(
    file_id      : str,
    token        : Optional[str] = None,
    authorization: Optional[str] = None,
    db: Session = Depends(get_db),
):
    active_user = get_user_flexible(token=token, authorization=authorization, db=db)

    subs = db.query(Submission).filter(
        (Submission.student_id == active_user.id) |
        Submission.assignment_id.in_(
            db.query(Assignment.id).filter(Assignment.teacher_id == active_user.id)
        )
    ).all()

    target_file = None
    for s in subs:
        if not s.file_ids:
            continue
        for f in s.file_ids:
            if isinstance(f, dict) and f.get("id") == file_id:
                target_file = f
                break
        if target_file:
            break

    if not target_file or not os.path.exists(target_file["path"]):
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=target_file["path"],
        filename=target_file["name"],
        media_type=target_file.get("content_type", "application/octet-stream"),
    )


@router.get("/my-submissions", response_model=List[SubmissionResponse])
async def get_my_submissions(
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    subs = db.query(Submission).filter(Submission.student_id == user.id).all()
    return [_sub_to_response(s) for s in subs]


# ─────────────────────────────────────────
# Classroom — teacher gère le code de classe
# ─────────────────────────────────────────

@router.get("/classroom", response_model=ClassroomResponse)
async def get_or_create_classroom(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        code = _ensure_unique_code(db)
        classroom = TeacherClassroom(
            id=str(uuid.uuid4()),
            teacher_id=user.id,
            class_code=code,
            name=f"Classe de {user.name}",
        )
        db.add(classroom)
        db.commit()
        db.refresh(classroom)
    return _classroom_to_response(classroom, db)


@router.post("/classroom/regenerate", response_model=ClassroomResponse)
async def regenerate_class_code(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")
    classroom.class_code = _ensure_unique_code(db)
    db.commit()
    db.refresh(classroom)
    return _classroom_to_response(classroom, db)


@router.get("/classroom/students", response_model=List[StudentResponse])
async def get_classroom_students(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        return []
    enrollments = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == classroom.id
    ).all()
    result = []
    for e in enrollments:
        u = Users.get_user_by_id(e.student_id)
        if u:
            result.append(StudentResponse(
                id=u.id, name=u.name, email=u.email, role=u.role,
                profile_image_url=getattr(u, "profile_image_url", None),
                last_active_at=getattr(u, "last_active_at", None),
                created_at=getattr(u, "created_at", None),
            ))
    return result


# ─────────────────────────────────────────
# Classroom — étudiant rejoint et consulte
# ─────────────────────────────────────────

@router.post("/join-classroom", response_model=JoinClassroomResponse)
async def join_classroom(
    form: JoinClassroomRequest,
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    code = form.code.strip().upper()
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.class_code == code
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Code de classe invalide. Vérifiez et réessayez.")

    existing = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == classroom.id,
        ClassroomEnrollment.student_id   == user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Vous êtes déjà inscrit dans cette classe.")

    enrollment = ClassroomEnrollment(
        id=str(uuid.uuid4()),
        classroom_id=classroom.id,
        student_id=user.id,
    )
    db.add(enrollment)
    db.commit()

    return JoinClassroomResponse(
        message="Inscription réussie !",
        classroom=_classroom_to_response(classroom, db),
    )


@router.get("/my-classrooms", response_model=List[StudentClassroomResponse])
async def get_my_classrooms(
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    enrollments = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.student_id == user.id
    ).all()
    result = []
    for e in enrollments:
        classroom = db.query(TeacherClassroom).filter(
            TeacherClassroom.id == e.classroom_id
        ).first()
        if not classroom:
            continue
        teacher = Users.get_user_by_id(classroom.teacher_id)
        assignment_count = db.query(Assignment).filter(
            Assignment.teacher_id == classroom.teacher_id
        ).count()
        result.append(StudentClassroomResponse(
            id=classroom.id,
            class_code=classroom.class_code,
            teacher_name=teacher.name if teacher else "Unknown",
            teacher_email=teacher.email if teacher else None,
            name=classroom.name,
            assignment_count=assignment_count,
            enrolled_at=e.enrolled_at.isoformat() if e.enrolled_at else None,
        ))
    return result


@router.get("/classroom/{code}/assignments", response_model=List[AssignmentResponse])
async def get_classroom_assignments(
    code: str,
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.class_code == code.upper()
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    enrolled = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == classroom.id,
        ClassroomEnrollment.student_id   == user.id,
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="You are not enrolled in this classroom")

    assignments = (
        db.query(Assignment)
        .filter(Assignment.teacher_id == classroom.teacher_id)
        .order_by(Assignment.created_at.desc())
        .all()
    )
    return [_assignment_to_response(a, db) for a in assignments]


# ─────────────────────────────────────────
# Classroom — cours des étudiants
# IMPORTANT : cette route délègue à courses.py
# Elle retourne les vrais cours uploadés (fichiers PDF/DOCX...)
# et non plus les knowledge bases RAG
# ─────────────────────────────────────────

@router.get("/classroom/{code}/courses")
async def get_classroom_courses_for_student(
    code: str,
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    """
    Retourne les cours (fichiers uploadés) du prof pour les étudiants inscrits.
    Importe CourseModel depuis courses.py pour éviter la duplication.
    """
    from open_tutorai.routers.courses import CourseModel, _to_response

    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.class_code == code.strip().upper()
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classe introuvable")

    enrolled = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == classroom.id,
        ClassroomEnrollment.student_id   == user.id,
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="Vous n'êtes pas inscrit dans cette classe")

    courses = (
        db.query(CourseModel)
        .filter(CourseModel.teacher_id == classroom.teacher_id)
        .order_by(CourseModel.created_at.desc())
        .all()
    )
    return [_to_response(c) for c in courses]


# ─────────────────────────────────────────
# Teacher Settings
# ─────────────────────────────────────────

@router.get("/settings", response_model=SettingsResponse)
async def get_settings(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    settings = db.query(TeacherSettings).filter(
        TeacherSettings.teacher_id == user.id
    ).first()
    if not settings:
        settings = TeacherSettings(id=str(uuid.uuid4()), teacher_id=user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return SettingsResponse(
        language=settings.language,
        timezone=settings.timezone,
        notifications_enabled=settings.notifications_enabled,
        email_notifications=settings.email_notifications,
        theme=settings.theme,
    )


@router.put("/settings", response_model=SettingsResponse)
async def update_settings(
    form: SettingsUpdate,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    settings = db.query(TeacherSettings).filter(
        TeacherSettings.teacher_id == user.id
    ).first()
    if not settings:
        settings = TeacherSettings(id=str(uuid.uuid4()), teacher_id=user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    for field, value in form.dict(exclude_unset=True).items():
        setattr(settings, field, value)
    settings.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(settings)
    return SettingsResponse(
        language=settings.language,
        timezone=settings.timezone,
        notifications_enabled=settings.notifications_enabled,
        email_notifications=settings.email_notifications,
        theme=settings.theme,
    )


# ─────────────────────────────────────────
# Classroom Knowledge (RAG) — partage de bases de connaissances
# ─────────────────────────────────────────

@router.get("/classroom/shared-courses", response_model=List[SharedCourseItem])
async def get_shared_courses(
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        return []
    items = (
        db.query(ClassroomKnowledge)
        .filter(ClassroomKnowledge.classroom_id == classroom.id)
        .order_by(ClassroomKnowledge.shared_at.desc())
        .all()
    )
    return [
        SharedCourseItem(
            knowledge_id=i.knowledge_id,
            knowledge_name=i.knowledge_name,
            shared_at=i.shared_at.isoformat() if i.shared_at else None,
        )
        for i in items
    ]


@router.post("/classroom/share-course", response_model=SharedCourseItem, status_code=201)
async def share_course_with_classroom(
    form: ShareCourseRequest,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        code = _ensure_unique_code(db)
        classroom = TeacherClassroom(
            id=str(uuid.uuid4()),
            teacher_id=user.id,
            class_code=code,
            name=f"Classe de {user.name}",
        )
        db.add(classroom)
        db.commit()
        db.refresh(classroom)

    existing = db.query(ClassroomKnowledge).filter(
        ClassroomKnowledge.classroom_id == classroom.id,
        ClassroomKnowledge.knowledge_id == form.knowledge_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Ce cours est déjà partagé avec la classe.")

    entry = ClassroomKnowledge(
        id=str(uuid.uuid4()),
        classroom_id=classroom.id,
        knowledge_id=form.knowledge_id,
        knowledge_name=form.knowledge_name,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return SharedCourseItem(
        knowledge_id=entry.knowledge_id,
        knowledge_name=entry.knowledge_name,
        shared_at=entry.shared_at.isoformat() if entry.shared_at else None,
    )


@router.delete("/classroom/share-course/{knowledge_id}", status_code=200)
async def unshare_course_from_classroom(
    knowledge_id: str,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.teacher_id == user.id
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    entry = db.query(ClassroomKnowledge).filter(
        ClassroomKnowledge.classroom_id == classroom.id,
        ClassroomKnowledge.knowledge_id == knowledge_id,
    ).first()
    if not entry:
        raise HTTPException(status_code=404, detail="Ce cours n'est pas partagé.")
    db.delete(entry)
    db.commit()
    return {"message": "Cours retiré de la classe."}