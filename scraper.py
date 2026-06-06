import asyncio
from playwright.async_api import async_playwright

async def scrape_yandex(url):
    results = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            print(f"[SCRAPER] Открываю страницу...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Даем время на загрузку и возможную капчу
            await asyncio.sleep(10)

            # Скроллинг
            for i in range(5):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(2)

            # Ждём появления хотя бы одной карточки (максимум 15 секунд)
            try:
                await page.wait_for_selector('.business-review-view', timeout=15000)
            except:
                print("[SCRAPER] Селектор .business-review-view не найден, пробуем альтернативный")
                # Альтернативный селектор (более общий)
                await page.wait_for_selector('[class*="review"]', timeout=10000)

            cards = await page.query_selector_all('.business-review-view')
            if not cards:
                # fallback
                cards = await page.query_selector_all('[class*="review"]')
            print(f"[SCRAPER] Найдено карточек: {len(cards)}")

            for card in cards:
                author_el = await card.query_selector('.business-review-view__author-name span')
                text_el = await card.query_selector('.spoiler-view__text-container')
                if not author_el:
                    author_el = await card.query_selector('[class*="author"] span')
                if not text_el:
                    text_el = await card.query_selector('[class*="text-container"]')
                if author_el and text_el:
                    results.append({
                        "author": await author_el.inner_text(),
                        "text": await text_el.inner_text(),
                        "rating": 4.0
                    })
            return results
        except Exception as e:
            print(f"[SCRAPER ERROR] {e}")
            return []
        finally:
            await browser.close()