import os
import smtplib
import ssl
import uuid
from datetime import timedelta
from email import policy
from email.parser import BytesParser
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from sqlalchemy import select
from app.auth_config import settings
from app.database import SessionLocal
from app.email_config import email_settings
from app.models import EmailDeliveryAttempt, EmailVerificationToken, User, WorkspaceMember
from app.models.auth import utcnow
from app.services.auth_security import token_hash
from app.services.email_service import SMTPEmailProvider, FileEmailProvider, prepare_delivery, deliver_email
from app.services.email_templates import action_email
from .test_auth import account, browser, latest_token, PASSWORD


def smtp_config(monkeypatch):
    for name,value in dict(EMAIL_PROVIDER='smtp',SMTP_HOST='smtp.gmail.com',SMTP_PORT='587',
                           SMTP_USE_STARTTLS='true',SMTP_USERNAME='sender@example.com',
                           SMTP_PASSWORD='private-app-password',SMTP_FROM_EMAIL='sender@example.com').items():
        monkeypatch.setenv(name,value)


@pytest.mark.parametrize('variable,value', [('SMTP_HOST',''),('SMTP_FROM_EMAIL',''),('SMTP_PORT','465'),
    ('SMTP_USE_STARTTLS','false'),('SMTP_USE_STARTTLS','typo'),('SMTP_PASSWORD',''),('SMTP_TIMEOUT_SECONDS','nan'),
    ('EMAIL_PROVIDER','unknown')])
def test_invalid_smtp_config(monkeypatch,variable,value):
    smtp_config(monkeypatch);monkeypatch.setenv(variable,value)
    with pytest.raises(RuntimeError):email_settings()


def test_production_rejects_file_and_bad_frontend_url(monkeypatch):
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError):email_settings()
    smtp_config(monkeypatch);monkeypatch.setenv('AUTH_COOKIE_SECURE','true')
    monkeypatch.setenv('FRONTEND_URL','https://user:password@example.com')
    with pytest.raises(RuntimeError):settings.__wrapped__()
    monkeypatch.setenv('FRONTEND_URL','https://annotation.example.com')
    monkeypatch.setenv('CORS_ORIGINS','https://annotation.example.com')
    assert settings.__wrapped__()['email_backend']=='smtp'


def test_smtp_sends_multipart_to_exact_recipient_with_verified_tls(monkeypatch):
    smtp_config(monkeypatch)
    server=MagicMock();server.send_message.return_value={}
    connection=MagicMock();connection.__enter__.return_value=server
    constructor=MagicMock(return_value=connection)
    monkeypatch.setattr('app.services.email_service.smtplib.SMTP',constructor)
    SMTPEmailProvider().send_email('recipient@example.com','Subject','Plain body','<p>HTML body</p>')
    constructor.assert_called_once_with('smtp.gmail.com',587,timeout=10)
    context=server.starttls.call_args.kwargs['context']
    assert context.check_hostname and context.verify_mode==ssl.CERT_REQUIRED
    server.login.assert_called_once_with('sender@example.com','private-app-password')
    message=server.send_message.call_args.args[0]
    assert message['To']=='recipient@example.com' and message.is_multipart()
    assert message.get_body(preferencelist=('plain',)).get_content().strip()=='Plain body'
    assert message.get_body(preferencelist=('html',)).get_content().strip()=='<p>HTML body</p>'
    assert server.send_message.call_args.kwargs['to_addrs']==['recipient@example.com']


def test_file_provider_keeps_both_parts_and_blocks_production(monkeypatch,tmp_path):
    monkeypatch.setenv('STORAGE_PATH',str(tmp_path))
    FileEmailProvider().send_email('user@example.com','Verify email','Text','<p>HTML</p>')
    path=next((tmp_path/'.emails').glob('*.eml'))
    message=BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    assert message['To']=='user@example.com' and message.is_multipart()
    monkeypatch.setenv('APP_ENV','production')
    with pytest.raises(RuntimeError):FileEmailProvider().send_email('user@example.com','x','y')


@pytest.mark.parametrize('failure',[smtplib.SMTPAuthenticationError(535,b'private-app-password'),TimeoutError('secret token'),smtplib.SMTPException('private-app-password')])
def test_delivery_failure_preserves_user_records_failure_and_never_falls_back(monkeypatch,caplog,failure):
    smtp_config(monkeypatch)
    monkeypatch.setattr(SMTPEmailProvider,'send_email',MagicMock(side_effect=failure))
    file_send=MagicMock();monkeypatch.setattr(FileEmailProvider,'send_email',file_send)
    email=uuid.uuid4().hex+'@example.com';client=browser()
    response=client.post('/api/auth/register',json={'email':email,'password':PASSWORD,'full_name':'Saved User'})
    assert response.status_code==201 and response.json()['email_delivery']=='failed'
    file_send.assert_not_called()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==email));assert user
        token=db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.user_id==user.id))
        attempt=db.scalar(select(EmailDeliveryAttempt).where(EmailDeliveryAttempt.resource_id==str(token.id)))
        assert attempt.status=='failed' and token.used_at is None
    assert 'private-app-password' not in caplog.text and 'secret token' not in caplog.text
    assert 'private-app-password' not in response.text and 'token' not in response.text


def test_registration_commits_token_before_smtp_and_records_acceptance(monkeypatch):
    smtp_config(monkeypatch)
    def send(to,subject,text,html):
        with SessionLocal() as db:
            user=db.scalar(select(User).where(User.email==to));assert user
            assert db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.user_id==user.id))
            assert db.scalar(select(EmailDeliveryAttempt).where(EmailDeliveryAttempt.status=='sending'))
        assert '24 hours' in text and '#token=' in text and 'Verify Email' in html
    mocked=MagicMock(side_effect=send);monkeypatch.setattr(SMTPEmailProvider,'send_email',mocked)
    client,email,registered,_=account()
    assert registered['email_delivery']=='sent';mocked.assert_called_once()


def test_verification_expiry_revocation_single_use_and_own_resend():
    client,email,user,_=account();first=latest_token(email,'verify-email')
    response=client.post('/api/auth/me/resend-verification')
    assert response.status_code==200 and response.json()['email_delivery']=='development'
    latest=latest_token(email,'verify-email');assert latest!=first
    assert client.post('/api/auth/verify-email',json={'token':first}).status_code==400
    with SessionLocal() as db:
        row=db.scalar(select(EmailVerificationToken).where(EmailVerificationToken.token_hash==token_hash(latest)))
        row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert 'expired' in client.post('/api/auth/verify-email',json={'token':latest}).json()['detail']
    assert client.post('/api/auth/verify-email',json={'token':'x'*40}).status_code==400
    client.post('/api/auth/resend-verification',json={'email':email});latest=latest_token(email,'verify-email')
    assert client.post('/api/auth/verify-email',json={'token':latest}).status_code==200
    assert client.post('/api/auth/verify-email',json={'token':latest}).status_code==400
    assert client.get('/api/auth/me').json()['email_verified']


def test_public_resend_is_generic_and_rate_limited():
    client,email,_,_=account()
    known=client.post('/api/auth/resend-verification',json={'email':email})
    unknown=client.post('/api/auth/resend-verification',json={'email':'missing@example.com'})
    assert known.json()==unknown.json() and 'token' not in known.text
    assert client.post('/api/auth/resend-verification',json={'email':email}).status_code==200
    assert client.post('/api/auth/resend-verification',json={'email':email}).status_code==429


def test_delivery_receipt_prevents_repeated_send(monkeypatch):
    send=MagicMock();monkeypatch.setattr(FileEmailProvider,'send_email',send)
    with SessionLocal() as db:
        attempt=prepare_delivery(db,'verification',uuid.uuid4());db.commit()
        assert deliver_email(db,attempt,'p@example.com','Subject','Body')=='development'
        with pytest.raises(RuntimeError,match='already attempted'):
            deliver_email(db,attempt,'p@example.com','Subject','Body')
    send.assert_called_once()


def test_templates_escape_untrusted_content():
    for kind in ['verification','password_reset','invitation']:
        subject,text,html=action_email(kind,'https://app.example/verify-email#token=safe',name='<script>alert(1)</script>',workspace='<img src=x onerror=alert(1)>')
        assert '<script>' not in html and '<img' not in html
        assert 'https://app.example/' in html and 'text' not in subject.lower()
        assert 'single-use' in text


def test_invitation_register_verify_accept_and_password_reset_use_same_provider():
    owner,_,_,_=account();client=browser();email=uuid.uuid4().hex+'@example.com'
    workspace=owner.get('/api/workspaces').json()[0]
    invitation=owner.post(f"/api/workspaces/{workspace['id']}/invitations",json={'email':email,'role':'reviewer'})
    assert invitation.status_code==201 and invitation.json()['delivery']=='development_file'
    client,email,user,_=account_with_email(client,email)
    verify=latest_token(email,'verify-email')
    assert client.post('/api/auth/verify-email',json={'token':verify}).status_code==200
    # Verification itself must never confer membership.
    assert all(row['id']!=workspace['id'] for row in client.get('/api/workspaces').json())
    rows=client.get('/api/me/invitations').json();assert len(rows)==1
    assert client.post(f"/api/me/invitations/{rows[0]['invitation_id']}/accept").status_code==200
    assert client.post('/api/auth/forgot-password',json={'email':email}).status_code==200
    reset=latest_token(email,'reset-password')
    assert client.post('/api/auth/reset-password',json={'token':reset,'new_password':'new password for email flow'}).status_code==200
    assert client.get('/api/auth/me').status_code==401


def account_with_email(client,email):
    registered=client.post('/api/auth/register',json={'email':email,'password':PASSWORD,'full_name':'Invited User'})
    assert registered.status_code==201
    login=client.post('/api/auth/login',json={'email':email,'password':PASSWORD}).json()
    client.headers['Authorization']='Bearer '+login['access_token']
    return client,email,registered.json(),login
