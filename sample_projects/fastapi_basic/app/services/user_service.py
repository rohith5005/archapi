class UserService:
    async def get_by_id(self, id: str):
        return {"id": id}


user_service = UserService()
