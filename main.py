import sys
import asyncio
import re
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()

from database import SessionLocal, User, Review
from scraper import scrape_yandex
from gigachat import GigaChat  # если используется, иначе закомментируй

GIGA_AUTH = os.getenv("GIGA_AUTH")

app = FastAPI(title="Review Intelligence API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Pydantic модели ----------
class UpdateProfileRequest(BaseModel):
    name: str
    email: str
    current_password: str

class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class UpdateAvatarRequest(BaseModel):
    avatar_url: str  # base64

class UpdateCompanyYandexUrlRequest(BaseModel):
    yandex_url: str
    current_password: str

class UserRegister(BaseModel):
    email: str
    password: str
    name: str
    account_type: str = "person"

class UserLogin(BaseModel):
    email: str
    password: str

class ManualReview(BaseModel):
    text: str
    venue_name: str = "Ручной ввод"

class YandexRequest(BaseModel):
    url: str
    venue_name: str
    user_id: Optional[int] = None

class UpdateYandexUrl(BaseModel):
    user_id: int
    yandex_url: str

# ---------- Вспомогательные функции для анализа ----------
def get_sentiment_by_keywords(text: str) -> str:
    lower = text.lower()
    pos_words = ["вкусно", "отлично", "супер", "хорошо", "приятно", "быстро", "вежливо", "рекомендую", "красиво", "внимание"]
    neg_words = ["плохо", "ужасно", "грязно", "дорого", "долго", "холодно", "невкусно", "хам", "ошибка", "забыли", "не принесли"]
    pos_count = sum(1 for w in pos_words if w in lower)
    neg_count = sum(1 for w in neg_words if w in lower)
    if pos_count > neg_count:
        return "positive"
    elif neg_count > pos_count:
        return "negative"
    else:
        return "neutral"

def calculate_nps_from_sentiments(reviews: List[Review]) -> int:
    if not reviews:
        return 0
    promoters = 0
    detractors = 0
    for r in reviews:
        sentiment = get_sentiment_by_keywords(r.text)
        if sentiment == "positive":
            promoters += 1
        elif sentiment == "negative":
            detractors += 1
    total = len(reviews)
    return int((promoters - detractors) / total * 100)

def get_gigachat_recommendations(reviews_text: str, account_type: str) -> str:
    if not GIGA_AUTH:
        return "Не настроен GigaChat"
    try:
        with GigaChat(credentials=GIGA_AUTH, verify_ssl_certs=False) as giga:
            if account_type == "company":
                prompt = f"""
                Ты — эксперт по ресторанному бизнесу. Проанализируй отзывы и выдай ровно от 3 до 6 конкретных рекомендаций, что улучшить в заведении.
                Каждую рекомендацию пиши с новой строки, начиная с дефиса и пробела. Не используй нумерацию, не пиши лишнего текста.
                Пример правильного ответа:
                - Ускорить подачу горячих блюд
                - Снизить цены на десерты
                - Улучшить качество мяса
                - Провести обучение персонала вежливости
                - Добавить больше мест на летней веранде

                Отзывы:
                {reviews_text[:3000]}
                """
            else:
                prompt = f"""
                Ты — помощник для гостей. На основе следующих отзывов ответь одной фразой: стоит ли обычному человеку посетить это заведение.
                Ответ должен начинаться с "Рекомендуется" или "Не рекомендуется" или "Частично рекомендуется". Затем через пробел дай 2-3 коротких обоснования, разделённых запятыми.
                Пример: "Рекомендуется. Атмосфера отличная, еда вкусная, но может быть дороговато."
                Не используй маркированные списки, только текст.

                Отзывы:
                {reviews_text[:3000]}
                """
            response = giga.chat(prompt)
            return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"GigaChat error: {e}")
        return "Ошибка связи с GigaChat"

def extract_keywords_from_text(text: str, positive=True) -> List[str]:
    """
    Ищет ключевые фразы в тексте отзыва для определения сильных/слабых сторон.
    Без использования полей plus/minus.
    """
    text_lower = text.lower()
    positive_keywords = ["вкусно", "отлично", "супер", "хорошо", "приятно", "быстро", "вежливо", "рекомендую"]
    negative_keywords = ["плохо", "ужасно", "грязно", "дорого", "долго", "холодно", "невкусно", "хам", "ошибка"]
    words = positive_keywords if positive else negative_keywords
    found = [kw for kw in words if kw in text_lower]
    # возвращаем уникальные, не более 3
    return list(dict.fromkeys(found))[:3]

def calculate_nps(reviews: List[Review]) -> int:
    if not reviews:
        return 0
    promoters = sum(1 for r in reviews if r.rating >= 4.5)
    detractors = sum(1 for r in reviews if r.rating <= 3)
    total = len(reviews)
    return int((promoters - detractors) / total * 100)

# ---------- Эндпоинты ----------
@app.put("/api/users/update-profile")
async def update_profile(user_id: int, req: UpdateProfileRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.password != req.current_password:
        raise HTTPException(401, "Неверный текущий пароль")
    user.name = req.name
    user.email = req.email
    db.commit()
    return {"status": "success", "user": {"id": user.id, "name": user.name, "email": user.email, "account_type": user.account_type}}

@app.put("/api/users/update-password")
async def update_password(user_id: int, req: UpdatePasswordRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.password != req.current_password:
        raise HTTPException(401, "Неверный текущий пароль")
    user.password = req.new_password
    db.commit()
    return {"status": "success"}

@app.put("/api/users/update-avatar")
async def update_avatar(user_id: int, req: UpdateAvatarRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    user.avatar_url = req.avatar_url
    db.commit()
    return {"status": "success", "avatar_url": user.avatar_url}

@app.put("/api/users/update-company-yandex-url")
async def update_company_yandex_url(user_id: int, req: UpdateCompanyYandexUrlRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Пользователь не найден")
    if user.account_type != "company":
        raise HTTPException(400, "Только для предприятий")
    if user.password != req.current_password:
        raise HTTPException(401, "Неверный пароль")
    user.yandex_url = req.yandex_url
    db.commit()
    return {"status": "success", "yandex_url": user.yandex_url}

#--------Основные Эндпоинты-----------------

@app.post("/api/competitor/compare")
async def compare_with_competitor(user_id: int, competitor_url: str, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(401, "Не авторизован")
    user = db.query(User).filter(User.id == user_id).first()
    if user.account_type != "company":
        raise HTTPException(400, "Только для предприятий")
    # Свои отзывы
    my_reviews = db.query(Review).filter(Review.user_id == user_id).all()
    my_nps = calculate_nps_from_sentiments(my_reviews)
    my_strengths = set()
    for r in my_reviews:
        my_strengths.update(extract_keywords_from_text(r.text, positive=True))

    # Парсим отзывы конкурента (не сохраняем в БД)
    competitor_reviews_data = await scrape_yandex(competitor_url)
    if not competitor_reviews_data:
        return {"error": "Не удалось собрать отзывы конкурента"}
    # Анализируем тексты
    competitor_nps = 0
    competitor_strengths = set()
    total = len(competitor_reviews_data)
    if total:
        pos = 0
        neg = 0
        for item in competitor_reviews_data:
            text = item.get('text', '')
            sent = get_sentiment_by_keywords(text)
            if sent == "positive":
                pos += 1
            elif sent == "negative":
                neg += 1
            competitor_strengths.update(extract_keywords_from_text(text, positive=True))
        competitor_nps = int((pos - neg) / total * 100)

    # Генерируем рекомендации через GigaChat
    my_texts = "\n".join([r.text for r in my_reviews[:10]])
    comp_texts = "\n".join([item.get('text', '') for item in competitor_reviews_data[:10]])
    prompt = f"""
    Сравни два заведения:
    Наше: NPS = {my_nps}%, сильные стороны: {', '.join(list(my_strengths)[:3])}
    Конкурент: NPS = {competitor_nps}%, сильные стороны: {', '.join(list(competitor_strengths)[:3])}
    Дай 3-4 конкретные рекомендации, как нашему заведению превзойти конкурента.
    Ответ короткими пунктами с новой строки, начиная с дефиса.
    """
    ai_rec = ""
    if GIGA_AUTH:
        try:
            with GigaChat(credentials=GIGA_AUTH, verify_ssl_certs=False) as giga:
                response = giga.chat(prompt)
                ai_rec = response.choices[0].message.content
        except:
            ai_rec = "Не удалось получить рекомендации"
    else:
        ai_rec = "Настройте GigaChat для получения ИИ-рекомендаций"

    return {
        "my_nps": f"{my_nps}%",
        "my_strengths": list(my_strengths)[:3],
        "competitor_nps": f"{competitor_nps}%",
        "competitor_strengths": list(competitor_strengths)[:3],
        "ai_recommendations": ai_rec
    }

@app.get("/api/reviews/timeline")
async def reviews_timeline(user_id: int = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    reviews = db.query(Review).filter(Review.user_id == user_id).all()
    # Группируем по дате (created_at)
    from collections import defaultdict
    daily = defaultdict(lambda: {"positive": 0, "negative": 0, "neutral": 0, "total": 0})
    for r in reviews:
        date_str = r.created_at.strftime("%Y-%m-%d")
        sent = get_sentiment_by_keywords(r.text)
        daily[date_str][sent] += 1
        daily[date_str]["total"] += 1
    # Превращаем в список для фронта
    timeline = [{"date": d, "positive": v["positive"], "negative": v["negative"], "neutral": v["neutral"], "total": v["total"]} for d, v in sorted(daily.items())]
    return timeline

@app.post("/api/register")
async def register(user: UserRegister, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")
    new_user = User(
        email=user.email,
        password=user.password,  # без хеширования
        name=user.name,
        account_type=user.account_type
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "status": "success",
        "user": {
            "id": new_user.id,
            "name": new_user.name,
            "email": new_user.email,
            "account_type": new_user.account_type
        }
    }

@app.post("/api/login")
async def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or db_user.password != user.password:
        raise HTTPException(status_code=401, detail="Неверный email или пароль")
    return {
        "status": "success",
        "user": {
            "id": db_user.id,
            "name": db_user.name,
            "email": db_user.email,
            "account_type": db_user.account_type,
            "yandex_url": db_user.yandex_url
        }
    }

@app.get("/api/users/me")
async def get_current_user(user_id: int = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "account_type": user.account_type,
        "yandex_url": user.yandex_url
    }

@app.put("/api/users/update-yandex")
async def update_yandex_url(data: UpdateYandexUrl, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.account_type != "company":
        raise HTTPException(status_code=400, detail="Только предприятия могут привязывать карточку")
    user.yandex_url = data.yandex_url
    db.commit()
    return {"status": "success", "yandex_url": user.yandex_url}

@app.post("/api/import/yandex")
async def import_yandex(request: YandexRequest, background_tasks: BackgroundTasks):
    if not request.user_id:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    background_tasks.add_task(process_reviews, request.url, request.venue_name, request.user_id)
    return {"status": "started", "message": "Парсер запущен"}

async def process_reviews(url: str, venue_name: str, user_id: int):
    try:
        data = await scrape_yandex(url)
        if not data:
            print(f"[TASK] Не удалось спарсить отзывы для {venue_name}")
            return
        db = SessionLocal()
        for item in data:
            new_review = Review(
                author_name=item.get('author', 'Аноним'),
                text=item.get('text', ''),
                venue_name=venue_name,
                user_id=user_id,
                source="Yandex"
            )
            db.add(new_review)
        db.commit()
        db.close()
        print(f"[TASK] Сохранено {len(data)} отзывов для user_id {user_id}")
    except Exception as e:
        print(f"[TASK ERROR] {e}")

@app.post("/api/import/manual")
async def manual_import(request: ManualReview, user_id: Optional[int] = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Требуется авторизация")
    raw_texts = re.split(r'\n\n|---', request.text)
    count = 0
    for text in raw_texts:
        clean_text = text.strip()
        if len(clean_text) > 10:
            new_review = Review(
                author_name="Ручной ввод",
                text=clean_text,
                venue_name=request.venue_name,
                user_id=user_id,
                source="Manual",
                sentiment="neutral"
            )
            db.add(new_review)
            count += 1
    db.commit()
    return {"status": "success", "message": f"Загружено {count} отзывов"}


@app.get("/api/reviews")
async def get_reviews(user_id: int = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    reviews = db.query(Review).filter(Review.user_id == user_id).order_by(Review.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "author_name": r.author_name,
            "text": r.text,
            "rating": r.rating,
            "venue_name": r.venue_name,
            "sentiment": r.sentiment,
            "plus": r.plus,
            "minus": r.minus,
            "created_at": r.created_at.isoformat() if r.created_at else None
        }
        for r in reviews
    ]

@app.delete("/api/reviews")
async def delete_reviews(user_id: int = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    db.query(Review).filter(Review.user_id == user_id).delete()
    db.commit()
    return {"status": "success", "message": "Отзывы удалены"}


@app.post("/api/reviews/analyze-all")
async def analyze_all_reviews(user_id: int = None, db: Session = Depends(get_db)):
    if not user_id:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    reviews = db.query(Review).filter(Review.user_id == user_id).all()
    if not reviews:
        return {
            "nps": "0%",
            "verdict": "Нет отзывов для анализа. Импортируйте данные.",
            "strengths": [],
            "weaknesses": [],
            "ai_recommendations": "",
        }
    nps = calculate_nps_from_sentiments(reviews)
    strengths_set = set()
    weaknesses_set = set()
    all_texts = ""
    for r in reviews:
        all_texts += r.text + "\n---\n"
        strengths_set.update(extract_keywords_from_text(r.text, positive=True))
        weaknesses_set.update(extract_keywords_from_text(r.text, positive=False))
    verdict = f"На основе {len(reviews)} отзывов. NPS = {nps}%. " + \
              ("Заведение пользуется лояльностью." if nps > 50 else "Есть потенциал для улучшения.")

    ai_rec = get_gigachat_recommendations(all_texts[:3000], user.account_type)

    return {
        "nps": f"{nps}%",
        "verdict": verdict,
        "strengths": list(strengths_set)[:3] if strengths_set else ["Нет явных сильных сторон"],
        "weaknesses": list(weaknesses_set)[:3] if weaknesses_set else ["Нет явных проблем"],
        "ai_recommendations": ai_rec,
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)