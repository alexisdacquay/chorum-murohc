"""Weekly interest arithmetic. Pure, floatless, and its own whole policy.

`_docs/interest-policy.md` is the approved rule; this is that rule and
nothing else: two percent of the balance held, floor-divided to a whole
point, capped at twenty points, and zero whenever the balance is zero or
negative. `weekly_interest` takes a plain integer balance and returns a
plain integer amount. It opens no database connection, reads no clock, and
raises nothing a caller needs to catch, so it is exactly as deterministic
and as easy to test as the policy that defines it.
"""

RATE_PERCENT = 2
WEEKLY_CAP = 20


def weekly_interest(balance):
    """This week's interest on `balance`, per `_docs/interest-policy.md`.

    Zero for any balance at or below zero - there is no negative interest
    and no interest charged on a debt. Otherwise `balance * RATE_PERCENT //
    100`, integer floor division so the result is always a whole point, then
    capped at `WEEKLY_CAP`. The return value is never negative, never a
    fraction, and never larger than the cap.
    """
    if balance <= 0:
        return 0
    return min(balance * RATE_PERCENT // 100, WEEKLY_CAP)
