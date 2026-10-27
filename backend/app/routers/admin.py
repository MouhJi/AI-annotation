from datetime import date,datetime,time,timedelta,timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from sqlalchemy import select,func,or_,update
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User,UserSession,Workspace,WorkspaceMember,Project,Image,Annotation,AuditLog
from ..models.auth import utcnow
from ..schemas.admin import AdminUserOut,UserPage,AccountAction
from ..services.platform_admin import require_platform_admin,admin_operation,protect_last_admin,safe_audit
from ..services.workspace_service import audit
from ..services.auth_security import aware
from ..auth_config import settings
from ..rate_limit import limiter
from .auth import check_origin,user_out

router=APIRouter(prefix='/api/admin',tags=['platform administration'],dependencies=[Depends(require_platform_admin),Depends(check_origin)])

def count(db,model,*criteria):return db.scalar(select(func.count()).select_from(model).where(*criteria)) or 0
def page_result(db,stmt,page,size):
    total=db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    return list(db.execute(stmt.offset((page-1)*size).limit(size)).all()),total
def envelope(items,total,page,size):return {'items':items,'total':total,'page':page,'page_size':size}
def member_count():return select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.user_id==User.id).correlate(User).scalar_subquery()
def user_summary(user,total):return {**user_out(user),'last_login_at':aware(user.last_login_at) if user.last_login_at else None,'workspace_count':total}
def recent(db,*criteria):return [safe_audit(row) for row in db.scalars(select(AuditLog).where(*criteria).order_by(AuditLog.created_at.desc(),AuditLog.id.desc()).limit(20))]

@router.get('/dashboard/summary')
def dashboard_summary(db:Session=Depends(get_db)):
    cutoff=utcnow()-timedelta(days=7)
    active=select(UserSession.user_id).where(UserSession.last_activity_at>=cutoff)
    grouped=dict(db.execute(select(Annotation.source,func.count()).group_by(Annotation.source)).all())
    return {'total_users':count(db,User),'verified_users':count(db,User,User.email_verified_at.is_not(None)),
            'active_users':count(db,User,User.status=='active',User.id.in_(active)),
            'total_workspaces':count(db,Workspace),'total_projects':count(db,Project),'total_images':count(db,Image),
            'total_annotations':sum(grouped.values()),'annotation_sources':grouped,
            'definitions':{'active_users':'Active accounts with recorded session activity during the last 7 days.',
                           'annotations':'Current objects only; soft-deleted annotations are excluded.'}}

@router.get('/dashboard/activity')
def dashboard_activity(days:int=Query(30,ge=1,le=90),db:Session=Depends(get_db)):
    start=utcnow().date()-timedelta(days=days-1); since=datetime.combine(start,time.min,tzinfo=timezone.utc)
    def series(model,column):
        bucket=func.date(func.timezone('UTC',column)) if db.bind.dialect.name=='postgresql' else func.date(column)
        counts={str(day):n for day,n in db.execute(select(bucket,func.count()).select_from(model).where(column>=since).group_by(bucket))}
        return [{'date':str(start+timedelta(days=i)),'count':counts.get(str(start+timedelta(days=i)),0)} for i in range(days)]
    return {'registrations':series(User,User.created_at),'annotations':series(Annotation,Annotation.created_at),
            'workspaces':series(Workspace,Workspace.created_at),'recent':recent(db)}

@router.get('/users',response_model=UserPage)
def users(q:str=Query('',max_length=150),verified:bool|None=None,status:Literal['active','disabled','pending_verification']|None=None,
          sort:Literal['created_at','full_name','email','last_login_at']='created_at',direction:Literal['asc','desc']='desc',
          page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    stmt=select(User,member_count())
    if q:stmt=stmt.where(or_(User.full_name.ilike('%'+q+'%'),User.email.ilike('%'+q+'%')))
    if verified is not None:stmt=stmt.where(User.email_verified_at.is_not(None) if verified else User.email_verified_at.is_(None))
    if status:stmt=stmt.where(User.status==status)
    column=getattr(User,sort);stmt=stmt.order_by(column.asc().nullslast() if direction=='asc' else column.desc().nullslast(),User.id)
    rows,total=page_result(db,stmt,page,page_size)
    return envelope([user_summary(u,n) for u,n in rows],total,page,page_size)

@router.get('/users/{user_id}')
def user_detail(user_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    user=db.get(User,user_id)
    if not user:raise HTTPException(404,'User not found')
    rows,total=page_result(db,select(WorkspaceMember,Workspace).join(Workspace,Workspace.id==WorkspaceMember.workspace_id).where(WorkspaceMember.user_id==user_id).order_by(Workspace.name,Workspace.id),page,page_size)
    owned=db.execute(select(Project.id,Project.name,Project.workspace_id).where(Project.owner_user_id==user_id).order_by(Project.id).limit(100)).all()
    return {'user':user_summary(user,total),'memberships':envelope([{'workspace_id':w.id,'name':w.name,'role':m.role,'joined_at':aware(m.joined_at)} for m,w in rows],total,page,page_size),
            'owned_projects':[dict(row._mapping) for row in owned],'owned_projects_total':count(db,Project,Project.owner_user_id==user_id),
            'recent_activity':recent(db,or_(AuditLog.actor_user_id==user_id,(AuditLog.resource_type=='user')&(AuditLog.resource_id==str(user_id))))}

@router.post('/users/{user_id}/{action}')
def account_action(user_id:UUID,action:Literal['disable','enable','revoke-sessions'],payload:AccountAction,request:Request,
                   actor=Depends(require_platform_admin),db:Session=Depends(get_db)):
    if payload.confirm_user_id!=user_id:raise HTTPException(422,'Confirmation does not match target user')
    limiter.check(request,'admin-account-action',str(actor.id),limit=20)
    with admin_operation(db):
        current=db.scalar(select(User).where(User.id==actor.id).execution_options(populate_existing=True));require_platform_admin(current)
        target=db.scalar(select(User).where(User.id==user_id).with_for_update().execution_options(populate_existing=True))
        if not target:raise HTTPException(404,'User not found')
        if action=='disable':
            if target.id==actor.id:raise HTTPException(409,'You cannot disable your own administrator account')
            protect_last_admin(db,target)
        previous=target.status
        if action=='disable':target.status='disabled'
        elif action=='enable':target.status='active' if target.email_verified_at or not settings()['verify_required'] else 'pending_verification'
        revoked=0
        if action in {'disable','revoke-sessions'}:
            result=db.execute(update(UserSession).where(UserSession.user_id==user_id,UserSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
            revoked=result.rowcount
        audit(db,None,actor.id,{'disable':'user.disabled','enable':'user.enabled','revoke-sessions':'user.sessions_revoked'}[action],
              'user',user_id,previous_status=previous,status=target.status,count=revoked)
        db.commit()
    return {'user_id':user_id,'status':target.status,'revoked_sessions':revoked}

def workspace_rows(db,rows):
    ids=[w.id for w,*_ in rows]
    owners={key:[] for key in ids}
    if ids:
        ranked=select(WorkspaceMember.workspace_id.label('wid'),User.id.label('uid'),User.full_name.label('name'),func.row_number().over(partition_by=WorkspaceMember.workspace_id,order_by=User.id).label('position')).join(User,User.id==WorkspaceMember.user_id).where(WorkspaceMember.workspace_id.in_(ids),WorkspaceMember.role=='owner').subquery()
        for wid,uid,name in db.execute(select(ranked.c.wid,ranked.c.uid,ranked.c.name).where(ranked.c.position<=5)):
            owners[wid].append({'id':uid,'full_name':name})
    return [{'id':w.id,'name':w.name,'slug':w.slug,'created_at':aware(w.created_at),'member_count':mc,'project_count':pc,'owners':owners[w.id]} for w,mc,pc in rows]

@router.get('/workspaces')
def workspaces(q:str=Query('',max_length=150),kind:Literal['all','personal','team']='all',page:int=Query(1,ge=1,le=100000),
               page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    mc=select(func.count()).select_from(WorkspaceMember).where(WorkspaceMember.workspace_id==Workspace.id).correlate(Workspace).scalar_subquery()
    pc=select(func.count()).select_from(Project).where(Project.workspace_id==Workspace.id).correlate(Workspace).scalar_subquery()
    stmt=select(Workspace,mc,pc)
    if q:stmt=stmt.where(or_(Workspace.name.ilike('%'+q+'%'),Workspace.slug.ilike('%'+q+'%')))
    if kind!='all':stmt=stmt.where(Workspace.personal_user_id.is_not(None) if kind=='personal' else Workspace.personal_user_id.is_(None))
    rows,total=page_result(db,stmt.order_by(Workspace.created_at.desc(),Workspace.id),page,page_size)
    return envelope(workspace_rows(db,rows),total,page,page_size)

@router.get('/workspaces/{workspace_id}')
def workspace_detail(workspace_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    w=db.get(Workspace,workspace_id)
    if not w:raise HTTPException(404,'Workspace not found')
    rows,total=page_result(db,select(WorkspaceMember,User).join(User,User.id==WorkspaceMember.user_id).where(WorkspaceMember.workspace_id==workspace_id).order_by(WorkspaceMember.role,WorkspaceMember.id),page,page_size)
    projects=project_items(db,workspace_id=workspace_id,page=1,page_size=20)
    return {'workspace':workspace_rows(db,[(w,total,projects['total'])])[0],
            'members':envelope([{'id':u.id,'full_name':u.full_name,'role':m.role,'status':u.status} for m,u in rows],total,page,page_size),
            'projects':projects,'recent_activity':recent(db,AuditLog.workspace_id==workspace_id)}

def project_items(db,q='',workspace_id=None,annotation_mode=None,page=1,page_size=20):
    images=select(func.count()).select_from(Image).where(Image.project_id==Project.id).correlate(Project).scalar_subquery()
    annotations=select(func.count(Annotation.id)).select_from(Annotation).join(Image,Image.id==Annotation.image_id).where(Image.project_id==Project.id).correlate(Project).scalar_subquery()
    stmt=select(Project,Workspace.name,images,annotations).outerjoin(Workspace,Workspace.id==Project.workspace_id)
    if q:stmt=stmt.where(Project.name.ilike('%'+q+'%'))
    if workspace_id:stmt=stmt.where(Project.workspace_id==workspace_id)
    if annotation_mode:stmt=stmt.where(Project.annotation_mode==annotation_mode)
    rows,total=page_result(db,stmt.order_by(Project.created_at.desc(),Project.id),page,page_size)
    return envelope([{'id':p.id,'name':p.name,'workspace_id':p.workspace_id,'workspace_name':name,'annotation_mode':p.annotation_mode,'image_count':ic,'annotation_count':ac,'created_at':aware(p.created_at)} for p,name,ic,ac in rows],total,page,page_size)

@router.get('/projects')
def projects(q:str=Query('',max_length=150),workspace_id:UUID|None=None,annotation_mode:Literal['object_detection','instance_segmentation']|None=None,
             page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    return project_items(db,q,workspace_id,annotation_mode,page,page_size)

@router.get('/audit-logs')
def audit_logs(actor_user_id:UUID|None=None,action:str=Query('',max_length=100),resource_type:str=Query('',max_length=100),
               resource_id:str=Query('',max_length=100),start:date|None=None,end:date|None=None,
               page:int=Query(1,ge=1,le=100000),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db)):
    if start and end and start>end:raise HTTPException(422,'Start date must be before end date')
    stmt=select(AuditLog)
    if actor_user_id:stmt=stmt.where(AuditLog.actor_user_id==actor_user_id)
    if action:stmt=stmt.where(AuditLog.action.ilike('%'+action+'%'))
    if resource_type:stmt=stmt.where(AuditLog.resource_type==resource_type)
    if resource_id:stmt=stmt.where(AuditLog.resource_id==resource_id)
    if start:stmt=stmt.where(AuditLog.created_at>=datetime.combine(start,time.min,tzinfo=timezone.utc))
    if end:stmt=stmt.where(AuditLog.created_at<datetime.combine(end+timedelta(days=1),time.min,tzinfo=timezone.utc))
    rows,total=page_result(db,stmt.order_by(AuditLog.created_at.desc(),AuditLog.id.desc()),page,page_size)
    return envelope([safe_audit(row) for row, in rows],total,page,page_size)

@router.get('/audit-logs/{log_id}')
def audit_detail(log_id:UUID,db:Session=Depends(get_db)):
    row=db.get(AuditLog,log_id)
    if not row:raise HTTPException(404,'Audit event not found')
    return safe_audit(row)
