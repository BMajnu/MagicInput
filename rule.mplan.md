# MPlan Implementation Protocol (Dev‑Friendly v2)

## Purpose
Make planning and execution fast, consistent, and verifiable. This protocol creates a clear blueprint (requirements, design, plan) and a tight build loop (implement → check off → test → move on).

## When To Trigger
- User says "make a plan" or "mplan".
- Any new feature/project where structure is needed before coding.

## What You Produce (always under `MPlan/`)
- `requirements.md` — what to build and why.
- `design.md` — how it will be built.
- `plan.md` — the step‑by‑step build checklist.

---
## Flow: Create the Plan (3 files)

### 1) Create `MPlan/requirements.md`
- Use only the user’s request and known constraints.
- Be specific, testable, and short.
- Number everything for traceability.

Template:
```markdown
# Requirements: {Project Title}

## 1. Goal
Concise summary of purpose, audience, outcome.

## 2. User Stories
- As a [role], I want [action] so that [benefit].
- As a [role], I want [action] so that [benefit].

## 3. Functional Requirements (FR)
- FR-1: {specific, testable capability}
- FR-2: {specific, testable capability}

## 4. Non-Functional Requirements (NFR)
- NFR-1 Performance: {e.g., "<2s initial load"}
- NFR-2 Security: {e.g., "hash+salt passwords"}
- NFR-3 Usability: {e.g., "responsive, accessible"}
```
Quality bar:
- Each FR/NFR is independently verifiable.
- At least 3 meaningful user stories for non‑trivial projects.

---
### 2) Create `MPlan/design.md`
- Derive strictly from `requirements.md`.
- Show the architecture, modules, data, and APIs.

Template:
```markdown
# System Design: {Project Title}

## 1. Architecture Overview
- Pattern (e.g., Client–Server, MVC). Why it fits.
- Text diagram/data flow (short bullets are ok).

## 2. Project Structure
/project-root
|-- /src
|   |-- /components
|   |-- /pages
|   |-- /api
|-- /public
|-- package.json

## 3. Components & Modules
### Component: {Name}
- Responsibility: {single clear responsibility}
- Interfaces: {public functions/events}
- Dependencies: {internal/external}

## 4. UI/UX Guidance
- Color: {#hex primary}, {#hex secondary}
- Typography: {fonts/sizes}
- Layout: {grid/responsive rules}
- Key Elements: {nav, buttons, forms, cards}

## 5. Data Schema
Table: `users`
| column | type | constraints | description |
|---|---|---|---|
| id | int | pk, auto | identifier |
| email | varchar(255) | unique, not null | login |
| password_hash | varchar(255) | not null | secret |

## 6. API Endpoints
POST /api/auth/register
- Request: { email, password }
- 201: { userId, message }
- 400: { error }
```
Quality bar:
- Every endpoint lists request+responses.
- Every component has 1 clear responsibility.

---
### 3) Create `MPlan/plan.md`
- Break work into Phases → Tasks → Subtasks.
- Use checkboxes. Add references to requirements/design.

Template:
```markdown
# Project Plan: {Project Title}

## Overview
1 paragraph referencing the goal.

## [ ] Phase 1: Foundation

### [ ] Task 1.1: Project Init
> References: design.md §2
> Must Read: Re-read these references before implementing any subtask.
- [ ] 1.1.1: Repo & version control
- [ ] 1.1.2: Directory structure
- [ ] 1.1.3: Install dependencies

### [ ] Task 1.2: DB & User Model
> References: requirements.md FR-1; design.md §5
> Must Read: Re-read these references before implementing any subtask.
- [ ] 1.2.1: Users table migration
- [ ] 1.2.2: UserModel

## [ ] Phase 2: Auth Feature

### [ ] Task 2.1: Backend Auth
> References: requirements.md FR-1, NFR-2; design.md §6
> Must Read: Re-read these references before implementing any subtask.
- [ ] 2.1.1: Register endpoint
- [ ] 2.1.2: Login endpoint
- [ ] 2.1.3: Password hashing

### [ ] Task 2.2: Frontend Auth UI
> References: requirements.md FR-1; design.md §4
> Must Read: Re-read these references before implementing any subtask.
- [ ] 2.2.1: Registration form
- [ ] 2.2.2: Login form
- [ ] 2.2.3: Wire to APIs
```
Quality bar:
- Each Task lists `> References:` above its subtasks and includes a "Must Read" reminder.
- Subtasks use numeric IDs X.Y.Z (e.g., 2.2.1) and are small (~30–90 min).
- Each numeric subtask has a clear, testable action.

---
## Implementation Mode: Executing `plan.md`
When asked to “build/implement/work on” a Task from `plan.md`, follow this loop:

1) Identify the target Task in `plan.md`.
2) Read its `> References:` then open the cited `requirements.md` FR/NFR and `design.md` sections.
3) Do a small batch of closely related Subtasks (X.Y.Z) when it speeds delivery; otherwise, do one subtask.
   - Batch criteria: same component/module/file, minimal context switching, no external blockers, total batch ≤ 3 subtasks.
   - While batching: keep changes atomic and reversible; commit logically.
4) Update `MPlan/plan.md` — mark each completed Subtask `[x]` in the batch.
5) Verify & test after finishing the parent Task.
   - End-of-task checks: build passes, core flows work, no regressions in affected areas.
   - Optional: quick smoke checks per subtask are recommended but may be skipped if trivial/low‑risk to move faster.
6) When all subtasks in the Task are complete, mark the parent Task as done and move to the next Task/Phase.

Batching guardrails:
- Prefer batches of 2–3 tightly coupled subtasks.
- Avoid batching across different components or unrelated files.
- If scope starts to creep, split the batch and ship incrementally.

Definition of Done (per subtask/batch):
- Change is isolated and reversible.
- Behavior matches relevant FR/NFR.
- Updated docs (if API/structure changed).
- Test evidence or brief notes exist (or covered by end-of-task verification).

Definition of Done (per task):
- All intended subtasks are completed and checked `[x]` in `plan.md`.
- End-of-task verification executed (or explicitly skipped with rationale when changes are trivial/low‑risk).
- Docs/design updated if APIs, schema, or structure changed.

---
## Rules of Thumb
- Do:
  - Keep all docs in `MPlan/`.
  - Reuse FR-# / NFR-# IDs consistently.
  - Keep checkboxes accurate; update as you progress.
  - Make small, atomic code changes per subtask.
- Don’t:
  - Skip requirements or references.
  - Combine multiple subtasks in one change.
  - Change APIs/schema without updating `design.md`.

## Naming & Linking
- IDs: `FR-#`, `NFR-#`, `Task X.Y`, `Subtask X.Y.Z`.
- Use `> References:` lines with back‑links to sections (e.g., `requirements.md` FR-2; `design.md §6`).

## Example Micro‑Run
- Request: “Add profile pictures.”
- Create FRs/NFRs → Design component & API → Plan subtasks.
- Implement Subtask “Upload endpoint” → mark `[x]` → test → next subtask.

## Versioning & Changes
- If this protocol evolves, bump a version at the top and briefly list changes.

## TL;DR
- Trigger → Produce 3 files under `MPlan/`.
- Build → One subtask at a time; mark `[x]` as you go.
- Always cross‑reference FR/NFR and Design; always test.
