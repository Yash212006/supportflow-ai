from sqlalchemy.orm import Session

from backend.models.user import SupportUser
from backend.config.settings import settings


def verify_login(db: Session, email: str, password: str) -> SupportUser | None:
    user = db.query(SupportUser).filter(SupportUser.email == email.lower()).first()
    if not user:
        if email.lower() == settings.demo_user_email.lower() and password == settings.demo_user_password:
            return SupportUser(
                id=0,
                email=settings.demo_user_email,
                display_name="Support Executive",
                password_hash="demo",
                role="executive",
            )
        return None
    if user.password_hash == password:
        return user
    return None
