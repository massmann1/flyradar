from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Chat, ErrorEvent, Message

from app.bot.keyboards.subscriptions import (
    calendar_keyboard,
    confirm_keyboard,
    date_input_mode_keyboard,
    edit_dates_keyboard,
    MAIN_MENU_CANCEL,
    MAIN_MENU_HELP,
    MAIN_MENU_NEW,
    MAIN_MENU_SUBSCRIPTIONS,
    main_menu_keyboard,
    place_suggestions_keyboard,
    return_mode_keyboard,
    subscription_actions_keyboard,
    trip_type_keyboard,
    yes_no_keyboard,
)
from app.bot.states import NewSubscriptionStates
from app.clients.travelpayouts_rest import TravelpayoutsRestClient
from app.core.config import Settings
from app.domain.enums import BaggagePolicy, CheckTrigger, TripType
from app.domain.schemas import SubscriptionCreate
from app.services.alerts import AlertService
from app.services.subscriptions import SubscriptionService

logger = logging.getLogger(__name__)


def build_subscription_router(
    *,
    settings: Settings,
    subscription_service: SubscriptionService,
    alert_service: AlertService,
    travelpayouts_client: TravelpayoutsRestClient,
) -> Router:
    router = Router()

    menu_keyboard = main_menu_keyboard()

    async def ensure_access(message_or_callback: Message | CallbackQuery) -> bool:
        user = message_or_callback.from_user
        chat = message_or_callback.message.chat if isinstance(message_or_callback, CallbackQuery) else message_or_callback.chat
        if not _is_private_chat(chat):
            target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
            await target.answer(
                "Этот бот работает только в личном чате.\n"
                "Открой диалог с ботом один на один и повтори команду."
            )
            return False
        if user is None or user.id not in settings.allowed_user_ids:
            target = message_or_callback.message if isinstance(message_or_callback, CallbackQuery) else message_or_callback
            user_id = user.id if user is not None else "unknown"
            username = user.username if user is not None else None
            logger.warning(
                "telegram_access_denied",
                extra={"telegram_user_id": user_id, "telegram_username": username},
            )
            await target.answer(
                "Доступ запрещен.\n"
                f"Твой Telegram ID: <code>{user_id}</code>\n"
                "Добавь его в <code>TELEGRAM_ALLOWED_USER_IDS</code> и перезапусти worker."
            )
            return False
        return True

    @router.error()
    async def error_handler(event: ErrorEvent) -> bool:
        logger.exception("telegram_handler_failed", exc_info=event.exception)
        update = event.update
        if update.message is not None:
            await update.message.answer(
                "Что-то пошло не так на этом шаге. Попробуй еще раз или начни заново через /new.",
                reply_markup=menu_keyboard,
            )
        elif update.callback_query is not None and update.callback_query.message is not None:
            await update.callback_query.message.answer(
                "Что-то пошло не так на этом шаге. Попробуй еще раз или начни заново через /new.",
                reply_markup=menu_keyboard,
            )
            await update.callback_query.answer()
        return True

    async def show_help(message: Message) -> None:
        await message.answer(_build_help_text(), reply_markup=menu_keyboard)

    async def cancel_dialog(message: Message, state: FSMContext) -> None:
        await state.clear()
        await message.answer("Текущий диалог отменен.", reply_markup=menu_keyboard)

    async def start_new_dialog(message: Message, state: FSMContext) -> None:
        await state.clear()
        await state.update_data(
            currency=settings.travelpayouts_default_currency.upper(),
            check_interval_minutes=settings.default_check_interval_minutes,
            preferred_airlines=[],
            baggage_policy=BaggagePolicy.IGNORE.value,
        )
        await state.set_state(NewSubscriptionStates.name)
        await message.answer("Название подписки?", reply_markup=menu_keyboard)

    async def start_edit_dialog(message: Message, state: FSMContext, subscription) -> None:
        await state.clear()
        await state.update_data(_subscription_to_state_data(subscription))
        await state.set_state(NewSubscriptionStates.name)
        await message.answer(
            "Редактируем подписку.\n"
            "На текстовых шагах можно отправить <code>.</code>, чтобы оставить текущее значение.\n\n"
            + _prompt_with_current_text("Название подписки?", subscription.name),
            reply_markup=menu_keyboard,
        )

    async def show_subscriptions_list(message: Message) -> None:
        subscriptions = await subscription_service.list_subscriptions(
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
        )
        if not subscriptions:
            await message.answer("Подписок пока нет. Создай первую через /new", reply_markup=menu_keyboard)
            return

        await message.answer("Твои подписки:", reply_markup=menu_keyboard)
        for subscription in subscriptions:
            summary = _render_subscription(subscription)
            await message.answer(summary, reply_markup=subscription_actions_keyboard(subscription.id, subscription.enabled))

    @router.message(Command("start"))
    async def start_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await show_help(message)

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await show_help(message)

    @router.message(Command("cancel"))
    async def cancel_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await cancel_dialog(message, state)

    @router.message(Command("new"))
    async def new_subscription_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await start_new_dialog(message, state)

    @router.message(Command("subscriptions"))
    @router.message(Command("subs"))
    async def subscriptions_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await show_subscriptions_list(message)

    @router.message(F.text == MAIN_MENU_HELP)
    async def help_button_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await show_help(message)

    @router.message(F.text == MAIN_MENU_CANCEL)
    async def cancel_button_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await cancel_dialog(message, state)

    @router.message(F.text == MAIN_MENU_NEW)
    async def new_button_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        await start_new_dialog(message, state)

    @router.message(F.text == MAIN_MENU_SUBSCRIPTIONS)
    async def subscriptions_button_handler(message: Message) -> None:
        if not await ensure_access(message):
            return
        await show_subscriptions_list(message)

    @router.message(NewSubscriptionStates.name)
    async def name_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        data = await state.get_data()
        if not (_is_keep_value(message.text) and _is_editing(data)):
            await state.update_data(name=message.text.strip())
        await state.set_state(NewSubscriptionStates.origin)
        data = await state.get_data()
        await message.answer(_prompt_with_current_text("Откуда? Отправь IATA-код или название города.", data.get("origin_iata"), editing=_is_editing(data)))

    @router.message(NewSubscriptionStates.origin)
    async def origin_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        data = await state.get_data()
        if _is_keep_value(message.text) and _is_editing(data):
            normalized = data.get("origin_iata")
        else:
            suggestions = await _resolve_airport_or_city_options(message.text, travelpayouts_client)
            if not suggestions:
                await message.answer("Не смог распознать город вылета. Попробуй IATA-код или более точное название.")
                return
            if len(suggestions) > 1:
                await state.update_data(origin_suggestions=suggestions)
                await message.answer(
                    f"Нашел несколько вариантов для <b>{message.text.strip()}</b>.\nВыбери нужный ниже или отправь более точное название.",
                    reply_markup=place_suggestions_keyboard("origin", suggestions),
                )
                return
            normalized = suggestions[0]["code"]
            await state.update_data(origin_iata=normalized)
        await state.set_state(NewSubscriptionStates.destination)
        data = await state.get_data()
        await message.answer(_prompt_with_current_text("Куда? Отправь IATA-код или название города.", data.get("destination_iata"), editing=_is_editing(data)))

    @router.message(NewSubscriptionStates.destination)
    async def destination_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        data = await state.get_data()
        if _is_keep_value(message.text) and _is_editing(data):
            normalized = data.get("destination_iata")
        else:
            suggestions = await _resolve_airport_or_city_options(message.text, travelpayouts_client)
            if not suggestions:
                await message.answer("Не смог распознать город прилета. Попробуй IATA-код или более точное название.")
                return
            if len(suggestions) > 1:
                await state.update_data(destination_suggestions=suggestions)
                await message.answer(
                    f"Нашел несколько вариантов для <b>{message.text.strip()}</b>.\nВыбери нужный ниже или отправь более точное название.",
                    reply_markup=place_suggestions_keyboard("destination", suggestions),
                )
                return
            normalized = suggestions[0]["code"]
            await state.update_data(destination_iata=normalized)
        await state.set_state(NewSubscriptionStates.trip_type)
        data = await state.get_data()
        current_trip_type = _render_trip_type(data["trip_type"]) if data.get("trip_type") else None
        await message.answer(
            _prompt_with_current_choice("Тип поездки?", current_trip_type, editing=_is_editing(data)),
            reply_markup=trip_type_keyboard(include_keep=_is_editing(data)),
        )

    @router.callback_query(F.data.startswith("new:place:"))
    async def place_suggestion_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        parts = (callback.data or "").split(":")
        if len(parts) < 4:
            await callback.answer()
            return

        _, _, field, action, *tail = parts
        if field not in {"origin", "destination"}:
            await callback.answer()
            return

        current_state = await state.get_state()
        expected_state = NewSubscriptionStates.origin.state if field == "origin" else NewSubscriptionStates.destination.state
        if current_state != expected_state:
            await callback.answer("Эта подсказка уже устарела.", show_alert=False)
            return

        if action == "retry":
            prompt = "Откуда? Отправь IATA-код или название города." if field == "origin" else "Куда? Отправь IATA-код или название города."
            data = await state.get_data()
            await callback.message.answer(
                _prompt_with_current_text(
                    prompt,
                    data.get(f"{field}_iata"),
                    editing=_is_editing(data),
                )
            )
            await callback.answer()
            return

        if action != "choose" or not tail:
            await callback.answer()
            return

        selected_code = tail[0].upper()
        data = await state.get_data()
        suggestions = data.get(f"{field}_suggestions") or []
        allowed_codes = {item.get("code") for item in suggestions}
        if selected_code not in allowed_codes:
            await callback.answer("Эта подсказка уже устарела. Отправь город заново.", show_alert=False)
            return

        await state.update_data(**{f"{field}_iata": selected_code, f"{field}_suggestions": None})
        await callback.answer(f"Выбрано: {selected_code}")

        if field == "origin":
            await state.set_state(NewSubscriptionStates.destination)
            refreshed = await state.get_data()
            await callback.message.answer(
                _prompt_with_current_text(
                    "Куда? Отправь IATA-код или название города.",
                    refreshed.get("destination_iata"),
                    editing=_is_editing(refreshed),
                )
            )
            return

        await state.set_state(NewSubscriptionStates.trip_type)
        refreshed = await state.get_data()
        current_trip_type = _render_trip_type(refreshed["trip_type"]) if refreshed.get("trip_type") else None
        await callback.message.answer(
            _prompt_with_current_choice("Тип поездки?", current_trip_type, editing=_is_editing(refreshed)),
            reply_markup=trip_type_keyboard(include_keep=_is_editing(refreshed)),
        )

    @router.callback_query(NewSubscriptionStates.trip_type, F.data.startswith("new:trip:"))
    async def trip_type_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        data = await state.get_data()
        if callback.data.endswith("keep"):
            trip_type = TripType(data["trip_type"])
        else:
            trip_type = TripType.ONE_WAY if callback.data.endswith("one_way") else TripType.ROUND_TRIP
        await state.update_data(trip_type=trip_type.value)
        if trip_type == TripType.ONE_WAY:
            await state.update_data(return_mode=None, return_date_from=None, return_date_to=None, min_trip_duration_days=None, max_trip_duration_days=None)
        await state.set_state(NewSubscriptionStates.departure_mode)
        await callback.message.answer(
            _prompt_with_current_choice(
                "Как задать даты вылета?\nМожно выбрать через календарь или ввести вручную.",
                _format_date_range(data.get("departure_date_from"), data.get("departure_date_to")) if data.get("departure_date_from") else None,
                editing=_is_editing(data),
            ),
            reply_markup=date_input_mode_keyboard("new:departure_mode", include_keep=_is_editing(data)),
        )
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.departure_mode, F.data.startswith("new:departure_mode:"))
    async def departure_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        mode = callback.data.rsplit(":", 1)[-1]
        data = await state.get_data()
        if mode == "keep" and _is_editing(data):
            await _after_departure_dates_selected(message=callback.message, state=state)
            await callback.answer()
            return
        if mode == "manual":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            await state.set_state(NewSubscriptionStates.departure_dates)
            await callback.message.answer(
                _manual_date_prompt("вылета", allow_retry=True),
                reply_markup=edit_dates_keyboard("departure"),
            )
        else:
            await _start_calendar_selection(
                message=callback.message,
                state=state,
                state_name=NewSubscriptionStates.departure_dates,
                context="departure",
                mode=mode,
            )
        await callback.answer()

    @router.message(NewSubscriptionStates.departure_dates)
    async def departure_dates_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            date_from, date_to = _parse_date_range(message.text)
        except ValueError:
            await message.answer(
                _manual_date_prompt("вылета", allow_retry=True),
                reply_markup=edit_dates_keyboard("departure"),
            )
            return

        await state.update_data(
            departure_date_from=date_from.isoformat(),
            departure_date_to=date_to.isoformat() if date_to else None,
            calendar_context=None,
            calendar_mode=None,
            calendar_stage=None,
        )
        await _after_departure_dates_selected(message=message, state=state)

    @router.callback_query(NewSubscriptionStates.return_mode, F.data.startswith("new:return:"))
    async def return_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        data = await state.get_data()
        if callback.data.endswith("keep") and _is_editing(data):
            await _after_return_dates_selected(message=callback.message, state=state)
            await callback.answer()
            return
        if callback.data.endswith("dates"):
            await state.update_data(return_mode="dates")
            await state.set_state(NewSubscriptionStates.return_date_mode)
            await callback.message.answer(
                _prompt_with_current_choice(
                    "Как задать даты возврата?\nМожно выбрать через календарь или ввести вручную.",
                    _format_date_range(data.get("return_date_from"), data.get("return_date_to")) if data.get("return_date_from") else None,
                    editing=_is_editing(data),
                ),
                reply_markup=date_input_mode_keyboard("new:return_date_mode", include_keep=_is_editing(data)),
            )
        else:
            await state.update_data(return_mode="duration")
            await state.set_state(NewSubscriptionStates.duration)
            current_duration = _format_duration_range(data.get("min_trip_duration_days"), data.get("max_trip_duration_days"))
            await callback.message.answer(_prompt_with_current_text("Длительность поездки в днях: 3 или 3-7", current_duration, editing=_is_editing(data)))
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.return_date_mode, F.data.startswith("new:return_date_mode:"))
    async def return_date_mode_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        mode = callback.data.rsplit(":", 1)[-1]
        data = await state.get_data()
        if mode == "keep" and _is_editing(data):
            await _after_return_dates_selected(message=callback.message, state=state)
            await callback.answer()
            return
        if mode == "manual":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            await state.set_state(NewSubscriptionStates.return_dates)
            await callback.message.answer(
                _manual_date_prompt("возврата", allow_retry=True),
                reply_markup=edit_dates_keyboard("return"),
            )
        else:
            await _start_calendar_selection(
                message=callback.message,
                state=state,
                state_name=NewSubscriptionStates.return_dates,
                context="return",
                mode=mode,
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("new:calendar:"))
    async def calendar_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        _, _, context, action, *payload = callback.data.split(":")
        data = await state.get_data()
        if action == "noop":
            await callback.answer()
            return

        if data.get("calendar_context") != context:
            await callback.answer("Этот календарь уже устарел. Используй кнопку «Изменить даты».", show_alert=True)
            return

        mode = data.get("calendar_mode", "fixed")
        stage = data.get("calendar_stage", "from")
        from_key, to_key = _calendar_keys(context)

        if action == "cancel":
            await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)
            if context == "departure":
                await state.set_state(NewSubscriptionStates.departure_mode)
                await callback.message.answer(
                    "Выбор даты отменен.\nКак задать даты вылета?",
                    reply_markup=date_input_mode_keyboard("new:departure_mode"),
                )
            else:
                await state.set_state(NewSubscriptionStates.return_date_mode)
                await callback.message.answer(
                    "Выбор даты отменен.\nКак задать даты возврата?",
                    reply_markup=date_input_mode_keyboard("new:return_date_mode"),
                )
            await callback.answer()
            return

        if action == "nav":
            year = int(payload[0])
            month = int(payload[1])
            selected_from = date.fromisoformat(data[from_key]) if stage == "to" and data.get(from_key) else None
            await callback.message.edit_text(
                _calendar_prompt(context=context, mode=mode, stage=stage),
                reply_markup=calendar_keyboard(context=context, year=year, month=month, selected_from=selected_from),
            )
            await callback.answer()
            return

        if action != "pick":
            await callback.answer()
            return

        selected_date = date.fromisoformat(payload[0])
        if mode == "fixed":
            await state.update_data(
                **{
                    from_key: selected_date.isoformat(),
                    to_key: None,
                    "calendar_context": None,
                    "calendar_mode": None,
                    "calendar_stage": None,
                }
            )
            await callback.message.answer(f"Выбрана дата: <b>{_format_date(selected_date)}</b>")
            if context == "departure":
                await _after_departure_dates_selected(message=callback.message, state=state)
            else:
                await _after_return_dates_selected(message=callback.message, state=state)
            await callback.answer()
            return

        if stage == "from":
            await state.update_data(**{from_key: selected_date.isoformat(), to_key: None, "calendar_stage": "to"})
            await callback.message.edit_text(
                _calendar_prompt(context=context, mode=mode, stage="to"),
                reply_markup=calendar_keyboard(
                    context=context,
                    year=selected_date.year,
                    month=selected_date.month,
                    selected_from=selected_date,
                ),
            )
            await callback.answer(f"Начало диапазона: {_format_date(selected_date)}")
            return

        start_date = date.fromisoformat(data[from_key])
        if selected_date < start_date:
            await callback.answer("Конец диапазона не может быть раньше начала.", show_alert=True)
            return

        await state.update_data(
            **{
                to_key: selected_date.isoformat(),
                "calendar_context": None,
                "calendar_mode": None,
                "calendar_stage": None,
            }
        )
        await callback.message.answer(
            f"Выбран диапазон: <b>{_format_date(start_date)} - {_format_date(selected_date)}</b>"
        )
        if context == "departure":
            await _after_departure_dates_selected(message=callback.message, state=state)
        else:
            await _after_return_dates_selected(message=callback.message, state=state)
        await callback.answer()

    @router.message(NewSubscriptionStates.return_dates)
    async def return_dates_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        try:
            date_from, date_to = _parse_date_range(message.text)
        except ValueError:
            await message.answer(
                _manual_date_prompt("возврата", allow_retry=True),
                reply_markup=edit_dates_keyboard("return"),
            )
            return
        await state.update_data(
            return_date_from=date_from.isoformat(),
            return_date_to=date_to.isoformat() if date_to else None,
            calendar_context=None,
            calendar_mode=None,
            calendar_stage=None,
        )
        await _after_return_dates_selected(message=message, state=state)

    @router.message(NewSubscriptionStates.duration)
    async def duration_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        data = await state.get_data()
        if _is_keep_value(message.text) and _is_editing(data):
            min_days = data.get("min_trip_duration_days")
            max_days = data.get("max_trip_duration_days")
        else:
            try:
                min_days, max_days = _parse_duration_range(message.text)
            except ValueError:
                await message.answer("Неверный формат. Используй 3 или 3-7")
                return
            await state.update_data(min_trip_duration_days=min_days, max_trip_duration_days=max_days)
        await state.set_state(NewSubscriptionStates.max_price)
        data = await state.get_data()
        await message.answer(
            _prompt_with_current_text(_max_price_prompt(), _format_money(data.get("max_price")), editing=_is_editing(data)),
            reply_markup=edit_dates_keyboard("departure"),
        )

    @router.message(NewSubscriptionStates.max_price)
    async def max_price_handler(message: Message, state: FSMContext) -> None:
        if not await ensure_access(message):
            return
        data = await state.get_data()
        if _is_keep_value(message.text) and _is_editing(data):
            parsed_price = Decimal(str(data["max_price"])) if data.get("max_price") is not None else None
        else:
            try:
                parsed_price = _parse_price_input(message.text)
            except (InvalidOperation, ValueError):
                await message.answer(_max_price_prompt())
                return
            await state.update_data(max_price=str(parsed_price) if parsed_price is not None else None)
        await state.set_state(NewSubscriptionStates.direct_only)
        data = await state.get_data()
        await message.answer(
            _prompt_with_current_choice(
                "Только прямые рейсы?",
                "да" if data.get("direct_only") else "нет",
                editing=_is_editing(data),
            ),
            reply_markup=yes_no_keyboard("new:direct", include_keep=_is_editing(data)),
        )

    @router.callback_query(NewSubscriptionStates.direct_only, F.data.startswith("new:direct:"))
    async def direct_only_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        data = await state.get_data()
        if callback.data.endswith("keep") and _is_editing(data):
            direct_only = data.get("direct_only", False)
        else:
            direct_only = callback.data.endswith("yes")
        await state.update_data(
            direct_only=direct_only,
            check_interval_minutes=settings.default_check_interval_minutes,
            preferred_airlines=[],
            baggage_policy=BaggagePolicy.IGNORE.value,
            currency=settings.travelpayouts_default_currency.upper(),
        )
        await state.set_state(NewSubscriptionStates.confirm)
        await callback.message.answer(_render_state_summary(await state.get_data()), reply_markup=confirm_keyboard())
        await callback.answer()

    @router.callback_query(F.data.startswith("new:edit:"))
    async def edit_dates_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        context = callback.data.rsplit(":", 1)[-1]
        await state.update_data(calendar_context=None, calendar_mode=None, calendar_stage=None)

        if context == "departure":
            await state.update_data(
                departure_date_from=None,
                departure_date_to=None,
                return_mode=None,
                return_date_from=None,
                return_date_to=None,
                min_trip_duration_days=None,
                max_trip_duration_days=None,
            )
            await state.set_state(NewSubscriptionStates.departure_mode)
            await callback.message.answer(
                "Давай выберем даты вылета заново.",
                reply_markup=date_input_mode_keyboard("new:departure_mode"),
            )
            await callback.answer()
            return

        if context == "return":
            await state.update_data(return_mode="dates", return_date_from=None, return_date_to=None)
            await state.set_state(NewSubscriptionStates.return_date_mode)
            await callback.message.answer(
                "Давай выберем даты возврата заново.",
                reply_markup=date_input_mode_keyboard("new:return_date_mode"),
            )
            await callback.answer()
            return

        await callback.answer()

    @router.callback_query(NewSubscriptionStates.confirm, F.data == "new:confirm:create")
    async def confirm_create_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        data = await state.get_data()
        payload = SubscriptionCreate(
            name=data["name"],
            origin_iata=data["origin_iata"],
            destination_iata=data["destination_iata"],
            trip_type=TripType(data["trip_type"]),
            departure_date_from=date.fromisoformat(data["departure_date_from"]),
            departure_date_to=date.fromisoformat(data["departure_date_to"]) if data.get("departure_date_to") else None,
            return_date_from=date.fromisoformat(data["return_date_from"]) if data.get("return_date_from") else None,
            return_date_to=date.fromisoformat(data["return_date_to"]) if data.get("return_date_to") else None,
            min_trip_duration_days=data.get("min_trip_duration_days"),
            max_trip_duration_days=data.get("max_trip_duration_days"),
            max_price=Decimal(data["max_price"]) if data.get("max_price") else None,
            currency=data.get("currency", settings.travelpayouts_default_currency.upper()),
            market=settings.travelpayouts_default_market,
            direct_only=data["direct_only"],
            baggage_policy=BaggagePolicy(data["baggage_policy"]),
            preferred_airlines=data.get("preferred_airlines", []),
            check_interval_minutes=data["check_interval_minutes"],
        )
        editing_subscription_id = data.get("editing_subscription_id")
        if editing_subscription_id:
            updated = await subscription_service.update_subscription(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=editing_subscription_id,
                payload=payload,
            )
            await state.clear()
            if updated:
                await callback.message.answer(
                    f"Подписка обновлена: {editing_subscription_id}\n"
                    "Новая проверка будет запущена автоматически в ближайшую минуту.",
                    reply_markup=menu_keyboard,
                )
            else:
                await callback.message.answer("Не удалось обновить подписку.", reply_markup=menu_keyboard)
            await callback.answer()
            return

        subscription_id = await subscription_service.create_subscription(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            payload=payload,
        )
        await state.clear()
        await callback.message.answer(
            f"Подписка создана: {subscription_id}\n"
            "Первая проверка будет запущена автоматически в ближайшую минуту.",
            reply_markup=menu_keyboard,
        )
        await callback.answer()

    @router.callback_query(NewSubscriptionStates.confirm, F.data == "new:confirm:cancel")
    async def confirm_cancel_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        await state.clear()
        await callback.message.answer("Создание подписки отменено.", reply_markup=menu_keyboard)
        await callback.answer()

    @router.callback_query(F.data.startswith("sub:"))
    async def subscription_action_handler(callback: CallbackQuery, state: FSMContext) -> None:
        if not await ensure_access(callback):
            return
        _, action, subscription_id = callback.data.split(":", 2)
        subscription = await subscription_service.get_subscription(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
            subscription_id=subscription_id,
        )
        if subscription is None:
            await callback.answer("Подписка не найдена", show_alert=True)
            return

        if action == "enable":
            await subscription_service.set_enabled(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                enabled=True,
            )
            await callback.message.answer("Подписка включена.", reply_markup=menu_keyboard)
        elif action == "disable":
            await subscription_service.set_enabled(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                enabled=False,
            )
            await callback.message.answer("Подписка выключена.", reply_markup=menu_keyboard)
        elif action == "delete":
            await subscription_service.delete(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
            )
            await callback.message.answer("Подписка удалена.", reply_markup=menu_keyboard)
        elif action == "check":
            await callback.message.answer("Запускаю ручную проверку...", reply_markup=menu_keyboard)
            result = await alert_service.run_subscription_check(subscription_id=subscription_id, trigger=CheckTrigger.MANUAL)
            await callback.message.answer(
                f"Проверка завершена.\nСтатус: {result.status.value}\n"
                f"Найдено офферов: {result.offers_found}\nОтправлено уведомлений: {result.notifications_sent}",
                reply_markup=menu_keyboard,
            )
        elif action == "latest":
            items = await subscription_service.list_recent_offers(
                telegram_user_id=callback.from_user.id,
                username=callback.from_user.username,
                subscription_id=subscription_id,
                limit=5,
            )
            if not items:
                await callback.message.answer("По этой подписке пока нет сохраненных офферов.", reply_markup=menu_keyboard)
            else:
                lines = []
                for offer, price in items:
                    lines.append(
                        f"{offer.origin_iata}->{offer.destination_iata} | "
                        f"{offer.departure_at.date().isoformat() if offer.departure_at else '-'} | "
                        f"{price.price_amount} {price.currency}"
                    )
                await callback.message.answer("Последние варианты:\n" + "\n".join(lines), reply_markup=menu_keyboard)
        elif action == "edit":
            await start_edit_dialog(callback.message, state, subscription)

        await callback.answer()

    return router


def _render_subscription(subscription) -> str:
    status = "включена" if subscription.enabled else "выключена"
    return (
        f"<b>{subscription.name}</b>\n"
        f"{subscription.origin_iata} -> {subscription.destination_iata}\n"
        f"Тип: {_render_trip_type(subscription.trip_type.value)}\n"
        f"Цена до: {_format_money(subscription.max_price)} {subscription.currency}\n"
        f"Прямые: {'да' if subscription.direct_only else 'нет'}\n"
        f"Интервал: {subscription.check_interval_minutes} мин\n"
        f"Статус: {status}"
    )


async def _resolve_airport_or_city_options(raw_text: str, client: TravelpayoutsRestClient) -> list[dict[str, str]]:
    text = raw_text.strip()
    upper = text.upper()
    if len(upper) == 3 and upper.isalpha():
        return [{"code": upper, "label": f"{upper}"}]
    options = await client.autocomplete_places(text)
    return _normalize_place_suggestions(options)


def _normalize_place_suggestions(options: list[dict]) -> list[dict[str, str]]:
    suggestions: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for option in options:
        code = str(option.get("code") or "").strip().upper()
        if len(code) != 3 or code in seen_codes:
            continue
        suggestions.append({"code": code, "label": _format_place_option(option, code)})
        seen_codes.add(code)
        if len(suggestions) >= 5:
            break
    return suggestions


def _format_place_option(option: dict, code: str | None = None) -> str:
    normalized_code = (code or option.get("code") or "").strip().upper()
    city_name = str(option.get("city_name") or option.get("cityName") or "").strip()
    place_name = str(option.get("name") or "").strip()
    country_name = str(option.get("country_name") or option.get("countryName") or "").strip()
    place_type = str(option.get("type") or "").strip().lower()

    if place_type == "airport" and city_name and place_name and city_name.casefold() != place_name.casefold():
        main_label = f"{city_name} — {place_name}"
    else:
        main_label = place_name or city_name or normalized_code

    if country_name and country_name.casefold() not in main_label.casefold():
        main_label = f"{main_label}, {country_name}"

    return f"{main_label} ({normalized_code})" if normalized_code else main_label


def _parse_date_range(value: str) -> tuple[date, date | None]:
    tokens = re.findall(r"\d{4}-\d{2}-\d{2}|\d{2}[./]\d{2}[./]\d{4}", value.strip())
    if not tokens:
        raise ValueError("Date value is missing")
    if len(tokens) > 2:
        raise ValueError("Too many dates in input")

    start_date = _parse_single_date(tokens[0])
    if len(tokens) == 1:
        return start_date, None

    end_date = _parse_single_date(tokens[1])
    if end_date < start_date:
        raise ValueError("End date must be after start date")
    return start_date, end_date


def _parse_duration_range(value: str) -> tuple[int, int | None]:
    text = value.strip()
    if "-" not in text:
        days = int(text)
        return days, days
    start, end = [part.strip() for part in text.split("-", 1)]
    start_days = int(start)
    end_days = int(end)
    if end_days < start_days:
        raise ValueError("Duration range is invalid")
    return start_days, end_days


def _render_state_summary(data: dict) -> str:
    currency = data.get("currency", "RUB")
    interval = data.get("check_interval_minutes", 60)
    parts = [
        "<b>Проверь подписку</b>",
        f"Название: {data['name']}",
        f"Маршрут: {data['origin_iata']} -> {data['destination_iata']}",
        f"Тип: {_render_trip_type(data['trip_type'])}",
        f"Вылет: {_format_date_range(data['departure_date_from'], data.get('departure_date_to'))}",
    ]
    if data.get("return_date_from"):
        parts.append(f"Возврат: {_format_date_range(data['return_date_from'], data.get('return_date_to'))}")
    if data.get("min_trip_duration_days"):
        parts.append(
            f"Длительность: {data['min_trip_duration_days']} .. {data.get('max_trip_duration_days') or data['min_trip_duration_days']} дней"
        )
    parts.extend(
        [
            f"Макс. цена: {_format_money(data.get('max_price'))}",
            f"Прямые: {'да' if data['direct_only'] else 'нет'}",
            f"Проверка: каждые {interval} минут",
            f"Валюта: {currency} (по умолчанию)",
        ]
    )
    return "\n".join(parts)


def _subscription_to_state_data(subscription) -> dict:
    return {
        "editing_subscription_id": subscription.id,
        "name": subscription.name,
        "origin_iata": subscription.origin_iata,
        "destination_iata": subscription.destination_iata,
        "trip_type": subscription.trip_type.value,
        "departure_date_from": subscription.departure_date_from.isoformat(),
        "departure_date_to": subscription.departure_date_to.isoformat() if subscription.departure_date_to else None,
        "return_date_from": subscription.return_date_from.isoformat() if subscription.return_date_from else None,
        "return_date_to": subscription.return_date_to.isoformat() if subscription.return_date_to else None,
        "min_trip_duration_days": subscription.min_trip_duration_days,
        "max_trip_duration_days": subscription.max_trip_duration_days,
        "max_price": str(subscription.max_price) if subscription.max_price is not None else None,
        "currency": subscription.currency,
        "direct_only": subscription.direct_only,
        "check_interval_minutes": subscription.check_interval_minutes,
        "preferred_airlines": subscription.preferred_airlines or [],
        "baggage_policy": subscription.baggage_policy.value,
        "return_mode": "dates" if subscription.return_date_from else ("duration" if subscription.min_trip_duration_days else None),
    }


def _prompt_with_current_text(prompt: str, current_value, *, editing: bool = False) -> str:
    if not editing:
        return prompt
    current = current_value if current_value not in (None, "", "-") else "-"
    return f"{prompt}\nТекущее значение: <b>{current}</b>\nОтправь <code>.</code>, чтобы оставить как есть."


def _prompt_with_current_choice(prompt: str, current_value, *, editing: bool = False) -> str:
    if not editing:
        return prompt
    current = current_value if current_value not in (None, "", "-") else "-"
    return f"{prompt}\nТекущее значение: <b>{current}</b>\nМожно оставить текущее значение кнопкой ниже."


def _is_editing(data: dict) -> bool:
    return bool(data.get("editing_subscription_id"))


def _is_keep_value(value: str | None) -> bool:
    return (value or "").strip() == "."


def _format_duration_range(min_days: int | None, max_days: int | None) -> str | None:
    if min_days is None:
        return None
    if max_days is None or max_days == min_days:
        return str(min_days)
    return f"{min_days}-{max_days}"


def _build_help_text() -> str:
    return (
        "Бот ищет дешевые авиабилеты по твоим подпискам и присылает уведомления.\n\n"
        "<b>Основные команды</b>\n"
        "/new - создать новую подписку\n"
        "/subscriptions - показать мои подписки\n"
        "/subs - короткая команда для списка подписок\n"
        "/help - показать инструкцию\n"
        "/cancel - отменить текущий диалог\n\n"
        "<b>Быстрый доступ</b>\n"
        "Внизу есть постоянное меню:\n"
        "• <b>➕ Новая подписка</b>\n"
        "• <b>📋 Мои подписки</b>\n"
        "• <b>ℹ️ Помощь</b>\n"
        "• <b>✖️ Отмена</b>\n\n"
        "<b>Как пользоваться</b>\n"
        "1. Напиши /new\n"
        "2. Укажи маршрут, даты и лимит цены\n"
        "3. Бот начнет проверять цены автоматически\n\n"
        "<b>Что можно делать в “Мои подписки”</b>\n"
        "• включать и выключать подписки\n"
        "• запускать ручную проверку\n"
        "• смотреть последние найденные варианты\n"
        "• редактировать подписку\n"
        "• удалять подписку\n\n"
        "<b>Подсказки</b>\n"
        "• Город можно вводить названием или IATA-кодом, например <code>MOW</code>, <code>BKK</code>, <code>NHA</code>\n"
        "• Если название неоднозначное или с опечаткой, бот покажет несколько вариантов на выбор\n"
        "• Максимальную цену можно писать как <code>45000</code>, <code>45 000</code> или просто <code>45</code> для 45 000 ₽\n"
        "• Валюта в боте фиксирована: <b>RUB</b>\n"
        "• Проверка выполняется автоматически каждые <b>60 минут</b>\n"
        "• Если ошибся в датах, используй кнопку <b>Изменить даты</b> в следующем сообщении\n"
        "• При редактировании можно оставить текущее значение как есть"
    )


def _is_private_chat(chat: Chat | None) -> bool:
    return bool(chat and chat.type == "private")


async def _after_departure_dates_selected(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if data["trip_type"] == TripType.ONE_WAY.value:
        await state.set_state(NewSubscriptionStates.max_price)
        await message.answer(
            _prompt_with_current_text(_max_price_prompt(), _format_money(data.get("max_price")), editing=_is_editing(data)),
            reply_markup=edit_dates_keyboard("departure"),
        )
        return

    await state.set_state(NewSubscriptionStates.return_mode)
    current_return = data.get("return_mode")
    current_return_label = "даты возврата" if current_return == "dates" else ("длительность" if current_return == "duration" else None)
    await message.answer(
        _prompt_with_current_choice("Как задавать обратный путь?", current_return_label, editing=_is_editing(data)),
        reply_markup=return_mode_keyboard(include_edit_departure=True, include_keep=_is_editing(data)),
    )


async def _after_return_dates_selected(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(NewSubscriptionStates.max_price)
    await message.answer(
        _prompt_with_current_text(_max_price_prompt(), _format_money(data.get("max_price")), editing=_is_editing(data)),
        reply_markup=edit_dates_keyboard("departure", "return"),
    )


async def _start_calendar_selection(
    *,
    message: Message,
    state: FSMContext,
    state_name,
    context: str,
    mode: str,
) -> None:
    today = date.today()
    await state.update_data(calendar_context=context, calendar_mode=mode, calendar_stage="from")
    await state.set_state(state_name)
    await message.answer(
        _calendar_prompt(context=context, mode=mode, stage="from"),
        reply_markup=calendar_keyboard(context=context, year=today.year, month=today.month),
    )


def _calendar_keys(context: str) -> tuple[str, str]:
    if context == "departure":
        return "departure_date_from", "departure_date_to"
    return "return_date_from", "return_date_to"


def _manual_date_prompt(label: str, *, allow_retry: bool = False) -> str:
    text = (
        f"Введи дату {label}.\n"
        "Поддерживаются оба формата:\n"
        "• 01.06.2026\n"
        "• 2026-06-01\n"
        "Для диапазона можно так:\n"
        "• 01.06.2026 - 12.06.2026\n"
        "• 2026-06-01:2026-06-12"
    )
    if allow_retry:
        text += "\n\nЕсли ошибся, нажми кнопку ниже и выбери даты заново."
    return text


def _max_price_prompt() -> str:
    return (
        "Максимальная цена?\n"
        "Можно ввести:\n"
        "• 45000\n"
        "• 45 000\n"
        "• 45 или 45к, если удобно считать тысячами\n"
        "• - если лимита нет"
    )


def _calendar_prompt(*, context: str, mode: str, stage: str) -> str:
    label = "вылета" if context == "departure" else "возврата"
    if mode == "fixed":
        return f"Выбери дату {label} в календаре."
    if stage == "from":
        return f"Выбери первую дату {label}."
    return f"Теперь выбери последнюю дату {label}."


def _parse_single_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Date format is invalid")


def _parse_price_input(raw_value: str | None) -> Decimal | None:
    value = (raw_value or "").strip().lower().replace(" ", "")
    if value == "-":
        return None
    if not value:
        raise ValueError("Price is required")

    multiplier = Decimal("1")
    if value.endswith(("k", "к")):
        multiplier = Decimal("1000")
        value = value[:-1]

    normalized = value.replace(",", ".")
    amount = Decimal(normalized)

    if normalized.isdigit() and 0 < int(normalized) < 1000:
        multiplier = Decimal("1000")

    amount *= multiplier
    if amount <= 0:
        raise ValueError("Price must be positive")

    if amount == amount.to_integral_value():
        return amount.quantize(Decimal("1"))
    return amount.quantize(Decimal("0.01"))


def _format_date(value: date | str) -> str:
    current = date.fromisoformat(value) if isinstance(value, str) else value
    return current.strftime("%d.%m.%Y")


def _format_date_range(date_from: date | str, date_to: date | str | None) -> str:
    start = _format_date(date_from)
    end = _format_date(date_to) if date_to else start
    return f"{start} - {end}"


def _format_money(value: Decimal | str | None) -> str:
    if value is None:
        return "-"
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    if amount == amount.to_integral_value():
        return f"{int(amount):,}".replace(",", " ")
    return f"{amount:,.2f}".replace(",", " ").rstrip("0").rstrip(".")


def _render_trip_type(value: str) -> str:
    return "в одну сторону" if value == TripType.ONE_WAY.value else "туда-обратно"


def _render_baggage_policy(value: str) -> str:
    labels = {
        BaggagePolicy.IGNORE.value: "не важно",
        BaggagePolicy.OPTIONAL.value: "желательно",
        BaggagePolicy.REQUIRED.value: "обязательно",
    }
    return labels.get(value, value)
