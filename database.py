from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime

engine = create_engine('sqlite:///reviews.db', connect_args={"check_same_thread": False})
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


# Создаём таблицы
Base.metadata.create_all(bind=engine)