from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.services.auth_service import AuthUser, get_current_user


router = APIRouter()


class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    picture: str = ""


@router.get("/me", response_model=UserResponse)
async def me(user: AuthUser = Depends(get_current_user)):
    return UserResponse(
        id=user.user_id,
        email=user.email,
        name=user.name,
        picture=user.picture,
    )
