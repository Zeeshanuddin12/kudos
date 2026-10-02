# Kudos System Specification

**Author / architect:** Mohammad Zeeshanuddin
**Status:** Approved for implementation
**Repository:** https://github.com/Zeeshanuddin12/kudos

This specification was generated with an AI assistant from the initial prompt, then reviewed and refined by me before implementation. My changes are marked **[Added in review]**.

## Functional Requirements

### User Stories

1. As a user, I can sign in so that kudos are sent under my own name.
2. As a user, I can select another user from a dropdown list of colleagues.
3. As a user, I can write a message of appreciation (max 500 characters).
4. As a user, I can submit the kudos, which gets stored in the database.
5. As a user, I can view a feed of recent kudos on the dashboard.
6. **[Added in review]** As an administrator, I can hide or delete inappropriate kudos messages so that the public feed stays appropriate.
7. **[Added in review]** As an administrator, I can restore a kudos that was hidden by mistake.

### Acceptance Criteria

**Story 1: Sign in**
- Sending kudos without being signed in is rejected (HTTP 401).
- The public feed can be read without signing in.

**Story 2: Select a colleague**
- The dropdown lists every user except the signed-in user, sorted by name.
- A user cannot send kudos to themselves; the request is rejected with a clear message.
- Selecting a user that does not exist returns "colleague not found".

**Story 3: Write a message**
- The message is required; empty or whitespace-only messages are rejected.
- The message is limited to 500 characters, enforced in the browser, the API and the database.
- A live character counter is shown.

**Story 4: Submit**
- A valid submission is saved with sender, recipient, message and timestamp, and appears at the top of the feed.
- Validation errors are shown next to the form without losing the typed message.

**Story 5: Public feed**
- Shows sender, recipient, message and time, newest first.
- Shows only kudos where `is_visible` is true.
- Loads 20 at a time with a "Show more" button.
- Message text is displayed as plain text and can never run as HTML or script.

**Story 6: Hide or delete [Added in review]**
- Only users with `is_admin` can hide or delete; others receive HTTP 403.
- Hiding sets `is_visible` to false; the kudos disappears from the public feed but stays in the database.
- Hiding records who moderated it, when, and an optional reason.
- Deleting permanently removes the kudos after a confirmation prompt.
- Administrators see hidden kudos in their view, marked "hidden".

**Story 7: Restore [Added in review]**
- An administrator can set a hidden kudos back to visible, and it returns to the public feed.

### Non-functional requirements

- Responsive layout that works on phone and desktop widths.
- Input validation and clear error messages on every endpoint.
- Moderation actions and kudos creation are logged.

## Technical Design

**Stack:** Python, Flask, SQLite, server-rendered page with a small amount of JavaScript.

### Database Schema

**users**

| Field | Type | Notes |
|---|---|---|
| id | integer | Primary key |
| name | text | Required |
| email | text | Required, unique |
| is_admin | boolean | Default false |

**kudos**

| Field | Type | Notes |
|---|---|---|
| id | integer | Primary key |
| sender_id | integer | Foreign key to users.id |
| recipient_id | integer | Foreign key to users.id; must differ from sender_id |
| message | text | 1 to 500 characters |
| created_at | timestamp | UTC |
| is_visible | boolean | **[Added in review]** Default true; false hides it from the feed |
| moderated_by | integer | **[Added in review]** Foreign key to users.id; nullable |
| moderated_at | timestamp | **[Added in review]** Nullable |
| reason_for_moderation | text | **[Added in review]** Nullable, max 200 characters |

Index on (`is_visible`, `created_at` descending) for the feed query.

Design decision: hiding is a "soft delete" using `is_visible`, so a mistaken moderation can be undone and there is a record of who acted. Delete remains available for content that must be removed entirely.

### API Endpoints

| Method | Path | Who | Purpose | Responses |
|---|---|---|---|---|
| GET | /api/users | Signed-in user | Colleagues for the dropdown (excludes self) | 200, 401 |
| GET | /api/kudos?page=N | Anyone | Visible kudos, newest first, 20 per page; returns `items`, `page`, `has_more` | 200, 400 |
| POST | /api/kudos | Signed-in user | Create kudos; body `recipient_id`, `message` | 201, 400, 401, 404 |
| GET | /api/admin/kudos | Administrator | All kudos including hidden, with moderation details | 200, 401, 403 |
| PATCH | /api/admin/kudos/{id} | Administrator | Hide or restore; body `is_visible`, optional `reason` | 200, 400, 401, 403, 404 |
| DELETE | /api/admin/kudos/{id} | Administrator | Permanently delete | 204, 401, 403, 404 |

Errors are returned as JSON: `{"error": "message"}`.

### Frontend Components

- **Header:** app name, sign-in control, signed-in user's name and sign-out.
- **KudosForm:** colleague dropdown, message box with character counter, submit button, inline error.
- **KudosFeed:** list of KudosItem, "Show more" button.
- **KudosItem:** sender, recipient, message, time. For administrators it also shows Hide/Restore and Delete buttons and a "hidden" marker.

Interaction: submitting the form calls POST /api/kudos, then reloads the feed. Moderation buttons call the admin endpoints, then reload the feed.

### Security

- Authentication through a signed session cookie. The demo uses a simple "sign in as" control; in the real portal this is replaced by company single sign-on.
- Authorization checked on the server for every admin endpoint.
- All SQL uses parameterized queries.
- Message text is rendered with `textContent`, so it cannot run as HTML.
- Known gap before production: add CSRF protection to the state-changing endpoints and replace the development secret key.

### Performance

- Feed is paginated (20 per page) and backed by an index.
- Admin list is capped at the 200 most recent items.
- Caching is not needed at this scale; revisit if the feed is loaded on every dashboard view for thousands of users.

### Error handling and logging

- Every endpoint validates input and returns a specific status code and message.
- Kudos creation, hide, restore and delete are logged with the acting user's id.

## Implementation Plan

1. Create the project structure, dependencies and database schema, including the moderation fields. (No dependencies)
2. Add sample users and the demo sign-in and sign-out. (Depends on 1)
3. Build GET /api/users and POST /api/kudos with validation. (Depends on 2)
4. Build GET /api/kudos with pagination and the visibility filter. (Depends on 1)
5. Build the admin endpoints: list, hide/restore, delete, with authorization. (Depends on 2)
6. Build the dashboard page: form, feed, admin controls, responsive styles. (Depends on 3, 4, 5)
7. Write automated tests for each user story, including permission and validation cases. (Depends on 3, 4, 5)
8. Write the README, run all tests, commit and push. (Depends on all)

### Testing strategy

Automated tests (in `tests/test_app.py`) cover: sign-in required; send and see in feed; all validation rules; user list excludes self; pagination and ordering; non-admin blocked from moderation; admin hide, restore and delete; script text not rendered as HTML. All 8 tests pass.

## Reflection

1. **How did the structured approach change the process?** Most of my effort went into deciding what the feature should do before any code existed. Gaps such as moderation, self-kudos and the 500-character limit were settled on paper, where they were cheap to change.
2. **What was the hardest part of reviewing the AI-generated specification?** Noticing what was missing. The draft read well, but it had no moderation, no rule about sending kudos to yourself and no record of who hid a message. A specification that looks complete is easy to approve too quickly.
3. **How did a complete specification affect the code?** The implementation matched the spec closely and the tests could be written straight from the acceptance criteria. The moderation fields were in the schema from the start, so nothing had to be reworked.
