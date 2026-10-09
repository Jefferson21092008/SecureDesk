"""SecureDesk Etapa 06: manual, read-only backup and offline verification.

Never restores a database or writes to S3. No .env, password or secret is
included in output/manifest. Backup contents and manifests are confidential.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
from datetime import datetime, timezone

CHUNK_SIZE = 1024 * 1024
MANIFEST_VERSION = 1
_SAFE_HOST = re.compile(r"[A-Za-z0-9][A-Za-z0-9.\-]*\Z")
_SAFE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*\Z")
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


class BackupError(Exception):
    """An anticipated backup or verification failure; omit secret diagnostics."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _identifier(prefix: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{timestamp}-{secrets.token_hex(4)}"


def _sha256_file(path: Path) -> tuple[int, str]:
    sha = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            total += len(chunk)
            sha.update(chunk)
    return total, sha.hexdigest()


def _backup_root(directory: str) -> Path:
    # The script is installed in SecureDesk/scripts; backups MUST be outside Git.
    repository = Path(__file__).resolve().parent.parent
    root = Path(directory).expanduser().resolve()
    if root == repository or repository in root.parents:
        raise BackupError("O destino do backup deve ficar FORA do repositorio Git")
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not root.is_dir():
            raise BackupError("Destino de backup invalido")
    except OSError as exc:
        raise BackupError("Nao foi possivel preparar destino do backup") from exc
    return root


def _approve_environment(args: argparse.Namespace) -> None:
    if args.environment == "production" and not args.confirm_production:
        raise BackupError("Producao requer --confirm-production (somente LEITURA)")


def _write_manifest(path: Path, content: dict) -> None:
    # Called only for a newly generated, unpublished backup path.
    with path.open("x", encoding="utf-8") as handle:
        json.dump(content, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")


def _safe_manifest_path(folder: Path, name: object) -> Path:
    if not isinstance(name, str) or not name or Path(name).name != name or name in {".", ".."}:
        raise BackupError("Manifesto tem nome de arquivo invalido")
    dest = folder / name
    if not dest.is_file() or dest.is_symlink():
        raise BackupError("Arquivo do backup ausente ou link simbolico")
    return dest


def _parse_manifest(path: Path, kind: str) -> dict:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 10 * 1024 * 1024:
            raise BackupError("Manifesto ausente ou grande demais")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise BackupError("Nao foi possivel ler o manifesto") from exc
    if not isinstance(data, dict) or data.get("schema_version") != MANIFEST_VERSION or data.get("kind") != kind:
        raise BackupError("Tipo/versao de manifesto invalido")
    return data


def _valid_archive_metadata(data: object) -> tuple[str, int, str]:
    if not isinstance(data, dict):
        raise BackupError("Metadados invalidos")
    filename, size, sha = data.get("filename"), data.get("size_bytes"), data.get("sha256")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise BackupError("Tamanho de arquivo invalido")
    if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
        raise BackupError("SHA-256 invalido")
    if not isinstance(filename, str):
        raise BackupError("Nome do arquivo invalido")
    return filename, size, sha


def _assert_digest(path: Path, expected_size: int, expected_sha: str) -> None:
    size, sha = _sha256_file(path)
    if size != expected_size or sha != expected_sha:
        raise BackupError("Integridade do backup FALHOU (tamanho ou SHA-256)")


def backup_database(args: argparse.Namespace) -> Path:
    _approve_environment(args)
    if not _SAFE_HOST.fullmatch(args.host) or not _SAFE_NAME.fullmatch(args.dbname) or not _SAFE_NAME.fullmatch(args.user):
        raise BackupError("Use host, nome do banco e usuario sem URL nem credenciais")
    if args.environment == "production":
        if args.sslmode not in {"require", "verify-ca", "verify-full"}:
            raise BackupError("Banco de producao exige SSL")
        if "-pooler" in args.host.lower():
            raise BackupError("Use o endpoint DIRETO do Neon, nao o pooler")
    if shutil.which("pg_dump") is None or shutil.which("pg_restore") is None:
        raise BackupError("pg_dump e pg_restore precisam estar no PATH")

    root = _backup_root(args.out_dir)
    ident = _identifier("db")
    archive = root / f"{ident}.dump"
    temp = root / f".{ident}.partial"
    manifest = root / f"{ident}.json"
    env = dict(os.environ)
    env["PGSSLMODE"] = args.sslmode
    command = [
        "pg_dump", "--format=custom", "--file", str(temp),
        "--host", args.host, "--port", str(args.port),
        "--username", args.user, "--dbname", args.dbname,
    ]
    try:
        # Keep stderr attached to the console so libpq can visibly prompt for
        # a password on Windows; never pass passwords on the command line.
        result = subprocess.run(command, env=env, stdout=subprocess.DEVNULL, check=False)
        if result.returncode != 0:
            raise BackupError("pg_dump falhou; confira conexao, permissao, senha e espaco em disco")
        if not temp.is_file() or temp.stat().st_size == 0:
            raise BackupError("pg_dump nao gerou um arquivo valido")
        result = subprocess.run(["pg_restore", "--list", str(temp)], capture_output=True, check=False)
        if result.returncode != 0:
            raise BackupError("pg_restore --list falhou para o dump criado")
        size, checksum = _sha256_file(temp)
        temp.replace(archive)
        _write_manifest(manifest, {
            "schema_version": MANIFEST_VERSION, "kind": "postgresql",
            "created_at_utc": _now(), "environment": args.environment,
            "archive": {"filename": archive.name, "size_bytes": size, "sha256": checksum},
            "verification": "pg_restore --list passed; NOT a full restore",
        })
        return manifest
    except (OSError, subprocess.SubprocessError) as exc:
        raise BackupError("Falha local ao executar backup; verifique PATH e permissao") from exc
    finally:
        temp.unlink(missing_ok=True)
        # Manifest and archive must always travel together.
        if archive.exists() and not manifest.exists():
            archive.unlink()


def verify_database(manifest_path: str) -> int:
    path = Path(manifest_path).resolve()
    data = _parse_manifest(path, "postgresql")
    name, size, sha = _valid_archive_metadata(data.get("archive"))
    if not name.endswith(".dump"):
        raise BackupError("Formato inesperado do dump")
    archive = _safe_manifest_path(path.parent, name)
    _assert_digest(archive, size, sha)
    if shutil.which("pg_restore") is None:
        raise BackupError("pg_restore nao esta no PATH")
    try:
        result = subprocess.run(["pg_restore", "--list", str(archive)], capture_output=True, check=False)
    except OSError as exc:
        raise BackupError("pg_restore nao pode ser executado") from exc
    if result.returncode:
        raise BackupError("pg_restore --list falhou")
    return 1


def _s3_client_and_bucket():
    # Reuses exactly the S3 connection configuration tested in Etapa 05.
    from app.core.config import settings
    from app.services.attachment_s3 import _client

    if not all((settings.s3_endpoint_url, settings.s3_bucket_name,
                settings.s3_access_key_id, settings.s3_secret_access_key.get_secret_value())):
        raise BackupError("Configure S3_* no .env local PRIVADO antes de exportar")
    return _client(), settings.s3_bucket_name


def _object_inventory(client, bucket: str, *, max_objects: int, max_bytes: int) -> list[tuple[str, int]]:
    inventory: list[tuple[str, int]] = []
    seen: set[str] = set()
    total = 0
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            key, size = obj.get("Key"), obj.get("Size")
            if (not isinstance(key, str) or not key or key in seen or
                    not isinstance(size, int) or isinstance(size, bool) or size < 0):
                raise BackupError("Inventario S3 tem chaves/tamanhos invalidos ou duplicados")
            seen.add(key)
            total += size
            inventory.append((key, size))
            if len(inventory) > max_objects or total > max_bytes:
                raise BackupError("Bucket excede limite seguro escolhido; ajuste --max-* conscientemente")
    return inventory


def backup_objects(args: argparse.Namespace) -> Path:
    _approve_environment(args)
    if args.max_objects < 1 or args.max_total_mib < 1:
        raise BackupError("Limites devem ser positivos")
    root = _backup_root(args.out_dir)
    # Do not print SDK errors, credentials, remote object keys or private hostnames.
    try:
        client, bucket = _s3_client_and_bucket()
        inventory = _object_inventory(
            client, bucket, max_objects=args.max_objects,
            max_bytes=args.max_total_mib * 1024 * 1024,
        )
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("Falha ao listar objetos S3; confira configuracao e permissao") from exc
    if not inventory and not args.allow_empty:
        raise BackupError("Bucket vazio; confirme destino ou use --allow-empty se esperado")

    ident = _identifier("objects")
    temp = root / f".{ident}.partial"
    final = root / ident
    entries = []
    try:
        temp.mkdir(mode=0o700)
        (temp / "objects").mkdir(mode=0o700)
        for key, expected in inventory:
            filename = hashlib.sha256(key.encode("utf-8")).hexdigest() + ".bin"
            output = temp / "objects" / filename
            response = client.get_object(Bucket=bucket, Key=key)
            body = response["Body"]
            count = 0
            digest = hashlib.sha256()
            try:
                with output.open("xb") as handle:
                    while chunk := body.read(CHUNK_SIZE):
                        count += len(chunk)
                        if count > expected:
                            raise BackupError("Objeto mudou durante o backup S3; refaca em janela sem escritas")
                        handle.write(chunk)
                        digest.update(chunk)
            finally:
                body.close()
            if count != expected:
                raise BackupError("Objeto mudou durante o backup S3; refaca em janela sem escritas")
            entries.append({
                "key": key,  # Confidential: required to restore the exact remote object later.
                "filename": filename, "size_bytes": count, "sha256": digest.hexdigest(),
            })
        _write_manifest(temp / "manifest.json", {
            "schema_version": MANIFEST_VERSION, "kind": "s3-objects",
            "created_at_utc": _now(), "environment": args.environment,
            "objects_count": len(entries), "objects": entries,
            "note": "Not a coordinated PostgreSQL+S3 snapshot. Contains sensitive keys.",
        })
        temp.rename(final)
        return final / "manifest.json"
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("Falha ao exportar objetos S3 (nenhuma exclusao remota)") from exc
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def verify_objects(manifest_path: str) -> int:
    path = Path(manifest_path).resolve()
    data = _parse_manifest(path, "s3-objects")
    objects = data.get("objects")
    count = data.get("objects_count")
    if (not isinstance(objects, list) or not isinstance(count, int) or
            isinstance(count, bool) or count != len(objects)):
        raise BackupError("Manifesto S3 tem contagem invalida")
    object_dir = path.parent / "objects"
    if not object_dir.is_dir() or object_dir.is_symlink():
        raise BackupError("Diretorio dos objetos nao encontrado")
    expected_names = set()
    keys = set()
    for entry in objects:
        name, size, sha = _valid_archive_metadata(entry)
        key = entry.get("key")
        if not isinstance(key, str) or not key or key in keys:
            raise BackupError("Objeto S3 sem chave valida ou duplicado")
        if name != hashlib.sha256(key.encode("utf-8")).hexdigest() + ".bin":
            raise BackupError("Nome do objeto nao corresponde a chave no manifesto")
        if name in expected_names:
            raise BackupError("Objeto duplicado no manifesto")
        keys.add(key)
        expected_names.add(name)
        _assert_digest(_safe_manifest_path(object_dir, name), size, sha)
    actual_names = {p.name for p in object_dir.iterdir()}
    if actual_names != expected_names:
        raise BackupError("Objetos extras ou faltando na pasta de backup")
    return len(objects)



def _local_snapshot_from_rows(source_root: Path, rows: list[tuple[str, int]], out_dir: str,
                              *, max_files: int, max_total_mib: int) -> Path:
    """Snapshot only locally stored attachment keys known to the development DB.

    All paths in the resulting manifest are confidential; no production writes.
    """
    if max_files < 1 or max_total_mib < 1:
        raise BackupError("Limites para anexos locais devem ser positivos")
    if not source_root.is_dir():
        raise BackupError("Diretorio de anexos locais inexistente")
    if not rows:
        raise BackupError("Nao existem anexos locais registrados neste banco")
    if len(rows) > max_files:
        raise BackupError("Quantidade de anexos locais ultrapassa --max-files")
    source_root = source_root.resolve()
    total = 0
    names: set[str] = set()
    sources: list[tuple[str, Path, int]] = []
    for key, size in rows:
        # The key is a server-generated filename, never a user-controlled path.
        if (not isinstance(key, str) or not key or key in {".", ".."}
                or "/" in key or "\\" in key or ":" in key or Path(key).name != key
                or key in names):
            raise BackupError("Chave de anexo local invalida ou repetida")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise BackupError("Tamanho registrado de anexo local invalido")
        names.add(key)
        total += size
        if total > max_total_mib * 1024 * 1024:
            raise BackupError("Anexos locais excedem limite de tamanho escolhido")
        original = source_root / key
        if original.is_symlink() or not original.is_file() or original.resolve().parent != source_root:
            raise BackupError("Anexo local ausente, link simbolico ou caminho inseguro")
        if original.stat().st_size != size:
            raise BackupError("Tamanho do anexo local difere do registro do banco")
        sources.append((key, original, size))

    root = _backup_root(out_dir)
    ident = _identifier("local")
    temp = root / f".{ident}.partial"
    final = root / ident
    entries = []
    try:
        temp.mkdir(mode=0o700)
        (temp / "objects").mkdir(mode=0o700)
        for key, original, expected_size in sources:
            filename = hashlib.sha256(key.encode("utf-8")).hexdigest() + ".bin"
            target = temp / "objects" / filename
            initial_size, initial_sha = _sha256_file(original)
            if initial_size != expected_size:
                raise BackupError("Anexo local mudou durante o backup")
            with original.open("rb") as inp, target.open("xb") as out:
                while chunk := inp.read(CHUNK_SIZE):
                    out.write(chunk)
            copied_size, copied_sha = _sha256_file(target)
            final_size, final_sha = _sha256_file(original)
            if ((copied_size, copied_sha) != (initial_size, initial_sha)
                    or (final_size, final_sha) != (initial_size, initial_sha)):
                raise BackupError("Anexo local mudou durante o backup")
            entries.append({"key": key, "filename": filename,
                            "size_bytes": copied_size, "sha256": copied_sha})
        _write_manifest(temp / "manifest.json", {
            "schema_version": MANIFEST_VERSION, "kind": "local-attachments",
            "created_at_utc": _now(), "environment": "development",
            "objects_count": len(entries), "objects": entries,
            "note": "Private keys and file contents. Local database metadata snapshot only.",
        })
        temp.rename(final)
        return final / "manifest.json"
    except BackupError:
        raise
    except OSError as exc:
        raise BackupError("Falha ao copiar anexos locais para o backup") from exc
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def backup_local(args: argparse.Namespace) -> Path:
    """Read attachment files listed by the local development database only."""
    if args.environment != "development":
        raise BackupError("Backup de legados locais exige ambiente development")
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from app.core.config import settings

        url = make_url(settings.database_url)
        if (str(settings.app_env).lower() != "development"
                or url.host not in {"localhost", "127.0.0.1", "::1"}):
            raise BackupError("Somente PostgreSQL LOCAL com APP_ENV=development")
        engine = create_engine(settings.database_url)
        try:
            with engine.connect() as conn:
                rows = [tuple(row) for row in conn.execute(text(
                    "SELECT storage_key, size_bytes FROM attachments "
                    "WHERE storage_backend='local' ORDER BY id"
                )).all()]
        finally:
            engine.dispose()
        return _local_snapshot_from_rows(
            Path(settings.attachments_dir), rows, args.out_dir,
            max_files=args.max_files, max_total_mib=args.max_total_mib,
        )
    except BackupError:
        raise
    except Exception as exc:
        raise BackupError("Falha na leitura dos anexos do banco local") from exc


def verify_local(manifest_path: str) -> int:
    path = Path(manifest_path).resolve()
    data = _parse_manifest(path, "local-attachments")
    objects = data.get("objects")
    count = data.get("objects_count")
    if (not isinstance(objects, list) or not isinstance(count, int)
            or isinstance(count, bool) or count != len(objects) or count < 1):
        raise BackupError("Manifesto local tem contagem invalida")
    objects_dir = path.parent / "objects"
    if not objects_dir.is_dir() or objects_dir.is_symlink():
        raise BackupError("Diretorio do backup local ausente")
    names: set[str] = set()
    keys: set[str] = set()
    for entry in objects:
        name, size, sha = _valid_archive_metadata(entry)
        key = entry.get("key")
        if (not isinstance(key, str) or not key or key in keys
                or key in {".", ".."} or "/" in key or "\\" in key or ":" in key):
            raise BackupError("Chave de anexo local invalida ou duplicada")
        if name != hashlib.sha256(key.encode("utf-8")).hexdigest() + ".bin" or name in names:
            raise BackupError("Nome de arquivo local incoerente")
        names.add(name)
        keys.add(key)
        _assert_digest(_safe_manifest_path(objects_dir, name), size, sha)
    if {p.name for p in objects_dir.iterdir()} != names:
        raise BackupError("Objetos extras ou faltando no backup local")
    return len(objects)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SecureDesk: backup manual SEM RESTORE e verificacao offline")
    sub = parser.add_subparsers(dest="operation", required=True)
    db = sub.add_parser("database", help="pg_dump custom com hash e validacao pg_restore --list")
    db.add_argument("--host", required=True, help="Somente hostname, NUNCA URI")
    db.add_argument("--dbname", required=True)
    db.add_argument("--user", required=True)
    db.add_argument("--port", type=int, choices=range(1, 65536), metavar="1-65535", default=5432)
    db.add_argument("--sslmode", choices=["disable", "prefer", "require", "verify-ca", "verify-full"], default="disable")
    objects = sub.add_parser("objects", help="Copia read-only de objetos do bucket S3 privado")
    objects.add_argument("--max-objects", type=int, default=1000)
    objects.add_argument("--max-total-mib", type=int, default=256)
    objects.add_argument("--allow-empty", action="store_true")
    legacy = sub.add_parser("local", help="Copia somente anexos legados do PostgreSQL LOCAL")
    legacy.add_argument("--out-dir", required=True, help="Pasta privada fora do repositorio")
    legacy.add_argument("--environment", choices=["development"], required=True)
    legacy.add_argument("--max-files", type=int, default=100)
    legacy.add_argument("--max-total-mib", type=int, default=30)
    for command in (db, objects):
        command.add_argument("--out-dir", required=True, help="Pasta PRIVADA FORA do repositorio")
        command.add_argument("--environment", required=True, choices=["development", "production"])
        command.add_argument("--confirm-production", action="store_true")
    verify_db = sub.add_parser("verify-database", help="SHA-256 + pg_restore --list, sem restaurar")
    verify_db.add_argument("--manifest", required=True)
    verify_s3 = sub.add_parser("verify-objects", help="SHA-256 e completude do snapshot S3 local")
    verify_s3.add_argument("--manifest", required=True)
    verify_legacy = sub.add_parser("verify-local", help="SHA-256 e completude dos anexos legados")
    verify_legacy.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.operation == "database":
            print(f"Backup DB pronto: {backup_database(args)}")
        elif args.operation == "objects":
            print(f"Backup S3 pronto: {backup_objects(args)}")
        elif args.operation == "local":
            print(f"Backup local pronto: {backup_local(args)}")
        elif args.operation == "verify-local":
            count = verify_local(args.manifest)
            print(f"Backup local verificado: {count} arquivo(s), tamanho e SHA-256 OK")
        elif args.operation == "verify-database":
            verify_database(args.manifest)
            print("Backup DB verificado: SHA-256 e pg_restore --list OK (restore REAL pendente)")
        else:
            total = verify_objects(args.manifest)
            print(f"Backup S3 verificado: {total} arquivo(s), tamanho e SHA-256 OK")
    except BackupError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
