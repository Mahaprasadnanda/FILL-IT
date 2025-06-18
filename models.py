from pydantic import BaseModel, EmailStr
class Token(BaseModel):
    id_token: str

class SignupRequest(BaseModel):
    username: str
    Name:str
    email: EmailStr
    phone: str
    role: str 
    password: str
    confirm_password: str
class UserModel(BaseModel):
    name: str
    role: str


