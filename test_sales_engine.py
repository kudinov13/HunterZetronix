import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import ai_engine
import database
import sales_engine
from price_catalog import calculate_quote, format_quote
from user_client import UserClient


class PriceCatalogTests(unittest.TestCase):
    def test_sums_base_options_and_quantities(self):
        quote = calculate_quote([
            {"code": "shop_100", "quantity": 1},
            {"code": "payment_integration", "quantity": 1},
            {"code": "multilingual_page", "quantity": 3},
        ])
        self.assertTrue(quote["complete"])
        self.assertEqual(quote["minimum"], 26500)
        self.assertEqual(quote["maximum"], 26500)
        self.assertEqual(format_quote(quote), "26 500 ₽")

    def test_negotiable_and_unknown_require_owner(self):
        quote = calculate_quote([
            {"code": "crm_integration", "quantity": 1},
            {"code": "unknown", "description": "обработка первичных документов"},
        ])
        self.assertFalse(quote["complete"])
        self.assertIn("Подключение CRM", quote["needs_owner"])
        self.assertIn("обработка первичных документов", quote["unknown"])


class SalesRulesTests(unittest.TestCase):
    def test_country_rules(self):
        self.assertEqual(sales_engine.normalize_country("РФ"), "Россия")
        self.assertFalse(sales_engine.is_supported_country("Украина"))
        self.assertTrue(sales_engine.is_supported_country("Казахстан"))

    def test_ready_state_does_not_regress(self):
        dialog = {
            "sender_name": "Иван", "sender_username": "ivan", "interest_level": "HOT",
            "ready_to_work": 1, "service_codes_json": "[]", "requirements_json": "[]",
        }
        updates, _ = sales_engine.merge_state(dialog, {
            "intent": "OTHER", "interest_level": "COLD", "services": [],
            "requirements": [], "ready_to_work": False,
        })
        self.assertEqual(updates["interest_level"], "HOT")
        self.assertEqual(updates["ready_to_work"], 1)

    def test_broadcast_safety(self):
        self.assertIsNotNone(ai_engine._BROADCAST_PROHIBITED_RE.search("Реклама и самореклама запрещены"))
        recent = ["Кто как решает проблему ручного учета заявок в таблицах?"]
        similar = "Кто как решает проблему ручного учёта заявок в таблицах?"
        self.assertGreaterEqual(ai_engine._broadcast_similarity(similar, recent), 0.52)


class DatabaseMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_dialog_sales_columns_and_identifier(self):
        original_path = database.DB_PATH
        try:
            with tempfile.TemporaryDirectory() as folder:
                database.DB_PATH = Path(folder) / "test.db"
                await database.init_db()
                async with database.aiosqlite.connect(database.DB_PATH) as connection:
                    async with connection.execute("PRAGMA table_info(dialogs)") as cursor:
                        columns = {row[1] for row in await cursor.fetchall()}
                self.assertTrue({
                    "country", "company", "service_codes_json", "requirements_json",
                    "awaiting_owner_price", "ready_to_work", "do_not_contact", "lead_source",
                }.issubset(columns))
                dialog_id = await database.create_dialog(1, 2, "Иван", "ivan", "cold")
                by_id = await database.get_dialog_by_identifier(str(dialog_id))
                by_username = await database.get_dialog_by_identifier("@ivan")
                self.assertEqual(by_id["id"], dialog_id)
                self.assertEqual(by_username["id"], dialog_id)
                self.assertEqual(by_id["lead_source"], "cold")
        finally:
            database.DB_PATH = original_path


class AutonomousFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_path = database.DB_PATH
        self.temp = tempfile.TemporaryDirectory()
        database.DB_PATH = Path(self.temp.name) / "flow.db"
        await database.init_db()
        self.notifications = AsyncMock()
        self.client = UserClient(notification_callback=self.notifications)
        self.client._send_message = AsyncMock(return_value=True)

    async def asyncTearDown(self):
        database.DB_PATH = self.original_path
        self.temp.cleanup()

    async def create_dialog(self):
        dialog_id = await database.create_dialog(1, 200, "Иван", "ivan", "cold")
        await database.update_dialog_sales_data(dialog_id, client_name="Иван", contact="@ivan")
        return await database.get_dialog_by_id(dialog_id)

    async def test_unknown_service_requests_owner_price(self):
        dialog = await self.create_dialog()
        analysis = {
            "intent": "ASKS_PRICE", "interest_level": "HOT", "country": "Россия",
            "client_name": None, "company": None, "contact": None,
            "services": [{"code": "unknown", "description": "обработка первичных документов", "quantity": 1}],
            "requirements": ["распознавать накладные"], "task_clear": True,
            "asks_price": True, "asks_payment": False, "ready_to_work": False,
            "reply_goal": "уточнить цену",
        }
        with patch.object(sales_engine, "analyze_turn", new=AsyncMock(return_value=analysis)), \
             patch.object(sales_engine, "recommend_price", new=AsyncMock(return_value="80 000–140 000 ₽")), \
             patch.object(sales_engine, "generate_reply", new=AsyncMock(return_value="Уточню стоимость по этому объёму и вернусь с точной цифрой.")):
            await self.client._continue_dialog(dialog, "Сколько будет стоить распознавание накладных?")
        updated = await database.get_dialog_by_id(dialog["id"])
        self.assertEqual(updated["stage"], "AWAITING_OWNER_PRICE")
        self.assertEqual(updated["awaiting_owner_price"], 1)
        self.assertEqual(self.notifications.await_args.kwargs["category"], "PRICE_REQUIRED")

    async def test_ready_client_is_handed_off(self):
        dialog = await self.create_dialog()
        await database.update_dialog_price(dialog["id"], "14 000 ₽")
        dialog = await database.get_dialog_by_id(dialog["id"])
        analysis = {
            "intent": "READY_TO_WORK", "interest_level": "HOT", "country": "Россия",
            "client_name": "Иван", "company": "ООО Ромашка", "contact": "@ivan",
            "services": [{"code": "landing_form_basic", "description": "лендинг", "quantity": 1}],
            "requirements": ["форма заявки в Telegram"], "task_clear": True,
            "asks_price": False, "asks_payment": True, "ready_to_work": True,
            "reply_goal": "передать владельцу",
        }
        with patch.object(sales_engine, "analyze_turn", new=AsyncMock(return_value=analysis)), \
             patch.object(sales_engine, "compose_brief", new=AsyncMock(return_value="ТЗ: лендинг с формой заявки")), \
             patch.object(sales_engine, "generate_reply", new=AsyncMock(return_value="Основные вводные зафиксировал, дальше подключится разработчик. Оплата криптовалютой через Telegram доступна.")):
            await self.client._continue_dialog(dialog, "Цена подходит, давайте работать от ООО Ромашка")
        updated = await database.get_dialog_by_id(dialog["id"])
        self.assertEqual(updated["stage"], "HANDOFF")
        self.assertEqual(updated["handoff_notified"], 1)
        self.assertEqual(self.notifications.await_args.kwargs["category"], "DEAL_READY")

    async def test_owner_price_by_username(self):
        dialog = await self.create_dialog()
        await database.update_dialog_stage(dialog["id"], "AWAITING_OWNER_PRICE")
        await database.update_dialog_sales_data(dialog["id"], awaiting_owner_price=1)
        with patch.object(sales_engine, "generate_reply", new=AsyncMock(return_value="Стоимость составит 90 000 ₽. Такой бюджет подходит?")):
            success = await self.client.continue_dialog_with_price("@ivan", "90 000 ₽")
        self.assertTrue(success)
        updated = await database.get_dialog_by_id(dialog["id"])
        self.assertEqual(updated["price"], "90 000 ₽")
        self.assertEqual(updated["awaiting_owner_price"], 0)
        self.assertEqual(updated["stage"], "NEGOTIATING")

    async def test_unsupported_country_closes_dialog(self):
        dialog = await self.create_dialog()
        analysis = {
            "intent": "OTHER", "interest_level": "HOT", "country": "Украина",
            "client_name": None, "company": None, "contact": None, "services": [],
            "requirements": [], "task_clear": False, "asks_price": False,
            "asks_payment": False, "ready_to_work": False, "reply_goal": "",
        }
        with patch.object(sales_engine, "analyze_turn", new=AsyncMock(return_value=analysis)):
            await self.client._continue_dialog(dialog, "Мы находимся в Украине")
        updated = await database.get_dialog_by_id(dialog["id"])
        self.assertEqual(updated["stage"], "ENDED")
        self.client._send_message.assert_awaited_once()

    async def test_do_not_contact_closes_without_reply(self):
        dialog = await self.create_dialog()
        analysis = {
            "intent": "DO_NOT_CONTACT", "interest_level": "COLD", "country": None,
            "client_name": None, "company": None, "contact": None, "services": [],
            "requirements": [], "task_clear": False, "asks_price": False,
            "asks_payment": False, "ready_to_work": False, "reply_goal": "",
        }
        with patch.object(sales_engine, "analyze_turn", new=AsyncMock(return_value=analysis)):
            await self.client._continue_dialog(dialog, "Больше не пишите")
        updated = await database.get_dialog_by_id(dialog["id"])
        self.assertEqual(updated["stage"], "ENDED")
        self.assertEqual(updated["do_not_contact"], 1)
        self.client._send_message.assert_not_awaited()


class IntentOverrideTests(unittest.IsolatedAsyncioTestCase):
    async def test_direct_mode_cannot_bypass_rules(self):
        with patch.object(ai_engine, "_chat_with_fallback", new=AsyncMock()) as mocked:
            result = await ai_engine.generate_broadcast(
                "Реклама и самореклама запрещены", [], "сейчас", is_direct_promo=True
            )
        self.assertTrue(result["skip"])
        mocked.assert_not_awaited()

    async def test_do_not_contact_is_deterministic(self):
        response = json.dumps({
            "intent": "OTHER", "interest_level": "WARM", "services": [],
            "requirements": [], "task_clear": False, "asks_price": False,
            "asks_payment": False, "ready_to_work": False,
        })
        with patch.object(ai_engine, "_chat_with_fallback", new=AsyncMock(return_value=response)):
            result = await sales_engine.analyze_turn(
                {"sender_name": "Иван", "service_codes_json": "[]", "requirements_json": "[]"},
                [], "Пожалуйста, больше мне не пишите",
            )
        self.assertEqual(result["intent"], "DO_NOT_CONTACT")

    async def test_country_in_sentence_is_deterministic(self):
        response = json.dumps({
            "intent": "OTHER", "interest_level": "WARM", "services": [],
            "requirements": [], "task_clear": False, "asks_price": False,
            "asks_payment": False, "ready_to_work": False,
        })
        with patch.object(ai_engine, "_chat_with_fallback", new=AsyncMock(return_value=response)):
            result = await sales_engine.analyze_turn(
                {"sender_name": "Иван", "service_codes_json": "[]", "requirements_json": "[]"},
                [], "Мы находимся в Украине",
            )
        self.assertEqual(result["country"], "Украина")
        self.assertFalse(sales_engine.is_supported_country(result["country"]))

    async def test_ready_to_work_is_deterministic(self):
        response = json.dumps({
            "intent": "OTHER", "interest_level": "WARM", "services": [],
            "requirements": [], "task_clear": True, "asks_price": False,
            "asks_payment": False, "ready_to_work": False,
        })
        with patch.object(ai_engine, "_chat_with_fallback", new=AsyncMock(return_value=response)):
            result = await sales_engine.analyze_turn(
                {"sender_name": "Иван", "service_codes_json": "[]", "requirements_json": "[]"},
                [], "Цена подходит, давайте начнем работать",
            )
        self.assertEqual(result["intent"], "READY_TO_WORK")
        self.assertTrue(result["ready_to_work"])
        self.assertEqual(result["interest_level"], "HOT")


if __name__ == "__main__":
    unittest.main()
