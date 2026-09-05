# Delegation and Task Dependency Map

This document controls when backlog tasks may be delegated. T001 means Task 1
in `_docs/tasks.md`, T002 means Task 2, and so on. Task IDs become stable when
this delegation structure is committed. A lower task number is not by itself a
prerequisite.

A prerequisite is satisfied only after it is approved where required, merged
into `main`, and passing the current checks. A formally not-applicable task must
meet the evidence rule in `_docs/process.md`.

The task brief remains in `_docs/tasks.md`. Before assignment, copy that brief
into the implementation issue template and add concrete acceptance criteria,
owned paths, verification commands, and the current base commit. The Ready gate
in `_docs/process.md` is mandatory.

## Foundation gate

Work remains single-writer while the foundation is established. Product
implementation must not fan out across write-capable workers until all of these
are merged and green:

- T001: canonical pytest baseline;
- T002: approved boundaries plus registered empty Django app shells;
- T005: guarded, isolated PostgreSQL test foundation;
- T006 and T007: custom user, household, and membership schema;
- T010: versioned API foundation;
- T011: frontend test foundation;
- T017: hardened baseline CI for both locked applications;
- T018: approved threat model and permission matrix; and
- T019: reusable household-role permission primitive.

An authorised human must then enable required CI checks and protection against
direct and force pushes to `main`. Until that external repository-control gate
is confirmed, delegated agents may review in parallel but only one may write.

Policy tasks may receive parallel read-only research and review after T002, but
repository edits remain single-writer until the repository-control gate. Their
dependent code remains Blocked until the product owner, and any required legal
or security authority, has recorded approval.

## Direct dependency map

Transitive prerequisites are omitted. Approval gates refer to
`_docs/dependency-approvals.md`. "Router if changed" means the issue must obtain
exclusive router ownership if its implementation cannot remain inside its
feature-owned route module.

| Task | Workstream | Direct prerequisite tasks | Additional gate or exclusive ownership |
| --- | --- | --- | --- |
| T001 | Foundation | None | DA-01; Python manifest and lockfile owner |
| T002 | Architecture | T001 | Django settings, app shells, and boundary contract owner |
| T003 | Foundation | T001 | DA-02; Python manifest and lockfile owner |
| T004 | Foundation | T001, T002 | Django settings owner |
| T005 | Foundation | T003, T004 | DA-03; database settings and lockfile owner |
| T006 | Identity schema | T002, T005 | Exclusive identity migration owner |
| T007 | Identity schema | T006 | Exclusive identity migration owner |
| T008 | Audit schema | T002, T007, T017 | Exclusive audit migration owner |
| T009 | Bootstrap | T008 | Management-command owner; guarded task database only |
| T010 | API foundation | T005, T008, T017 | DA-04; Python lockfile, Django settings, and root URL owner |
| T011 | Frontend foundation | T001 | DA-05; frontend manifest and lockfile owner |
| T012 | Frontend foundation | T011, T017 | DA-06; frontend manifest, lockfile, and global-token owner |
| T013 | Frontend foundation | T012 | DA-07; frontend manifest, lockfile, and shared-primitive owner |
| T014 | Frontend foundation | T013 | Application-shell owner |
| T015 | Frontend foundation | T014, T018, T027 | Router and navigation owner; no new router package |
| T016 | Frontend integration | T010, T014 | DA-08; frontend manifest, lockfile, proxy, and API-client owner |
| T017 | Integration | T003, T005, T007, T011 | Exclusive hardened CI owner; repository-control gate follows |
| T018 | Access policy | T002 | Product-owner and independent security approval |
| T019 | Access control | T007, T010, T017, T018 | Permission primitive owner |
| T020 | Retention policy | T002 | Recorded product-owner approval |
| T021 | Account directory API | T008, T009, T019, T020, T027, T067 | Identity API owner; also T079 if T067 selects during account creation |
| T022 | Account update API | T021 | Identity API owner |
| T023 | Account removal API | T020, T022 | Identity API owner; retention decision enforced |
| T024 | Account directory UI | T021, T028 | Account feature directory and router if changed; also T080 for creation-time selection |
| T025 | Account update UI | T022, T024 | Account feature directory; router if changed |
| T026 | Account removal UI | T023, T025 | Account feature directory; router if changed |
| T027 | Authentication | T009, T010, T019 | Session and CSRF contract owner |
| T028 | Authentication UI | T015, T016, T027 | DA-09; frontend manifest, lockfile, authentication directory, and router if changed |
| T029 | PIN policy | T002, T018 | Product-owner and independent security approval |
| T030 | PIN service | T008, T029 | Identity migration owner; secret-safe evidence |
| T031 | PIN management API | T027, T030 | PIN API and verification-service owner |
| T032 | PIN management UI | T028, T031 | PIN feature directory and router if changed |
| T033 | PIN security | T031 | Exclusive PIN verification-state owner |
| T034 | Chore schema | T002, T007, T008, T020 | Exclusive chore migration owner |
| T035 | Chore API | T010, T019, T027, T034 | Chore API ownership |
| T036 | Child chore UI | T014, T028, T035 | Child chore feature directory and router if changed |
| T037 | Parent chore UI | T014, T028, T035 | Parent chore feature directory and router if changed |
| T038 | Ledger schema | T002, T007, T008 | Exclusive ledger migration owner |
| T039 | Balance API | T010, T019, T027, T038 | Ledger service and API ownership |
| T040 | Completion policy | T002, T020 | Recorded product-owner approval |
| T041 | Submission schema | T034, T040 | Exclusive submission migration owner |
| T042 | Submission API | T008, T019, T027, T041 | Submission API ownership |
| T043 | Submission UI | T036, T042 | Child chore feature ownership; router if changed |
| T044 | Approval queue API | T019, T027, T041 | Approval query ownership |
| T045 | Approval transaction | T008, T030, T033, T038, T041 | Exclusive submission and ledger transaction owner |
| T046 | Approval mutation API | T019, T027, T045 | Approval mutation contract owner |
| T047 | Child-device approval UI | T028, T032, T033, T043, T046 | Child approval feature ownership; router if changed |
| T048 | Parent approval UI | T028, T032, T033, T044, T046 | Parent approval feature ownership; router if changed |
| T049 | Points UI | T028, T039 | Points feature directory and router if changed |
| T050 | Interest policy | T061 | Recorded product-owner approval |
| T051 | Interest calculator | T050 | Pure-domain ownership |
| T052 | Interest transaction | T038, T051, T062 | Exclusive ledger and progression transaction owner |
| T053 | Interest command | T052 | Management-command ownership |
| T054 | Interest scheduling | T053 | Repository artefacts only; external host action needs approval |
| T055 | Reward policy | T002 | Recorded product-owner approval |
| T056 | Reward transaction | T008, T038, T039, T055 | Exclusive reward migration and ledger transaction owner |
| T057 | Child reward API | T019, T027, T056 | Reward API ownership |
| T058 | Child reward UI | T028, T039, T057 | Child reward feature directory and router if changed |
| T059 | Parent reward API | T019, T027, T057 | Reward API owner; may resolve formally not applicable |
| T060 | Parent reward UI | T028, T059 | Parent reward feature directory and router if changed; may be N/A |
| T061 | Levelling policy | T002 | Recorded product-owner approval |
| T062 | Progression schema | T002, T007, T008, T061 | Exclusive progression migration owner |
| T063 | Level transaction | T038, T062 | Exclusive ledger and progression transaction owner |
| T064 | Level API | T019, T027, T063 | Progression API ownership |
| T065 | Level UI | T028, T039, T064 | Progression feature directory and router if changed |
| T066 | Creature rights policy | T002 | Rights or legal clearance per lineage; plan amendment for replacements |
| T067 | Onboarding policy | T002, T018 | Product/security approval; plan amendment if child-at-signup changes |
| T068 | Creature asset contract | T061, T066 | Storage, external-media approval, and frozen per-lineage contract |
| T069 | Creature schema | T002, T007, T068 | Exclusive creature migration owner |
| T070 | Creature lineage 1 | T068, T069, T077 | Lineage 1 directory and manifest only |
| T071 | Creature lineage 2 | T068, T069, T077 | Lineage 2 directory and manifest only |
| T072 | Creature lineage 3 | T068, T069, T077 | Lineage 3 directory and manifest only |
| T073 | Creature lineage 4 | T068, T069, T077 | Lineage 4 directory and manifest only |
| T074 | Creature lineage 5 | T068, T069, T077 | Lineage 5 directory and manifest only |
| T075 | Creature lineage 6 | T068, T069, T077 | Lineage 6 directory and manifest only |
| T076 | Creature lineage 7 | T068, T069, T077 | Lineage 7 directory and manifest only |
| T077 | Catalogue validator | T061, T068, T069 | Exclusive validator and fixture owner |
| T078 | Catalogue loading | T069, T070-T077 | Full-catalogue validation, loader, and catalogue-write owner |
| T079 | Creature selection | T008, T019, T027, T067, T078 | Service owner; standalone API only for a post-creation path |
| T080 | Creature chooser UI | T028, T079 | Component owner; screen/route only for a post-creation path |
| T081 | Evolution service | T061, T062, T078, T079 | Pure evolution-domain ownership |
| T082 | Evolution API | T019, T027, T081 | Evolution API ownership |
| T083 | Evolution UI | T028, T082 | DA-10 only if justified; manifest/lock, gallery, and router ownership |
| T084 | Parent overview API | T019, T027, T039, T044, T062, T081 | Read-model composition only |
| T085 | Parent overview UI | T024-T026, T037, T048, T060, T065, T080, T083, T084 | Parent dashboard and route integration owner |
| T086 | Audit API | T008, T019, T027 | Read-only audit API ownership |
| T087 | Audit UI | T028, T086 | Audit feature directory and router if changed |
| T088 | Browser-test harness | T017, T028 | DA-11; frontend lockfile, Playwright config, and CI owner |
| T089 | Child approval journey | T033, T043, T046, T047, T049, T088 | Dedicated Playwright spec and isolated data |
| T090 | Parent approval journey | T033, T044, T046, T048, T049, T088 | Dedicated Playwright spec and isolated data |
| T091 | Reward journey | T049, T058, T060, T087, T088 | Dedicated Playwright spec and isolated data |
| T092 | Creature onboarding journey | T078, T080, T088 | Dedicated Playwright spec and isolated data |
| T093 | Levelling journey | T039, T062-T065, T079, T081-T083, T088 | Dedicated Playwright spec and isolated data |
| T094 | Accessibility audit | T085, T087, T089-T093 | Report only; follow-ups become separate issues |
| T095 | Security audit | T054, T085-T093 | Report only; independent reviewer required |
| T096 | Plan verification | T001-T095 | Every task merged, approved, or formally not applicable |

## Safe parallel workstreams

After the foundation and repository-control gates are green, the integration
owner may release work in these lanes. Tasks remain serial within a Django app
whenever they create or depend on migrations, and ledger-mutating transactions
are integrated one at a time.

- Identity and access: T020-T033.
- Chores and completion: T034-T048.
- Ledger, rewards, and levelling: T038-T065, following the explicit transaction
  dependencies in the table.
- Creature policy and assets: T066-T083. T070-T076 may run concurrently only
  after the asset contract and validator are frozen and each lineage has
  separate ownership.
- Reporting and audit: T084-T087.
- Browser verification and final audits: T088-T096.

Read-only policy research can overlap implementation foundations, but policy
branches and policy-dependent code cannot bypass the repository-control gate.
Interest implementation deliberately waits for the progression schema because
persisted accrual reads the child's current level.

## Conditional onboarding path

T067 must choose and approve the actor, timing, and ownership of initial creature
selection before account or selection work becomes Ready:

- If selection occurs during account creation, T021 additionally waits for and
  calls the T079 service, while T024 additionally waits for and reuses the T080
  chooser component.
- If selection occurs at first login or in a separate parent-assisted flow,
  T021 creates an explicitly incomplete account and T079-T080 own the later
  selection operation and interface.

Any path that changes the plan's requirement that the child chooses at signup
also requires an approved `_docs/plan.md` amendment. No task may implement both
paths speculatively.

## Creature-lineage exception

The product owner requested one task per lineage. T070-T076 are therefore an
explicit exception to the one-session sizing target: each may use several
checkpoint commits but retains one owner, one branch, one issue, one exact
form-index checklist, and one lineage-specific manifest. A lineage worker must
not edit an aggregate manifest. T077 owns the validator; T078 alone aggregates,
validates, and loads the seven results.
