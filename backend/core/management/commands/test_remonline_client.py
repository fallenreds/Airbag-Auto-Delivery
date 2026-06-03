"""
Management command: test_remonline_client
Usage:
    python manage.py test_remonline_client
    python manage.py test_remonline_client --phone +380991234567 --first-name Іван --last-name Петренко --email test@example.com --address "Одеса, НП №5"
    python manage.py test_remonline_client --phone +380991234567 --delete
"""
import logging
from django.core.management.base import BaseCommand
from django.conf import settings
from core.services.remonline.api import RemonlineInterface

logger = logging.getLogger(__name__)

REMONLINE_API_KEY = getattr(settings, "REMONLINE_API_KEY", None)


class Command(BaseCommand):
    help = "Test Remonline client creation/lookup. Creates a client and prints the result."

    def add_arguments(self, parser):
        parser.add_argument("--phone", default="+380990000999", help="Phone number (default: +380990000999)")
        parser.add_argument("--first-name", default="Тест", help="First name")
        parser.add_argument("--last-name", default="Автотест", help="Last name")
        parser.add_argument("--email", default="autotest@airbagad.test", help="Email")
        parser.add_argument("--address", default="Одеса, НП відділення 10", help="Address")
        parser.add_argument("--delete", action="store_true", help="Delete the test client after creation")

    def handle(self, *args, **options):
        if not REMONLINE_API_KEY:
            self.stderr.write(self.style.ERROR("REMONLINE_API_KEY not set in settings"))
            return

        phone = options["phone"]
        first_name = options["first_name"]
        last_name = options["last_name"]
        email = options["email"]
        address = options["address"]

        self.stdout.write(self.style.MIGRATE_HEADING("=== Remonline Client Autotest ==="))
        self.stdout.write(f"  phone:      {phone}")
        self.stdout.write(f"  first_name: {first_name}")
        self.stdout.write(f"  last_name:  {last_name}")
        self.stdout.write(f"  email:      {email}")
        self.stdout.write(f"  address:    {address}")
        self.stdout.write("")

        try:
            remonline = RemonlineInterface(REMONLINE_API_KEY)
            self.stdout.write("✓ Token obtained")

            # Step 1: create/find
            self.stdout.write("\n→ Calling find_or_create_client...")
            result = remonline.find_or_create_client(
                phone=phone,
                first_name=first_name,
                last_name=last_name,
                address=address,
                email=email,
            )

            self.stdout.write(self.style.SUCCESS("\n✓ Client in Remonline:"))
            for key in ["id", "name", "first_name", "last_name", "email", "phone", "address"]:
                val = result.get(key, "—")
                ok = "✓" if val and val != "—" else "✗"
                self.stdout.write(f"  {ok} {key}: {val}")

            # Validation
            self.stdout.write("\n=== Validation ===")
            checks = [
                ("first_name set", bool(result.get("first_name"))),
                ("last_name set", bool(result.get("last_name"))),
                ("phone set", bool(result.get("phone"))),
                ("email set", bool(result.get("email"))),
                ("address set", bool(result.get("address"))),
                ("phone starts with +380 or 380", (
                    str(result.get("phone", [""])[0] if result.get("phone") else "").startswith("380")
                )),
            ]
            all_ok = True
            for label, passed in checks:
                icon = self.style.SUCCESS("✓") if passed else self.style.ERROR("✗")
                self.stdout.write(f"  {icon} {label}")
                if not passed:
                    all_ok = False

            if all_ok:
                self.stdout.write(self.style.SUCCESS("\n✅ All checks passed!"))
            else:
                self.stdout.write(self.style.WARNING("\n⚠ Some checks failed"))

        except Exception as e:
            self.stderr.write(self.style.ERROR(f"ERROR: {e}"))
            import traceback
            self.stderr.write(traceback.format_exc())
