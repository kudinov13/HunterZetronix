"""Структурированный прайс-каталог и детерминированный расчёт стоимости."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ServicePrice:
    code: str
    name: str
    minimum: int | None
    maximum: int | None
    unit: str = "project"

    @property
    def is_negotiable(self) -> bool:
        return self.minimum is None or self.maximum is None


SERVICES = {
    item.code: item for item in [
        ServicePrice("landing_call_basic", "Лендинг с кнопкой звонка и базовым SEO", 12000, 12000),
        ServicePrice("landing_call_competitor_seo", "Лендинг с кнопкой звонка и SEO-анализом конкурентов", 14000, 14000),
        ServicePrice("landing_form_basic", "Лендинг с формой заявки в Telegram или Email и базовым SEO", 14000, 14000),
        ServicePrice("landing_form_competitor_seo", "Лендинг с формой заявки и SEO-анализом конкурентов", 16000, 16000),
        ServicePrice("landing_booking", "Лендинг с записью по дате и времени и уведомлением в Telegram", 20000, 20000),
        ServicePrice("video_player", "Встройка видео или собственный видеоплеер", 1000, 4000),
        ServicePrice("live_stream", "Встройка прямой трансляции или собственное решение", 1000, 4000),
        ServicePrice("calculator", "Интерактивный калькулятор", 3000, 6000),
        ServicePrice("multilingual_page", "Мультиязычность RU/EN и другие языки", 500, 500, "page"),
        ServicePrice("shop_100", "Интернет-магазин до 100 товаров с админ-панелью", 20000, 20000),
        ServicePrice("shop_500", "Интернет-магазин до 500 товаров с фильтрами", 23000, 23000),
        ServicePrice("shop_1000", "Интернет-магазин от 1000 товаров с расширенным поиском", 25000, 25000),
        ServicePrice("payment_integration", "Подключение системы оплаты", 5000, 5000),
        ServicePrice("delivery_integration", "Расчёт доставки и интеграция с логистическими службами", 3000, 3000),
        ServicePrice("customer_account", "Личный кабинет покупателя", 2000, 2000),
        ServicePrice("inventory", "Складской учёт, остатки и резервирование", 2000, 2000),
        ServicePrice("reviews", "Отзывы и рейтинги с модерацией", 2000, 2000),
        ServicePrice("multicurrency_page", "Цены в разных валютах", 600, 600, "page"),
        ServicePrice("admin_panel", "Админ-панель", 2000, 4000),
        ServicePrice("corporate_portal", "Корпоративный портал без нестандартной автоматизации документов", 14000, 14000),
        ServicePrice("online_booking_site", "Сайт с онлайн-бронированием и календарём", 16000, 16000),
        ServicePrice("education_platform", "Образовательная платформа", 25000, 25000),
        ServicePrice("resume_builder", "Конструктор резюме или анкет с формированием PDF", 12000, 12000),
        ServicePrice("classifieds", "Агрегатор или доска объявлений с модерацией", 30000, 30000),
        ServicePrice("simple_chatbot", "Простой чат-бот по сценарию", 1500, 1500),
        ServicePrice("ai_chatbot", "Чат-бот с AI-помощником", 4000, 4000),
        ServicePrice("realtime_chat", "Сайт с онлайн-чатом через WebSocket", 25000, 40000),
        ServicePrice("template_design", "Адаптация готового шаблона дизайна", 5000, 5000),
        ServicePrice("responsive", "Адаптивная версия для телефона и планшета", 5000, 5000),
        ServicePrice("crm_integration", "Подключение CRM", None, None),
        ServicePrice("email_marketing", "Подключение Email-рассылки", 5000, 5000),
        ServicePrice("analytics", "Настройка аналитики и целей", 3000, 5000),
        ServicePrice("external_api", "Подключение внешнего API", None, None),
        ServicePrice("speed_optimization", "Оптимизация скорости, кэширование и CDN", 3000, 3000),
        ServicePrice("content_page", "Наполнение контентом", 300, 400, "page_or_product"),
        ServicePrice("seo_basic", "Базовая настройка SEO", 2000, 2000),
        ServicePrice("seo_competitor", "SEO с анализом конкурентов", 4000, 4000),
    ]
}


def catalog_for_prompt() -> str:
    rows = []
    for item in SERVICES.values():
        if item.is_negotiable:
            price = "договорная — обязательно запросить цену у владельца"
        elif item.minimum == item.maximum:
            price = f"{item.minimum} ₽"
        else:
            price = f"{item.minimum}–{item.maximum} ₽"
        unit = "" if item.unit == "project" else f" за {item.unit}"
        rows.append(f"{item.code}: {item.name} — {price}{unit}")
    return "\n".join(rows)


def calculate_quote(requested: list[dict]) -> dict:
    minimum = 0
    maximum = 0
    matched = []
    needs_owner = []
    unknown = []
    seen = set()
    for request in requested:
        code = str(request.get("code") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        item = SERVICES.get(code)
        if not item:
            unknown.append(str(request.get("description") or code))
            continue
        quantity = request.get("quantity", 1)
        try:
            quantity = max(1, int(quantity or 1))
        except (TypeError, ValueError):
            quantity = 1
        if item.is_negotiable:
            needs_owner.append(item.name)
            continue
        multiplier = quantity if item.unit != "project" else 1
        item_min = item.minimum * multiplier
        item_max = item.maximum * multiplier
        minimum += item_min
        maximum += item_max
        matched.append({
            "code": item.code,
            "name": item.name,
            "quantity": multiplier,
            "minimum": item_min,
            "maximum": item_max,
        })
    return {
        "minimum": minimum,
        "maximum": maximum,
        "matched": matched,
        "needs_owner": needs_owner,
        "unknown": unknown,
        "complete": bool(matched) and not needs_owner and not unknown,
    }


def format_quote(quote: dict) -> str:
    if not quote.get("matched"):
        return ""
    minimum = quote["minimum"]
    maximum = quote["maximum"]
    if minimum == maximum:
        return f"{minimum:,} ₽".replace(",", " ")
    return f"{minimum:,}–{maximum:,} ₽".replace(",", " ")
