"""
db.py — SQLAlchemy + SQLite persistence layer for workflow runs and templates.
"""
import json
import os
import glob
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Text, DateTime, Integer, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = os.path.join(os.path.dirname(__file__), "runs.db")
ENGINE = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=ENGINE)
Base = declarative_base()

class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"
    run_id = Column(String, primary_key=True, index=True)
    name = Column(String, default="Workflow Run")
    status = Column(String, default="started")   # started | running | completed | error
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration = Column(String, nullable=True)       # human-readable, e.g. "2.3s"
    result = Column(Text, nullable=True)           # JSON string
    logs = Column(Text, nullable=True)             # JSON list of log strings
    config = Column(Text, nullable=True)           # JSON string of config
    template = Column(String, nullable=True)

class TemplateRecord(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, unique=True, index=True, nullable=False)
    use_case = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    sample_prompt = Column(Text, nullable=True)
    template_json = Column(Text, nullable=True)    # JSON string of workflow config
    source_file = Column(String, nullable=True)    # originating filename
    # Versioning fields
    version = Column(Integer, nullable=False, default=1)
    parent_name = Column(String, nullable=True)    # base template name this was derived from
    is_custom = Column(Boolean, nullable=False, default=False)  # user-created/modified
    updated_at = Column(DateTime, default=datetime.utcnow)

def init_db():
    Base.metadata.create_all(bind=ENGINE)

# ── Template helpers ──────────────────────────────────────────────────────────

def seed_templates_from_files(template_dir: str = None):
    """
    Read every JSON file in prompt_templates/, parse templates (each file is
    either a list of template objects or a single template object), and upsert
    them into the DB.  Each entry must have at least 'use_case' and
    'template_json' keys.  Always overwrites existing records so format upgrades
    are reflected immediately on restart.
    """
    if template_dir is None:
        template_dir = os.path.join(os.path.dirname(__file__), "prompt_templates")
    # Also look one level up (repo root prompt_templates/)
    alt_dir = os.path.join(os.path.dirname(__file__), "..", "prompt_templates")
    dirs_to_scan = [d for d in [template_dir, alt_dir] if os.path.isdir(d)]

    db = SessionLocal()
    seeded = 0
    try:
        for scan_dir in dirs_to_scan:
            for fpath in glob.glob(os.path.join(scan_dir, "*.json")):
                fname = os.path.basename(fpath)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        raw = json.load(f)
                except Exception:
                    continue

                # Each file may be a list or a single dict
                entries = raw if isinstance(raw, list) else [raw]

                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    use_case = entry.get("use_case") or entry.get("name") or entry.get("graph_name")
                    # Prefer explicit template_json key; fall back to whole entry
                    template_json = entry.get("template_json") or entry.get("config")
                    if template_json is None:
                        # Whole entry IS the workflow config (legacy format)
                        template_json = entry
                    if not use_case:
                        continue
                    existing = db.query(TemplateRecord).filter_by(name=use_case).first()
                    if existing:
                        # Always refresh — ensures format upgrades are applied
                        existing.use_case = use_case
                        existing.description = entry.get("description")
                        existing.sample_prompt = entry.get("sample_prompt")
                        existing.template_json = json.dumps(template_json)
                        existing.source_file = fname
                    else:
                        record = TemplateRecord(
                            name=use_case,
                            use_case=use_case,
                            description=entry.get("description"),
                            sample_prompt=entry.get("sample_prompt"),
                            template_json=json.dumps(template_json),
                            source_file=fname,
                        )
                        db.add(record)
                        seeded += 1

        db.commit()
    finally:
        db.close()
    return seeded

def get_all_templates() -> list:
    db = SessionLocal()
    try:
        return db.query(TemplateRecord).order_by(TemplateRecord.source_file, TemplateRecord.id).all()
    finally:
        db.close()

def get_template_by_name(name: str):
    db = SessionLocal()
    try:
        return db.query(TemplateRecord).filter_by(name=name).first()
    finally:
        db.close()

def template_record_to_dict(record) -> dict:
    tj = None
    try:
        if record.template_json:
            tj = json.loads(record.template_json)
    except Exception:
        tj = record.template_json
    return {
        "name": record.name,
        "use_case": record.use_case,
        "description": record.description,
        "sample_prompt": record.sample_prompt,
        "example": tj,
        "source_file": record.source_file,
        "version": getattr(record, "version", 1) or 1,
        "parent_name": getattr(record, "parent_name", None),
        "is_custom": getattr(record, "is_custom", False) or False,
        "updated_at": record.updated_at.isoformat() if getattr(record, "updated_at", None) else None,
    }

def save_custom_template(name: str, description: str, template_json_obj: dict,
                         parent_name: str = None, sample_prompt: str = None) -> dict:
    """
    Save a user-customized template. Auto-increments version if a template with
    the same name already exists. Returns the saved record as a dict.
    """
    db = SessionLocal()
    try:
        existing = db.query(TemplateRecord).filter_by(name=name).first()
        if existing:
            existing.description = description
            existing.sample_prompt = sample_prompt or existing.sample_prompt
            existing.template_json = json.dumps(template_json_obj)
            existing.version = (existing.version or 1) + 1
            existing.parent_name = parent_name or existing.parent_name
            existing.is_custom = True
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return template_record_to_dict(existing)
        else:
            # Determine initial version: if derived from a parent, find max version of siblings
            initial_version = 1
            if parent_name:
                siblings = db.query(TemplateRecord).filter(
                    TemplateRecord.parent_name == parent_name
                ).all()
                if siblings:
                    initial_version = max((s.version or 1) for s in siblings) + 1
            record = TemplateRecord(
                name=name,
                use_case=name,
                description=description,
                sample_prompt=sample_prompt,
                template_json=json.dumps(template_json_obj),
                source_file="custom",
                version=initial_version,
                parent_name=parent_name,
                is_custom=True,
                updated_at=datetime.utcnow(),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return template_record_to_dict(record)
    finally:
        db.close()

def get_template_versions(base_name: str) -> list:
    """Return all versions of a template family (by parent_name or name)."""
    db = SessionLocal()
    try:
        records = db.query(TemplateRecord).filter(
            (TemplateRecord.parent_name == base_name) |
            (TemplateRecord.name == base_name) |
            TemplateRecord.name.like(f"{base_name}_v%")
        ).order_by(TemplateRecord.version).all()
        return [template_record_to_dict(r) for r in records]
    finally:
        db.close()

def get_custom_templates() -> list:
    """Return all user-customized templates."""
    db = SessionLocal()
    try:
        records = db.query(TemplateRecord).filter_by(is_custom=True)\
            .order_by(TemplateRecord.updated_at.desc()).all()
        return [template_record_to_dict(r) for r in records]
    finally:
        db.close()


def upsert_run(run_id: str, **kwargs):
    """Create or update a run record."""
    db = SessionLocal()
    try:
        record = db.query(WorkflowRunRecord).filter_by(run_id=run_id).first()
        if not record:
            record = WorkflowRunRecord(run_id=run_id)
            db.add(record)
        for key, value in kwargs.items():
            if key in ("result", "config", "logs") and value is not None and not isinstance(value, str):
                value = json.dumps(value, default=str)
            setattr(record, key, value)
        db.commit()
        db.refresh(record)
        return record
    finally:
        db.close()

def get_run(run_id: str):
    db = SessionLocal()
    try:
        return db.query(WorkflowRunRecord).filter_by(run_id=run_id).first()
    finally:
        db.close()

def get_all_runs():
    db = SessionLocal()
    try:
        return db.query(WorkflowRunRecord).order_by(WorkflowRunRecord.start_time.desc()).all()
    finally:
        db.close()

def record_to_dict(record) -> dict:
    """Convert a WorkflowRunRecord to a JSON-serializable dict."""
    if record is None:
        return {}
    logs = []
    try:
        if record.logs:
            logs = json.loads(record.logs)
    except Exception:
        pass
    result = None
    try:
        if record.result:
            result = json.loads(record.result)
    except Exception:
        result = record.result
    config = None
    try:
        if record.config:
            config = json.loads(record.config)
    except Exception:
        config = record.config
    return {
        "id": record.run_id,
        "name": record.name or "Workflow Run",
        "status": (record.status or "unknown").upper(),
        "startTime": record.start_time.isoformat() if record.start_time else None,
        "endTime": record.end_time.isoformat() if record.end_time else None,
        "duration": record.duration,
        "result": result,
        "logs": logs,
        "config": config,
        "template": record.template,
    }
