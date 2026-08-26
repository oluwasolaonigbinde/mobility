import os
import subprocess
import time
from pathlib import Path


def _fake_docker(bin_dir: Path) -> None:
    executable = bin_dir / "docker"
    executable.write_text(
        "#!/usr/bin/env bash\nprintf 'synthetic-backup'\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)


def test_backup_prunes_files_older_than_the_bounded_rotation(tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    bin_dir = tmp_path / "bin"
    backup_dir.mkdir()
    bin_dir.mkdir()
    _fake_docker(bin_dir)
    expired = backup_dir / "mobility_20260101T000000Z.dump"
    recent = backup_dir / "mobility_20260825T000000Z.dump"
    expired.write_bytes(b"expired")
    recent.write_bytes(b"recent")
    forty_days_ago = time.time() - (40 * 24 * 60 * 60)
    os.utime(expired, (forty_days_ago, forty_days_ago))

    result = subprocess.run(
        ["bash", "scripts/db_backup.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env={
            **os.environ,
            "BACKUP_DIR": str(backup_dir),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not expired.exists()
    assert recent.exists()
    assert "never over 35 days" in result.stdout


def test_backup_rejects_retention_beyond_architecture_bound(tmp_path: Path) -> None:
    result = subprocess.run(
        ["bash", "scripts/db_backup.sh"],
        cwd=Path(__file__).resolve().parents[1],
        env={**os.environ, "BACKUP_DIR": str(tmp_path), "BACKUP_RETENTION_DAYS": "36"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "1 through 35" in result.stderr
