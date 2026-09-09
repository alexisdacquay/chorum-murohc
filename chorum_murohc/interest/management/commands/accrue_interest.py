"""`manage.py accrue_interest`: the one operational entry point for weekly
interest accrual (T053), applying `chorum_murohc.interest.services` to every
eligible child.

`--date` is always required and never inferred from "today": a missed week
is recovered by naming its date explicitly, exactly as
`_docs/interest-schedule.md`'s manual-retry and missed-run-recovery
sections describe. `--household` bounds one run to a single household, and
`--dry-run` reports what a real run would credit without writing anything.

Every user is processed inside its own transaction
(`services.accrue_interest_for_user`), so one user's failure never rolls
back another user's success. The command reports one compact summary line -
counts only, no username, no balance, no household name - and exits
non-zero (`CommandError`) when any user could not be processed, so a
scheduler sees a real failure rather than a silently swallowed one.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError

from chorum_murohc.interest.services import (
    accrue_interest_for_user,
    eligible_children,
    preview_interest_for_user,
)


class Command(BaseCommand):
    help = "Accrue this week's interest for every eligible child."

    def add_arguments(self, parser):
        parser.add_argument(
            '--date',
            required=True,
            help='Accrual date, as YYYY-MM-DD. Never inferred from "today".',
        )
        parser.add_argument(
            '--household',
            type=int,
            default=None,
            help='Limit accrual to one household id.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Report what would happen without writing anything.',
        )

    def handle(self, *args, **options):
        try:
            accrual_date = date.fromisoformat(options['date'])
        except ValueError:
            raise CommandError('Invalid date. Use YYYY-MM-DD.') from None

        dry_run = options['dry_run']
        credited = 0
        skipped = 0
        failed = 0

        for membership in eligible_children(household_id=options['household']):
            try:
                if dry_run:
                    amount = preview_interest_for_user(
                        membership.household, membership.user
                    )
                    if amount > 0:
                        credited += 1
                    else:
                        skipped += 1
                    continue

                _entry, created = accrue_interest_for_user(
                    household=membership.household,
                    user=membership.user,
                    accrual_date=accrual_date,
                )
                if created:
                    credited += 1
                else:
                    skipped += 1
            except Exception:  # noqa: BLE001 - one failure must not stop the rest.
                failed += 1
                self.stderr.write(
                    f'Interest accrual failed for household '
                    f'{membership.household_id}, user {membership.user_id}.'
                )

        prefix = 'Dry run: ' if dry_run else ''
        self.stdout.write(
            f'{prefix}Interest accrual for {accrual_date.isoformat()}: '
            f'{credited} credited, {skipped} skipped, {failed} failed.'
        )
        if failed > 0:
            raise CommandError('Interest accrual had unrecovered failures.')
