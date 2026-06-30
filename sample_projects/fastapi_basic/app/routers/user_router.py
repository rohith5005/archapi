from fastapi import APIRouter
from app.services.user_service import user_service

router = APIRouter()


@router.get("/users/{id}")
async def get_user(id: str):
    return await user_service.get_by_id(id)
