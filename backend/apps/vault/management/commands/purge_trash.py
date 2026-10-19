"""Purge recycle-bin items whose retention period has expired."""

from django.core.management.base import BaseCommand

from apps.vault.content_services import purge_expired_items


class Command(BaseCommand):
    help = "Delete trashed vault items older than the configured retention period."

    def handle(self, *args, **options):
        count = purge_expired_items()
        self.stdout.write(f"purged={count}")
