import os
import uuid
import shutil
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.orm import Session

import open_webui.utils.auth as auth
from open_webui.internal.db import get_session as get_db, Base

router = APIRouter()

# ─────────────────────────────────────────
# Dossier de stockage des fichiers
# ─────────────────────────────────────────
COURSES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "courses"
)
os.makedirs(COURSES_DIR, exist_ok=True)

MODULES = [
    "Généralités sur les systèmes informatiques",
    "Logiciels",
    "Représentation de l'information",
    "Algorithmique et programmation",
    "Réseaux informatiques",
    "Bases de données",
    "Systèmes d'exploitation",
    "Sécurité informatique",
    "Internet et Web",
    "Autre",
]

# ─────────────────────────────────────────
# Modèle SQLAlchemy
# ─────────────────────────────────────────
class CourseModel(Base):
    __tablename__ = "courses"

    id               = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title            = Column(String, nullable=False)
    description      = Column(Text, default="")
    module           = Column(String, nullable=False)
    filename         = Column(String, nullable=False)   # nom stocké sur disque
    original_filename= Column(String, nullable=False)   # nom original du fichier
    file_type        = Column(String, nullable=False)   # .pdf / .docx ...
    file_size        = Column(Integer, default=0)
    teacher_id       = Column(String, nullable=False)
    teacher_name     = Column(String, default="")
    created_at       = Column(DateTime, default=datetime.utcnow)

# ─────────────────────────────────────────
# Schémas Pydantic
# ─────────────────────────────────────────
class CourseResponse(BaseModel):
    id               : str
    title            : str
    description      : Optional[str]
    module           : str
    filename         : str
    original_filename: Optional[str]
    file_type        : str
    file_size        : int
    teacher_id       : str
    teacher_name     : Optional[str]
    created_at       : Optional[str]

    class Config:
        from_attributes = True

def _to_response(c: CourseModel) -> CourseResponse:
    return CourseResponse(
        id=c.id,
        title=c.title,
        description=c.description,
        module=c.module,
        filename=c.filename,
        original_filename=c.original_filename,
        file_type=c.file_type,
        file_size=c.file_size,
        teacher_id=c.teacher_id,
        teacher_name=c.teacher_name,
        created_at=c.created_at.isoformat() if c.created_at else None,
    )

# ─────────────────────────────────────────
# Auth helpers
# ─────────────────────────────────────────
def get_teacher_or_admin(user=Depends(auth.get_verified_user)):
    if user.role not in {"teacher", "admin"}:
        raise HTTPException(status_code=403, detail="Réservé aux enseignants")
    return user

# ─────────────────────────────────────────
# Routes
# ─────────────────────────────────────────

@router.get("/modules")
async def get_modules():
    return {"modules": MODULES}


# ── Liste des cours (teacher : ses cours / étudiant : tous) ──
@router.get("/courses", response_model=List[CourseResponse])
async def list_courses(
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    if user.role in {"teacher", "admin"}:
        courses = db.query(CourseModel).filter(
            CourseModel.teacher_id == user.id
        ).order_by(CourseModel.created_at.desc()).all()
    else:
        # Pour les étudiants : utiliser la route /classroom/{code}/courses
        # Cette route renvoie [] par défaut (les cours sont filtrés par classe)
        courses = []
    return [_to_response(c) for c in courses]


# ── Créer un cours (teacher) ──
@router.post("/courses", response_model=CourseResponse, status_code=201)
async def create_course(
    title      : str        = Form(...),
    description: str        = Form(""),
    module     : str        = Form(...),
    file       : UploadFile = File(...),
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    allowed = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Type de fichier non supporté: {ext}")

    course_id = str(uuid.uuid4())
    safe_name = f"{course_id}{ext}"
    dest = os.path.join(COURSES_DIR, safe_name)

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = os.path.getsize(dest)

    course = CourseModel(
        id=course_id,
        title=title,
        description=description,
        module=module,
        filename=safe_name,
        original_filename=file.filename,
        file_type=ext,
        file_size=file_size,
        teacher_id=user.id,
        teacher_name=user.name,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return _to_response(course)


# ── Modifier un cours (teacher) ──
@router.put("/courses/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id  : str,
    title      : str                  = Form(...),
    description: str                  = Form(""),
    module     : str                  = Form(...),
    file       : Optional[UploadFile] = File(None),
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    course = db.query(CourseModel).filter(
        CourseModel.id == course_id,
        CourseModel.teacher_id == user.id,
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Cours non trouvé")

    course.title       = title
    course.description = description
    course.module      = module

    if file and file.filename:
        allowed = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed:
            raise HTTPException(status_code=400, detail=f"Type non supporté: {ext}")

        # Supprimer l'ancien fichier
        old_path = os.path.join(COURSES_DIR, course.filename)
        if os.path.exists(old_path):
            os.remove(old_path)

        # Sauvegarder le nouveau
        new_name = f"{course_id}{ext}"
        dest = os.path.join(COURSES_DIR, new_name)
        with open(dest, "wb") as f:
            shutil.copyfileobj(file.file, f)

        course.filename          = new_name
        course.original_filename = file.filename
        course.file_type         = ext
        course.file_size         = os.path.getsize(dest)

    db.commit()
    db.refresh(course)
    return _to_response(course)


# ── Supprimer un cours (teacher) ──
@router.delete("/courses/{course_id}")
async def delete_course(
    course_id: str,
    user=Depends(get_teacher_or_admin),
    db: Session = Depends(get_db),
):
    course = db.query(CourseModel).filter(
        CourseModel.id == course_id,
        CourseModel.teacher_id == user.id,
    ).first()
    if not course:
        raise HTTPException(status_code=404, detail="Cours non trouvé")

    path = os.path.join(COURSES_DIR, course.filename)
    if os.path.exists(path):
        os.remove(path)

    db.delete(course)
    db.commit()
    return {"message": "Cours supprimé"}


# ── Télécharger / afficher le fichier ──
@router.get("/courses/{course_id}/file")
async def get_course_file(
    course_id: str,
    token    : Optional[str] = None,
    user=Depends(auth.get_verified_user),
    db: Session = Depends(get_db),
):
    course = db.query(CourseModel).filter(CourseModel.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Cours non trouvé")

    path = os.path.join(COURSES_DIR, course.filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le disque")

    media_types = {
        ".pdf" : "application/pdf",
        ".doc" : "application/msword",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".ppt" : "application/vnd.ms-powerpoint",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".txt" : "text/plain",
    }
    media_type = media_types.get(course.file_type, "application/octet-stream")

    return FileResponse(
        path=path,
        filename=course.original_filename or course.filename,
        media_type=media_type,
        headers={"Content-Disposition": f"inline; filename={course.original_filename or course.filename}"}
    )


# ─────────────────────────────────────────
# Route ÉTUDIANTS : cours d'une classe
# Appelée par le frontend étudiant via /api/v1/classroom/{code}/courses
# ─────────────────────────────────────────
from open_tutorai.models.database import TeacherClassroom, ClassroomEnrollment

@router.get("/classroom/{code}/courses", response_model=List[CourseResponse])
async def get_classroom_courses_for_student(
    code: str,
    user=Depends(auth.get_verified_user),
    db : Session = Depends(get_db),
):
    """
    L'étudiant récupère tous les cours uploadés par le prof de la classe
    à laquelle il est inscrit.
    """
    # 1. Trouver la classe par son code
    classroom = db.query(TeacherClassroom).filter(
        TeacherClassroom.class_code == code.strip().upper()
    ).first()
    if not classroom:
        raise HTTPException(status_code=404, detail="Classe introuvable")

    # 2. Vérifier que l'étudiant est bien inscrit
    enrolled = db.query(ClassroomEnrollment).filter(
        ClassroomEnrollment.classroom_id == classroom.id,
        ClassroomEnrollment.student_id   == user.id,
    ).first()
    if not enrolled:
        raise HTTPException(status_code=403, detail="Vous n'êtes pas inscrit dans cette classe")

    # 3. Retourner tous les cours créés par ce prof
    courses = db.query(CourseModel).filter(
        CourseModel.teacher_id == classroom.teacher_id
    ).order_by(CourseModel.created_at.desc()).all()

    return [_to_response(c) for c in courses]