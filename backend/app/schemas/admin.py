from datetime import datetime
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field

class AdminUserOut(BaseModel):
    id:UUID
    full_name:str
    email:str
    status:str
    email_verified:bool
    is_platform_admin:bool
    created_at:datetime
    last_login_at:datetime|None
    workspace_count:int

class UserPage(BaseModel):
    items:list[AdminUserOut]
    total:int
    page:int
    page_size:int

class AccountAction(BaseModel):
    model_config=ConfigDict(extra='forbid')
    confirm_user_id:UUID
