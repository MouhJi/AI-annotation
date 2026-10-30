"""Single source of role permissions. Unknown roles/operations are denied."""
READ = {"workspace.read", "project.read", "image.read", "annotation.read", "class.read", "prediction.read", "dataset.read", "review.read", "comment.read", "quality.read"}
ANNOTATE = {"annotation.create", "annotation.update", "annotation.delete", "prediction.run", "prediction.review", "class.mapping", "review.submit", "comment.create", "comment.resolve", "activity.record"}
REVIEW = {"annotation.edit_others", "review.approve", "review.reject", "review.reopen"}
MANAGE = {"workspace.update", "workspace.members.read", "workspace.members.invite", "workspace.members.manage", "workspace.audit.read",
          "project.create", "project.update", "project.delete", "image.upload", "image.delete", "class.create", "class.update", "class.delete", "dataset.split", "dataset.export", "export.approved", "project.review_settings.manage", "quality.project.read"}
ROLE_PERMISSIONS = {
    "viewer": frozenset(READ), "annotator": frozenset(READ | ANNOTATE), "reviewer": frozenset(READ | ANNOTATE | REVIEW),
    "admin": frozenset(READ | ANNOTATE | REVIEW | MANAGE),
    "owner": frozenset(READ | ANNOTATE | REVIEW | MANAGE | {"workspace.delete", "workspace.owner.transfer"}),
}

def permissions(role): return sorted(ROLE_PERMISSIONS.get(role, ()))

def assignable_roles(actor_role):
    return ["owner", "admin", "annotator", "reviewer", "viewer"] if actor_role == "owner" else ["annotator", "reviewer", "viewer"] if actor_role == "admin" else []
