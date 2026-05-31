# from sqlalchemy.orm import Session
# from fastapi import HTTPException, status

# from app.models.user import User
# from app.models.role import Role
# from app.utils.password import hash_password
# from app.services.audit_service import log_audit
# # from app.models.associations import user_roles_
# from app.models.user_role import UserRole

# import logging
# from app.core.logging import setup_logging
# logger = setup_logging()
# logger = logging.getLogger(__name__)


# def create_user(
#     db: Session,
#     *,
#     email: str,
#     password: str,
#     tenant_id: int,
#     role_ids: list[int],
#     created_by,
#     request
# ):
#     if db.query(User).filter(User.email == email).first():
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Email already exists"
#         )

#     roles = db.query(Role).filter(
#         Role.id.in_(role_ids),
#         Role.tenant_id == tenant_id
#     ).all()
#     logger.info(f"roles >>>>>>>>>> {roles}")

#     logger.info(f"{len(roles)} >>>>>>>>>> {len(role_ids)}")
#     if len(roles) == len(role_ids):
#         pass
#     else:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Invalid roles for tenant"
#         )



#     user = User(
#         email=email,
#         password_hash=hash_password(password),
#         tenant_id=tenant_id,
#         role = "Read Only",
#         is_active=True
#     )

#     db.add(user)
#     db.flush()  #  critical

#     logger.info(f"{user }  user.id : {user.id} ,role_id : roles[0] ,created_by.office_id user.office_id")

#     # db.add_all([
#     #     UserRole(
#     #         user_id=user.id,
#     #         role_id=role.id,
#     #         office_id=user.office_id
#     #     )
#     #     for role in roles
#     # ])

#     db.commit()
#     db.refresh(user)

#     log_audit(
#         db,
#         action="USER_CREATE",
#         success=True,
#         tenant_id=tenant_id,
#         user_id=created_by.id,
#         resource="USER",
#         resource_id=str(user.id),
#         request=request
#     )

#     return user
