"""Persistence operations for process status note documents."""

from uuid import UUID

from beanie.operators import In

from core.utils.datetime import utc_now
from labs.process_status.models import ProcessStatusNote


class ProcessStatusNoteRepository:
    """Wrap Beanie operations for process status note persistence."""

    async def create(
        self,
        *,
        process_status_id: UUID,
        description: str,
    ) -> ProcessStatusNote:
        process_status_note = ProcessStatusNote(
            process_status_id=process_status_id,
            description=description,
        )
        await process_status_note.insert()
        return process_status_note

    async def get_by_id(self, note_id: UUID) -> ProcessStatusNote | None:
        return await ProcessStatusNote.find_one(ProcessStatusNote.id == note_id)

    async def update(
        self,
        *,
        note: ProcessStatusNote,
        description: str,
    ) -> ProcessStatusNote:
        note.description = description
        note.updated_at = utc_now()
        await note.save()
        return note

    async def list_by_process_status_ids(
        self,
        process_status_ids: list[UUID],
    ) -> list[ProcessStatusNote]:
        if not process_status_ids:
            return []

        return await (
            ProcessStatusNote.find(
                In(ProcessStatusNote.process_status_id, process_status_ids)
            )
            .sort("-updated_at", "-created_at")
            .to_list()
        )

    async def list_by_process_status_id(
        self,
        process_status_id: UUID,
    ) -> list[ProcessStatusNote]:
        return await (
            ProcessStatusNote.find(
                ProcessStatusNote.process_status_id == process_status_id
            )
            .sort("created_at", "updated_at")
            .to_list()
        )
