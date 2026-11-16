# Changes requested in this conversation

This note records the implementation work requested during this conversation. It separates code changes from items that still need deployment configuration or follow-up.

## Implemented

- Applied the dark-only Hallmark-style interface across the student app, with a single visual system, rounded/varied surfaces, and no light/dark toggle.
- Added student subject selection for the supported CSE and AI-ML cohorts in semesters 3 and 4. Queries are scoped to the selected branch, semester, and subject.
- Updated the pricing controls with a selected billing-period state and a blue premium action. The upgrade modal’s checkout action also has visible color and contrast.
- Removed the simulated payment-success path. A student is marked paid only after the Razorpay payment verification call succeeds. If checkout cannot start or verification fails, the UI shows an error instead of granting the plan.
- Added the `Slides PDF` upload document type in the admin UI and backend enum.
- Reworked admin sign-in to submit a username and password to the backend. Admin API routes require a signed, time-limited session token; credentials are not embedded in frontend code. The admin return button’s low-contrast styling was corrected and checked on localhost.
- Updated quota loading to use a browser-persistent UUID and show a retry state after a failed request or timeout.
- Made Gemini summary timeouts and HTTP errors fall through to the next summary model or skip the summary, so a summary API failure does not by itself fail completed document indexing.
- Prevented previous-paper documents from supplying stored chapter summaries.
- Changed retrieval so ordinary course questions exclude previous papers. Explicit past-paper requests search previous-paper chunks, pass a larger set of those chunks to the free-user model chain, and request extraction of actual questions without inventing missing ones. The answer cache key was versioned so old refusal responses are not reused.

## Local check

The local frontend and backend were started. A fresh previous-year question request reached the free Gemini chain and returned eight cited questions from the available excerpts. The answer stated that only eight distinct questions were found rather than fabricating ten.

## Still needs follow-up

- Production admin login requires `ADMIN_USERNAME` and `ADMIN_PASSWORD` to be configured in Render’s backend environment and the backend redeployed. The production login was not tested.
- The checkout is wired to Razorpay verification, but a UPI merchant/account configuration was not provided or connected in this conversation. No payment was made.
- The admin model-usage counters were not changed to mirror Google’s live quota dashboard. They are app-side counters, not Google’s authoritative provider usage.
- Student profiles are still browser-created rather than backed by verified student authentication. Local logs showed database foreign-key errors when a browser profile ID was used for chat-session and usage rows; real multi-user deployment needs server-verified identities and profile creation/ownership handling.
- Previous-paper output can only list questions present in the indexed, selected-subject documents. This local dataset returned eight distinct questions; additional questions require complete and correctly tagged paper PDFs.
- Conversation memory architecture was discussed as a recommendation only; no memory-system implementation was requested or made.
