from sqlalchemy import update
from ..models import ImageRevision, ReviewEvent, CommentThread, AnnotationActivity


def detach_image_quality(db, image_ids):
    """Retain historical records and original identities when their image is deleted.

    Detached history cannot be addressed through another image/project API, even
    if SQLite later reuses a numeric image ID. Snapshot content is untouched.
    """
    for model in (ImageRevision, ReviewEvent, CommentThread, AnnotationActivity):
        db.execute(update(model).where(model.image_id.in_(image_ids)).values(image_id=None))
