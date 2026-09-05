# Requirements Evidence Matrix

This matrix maps the current product plan to implementation and verification.
It excludes `_docs/roadmap.md`. The integration owner updates it after a task is
merged, using evidence supplied by that task's pull request; feature workers do
not edit this shared file concurrently.

Statuses are Planned, Implemented, Verified, Not applicable, or Blocked. A row
is Verified only when its evidence is reproducible from the merged branch.

| ID | Current-plan requirement | Planned task coverage | Status | Merged evidence |
| --- | --- | --- | --- | --- |
| IT-01 | Django is the required backend framework and Python is the primary language | T001-T010 | Planned | — |
| IT-02 | Frontend, data, testing, and architecture follow the approved design track | T001-T019, T028, T083, T088 | Planned | — |
| IT-03 | Development starts locally while containerised and distributed operation remains deferred | T002, T017, T054, T096 | Planned | — |
| UA-01 | Accounts use username and password | T006, T021-T023, T027 | Planned | — |
| UA-02 | Parent/admin and child roles | T007, T018-T019, T022 | Planned | — |
| UA-03 | Parents create users and assign roles | T021-T025 | Planned | — |
| UA-04 | Household size is configurable, with a two-adult/two-child example | T007 | Planned | — |
| CP-01 | Adults manage a reusable chore pool | T020, T034-T037 | Planned | — |
| CP-02 | Each chore has a parent-set name and point value | T034-T037 | Planned | — |
| CP-03 | Chores remain available without scheduling or claiming | T034-T036 | Planned | — |
| CP-04 | Any child may select any active household chore | T035-T036 | Planned | — |
| CP-05 | Parents manually approve or reject frequency | T040-T048 | Planned | — |
| TC-01 | A child selects a chore and attests it is done | T040-T043 | Planned | — |
| TC-02 | A completed chore is submitted for approval | T041-T043 | Planned | — |
| TC-03 | A parent may decide on the child's device using a PIN | T029-T033, T045-T047 | Planned | — |
| TC-04 | A parent may decide from their own queue using a PIN | T029-T033, T044-T046, T048 | Planned | — |
| TC-05 | Approval credits points exactly once | T038-T039, T045-T046 | Planned | — |
| TC-06 | Children cannot approve submissions or create chores | T018-T019, T035, T042, T046 | Planned | — |
| TC-07 | Submission explicitly asserts completion without claiming server proof | T040-T043 | Planned | — |
| PE-01 | Approved chores award their configured flat points | T034, T038, T045 | Planned | — |
| IN-01 | Unspent points use the approved interpretation of 20 percent monthly interest | T050-T054 | Planned | — |
| IN-02 | Interest accrues daily and idempotently | T050-T054 | Planned | — |
| IN-03 | Each creature level adds the approved interpretation of 30 percent | T050-T052, T061-T063 | Planned | — |
| IN-04 | The level-10 policy example resolves to the approved exact arithmetic | T050-T051 | Planned | — |
| RW-01 | One point converts to one minute of game time | T055-T060 | Planned | — |
| RW-02 | Two hundred points convert to five pounds pocket money | T055-T060 | Planned | — |
| RW-03 | No unapproved reward type is exposed | T055-T060 | Planned | — |
| LV-01 | Levelling spends the same points currency | T038, T061-T065 | Planned | — |
| LV-02 | Level 1 costs exactly 500 points | T061, T063 | Planned | — |
| LV-03 | Level 2 costs exactly 510 additional points | T061, T063 | Planned | — |
| LV-04 | Later costs follow the approved mild-escalation table | T061, T063-T065 | Planned | — |
| LV-05 | The approved maximum is within the planned 30-to-40-level range | T061-T065 | Planned | — |
| CS-01 | Each child chooses a creature line at signup unless an approved plan amendment changes it | T067, T078-T080 | Planned | — |
| CL-01 | Proposed Warhammer 40k Soldier lineage or approved plan replacement | T066, T070, T077-T078 | Planned | — |
| CL-02 | Proposed Warhammer Tyranid lineage or approved plan replacement | T066, T071, T077-T078 | Planned | — |
| CL-03 | Proposed Golem lineage or approved plan replacement | T066, T072, T077-T078 | Planned | — |
| CL-04 | Proposed Dragon lineage or approved plan replacement | T066, T073, T077-T078 | Planned | — |
| CL-05 | Proposed Pikachu lineage or approved plan replacement | T066, T074, T077-T078 | Planned | — |
| CL-06 | Proposed Lego Star Wars Stormtrooper lineage or approved plan replacement | T066, T075, T077-T078 | Planned | — |
| CL-07 | Proposed Playmobil Pirate lineage or approved plan replacement | T066, T076-T078 | Planned | — |
| EV-00 | Every current-scope lineage uses AI-generated imagery unless an approved plan amendment changes it | T066, T068, T070-T078 | Planned | — |
| EV-01 | Every approved lineage has the exact policy-defined form sequence | T061, T068, T070-T078 | Planned | — |
| EV-02 | Evolution progresses gradually and smoothly | T068, T070-T078, T081-T083 | Planned | — |
| EV-03 | Early forms are small, dull, and minimally detailed | T068, T070-T078 | Planned | — |
| EV-04 | Late forms are massive, vivid, and elaborate | T068, T070-T078 | Planned | — |
| EV-05 | Adjacent forms show a clear but small change | T068, T070-T078 | Planned | — |
| EV-06 | Children can browse previously unlocked forms | T081-T083 | Planned | — |
| AD-01 | Parents can create and remove or deactivate users | T020-T024, T026 | Planned | — |
| AD-02 | Parents can assign roles | T022, T025 | Planned | — |
| AD-03 | Parents can create, edit, and remove or deactivate chores | T020, T034-T037 | Planned | — |
| AD-04 | Parents can approve or reject submissions | T029-T033, T044-T048 | Planned | — |
| AD-05 | Parents can view users' balances and levels | T084-T085 | Planned | — |

T096 produces the final go or no-go decision from this matrix. A named-lineage
replacement changes current scope and therefore requires an approved edit to
`_docs/plan.md` before the corresponding row is updated.
