from __future__ import annotations

import base64
import hashlib
import io
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

from poetry.core.masonry import api as poetry_api


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
SOURCE = REPO_ROOT / "src" / "main.cpp"
TARGET = PROJECT_ROOT / "cppkh_interface" / "data" / "src" / "main.cpp"
WHEEL_SOURCE_NAME = "cppkh_interface/data/src/main.cpp"


def _sync_cpp_source() -> None:
    if SOURCE.exists():
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE, TARGET)
        return
    if TARGET.exists():
        return
    raise FileNotFoundError(
        "cppkh source file was not found. Expected either "
        f"{SOURCE} in the repository checkout or {TARGET} in the source tree."
    )


def _clean_cpp_source() -> None:
    if TARGET.exists() and SOURCE.exists():
        TARGET.unlink()


def _source_bytes() -> bytes:
    if TARGET.exists():
        return TARGET.read_bytes()
    if SOURCE.exists():
        return SOURCE.read_bytes()
    raise FileNotFoundError("cppkh source file was not available for packaging")


def _wheel_hash_and_size(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return f"sha256={encoded}", str(len(data))


def _make_universal_wheel_metadata(data: bytes) -> bytes:
    text = data.decode("utf-8")
    lines = []
    tag_written = False
    root_written = False
    for line in text.splitlines():
        if line.startswith("Root-Is-Purelib:"):
            lines.append("Root-Is-Purelib: true")
            root_written = True
        elif line.startswith("Tag:"):
            if not tag_written:
                lines.append("Tag: py3-none-any")
                tag_written = True
        else:
            lines.append(line)
    if not root_written:
        lines.append("Root-Is-Purelib: true")
    if not tag_written:
        lines.append("Tag: py3-none-any")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _universal_wheel_path(wheel_path: Path, record_name: str) -> Path:
    dist_info = record_name.split("/", 1)[0]
    base = dist_info.removesuffix(".dist-info")
    return wheel_path.with_name(f"{base}-py3-none-any.whl")


def _rewrite_wheel_with_source(wheel_path: Path) -> Path:
    source_data = _source_bytes()
    rows: list[tuple[str, str, str]] = []

    with zipfile.ZipFile(wheel_path, "r") as zin:
        record_name = next(
            (name for name in zin.namelist() if name.endswith(".dist-info/RECORD")),
            None,
        )
        if record_name is None:
            raise RuntimeError(f"wheel RECORD file not found in {wheel_path}")
        output_path = _universal_wheel_path(wheel_path, record_name)
        temp_path = output_path.with_name(output_path.name + ".tmp")

        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            wheel_metadata_name = record_name.removesuffix("RECORD") + "WHEEL"

            for item in zin.infolist():
                if item.filename in (WHEEL_SOURCE_NAME, record_name):
                    continue
                data = zin.read(item.filename)
                if item.filename == wheel_metadata_name:
                    data = _make_universal_wheel_metadata(data)
                zout.writestr(item, data)
                if not item.is_dir():
                    digest, size = _wheel_hash_and_size(data)
                    rows.append((item.filename, digest, size))

            source_info = zipfile.ZipInfo(WHEEL_SOURCE_NAME, date_time=(2016, 1, 1, 0, 0, 0))
            source_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(source_info, source_data)
            digest, size = _wheel_hash_and_size(source_data)
            rows.append((WHEEL_SOURCE_NAME, digest, size))

            rows.append((record_name, "", ""))
            record_text = "".join(f"{path},{digest},{size}\n" for path, digest, size in rows)
            record_info = zipfile.ZipInfo(record_name, date_time=(2016, 1, 1, 0, 0, 0))
            record_info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(record_info, record_text.encode("utf-8"))

    temp_path.replace(output_path)
    if output_path != wheel_path and wheel_path.exists():
        wheel_path.unlink()
    return output_path


def finalize_poetry_wheels() -> None:
    dist = PROJECT_ROOT / "dist"
    if not dist.exists():
        return
    for wheel_path in sorted(dist.glob("cppkh_interface-*.whl")):
        _rewrite_wheel_with_source(wheel_path)


def _rewrite_sdist_with_source(sdist_path: Path) -> None:
    source_data = _source_bytes()
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz")
    temp_path = Path(temp_file.name)
    temp_file.close()

    try:
        with tarfile.open(sdist_path, "r:gz") as tin, tarfile.open(temp_path, "w:gz") as tout:
            names = tin.getnames()
            if not names:
                raise RuntimeError(f"sdist is empty: {sdist_path}")
            root = names[0].split("/", 1)[0]
            source_name = f"{root}/{WHEEL_SOURCE_NAME}"

            for member in tin.getmembers():
                if member.name == source_name:
                    continue
                if member.isfile():
                    extracted = tin.extractfile(member)
                    if extracted is None:
                        raise RuntimeError(f"could not read {member.name} from {sdist_path}")
                    with extracted:
                        tout.addfile(member, extracted)
                else:
                    tout.addfile(member)

            source_info = tarfile.TarInfo(source_name)
            source_info.size = len(source_data)
            source_info.mtime = 0
            source_info.mode = 0o644
            tout.addfile(source_info, io.BytesIO(source_data))

        temp_path.replace(sdist_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def get_requires_for_build_wheel(config_settings=None):
    return poetry_api.get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    return poetry_api.get_requires_for_build_sdist(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    _sync_cpp_source()
    try:
        return poetry_api.prepare_metadata_for_build_wheel(metadata_directory, config_settings)
    finally:
        _clean_cpp_source()


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    _sync_cpp_source()
    try:
        wheel_name = poetry_api.build_wheel(wheel_directory, config_settings, metadata_directory)
        final_path = _rewrite_wheel_with_source(Path(wheel_directory) / wheel_name)
        return final_path.name
    finally:
        _clean_cpp_source()


def build_sdist(sdist_directory, config_settings=None):
    _sync_cpp_source()
    try:
        sdist_name = poetry_api.build_sdist(sdist_directory, config_settings)
        _rewrite_sdist_with_source(Path(sdist_directory) / sdist_name)
        return sdist_name
    finally:
        _clean_cpp_source()
