"""Single source of role permissions. Unknown roles/operations are denied."""
READ = {"workspace.read", "project.read", "image.read", "annotation.read", "class.read", "prediction.read", "dataset.read"}
ANNOTATE = {"annotation.create", "annotation.update", "annotation.delete", "prediction.run", "prediction.review", "class.mapping"}
MANAGE = {"workspace.update", "workspace.members.read", "workspace.members.invite", "workspace.members.manage", "workspace.audit.read",
          "project.create", "project.update", "project.delete", "image.upload", "image.delete", "class.create", "class.update", "class.delete", "dataset.split", "dataset.export"}
ROLE_PERMISSIONS = {
    "viewer": frozenset(READ), "annotator": frozenset(READ | ANNOTATE), "reviewer": frozenset(READ | ANNOTATE),
    "admin": frozenset(READ | ANNOTATE | MANAGE),
    "owner": frozenset(READ | ANNOTATE | MANAGE | {"workspace.delete", "workspace.owner.transfer"}),
}

def permissions(role): return sorted(ROLE_PERMISSIONS.get(role, ()))

def assignable_roles(actor_role):
    return ["owner", "admin", "annotator", "reviewer", "viewer"] if actor_role == "owner" else ["annotator", "reviewer", "viewer"] if actor_role == "admin" else []
