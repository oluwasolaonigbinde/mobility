from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.dependencies import (
    AdminUserDependency,
    AdvertiserUserDependency,
    DriverUserDependency,
    SessionDependency,
    SettingsDependency,
    StorageDependency,
)
from app.models.stored_file import StoredFile
from app.schemas.stored_files import (
    FileDownloadRead,
    FileDownloadRequest,
    FileUploadCreate,
    FileUploadRead,
    PresignedPostRead,
    StoredFileRead,
)
from app.services.stored_files import (
    confirm_advertiser_upload,
    confirm_driver_upload,
    create_advertiser_upload_intent,
    create_driver_upload_intent,
    get_advertiser_stored_file,
    get_driver_stored_file,
    issue_admin_file_download,
    issue_advertiser_file_download,
)

router = APIRouter(tags=["Files"])


def stored_file_response(stored_file: StoredFile) -> StoredFileRead:
    return StoredFileRead.model_validate(stored_file)


@router.post(
    "/advertiser/files/uploads",
    response_model=FileUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_file_upload(
    payload: FileUploadCreate,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> FileUploadRead:
    intent, post = await create_advertiser_upload_intent(
        session,
        actor_user_id=user.id,
        payload=payload,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return FileUploadRead(
        upload_id=intent.id,
        expires_at=intent.expires_at,
        upload=PresignedPostRead(url=post.url, fields=post.fields),
    )


@router.post(
    "/advertiser/files/uploads/{upload_id}/confirm",
    response_model=StoredFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_file_upload(
    upload_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> StoredFileRead:
    stored_file = await confirm_advertiser_upload(
        session,
        actor_user_id=user.id,
        upload_id=upload_id,
        storage=storage,
    )
    await session.commit()
    return stored_file_response(stored_file)


@router.get("/advertiser/files/{file_id}", response_model=StoredFileRead)
async def get_file(
    file_id: UUID,
    user: AdvertiserUserDependency,
    session: SessionDependency,
) -> StoredFileRead:
    return stored_file_response(
        await get_advertiser_stored_file(
            session,
            actor_user_id=user.id,
            file_id=file_id,
        )
    )


@router.post(
    "/driver/files/uploads",
    response_model=FileUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_driver_file_upload(
    payload: FileUploadCreate,
    user: DriverUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> FileUploadRead:
    intent, post = await create_driver_upload_intent(
        session,
        actor_user_id=user.id,
        payload=payload,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return FileUploadRead(
        upload_id=intent.id,
        expires_at=intent.expires_at,
        upload=PresignedPostRead(url=post.url, fields=post.fields),
    )


@router.post(
    "/driver/files/uploads/{upload_id}/confirm",
    response_model=StoredFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_driver_file_upload(
    upload_id: UUID,
    user: DriverUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
) -> StoredFileRead:
    stored_file = await confirm_driver_upload(
        session,
        actor_user_id=user.id,
        upload_id=upload_id,
        storage=storage,
    )
    await session.commit()
    return stored_file_response(stored_file)


@router.get("/driver/files/{file_id}", response_model=StoredFileRead)
async def get_driver_file(
    file_id: UUID,
    user: DriverUserDependency,
    session: SessionDependency,
) -> StoredFileRead:
    return stored_file_response(
        await get_driver_stored_file(
            session,
            actor_user_id=user.id,
            file_id=file_id,
        )
    )


@router.post(
    "/advertiser/files/{file_id}/download",
    response_model=FileDownloadRead,
)
async def download_advertiser_file(
    file_id: UUID,
    payload: FileDownloadRequest,
    user: AdvertiserUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> FileDownloadRead:
    download = await issue_advertiser_file_download(
        session,
        actor_user_id=user.id,
        file_id=file_id,
        access_purpose=payload.purpose,
        reason=payload.reason,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return FileDownloadRead(
        url=download.url,
        expires_in_seconds=download.expires_in_seconds,
    )


@router.post("/admin/files/{file_id}/download", response_model=FileDownloadRead)
async def download_admin_file(
    file_id: UUID,
    payload: FileDownloadRequest,
    user: AdminUserDependency,
    session: SessionDependency,
    storage: StorageDependency,
    settings: SettingsDependency,
) -> FileDownloadRead:
    download = await issue_admin_file_download(
        session,
        actor_user_id=user.id,
        file_id=file_id,
        access_purpose=payload.purpose,
        reason=payload.reason,
        storage=storage,
        settings=settings,
    )
    await session.commit()
    return FileDownloadRead(
        url=download.url,
        expires_in_seconds=download.expires_in_seconds,
    )
