from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone

from core.models import Client, Discount, Order


class DiscountService:
    @staticmethod
    def get_previous_month_spending(client: Client) -> int:
        """
        Calculate total spending for the previous month

        Args:
            client: Client instance

        Returns:
            int: Total spending in minor units
        """
        today = timezone.now().date()
        first_day_of_current_month = today.replace(day=1)
        last_day_of_previous_month = first_day_of_current_month - timedelta(days=1)
        first_day_of_previous_month = last_day_of_previous_month.replace(day=1)

        return (
            Order.objects.filter(
                client=client,
                is_completed=True,
                date__gte=first_day_of_previous_month,
                date__lt=first_day_of_current_month,
            ).aggregate(total=Sum("grand_total_minor"))["total"]
            or 0
        )

    @staticmethod
    def get_current_month_spending(client: Client) -> int:
        """
        Calculate total spending for the current month

        Args:
            client: Client instance

        Returns:
            int: Total spending in minor units
        """
        today = timezone.now().date()
        start_of_month = today.replace(day=1)

        return (
            Order.objects.filter(
                client=client,
                is_completed=True,
                date__gte=start_of_month,
            ).aggregate(total=Sum("grand_total_minor"))["total"]
            or 0
        )

    @staticmethod
    def calculate_discount_percentage(amount_spent: int) -> int:
        """
        Calculate discount percentage based on amount spent

        Args:
            amount_spent: Total amount spent in minor units

        Returns:
            int: Discount percentage (0-100)
        """
        if amount_spent <= 0:
            return 0

        # Get all discounts ordered by month_payment
        discounts = list(Discount.objects.all().order_by("month_payment"))

        if not discounts:
            return 0

        # Find appropriate discount tier
        for i, discount in enumerate(discounts):
            if i < len(discounts) - 1:
                next_discount = discounts[i + 1]
                if discount.month_payment <= amount_spent < next_discount.month_payment:
                    return discount.percentage
            else:
                # Last discount in the list
                if amount_spent >= discount.month_payment:
                    return discount.percentage

        return 0

    @classmethod
    def get_client_discount_info(cls, client: Client) -> dict:
        """
        Get client's discount information

        Args:
            client: Client instance

        Returns:
            dict: Dictionary containing discount information
                {
                    'discount_percentage': int,
                    'previous_month_spending': int,
                    'current_month_spending': int
                }
        """
        previous_month_spending = cls.get_previous_month_spending(client)
        current_month_spending = cls.get_current_month_spending(client)
        discount_percentage = cls.calculate_discount_percentage(previous_month_spending)

        return {
            "discount_percentage": discount_percentage,
            "previous_month_spending": previous_month_spending,
            "current_month_spending": current_month_spending,
        }
