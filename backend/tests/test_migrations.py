import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, text, inspect

def test_alembic_preserves_populated_legacy_database(tmp_path):
    root=Path(__file__).resolve().parents[1]
    url='sqlite:///'+(tmp_path/'migration.db').as_posix()
    env={**os.environ,'DATABASE_URL':url}
    def migrate(revision):
        result=subprocess.run([sys.executable,'-m','alembic','upgrade',revision],cwd=root,env=env,capture_output=True,text=True,timeout=60)
        assert result.returncode==0,result.stderr
    migrate('0001_legacy')
    engine=create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO projects(id,name,created_at,updated_at,annotation_mode) VALUES (100,'Legacy',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,'instance_segmentation')"))
        connection.execute(text("INSERT INTO classes(id,project_id,name,created_at) VALUES(100,100,'fox',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO images(id,project_id,filename,filepath,width,height,split,created_at) VALUES(100,100,'fox.png','/saved/fox.png',100,100,'train',CURRENT_TIMESTAMP)"))
        connection.execute(text("INSERT INTO annotations(id,image_id,class_id,x,y,width,height,annotation_type,points_json,created_at,updated_at) VALUES(100,100,100,1,1,20,20,'polygon','[[1,1],[21,1],[1,21]]',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"))
        before=connection.execute(text('SELECT * FROM annotations')).all()
        connection.execute(text('DROP TABLE alembic_version'))  # disposable test DB: simulate existing unversioned schema
    migrate('head'); migrate('head')
    with engine.connect() as connection:
        assert connection.execute(text('SELECT id,image_id,class_id,x,y,width,height,annotation_type,points_json,created_at,updated_at FROM annotations')).all()==before
        assert connection.execute(text('SELECT created_by,updated_by,source,version FROM annotations')).one()==(None,None,'legacy',1)
        assert connection.execute(text('SELECT owner_user_id FROM projects WHERE id=100')).scalar() is None
        assert connection.execute(text('SELECT filepath,split FROM images WHERE id=100')).one()==('/saved/fox.png','train')
        assert connection.execute(text('SELECT count(*) FROM users')).scalar()==0
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar()=='0010_annotation_quality'
        assert connection.execute(text('SELECT review_state,revision,approved_revision,negative_confirmed FROM images WHERE id=100')).one()==('in_progress',1,None,False)
        assert connection.execute(text('SELECT require_review FROM projects WHERE id=100')).scalar()==False
    assert {'users','user_sessions','password_reset_tokens','email_verification_tokens'}<=set(inspect(engine).get_table_names())
