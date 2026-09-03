import logging
from django.db import transaction
from django.utils import timezone
from core.models import CancelReason, Order
from core.models import OrderEvent, OrderEventType
from core.services import order_status
from payments.models import MonobankInvoiceEvent, Payment
from payments.services.monobank.api import MonobankAPI, MonobankError, MonobankOrderInProgress, MonobankInvoiceAlreadyUsed
from rest_framework.exceptions import ValidationError


class PaymentNotFound(Exception):
    """Вебхук пришёл на invoiceId, которого нет в нашей базе."""


class MonobankPaymentService:
    def __init__(self, token: str, webhook_key: str | None = None):
        if not token:
            raise ValueError("MONOBANK_TOKEN is not configured")
        self.client = MonobankAPI(token, webhook_key)

    @staticmethod
    def _extract_failure_reason(payload: dict) -> str | None:
        return (
            payload.get("failureReason")
            or payload.get("errText")
            or payload.get("cancelReason")
            or payload.get("statusDescription")
        )

    @staticmethod
    def _extract_failure_code(payload: dict) -> str | None:
        code = (
            payload.get("failureCode")
            or payload.get("errCode")
            or payload.get("declineCode")
            or payload.get("status")
        )
        if code is None:
            return None
        return str(code)

    def create_invoice(
        self,
        order: Order,
        redirect_url: str | None = None,
        success_url: str | None = None,
        fail_url: str | None = None,
        web_hook_url: str | None = None,
    ) -> Payment:
        """
        Создает платежный инвойс в Monobank.
        Перед созданием нового диактивирует все ожидающие платежи заказа.

        success_url / fail_url — куда вернуть пользователя после успешной/неуспешной оплаты
        """

        amount = order.grand_total_minor

        data = {
            "amount": amount,
            "redirect_url": redirect_url,
            "success_url": success_url,
            "fail_url": fail_url,
            "web_hook_url": web_hook_url,
            "displayType": "iframe"
        }

        try:
            self.deactivate_order_payments(order)

        except MonobankOrderInProgress:
            raise ValidationError(
                "Your previous payment is still in progress. Please try again later."
            )
        except MonobankInvoiceAlreadyUsed:
            raise ValidationError(
                "Your previous payment is alredy finished. Please contact administator."
            )
        except MonobankError:
            raise ValidationError(
                "Problem with deactivation of previous invoice."
            )

        response = self.client.create_invoice(**data)

        payment = Payment.objects.create(
            order=order,
            amount=amount,
            mono_invoice_id=response["invoiceId"],
            mono_url=response["pageUrl"],
            status=Payment.STATUS_PENDING,
        )

        return payment

    def deactivate_order_payments(self, order: Order):
        """
        Деактивирует все ожидающие платежи заказа.
        """
        payments = Payment.objects.filter(
            order=order,
            status=Payment.STATUS_PENDING
        )

        for payment in payments:
            self.client.deactivate_invoice(payment.mono_invoice_id)

            payment.status = Payment.STATUS_CANCELED
            payment.save(update_fields=["status"])

            logging.info(
                f"Deactivated invoice {payment.mono_invoice_id} for order {order.id}"
            )

    def refund_order_payment(self, order: Order) -> Payment | None:
        """
        Возвращает средства по последнему успешному платежу заказа.

        Возврат подтверждается вебхуком со статусом `reversed`, поэтому здесь
        заказ переводится в refund_state=PENDING; финальное состояние ставит
        proccess_invoice_event. Если Monobank ответил финальным статусом сразу —
        закрываем возврат, не дожидаясь вебхука (вебхук отработает идемпотентно).

        Возвращает платёж, по которому пошёл возврат, или None, если успешных
        платежей у заказа нет (оплата была не через Monobank).
        """
        payment = (
            Payment.objects.filter(order=order, status=Payment.STATUS_SUCCESS)
            .order_by("-paid_at", "-created_at", "-id")
            .first()
        )
        if payment is None:
            logging.info(
                "No successful Monobank payment for order %s — nothing to refund",
                order.id,
            )
            return None

        response = self.client.cancel_invoice(
            payment.mono_invoice_id,
            amount=payment.amount,
            # extRef делает повторный вызов идемпотентным на стороне Monobank:
            # двойное подтверждение отмены не спишет деньги дважды.
            ext_ref=f"order-{order.id}-refund",
        )

        if response.get("status") == "success":
            self.mark_order_as_refunded(payment)
        else:
            order.refund_state = Order.RefundState.PENDING
            order.save(update_fields=["refund_state"])

        return payment

    def mark_order_as_refunded(self, payment: Payment):
        """Фиксирует состоявшийся возврат средств по платежу."""
        order = payment.order

        if payment.status != Payment.STATUS_REVERSED:
            payment.status = Payment.STATUS_REVERSED
            payment.refunded_at = timezone.now()
            payment.save(update_fields=["status", "refunded_at"])

        if order is None or order.refund_state == Order.RefundState.DONE:
            return

        order.refund_state = Order.RefundState.DONE
        order.save(update_fields=["refund_state"])

        OrderEvent.objects.create(
            type=OrderEventType.REFUNDED,
            order=order,
            details=f"Refunded {payment.amount} via Monobank",
        )

    def proccess_invoice_event(self, event: dict):
        """
        Обрабатывает событие от монобанка.

        Monobank ретраит вебхуки и не гарантирует порядок доставки, поэтому
        обработка обязана быть идемпотентной: дубль события игнорируется,
        событие старше уже обработанного не откатывает статус платежа.
        """
        logging.info("Registering invoice event: %s", event)
        with transaction.atomic():
            payment = (
                Payment.objects.select_for_update()
                .filter(mono_invoice_id=event.get("invoiceId"))
                .first()
            )
            if payment is None:
                raise PaymentNotFound(
                    f"No payment for invoiceId {event.get('invoiceId')!r}"
                )

            invoice_event, created = MonobankInvoiceEvent.objects.get_or_create(
                invoice_id=event.get("invoiceId"),
                status=event.get("status"),
                modified_date=event.get("modifiedDate"),
                defaults={
                    "amount": event.get("amount"),
                    "ccy": event.get("ccy"),
                    "created_date": event.get("createdDate"),
                    "raw_payload": event,
                },
            )
            if not created:
                logging.info(
                    "Duplicate webhook for invoice %s (%s), skipping",
                    invoice_event.invoice_id,
                    invoice_event.status,
                )
                return invoice_event

            is_stale = (
                MonobankInvoiceEvent.objects.filter(
                    invoice_id=invoice_event.invoice_id,
                    modified_date__gt=invoice_event.modified_date,
                )
                .exclude(pk=invoice_event.pk)
                .exists()
            )
            if is_stale:
                logging.warning(
                    "Out-of-order webhook for invoice %s (%s) — newer event already "
                    "processed, payment status left untouched",
                    invoice_event.invoice_id,
                    invoice_event.status,
                )
                return invoice_event

            # Сумма события обязана совпасть с суммой платежа: иначе заказ можно
            # было бы закрыть оплатой на произвольную сумму.
            if invoice_event.amount != payment.amount:
                logging.error(
                    "Amount mismatch for invoice %s: event=%s payment=%s",
                    invoice_event.invoice_id,
                    invoice_event.amount,
                    payment.amount,
                )
                payment.failure_reason = (
                    f"Amount mismatch: expected {payment.amount}, "
                    f"got {invoice_event.amount}"
                )
                payment.save(update_fields=["failure_reason"])
                return invoice_event

            failure_reason = None
            failure_code = None
            if invoice_event.status in {
                Payment.STATUS_FAILED,
                Payment.STATUS_CANCELED,
                Payment.STATUS_EXPIRED,
            }:
                failure_reason = self._extract_failure_reason(event)
                failure_code = self._extract_failure_code(event)
            match invoice_event.status:
                case Payment.STATUS_PENDING:
                    pass
                case Payment.STATUS_FAILED:
                    pass
                case Payment.STATUS_CANCELED:
                    self.client.deactivate_invoice(payment.mono_invoice_id)
                case Payment.STATUS_EXPIRED:
                    self.client.deactivate_invoice(payment.mono_invoice_id)
                case Payment.STATUS_SUCCESS:
                    payment.paid_at = timezone.now()
                    self.mark_order_as_paid(payment.order)
                case Payment.STATUS_REVERSED:
                    payment.refunded_at = timezone.now()
                    self.handle_reversal(payment.order)

            payment.status = invoice_event.status
            payment.failure_code = failure_code
            payment.failure_reason = failure_reason
            payment.save(
                update_fields=[
                    "status",
                    "failure_code",
                    "failure_reason",
                    "paid_at",
                    "refunded_at",
                ]
            )
            return invoice_event

    def handle_reversal(self, order: Order | None):
        """
        Реакция на возврат средств, подтверждённый вебхуком.

        Возврат обычно инициирован подтверждением отмены (approve_cancel), но
        админ может вернуть деньги и из кабинета Monobank — тогда заказ ещё
        активен, и его надо закрыть, иначе он уедет в доставку уже оплаченным
        «в минус».
        """
        if order is None:
            return

        if order.refund_state != Order.RefundState.DONE:
            order.refund_state = Order.RefundState.DONE
            order.save(update_fields=["refund_state"])
            OrderEvent.objects.create(
                type=OrderEventType.REFUNDED,
                order=order,
                details="Refund confirmed by Monobank",
            )

        if order.cancel_state != Order.CancelState.CANCELED:
            from core.services.order_cancel import cancel_order

            logging.warning(
                "Refund for order %s arrived without cancellation — canceling it",
                order.id,
            )
            cancel_order(
                order,
                actor=None,
                reason=CancelReason.OTHER,
                comment="Кошти повернуто в Monobank без запиту на скасування",
            )

    
    def validate_webhook(self, x_sign: str, raw_body: bytes) -> bool:
        """
        Проверяет валидность вебхука от Monobank.
        Возвращает True если вебхук валиден и пришел от монобанка, False в противном случае.
        """
        return self.client.validate(x_sign, raw_body)

    def pay_by_google_token(
        self,
        *,
        g_token: str,
        amount: int,
        ccy: int = 980,
        redirect_url: str | None = None,
    ):
        """Проводит оплату по токену (Google Pay) через Monobank wallet/payment."""
        return self.client.wallet_payment(
            g_token=g_token,
            amount=amount,
            ccy=ccy,
            redirect_url=redirect_url,
        )

    def pay_order_by_google_token(
        self,
        *,
        order: Order,
        g_token: str,
        ccy: int = 980,
        redirect_url: str | None = None,
    ) -> tuple[Payment, dict]:
        """
        Проводит Google Pay оплату для конкретного заказа.
        Создает Payment с привязкой к order аналогично flow с invoice/create.
        """
        amount = order.grand_total_minor

        try:
            self.deactivate_order_payments(order)
        except MonobankOrderInProgress:
            raise ValidationError(
                "Your previous payment is still in progress. Please try again later."
            )
        except MonobankInvoiceAlreadyUsed:
            raise ValidationError(
                "Your previous payment is alredy finished. Please contact administator."
            )
        except MonobankError:
            raise ValidationError("Problem with deactivation of previous invoice.")

        mono_response = self.client.wallet_payment(
            g_token=g_token,
            amount=amount,
            ccy=ccy,
            redirect_url=redirect_url,
        )

        invoice_id = mono_response.get("invoiceId")
        if not invoice_id:
            raise ValidationError("Monobank did not return invoiceId for wallet payment")

        payment_status = mono_response.get("status", Payment.STATUS_PENDING)
        payment = Payment.objects.create(
            order=order,
            amount=amount,
            mono_invoice_id=invoice_id,
            mono_url=mono_response.get("pageUrl") or mono_response.get("redirectUrl"),
            status=payment_status,
            failure_code=(
                self._extract_failure_code(mono_response)
                if payment_status
                in {Payment.STATUS_FAILED, Payment.STATUS_CANCELED, Payment.STATUS_EXPIRED}
                else None
            ),
            failure_reason=(
                self._extract_failure_reason(mono_response)
                if payment_status
                in {Payment.STATUS_FAILED, Payment.STATUS_CANCELED, Payment.STATUS_EXPIRED}
                else None
            ),
        )

        if payment_status == Payment.STATUS_SUCCESS:
            self.mark_order_as_paid(order)

        return payment, mono_response

    
    def mark_order_as_paid(self, order: Order):
        was_paid = order.is_paid
        if was_paid:
            # Повторный вебхук: заказ уже закрыт, дёргать RemOnline снова незачем.
            return

        order.is_paid = True
        order.save(update_fields=["is_paid"])

        # Заказ с оплатой картой до этого момента был черновиком: его не видел
        # ни клиент, ни админ, и в CRM он не попадал. Деньги пришли — заказ
        # становится обычным, и только теперь о нём есть смысл сообщать.
        if order.is_draft:
            order_status.promote_draft(order)

        # Последствия оплаты одни и те же, кем бы она ни была подтверждена —
        # вебхуком или админом кнопкой в боте.
        order_status.payment_confirmed(order)
        
    
  
