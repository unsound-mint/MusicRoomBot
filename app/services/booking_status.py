async def build_status_summary(db, user):
    from app.services import booking_service

    return await booking_service.build_status_summary(db, user)
