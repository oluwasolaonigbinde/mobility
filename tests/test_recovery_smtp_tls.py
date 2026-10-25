import asyncio
import socket
import ssl
import threading
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.adapters.messaging.email import EmailMessage, EmailSendError, SmtpEmailAdapter
from app.core.config import Settings


def local_certificate(tmp_path, *, expired):
    now = datetime.now(UTC)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert = tmp_path / "certificate.pem"
    private = tmp_path / "private.pem"
    cert.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return cert, private


def serve_smtp(listener, context, commands):
    connection = None
    try:
        connection, _ = listener.accept()
        connection.settimeout(5)
        connection.sendall(b"220 local verification fixture\r\n")
        while True:
            # One byte at a time avoids buffering TLS bytes into a plaintext reader.
            line = bytearray()
            while not line.endswith(b"\r\n"):
                chunk = connection.recv(1)
                if not chunk:
                    return
                line.extend(chunk)
            command = bytes(line).split(b" ", 1)[0].strip().upper()
            commands.append(command)
            if command == b"EHLO":
                connection.sendall(b"250-localhost\r\n250-STARTTLS\r\n250 AUTH PLAIN\r\n")
            elif command == b"STARTTLS":
                connection.sendall(b"220 start verification\r\n")
                connection = context.wrap_socket(connection, server_side=True)
            elif command == b"AUTH":
                connection.sendall(b"235 authenticated\r\n")
            elif command == b"DATA":
                connection.sendall(b"354 send data\r\n")
                body = bytearray()
                while not body.endswith(b"\r\n.\r\n"):
                    body.extend(connection.recv(1))
                connection.sendall(b"250 accepted\r\n")
            elif command == b"QUIT":
                connection.sendall(b"221 bye\r\n")
                return
            else:
                connection.sendall(b"250 ok\r\n")
    except (OSError, ssl.SSLError):
        pass
    finally:
        if connection is not None:
            connection.close()


@pytest.mark.parametrize("mode", ["trusted", "untrusted", "hostname_mismatch", "expired"])
def test_actual_smtp_tls_verification_before_auth_or_data(tmp_path, monkeypatch, mode):
    cert, private = local_certificate(tmp_path, expired=mode == "expired")
    if mode != "untrusted":
        monkeypatch.setenv("SSL_CERT_FILE", str(cert))
    else:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, private)
    commands = []
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        thread = threading.Thread(
            target=serve_smtp, args=(listener, context, commands), daemon=True
        )
        thread.start()
        adapter = SmtpEmailAdapter(
            Settings(
                environment="test",
                email_smtp_host="127.0.0.1" if mode == "hostname_mismatch" else "localhost",
                email_smtp_port=listener.getsockname()[1],
                email_smtp_starttls=True,
                email_smtp_username="synthetic-user",
                email_sender_address="fixture@cardvert.invalid",
            )
        )
        message = EmailMessage(
            recipient="recipient@cardvert.invalid",
            subject="TLS fixture",
            text_body="Synthetic",
            html_body="<p>Synthetic</p>",
            idempotency_key="local-tls-fixture",
        )
        if mode == "trusted":
            asyncio.run(adapter.send(message))
        else:
            with pytest.raises(EmailSendError) as failure:
                asyncio.run(adapter.send(message))
            assert failure.value.code == "email_provider_unavailable"
            assert isinstance(failure.value.__cause__, ssl.SSLCertVerificationError)
        thread.join(timeout=6)
        assert not thread.is_alive()
    assert commands.count(b"STARTTLS") == 1
    assert (b"AUTH" in commands) is (mode == "trusted")
    assert (b"DATA" in commands) is (mode == "trusted")
