from __future__ import annotations

import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
MAP_STYLE = "https://maps.example.test/styles/rel005-sentinel.json"
RELEASE_REVISION = "rel005-revision-a1b2c3d4"
SENTRY_DSN = "https://public@example.test/42"


def run_docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture(scope="module")
def configured_frontend_image() -> Iterator[str]:
    image = f"cardvert-rel005-test:{uuid.uuid4().hex}"
    try:
        run_docker(
            "build",
            "--tag",
            image,
            "--build-arg",
            f"NEXT_PUBLIC_MAP_STYLE_URL={MAP_STYLE}",
            "--build-arg",
            f"NEXT_PUBLIC_SENTRY_DSN={SENTRY_DSN}",
            "--build-arg",
            f"VCS_REF={RELEASE_REVISION}",
            str(FRONTEND),
        )
        yield image
    finally:
        run_docker("image", "rm", "--force", image, check=False)


def assert_configured_release(
    image: str,
    *,
    expected_map_style: str | None,
    expected_revision: str | None,
    runtime_map_style: str | None = None,
) -> None:
    assert expected_map_style, "configured release inspection requires a map style"
    assert expected_revision, "configured release inspection requires a revision"

    run_args = ["run", "--rm"]
    if runtime_map_style is not None:
        run_args.extend(["--env", f"NEXT_PUBLIC_MAP_STYLE_URL={runtime_map_style}"])
    run_args.extend(
        [
            "--entrypoint",
            "sh",
            image,
            "-c",
            'grep -R -F -l -- "$1" /app/.next >/dev/null '
            '&& grep -R -F -l -- "$2" /app/.next >/dev/null',
            "rel005-inspector",
            expected_map_style,
            expected_revision,
        ]
    )
    artifact = run_docker(*run_args, check=False)
    assert artifact.returncode == 0, (
        "runtime artifact does not contain the expected compiled map style and revision\n"
        f"stdout:\n{artifact.stdout}\nstderr:\n{artifact.stderr}"
    )

    if runtime_map_style is not None:
        conflicting_artifact = run_docker(
            "run",
            "--rm",
            "--env",
            f"NEXT_PUBLIC_MAP_STYLE_URL={runtime_map_style}",
            "--entrypoint",
            "sh",
            image,
            "-c",
            'grep -R -F -l -- "$1" /app/.next >/dev/null',
            "rel005-conflict-inspector",
            runtime_map_style,
            check=False,
        )
        assert conflicting_artifact.returncode == 1, (
            "runtime map environment unexpectedly appears in the immutable artifact\n"
            f"stdout:\n{conflicting_artifact.stdout}\n"
            f"stderr:\n{conflicting_artifact.stderr}"
        )

    label = run_docker(
        "image",
        "inspect",
        "--format",
        "{{ index .Config.Labels \"org.opencontainers.image.revision\" }}",
        image,
    )
    assert label.stdout.strip() == expected_revision


def test_configured_map_and_revision_survive_immutable_image_build(
    configured_frontend_image: str,
) -> None:
    assert_configured_release(
        configured_frontend_image,
        expected_map_style=MAP_STYLE,
        expected_revision=RELEASE_REVISION,
    )


def test_runtime_map_environment_cannot_replace_compiled_map(
    configured_frontend_image: str,
) -> None:
    assert_configured_release(
        configured_frontend_image,
        expected_map_style=MAP_STYLE,
        expected_revision=RELEASE_REVISION,
        runtime_map_style="https://runtime.example.test/conflicting-style.json",
    )


@pytest.mark.parametrize(
    ("expected_map_style", "expected_revision"),
    [
        (None, RELEASE_REVISION),
        ("https://maps.example.test/styles/changed.json", RELEASE_REVISION),
        (MAP_STYLE, None),
        (MAP_STYLE, "changed-revision"),
    ],
)
def test_configured_release_inspection_rejects_missing_or_changed_expectations(
    configured_frontend_image: str,
    expected_map_style: str | None,
    expected_revision: str | None,
) -> None:
    with pytest.raises(AssertionError):
        assert_configured_release(
            configured_frontend_image,
            expected_map_style=expected_map_style,
            expected_revision=expected_revision,
        )
