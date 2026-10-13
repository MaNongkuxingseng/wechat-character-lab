from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """所有持久化领域模型共享的声明式元数据基类。"""
