from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import select
from database import get_session, Role, User as DBUser

# JWT configuration
SECRET_KEY = "your-secret-key-here"  # In production, use a secure secret key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Password hashing
pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# User models
class User(BaseModel):
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: str
    department: Optional[str] = None


class UserInDB(User):
    hashed_password: str

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_user(username: str):
    session = get_session()
    try:
        db_user = session.exec(select(DBUser).where(DBUser.username == username)).first()
        if not db_user:
            return None
        # resolve role name
        role_name = None
        if db_user.role_id is not None:
            role = session.exec(select(Role).where(Role.id == db_user.role_id)).first()
            role_name = role.name if role else "user"
        return UserInDB(
            username=db_user.username,
            full_name=db_user.full_name,
            email=db_user.email,
            disabled=db_user.disabled,
            role=role_name or "user",
            department=getattr(db_user, 'department', None),
            hashed_password=db_user.hashed_password,
        )
    finally:
        session.close()

def create_user_in_db(username: str, password: str, full_name: Optional[str] = None, email: Optional[str] = None, role: str = "user"):
    session = get_session()
    try:
        existing = session.exec(select(DBUser).where(DBUser.username == username)).first()
        if existing:
            raise ValueError("User already exists")
        # ensure role exists
        role_row = session.exec(select(Role).where(Role.name == role)).first()
        if not role_row:
            role_row = Role(name=role)
            session.add(role_row)
            session.commit()
            session.refresh(role_row)

        hashed = pwd_context.hash(password)
        # ensure role_row.id is set so it can be assigned to DBUser.role_id (expected int)
        assert role_row.id is not None, "Role ID was not assigned"
        db_user = DBUser(
            username=username,
            full_name=full_name,
            email=email,
            hashed_password=hashed,
            disabled=False,
            role_id=role_row.id,
        )
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        return UserInDB(
            username=db_user.username,
            full_name=db_user.full_name,
            email=db_user.email,
            disabled=db_user.disabled,
            role=role_row.name,
            hashed_password=db_user.hashed_password,
        )
    finally:
        session.close()

def authenticate_user(username: str, password: str):
    user = get_user(username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def seed_users():
    # create default admin and user if they don't exist
    try:
        create_user_in_db("admin", "admin123", "Admin User", "admin@example.com", "admin")
    except ValueError:
        pass
    try:
        create_user_in_db("user", "user123", "Regular User", "user@example.com", "user")
    except ValueError:
        pass

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username_any = payload.get("sub")
        if username_any is None or not isinstance(username_any, str):
            raise credentials_exception
        username: str = username_any
    except JWTError:
        raise credentials_exception
    user = get_user(username)
    if user is None:
        raise credentials_exception
    return user

def check_admin_role(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions"
        )
    return user