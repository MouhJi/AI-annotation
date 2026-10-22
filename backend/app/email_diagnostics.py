"""Operator-only CLI, never an HTTP endpoint. Does not print secrets or tokens."""
import argparse
import json
import smtplib
import socket
import ssl
from .email_config import email_settings
from .services.email_service import SMTPEmailProvider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-network', action='store_true', help='Check DNS, SMTP greeting and TLS; no email or login')
    parser.add_argument('--send-to', help='Explicitly send one diagnostic email to this address')
    args = parser.parse_args()
    try:
        config = email_settings()
        report = {'provider': config['provider'], 'real_email_enabled': config['provider'] == 'smtp',
                  'credentials_configured': bool(config['username'] and config['password']),
                  'starttls': config['starttls'], 'port': config['port']}
        if args.check_network or args.send_to:
            if config['provider'] != 'smtp':
                print(json.dumps({**report, 'status': 'Real email is not configured'}))
                return 1
        if args.check_network:
            socket.getaddrinfo(config['host'], config['port'], type=socket.SOCK_STREAM)
            with smtplib.SMTP(config['host'], config['port'], timeout=config['timeout']) as server:
                server.ehlo()
                if config['starttls']:
                    server.starttls(context=ssl.create_default_context())
                    server.ehlo()
            report['network'] = 'DNS, SMTP connection and TLS succeeded'
        if args.send_to:
            # No retries; explicit CLI flag is required for any outbound message.
            SMTPEmailProvider().send_email(args.send_to, 'Email delivery test — Data Annotation Platform',
                'This is a requested email delivery test. It contains no verification link or account token.')
            report['test_email'] = 'Accepted by SMTP; check the destination inbox and spam folder'
        print(json.dumps(report))
        return 0
    except (RuntimeError, ValueError, OSError, smtplib.SMTPException):
        print(json.dumps({'status': 'Email check failed. Review provider settings, credentials and network access.'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
