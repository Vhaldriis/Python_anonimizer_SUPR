import os
import httpx
import logging
from typing import List, Dict
from app.database import save_entity, get_or_create_pseudonym

logger = logging.getLogger("claude_anonimizer")

BITRIX24_WEBHOOK_URL = os.getenv("BITRIX24_WEBHOOK_URL", "")

# Глобальный user_id / session_id для общих сущностей Bitrix24 (не привязаны к пользователю чата)
GLOBAL_USER_ID = 0
GLOBAL_SESSION = "bitrix24_global"


async def _fetch_all_from_bitrix24(webhook_url: str, method: str, select_fields: List[str]) -> List[Dict]:
    """
    Загружает ВСЕ записи из Bitrix24 с учётом пагинации.
    Bitrix24 отдаёт по 50 записей за запрос, нужно листать через параметр start.
    """
    base_url = webhook_url.rstrip("/") + f"/{method}.json"
    # select передаём как строку через запятую (формат Bitrix24)
    select_str = ",".join(select_fields)
    all_results: List[Dict] = []
    start = 0
    page_size = 50

    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            params = {"select": select_str, "start": start}
            try:
                resp = await client.get(base_url, params=params)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.error(f"Ошибка запроса к Bitrix24 {method}: {e}")
                break

            result = data.get("result", [])
            all_results.extend(result)

            # Проверяем, есть ли ещё данные
            next_param = data.get("next")
            if not next_param or len(result) < page_size:
                break

            start = next_param

    logger.info(f"Bitrix24 {method}: загружено {len(all_results)} записей")
    return all_results


async def fetch_bitrix24_companies(webhook_url: str) -> List[Dict]:
    """Загружает ВСЕ компании из Bitrix24 через CRM REST API (с пагинацией)."""
    return await _fetch_all_from_bitrix24(
        webhook_url,
        "crm.company.list",
        ["ID", "TITLE", "ADDRESS", "PHONE", "EMAIL"],
    )


async def fetch_bitrix24_contacts(webhook_url: str) -> List[Dict]:
    """Загружает ВСЕ контакты из Bitrix24 через CRM REST API (с пагинацией)."""
    return await _fetch_all_from_bitrix24(
        webhook_url,
        "crm.contact.list",
        ["ID", "NAME", "LAST_NAME", "PHONE", "EMAIL", "COMPANY_ID"],
    )


async def sync_companies_from_bitrix24() -> int:
    """Синхронизирует компании из Bitrix24 как известные сущности для анонимизации."""
    if not BITRIX24_WEBHOOK_URL:
        logger.warning("BITRIX24_WEBHOOK_URL не задан в .env")
        return 0

    try:
        companies = await fetch_bitrix24_companies(BITRIX24_WEBHOOK_URL)
    except Exception as e:
        logger.error(f"Не удалось загрузить компании из Bitrix24: {e}")
        return 0

    count = 0
    for comp in companies:
        title = (comp.get("TITLE") or "").strip()
        if not title:
            continue
        # Создаём стабильный псевдоним для компании (используется глобальный user/session)
        pseudonym = get_or_create_pseudonym(title, "company", GLOBAL_USER_ID, GLOBAL_SESSION)
        save_entity("company", str(comp.get("ID")), title, pseudonym)
        count += 1

    logger.info(f"Синхронизировано компаний: {count}")
    return count


async def sync_contacts_from_bitrix24() -> int:
    """Синхронизирует контакты из Bitrix24 как известные сущности."""
    if not BITRIX24_WEBHOOK_URL:
        logger.warning("BITRIX24_WEBHOOK_URL не задан в .env")
        return 0

    try:
        contacts = await fetch_bitrix24_contacts(BITRIX24_WEBHOOK_URL)
    except Exception as e:
        logger.error(f"Не удалось загрузить контакты из Bitrix24: {e}")
        return 0

    count = 0
    for contact in contacts:
        first = (contact.get("NAME") or "").strip()
        last = (contact.get("LAST_NAME") or "").strip()
        full_name = f"{last} {first}".strip() or first
        if not full_name:
            continue
        pseudonym = get_or_create_pseudonym(full_name, "name", GLOBAL_USER_ID, GLOBAL_SESSION)
        save_entity("contact", str(contact.get("ID")), full_name, pseudonym)
        count += 1

    logger.info(f"Синхронизировано контактов: {count}")
    return count


async def sync_all_bitrix24_entities() -> Dict[str, int]:
    """Полная синхронизация компаний и контактов из Bitrix24."""
    companies_count = await sync_companies_from_bitrix24()
    contacts_count = await sync_contacts_from_bitrix24()
    return {"companies": companies_count, "contacts": contacts_count}
