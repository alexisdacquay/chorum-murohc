# Plan Verification - go or no-go

> **Status:** Evidence-backed verdict (T096), 2026-09-09, restated against
> `1ec2d24`. Nothing is fixed here; a gap is recorded, not closed.

## Verdict: go

Every requirement in `_docs/plan.md` is implemented, tested, and driven end to
end in a browser. The last one outstanding - a parent seeing every child's
balance and level - landed in #84 while this verification was being written,
and the audit re-run covers its screen.

The go is on the product, not on the paperwork: `_docs/plan.md` still states
three sets of terms the product deliberately no longer follows, which is
recorded below as P-02. Read the plan and you will be told the wrong rules for
interest, rewards and levelling.

## Requirement by requirement

| Plan requirement | Status | Evidence |
| --- | --- | --- |
| Admin-configurable accounts, username and password | Done | `identity.User`, `/api/v1/household-members/`, the Household screen |
| Two roles, admin creates users and assigns roles | Done | `identity.Membership`, the permission matrix, `api/test_members.py` |
| Configurable household size | Done | Nothing caps membership; `identity/tests.py` proves a two-parent two-child household and a differently sized one |
| Adults create and manage a chore pool with fixed point values | Done | `chores.Chore`, `/api/v1/chores/`, the Chore pool screen |
| All chores always available, any child, any time | Done | The child chore list filters on active only, never on a claim |
| Child marks a chore done and submits it | Done | `submissions`, the `child-submission` browser journey |
| Parent approves on the child's device with a PIN | Done | `child-submission` journey: parent named, wrong PIN refused, right PIN credits |
| Parent approves on their own device with a PIN | Done | `parent-queue` journey: PIN asked again for every decision |
| Points credited on approval | Done | Journey asserts the exact credit on the points dashboard |
| Children cannot approve or create chores | Done | `audit-security` journey probes it live from a child session |
| Interest on unspent points | Done, superseded terms | `_docs/interest-policy.md` replaced the plan's 20 percent monthly, daily, level-scaled draft with a flat weekly 2 percent capped at 20 points. Approved on #49; the plan text was never updated |
| Rewards: 1 point per minute of game time, 200 points for GBP 5 | Done, superseded terms | #55 replaced the two fixed conversions with a parent-defined reward catalogue. The `reward` journey proves the spend and the exact ledger effect. The plan text was never updated |
| Levelling consumes points, 500 for level 1, 30 to 40 levels | Done, superseded terms | #61 replaced spending with earning: ten levels from lifetime points, thresholds 50 to 2750, spending never demotes. The `creature` journey proves the level and its celebration. The plan text was never updated |
| Each child picks a creature line at first sign-in, kept for good | Done | `creature` journey: chooser, confirmation, write-once, survives a reload |
| Seven original lines, four forms each, at levels 1, 4, 7 and 10 | Done | `creatures/catalogue.py`, 28 committed SVGs, `test_catalogue.py` |
| Later forms shown as silhouettes with the level that reveals them | Done | `creature` journey asserts the locked tile, its level text and its empty alt |
| Admin: create and delete users, assign roles | Done | Household screen and its API |
| Admin: create, edit, delete chores and point values | Done | Chore pool screen and its API |
| Admin: approve or reject submissions | Done | Approvals screen and both PIN paths |
| Admin: view all users' point balances and levels | Done | `/api/v1/overview/` and the Overview screen, landed in [#84](https://github.com/alexisdacquay/chorum-murohc/issues/84) at `e607658`. Audited in place; one heading-order finding, A-04 |

## Gaps recorded

| Id | What is missing | Owner |
| --- | --- | --- |
| P-01 | Closed. The parent household overview landed in #84 at `e607658` | [#84](https://github.com/alexisdacquay/chorum-murohc/issues/84) |
| P-02 | `_docs/plan.md` still states the superseded interest, reward and levelling terms. Three approved decisions changed them and none amended the plan, so the plan now contradicts the product in three places | Unowned; a documentation edit, not a code change |
| P-03 | `_docs/tasks.md` T091 cites `_docs/reward-policy.md`, which does not exist. The reward policy lives in issue #55's brief instead | Unowned |

Accessibility and security findings are not repeated here; they are in
`_docs/audit-accessibility.md` and `_docs/audit-security.md`.
