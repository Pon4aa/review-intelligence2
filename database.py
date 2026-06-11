import os
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

# Получаем URL базы данных из переменной окружения Render
DATABASE_URL = os.getenv("DATABASE_URL")

# Если переменная не задана (локальная разработка), используем SQLite
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./reviews.db"
    connect_args = {"check_same_thread": False}
else:
    # Для PostgreSQL на Render
    connect_args = {}

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)
    name = Column(String, nullable=False)
    account_type = Column(String, default="person")
    created_at = Column(DateTime, default=datetime.utcnow)
    yandex_url = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)

    reviews = relationship("Review", back_populates="owner", cascade="all, delete-orphan")

class Review(Base):
    __tablename__ = "reviews"
    id = Column(Integer, primary_key=True, index=True)
    author_name = Column(String, default="Аноним")
    text = Column(String, nullable=False)
    rating = Column(Float, default=0)
    venue_name = Column(String, default="")
    sentiment = Column(String, default="neutral")
    plus = Column(String, default="")
    minus = Column(String, default="")
    source = Column(String, default="manual")
    created_at = Column(DateTime, default=datetime.utcnow)

    user_id = Column(Integer, ForeignKey("users.id"))
    owner = relationship("User", back_populates="reviews")

# Создаём таблицы господи помоги
Base.metadata.create_all(bind=engine)