"""
Database module for OpenTutorAI
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import relationship
from open_webui.internal.db import Base, get_db, JSONField

PREFIX = "opentutorai_"

class Support(Base):
    __tablename__ = f"{PREFIX}support"
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    title = Column(String, nullable=False)
    short_description = Column(String, nullable=True)
    subject = Column(String, nullable=False)
    custom_subject = Column(String, nullable=True)
    course_id = Column(String, nullable=True)
    learning_objective = Column(Text, nullable=True)
    learning_type = Column(String, nullable=True)
    level = Column(String, nullable=False)
    content_language = Column(String, nullable=True, default="English")
    estimated_duration = Column(String, nullable=True)
    access_type = Column(String, nullable=True, default="Private")
    keywords = Column(String, nullable=True)
    start_date = Column(String, nullable=True)
    end_date = Column(String, nullable=True)
    avatar_id = Column(String, nullable=True)
    status = Column(String, nullable=False, default="open")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())
    meta_data = Column(JSONField, nullable=True)
    chat_id = Column(String, ForeignKey("chat.id", ondelete="CASCADE"), index=True, nullable=True)

class SupportFile(Base):
    __tablename__ = f"{PREFIX}support_file"
    id = Column(String, primary_key=True, index=True)
    support_id = Column(String, ForeignKey(f"{PREFIX}support.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_type = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    support = relationship("Support", backref="files")

class Assignment(Base):
    __tablename__ = f"{PREFIX}assignment"
    id = Column(String, primary_key=True)
    teacher_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    course = Column(String, nullable=True)
    course_id = Column(String, nullable=True)
    course_color = Column(String, nullable=True)
    due_date = Column(String, nullable=False)
    due_time = Column(String, nullable=True, default="23:59")
    points = Column(Integer, nullable=True, default=100)
    status = Column(String, nullable=True, default="active")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

class Submission(Base):
    __tablename__ = f"{PREFIX}submission"
    id = Column(String, primary_key=True)
    assignment_id = Column(String, ForeignKey(f"{PREFIX}assignment.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, nullable=False, index=True)
    student_name = Column(String, nullable=True)
    student_email = Column(String, nullable=True)
    content = Column(Text, nullable=True)
    file_ids = Column(JSONField, nullable=True)
    status = Column(String, nullable=True, default="submitted")
    grade = Column(String, nullable=True)
    feedback = Column(Text, nullable=True)
    submitted_at = Column(DateTime, server_default=func.now())
    graded_at = Column(DateTime, nullable=True)

class TeacherClassroom(Base):
    __tablename__ = f"{PREFIX}teacher_classroom"
    id = Column(String, primary_key=True)
    teacher_id = Column(String, nullable=False, index=True)
    class_code = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class ClassroomEnrollment(Base):
    __tablename__ = f"{PREFIX}classroom_enrollment"
    id = Column(String, primary_key=True)
    classroom_id = Column(String, ForeignKey(f"{PREFIX}teacher_classroom.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id = Column(String, nullable=False, index=True)
    enrolled_at = Column(DateTime, server_default=func.now())

class TeacherSettings(Base):
    __tablename__ = f"{PREFIX}teacher_settings"
    id = Column(String, primary_key=True)
    teacher_id = Column(String, nullable=False, unique=True, index=True)
    language = Column(String, nullable=True, default="fr")
    timezone = Column(String, nullable=True, default="UTC")
    notifications_enabled = Column(Boolean, nullable=True, default=True)
    email_notifications = Column(Boolean, nullable=True, default=True)
    theme = Column(String, nullable=True, default="light")
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

class ClassroomKnowledge(Base):
    __tablename__ = f"{PREFIX}classroom_knowledge"
    id = Column(String, primary_key=True)
    classroom_id = Column(String, ForeignKey(f"{PREFIX}teacher_classroom.id", ondelete="CASCADE"), nullable=False, index=True)
    knowledge_id = Column(String, nullable=False)
    knowledge_name = Column(String, nullable=True)
    shared_at = Column(DateTime, server_default=func.now())

def init_database():
    from open_webui.internal.db import engine
    Base.metadata.create_all(bind=engine, checkfirst=True)
    print("OpenTutorAI database tables initialized successfully")
    return engine