"""Process entry point pieces: data dir, session record, and serving (R01).

The launcher is the only place that decides the data directory, binds the
listener, mints the session, and writes the private credential record.
Order matters: the listener is bound first so the session's authority is
the *actual* origin (a stale or placeholder address is never printed), the
session is minted second, and the record is written third -- before the
first request is served, so the maintainer's slash entry point can read
the bootstrap receipt as soon as the process is up.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .assets import AssetService
from .blobs import BlobStore
from .credentials import remove_private_file, write_private_json
from .components import ComponentService
from .canvas import CanvasService
from .orchestration import OrchestrationService
from .backup import BackupService
from .lifecycle import LifecycleService
from .owners import OwnerProjectionService
from .work import WorkRequestService
from .designsystem import DesignSystemService
from .http_server import WorkbenchHTTPServer
from .preview import PreviewServer
from .proposals import ProposalService
from .reuse import ReuseService
from .service import WorkbenchService
from .session import DEFAULT_SESSION_TTL_SECONDS, WorkbenchSession
from .store import Store, WorkbenchDataDirectory

RECORD_SCHEMA_VERSION = 1


@dataclass
class WorkbenchRuntime:
    """One running workbench service and everything it owns."""

    data_dir: WorkbenchDataDirectory
    store: Store
    session: WorkbenchSession
    service: WorkbenchService
    proposals: ProposalService
    assets: AssetService
    reuse: ReuseService
    design_system: DesignSystemService
    components: ComponentService
    canvases: CanvasService
    orchestration: OrchestrationService
    work: WorkRequestService
    owners: OwnerProjectionService
    lifecycle: LifecycleService
    backup: BackupService
    preview: PreviewServer
    server: WorkbenchHTTPServer
    record_path: Path
    record: dict

    @property
    def origin(self) -> str:
        return self.server.origin

    @property
    def preview_origin(self) -> str:
        return self.preview.origin

    @property
    def bootstrap_url(self) -> str:
        return self.record["bootstrapUrl"]

    def stop(self) -> None:
        """Stop serving, drop the credential record, and close the store."""
        try:
            self.server.stop()
        finally:
            try:
                self.preview.stop()
            finally:
                remove_private_file(self.record_path)
                self.store.close()


def build_record(*, session: WorkbenchSession, bootstrap_url: str) -> dict:
    """The private receipt: the OS-protected session credential plus the launch URL.

    R01 places the session credential in this record precisely so the
    maintainer's own non-browser entry points (slash) can reach the local
    service without a bootstrap exchange; the file is readable only by the
    current OS user, is never served, and is deleted when the service
    stops. Capabilities are added to the same record as they are minted.
    """
    return {
        "schemaVersion": RECORD_SCHEMA_VERSION,
        "authority": session.authority,
        "bootId": session.boot_id,
        "startedAt": session.started_at_iso,
        "expiresAt": session.expires_at_iso,
        "bootstrapUrl": bootstrap_url,
        "sessionToken": session.token,
        "capabilities": {},
    }


def write_record(path: Path, record: dict) -> Path:
    """Rewrite the private record (new capabilities are added here, never served)."""
    return write_private_json(path, record)


def start_runtime(
    *,
    data_dir: Path | str,
    bind_host: str = "127.0.0.1",
    port: int = 0,
    ui_directory: Path | str | None = None,
    ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    now_fn: Callable[[], float] | None = None,
) -> WorkbenchRuntime:
    """Bind, mint, persist the receipt, and start serving one workbench."""
    directory = WorkbenchDataDirectory(data_dir).ensure()
    store = Store(directory.database_path)
    blobs = BlobStore(directory.blob_dir)
    server = WorkbenchHTTPServer(
        bind_host=bind_host, port=port, ui_directory=ui_directory
    )
    try:
        # The preview origin is created after the management listener so the
        # preview policy can name exactly one allowed frame ancestor.
        preview = PreviewServer(blobs, frame_ancestors=(server.origin,))
        session = WorkbenchSession(
            authority=server.origin, ttl_seconds=ttl_seconds, now_fn=now_fn
        )
        service = WorkbenchService(store=store, data_dir=directory)
        proposals = ProposalService(store=store, service=service, data_dir=directory)
        assets = AssetService(store=store, service=service, blobs=blobs)
        reuse = ReuseService(
            store=store, service=service, assets=assets, blobs=blobs
        )
        design_system = DesignSystemService(
            store=store,
            service=service,
            assets=assets,
            proposals=proposals,
            blobs=blobs,
        )
        components = ComponentService(
            store=store,
            service=service,
            assets=assets,
            reuse=reuse,
            blobs=blobs,
        )
        canvases = CanvasService(
            store=store,
            service=service,
            components=components,
            reuse=reuse,
            blobs=blobs,
        )
        orchestration = OrchestrationService(
            store=store,
            service=service,
            canvases=canvases,
            assets=assets,
            blobs=blobs,
        )
        work = WorkRequestService(
            store=store,
            service=service,
            proposals=proposals,
            orchestration=orchestration,
            session=session,
            data_dir=directory,
        )
        owners = OwnerProjectionService(
            store=store,
            service=service,
            assets=assets,
            components=components,
            blobs=blobs,
        )
        lifecycle = LifecycleService(
            store=store,
            service=service,
            assets=assets,
        )
        backup = BackupService(
            store=store,
            service=service,
            data_dir=directory,
            blobs=blobs,
        )
        record = build_record(session=session, bootstrap_url=session.bootstrap_url())
        record_path = write_record(directory.session_record_path, record)
        server.attach(
            session=session,
            service=service,
            proposals=proposals,
            assets=assets,
            reuse=reuse,
            design_system=design_system,
            components=components,
            canvases=canvases,
            orchestration=orchestration,
            work=work,
            owners=owners,
            lifecycle=lifecycle,
            backup=backup,
            preview_origin=preview.origin,
        )
        preview.start_serving()
        server.start_serving()
    except BaseException:
        try:
            server.server_close()
        except Exception:
            pass
        try:
            preview.stop()
        except Exception:
            pass
        store.close()
        raise
    return WorkbenchRuntime(
        data_dir=directory,
        store=store,
        session=session,
        service=service,
        proposals=proposals,
        assets=assets,
        reuse=reuse,
        design_system=design_system,
        components=components,
        canvases=canvases,
        orchestration=orchestration,
        work=work,
        owners=owners,
        lifecycle=lifecycle,
        backup=backup,
        preview=preview,
        server=server,
        record_path=record_path,
        record=record,
    )


def describe(runtime: WorkbenchRuntime) -> str:
    """The one launch line printed to the maintainer's terminal."""
    return json.dumps(
        {
            "authority": runtime.origin,
            "previewOrigin": runtime.preview_origin,
            "bootId": runtime.session.boot_id,
            "expiresAt": runtime.session.expires_at_iso,
            "bootstrapUrl": runtime.bootstrap_url,
            "dataDir": str(runtime.data_dir.root),
            "record": str(runtime.record_path),
        },
        ensure_ascii=False,
        indent=2,
    )
