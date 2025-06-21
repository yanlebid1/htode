# common/db/repositories/payment_repository.py

from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from sqlalchemy import desc, and_
from sqlalchemy.orm import Session

from common.db.models.payment import Payment
from common.db.repositories.base_repository import BaseRepository
from common.utils.logging_config import log_operation, log_context

# Import the repository logger
from . import logger


class PaymentRepository(BaseRepository):
    """Repository for payment operations with unified Payment model"""

    @staticmethod
    @log_operation("get_payment_by_order_id")
    def get_payment_by_order_id(db: Session, order_id: str) -> Optional[Payment]:
        """Get payment by order ID"""
        with log_context(logger, order_id=order_id):
            payment = db.query(Payment).filter(Payment.order_id == order_id).first()

            if payment:
                logger.debug(
                    "Found payment",
                    extra={
                        "order_id": order_id,
                        "payment_id": payment.id,
                        "user_id": payment.user_id,
                        "status": payment.status,
                    },
                )
            else:
                logger.debug("Payment not found", extra={"order_id": order_id})

            return payment

    @staticmethod
    @log_operation("create_payment")
    def create_payment(
        db: Session, user_id: int, order_id: str, amount: float, period: str
    ) -> Payment:
        """Create a new payment"""
        with log_context(
            logger, user_id=user_id, order_id=order_id, amount=amount, period=period
        ):
            payment = Payment(
                user_id=user_id,
                order_id=order_id,
                amount=amount,
                period=period,
                status="pending",
            )
            db.add(payment)
            db.commit()
            db.refresh(payment)

            logger.info(
                "Created payment",
                extra={
                    "payment_id": payment.id,
                    "order_id": order_id,
                    "user_id": user_id,
                    "amount": amount,
                    "period": period,
                },
            )

            return payment

    @staticmethod
    @log_operation("update_payment_status")
    def update_payment_status(
        db: Session,
        order_id: str,
        status: str,
        transaction_id: Optional[str] = None,
        card_mask: Optional[str] = None,
        payment_details: Optional[Dict[str, Any]] = None,
    ) -> Optional[Payment]:
        """Update payment status and optionally add transaction details"""
        with log_context(logger, order_id=order_id, new_status=status):
            payment = db.query(Payment).filter(Payment.order_id == order_id).first()

            if payment:
                old_status = payment.status
                payment.status = status
                payment.updated_at = datetime.now()

                # If completed, set completion time
                if status == "completed" and not payment.completed_at:
                    payment.completed_at = datetime.now()

                # Add transaction details if provided
                if transaction_id:
                    payment.transaction_id = transaction_id
                if card_mask:
                    payment.card_mask = card_mask
                if payment_details:
                    payment.payment_details = payment_details

                db.commit()
                db.refresh(payment)

                logger.info(
                    "Updated payment status",
                    extra={
                        "payment_id": payment.id,
                        "order_id": order_id,
                        "old_status": old_status,
                        "new_status": status,
                        "user_id": payment.user_id,
                        "has_transaction_id": bool(transaction_id),
                    },
                )
            else:
                logger.warning(
                    "Payment not found for status update",
                    extra={"order_id": order_id, "new_status": status},
                )

            return payment

    @staticmethod
    @log_operation("get_user_payments")
    def get_user_payments(
        db: Session, user_id: int, status: Optional[str] = None, limit: int = 10
    ) -> List[Payment]:
        """Get payments for a user, optionally filtered by status"""
        with log_context(logger, user_id=user_id, status=status, limit=limit):
            query = db.query(Payment).filter(Payment.user_id == user_id)

            if status:
                query = query.filter(Payment.status == status)

            payments = query.order_by(desc(Payment.created_at)).limit(limit).all()

            logger.debug(
                "Retrieved user payments",
                extra={
                    "user_id": user_id,
                    "status_filter": status,
                    "limit": limit,
                    "found_count": len(payments),
                },
            )

            return payments

    @staticmethod
    @log_operation("get_pending_payments")
    def get_pending_payments(db: Session, user_id: int) -> List[Payment]:
        """Get all pending payments for a user"""
        with log_context(logger, user_id=user_id):
            payments = (
                db.query(Payment)
                .filter(and_(Payment.user_id == user_id, Payment.status == "pending"))
                .order_by(desc(Payment.created_at))
                .all()
            )

            logger.debug(
                "Retrieved pending payments",
                extra={"user_id": user_id, "found_count": len(payments)},
            )

            return payments

    @staticmethod
    @log_operation("get_successful_payments")
    def get_successful_payments(
        db: Session, user_id: int, limit: int = 10
    ) -> List[Payment]:
        """Get successful payment history for a user"""
        with log_context(logger, user_id=user_id, limit=limit):
            payments = (
                db.query(Payment)
                .filter(and_(Payment.user_id == user_id, Payment.status == "completed"))
                .order_by(desc(Payment.completed_at))
                .limit(limit)
                .all()
            )

            logger.debug(
                "Retrieved successful payments",
                extra={
                    "user_id": user_id,
                    "limit": limit,
                    "found_count": len(payments),
                },
            )

            return payments

    @staticmethod
    @log_operation("cleanup_expired_pending_payments")
    def cleanup_expired_pending_payments(db: Session, hours: int = 24) -> int:
        """Clean up pending payments older than specified hours"""
        with log_context(logger, hours=hours):
            cutoff_time = datetime.now() - timedelta(hours=hours)

            result = (
                db.query(Payment)
                .filter(
                    and_(Payment.status == "pending", Payment.created_at < cutoff_time)
                )
                .update(
                    {"status": "expired", "updated_at": datetime.now()},
                    synchronize_session=False,
                )
            )

            db.commit()

            logger.info(
                "Cleaned up expired pending payments",
                extra={"hours": hours, "expired_count": result},
            )

            return result

    @staticmethod
    @log_operation("get_payment_statistics")
    def get_payment_statistics(db: Session, user_id: int) -> Dict[str, Any]:
        """Get payment statistics for a user"""
        with log_context(logger, user_id=user_id):
            payments = db.query(Payment).filter(Payment.user_id == user_id).all()

            stats = {
                "total_payments": len(payments),
                "completed": len([p for p in payments if p.status == "completed"]),
                "pending": len([p for p in payments if p.status == "pending"]),
                "failed": len([p for p in payments if p.status == "failed"]),
                "total_spent": sum(
                    float(p.amount) for p in payments if p.status == "completed"
                ),
            }

            logger.debug(
                "Retrieved payment statistics",
                extra={"user_id": user_id, "stats": stats},
            )

            return stats
