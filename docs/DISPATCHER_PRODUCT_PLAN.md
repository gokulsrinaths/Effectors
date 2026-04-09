# Effector Product Dispatcher Plan

## Task

Turn the current research demo into a hostable product without breaking the working
demo path for structure upload, sequence search, FASTA processing, and optional
ChimeraX visualization.

## Inputs

- Current backend entrypoint: `backend/main.py`
- Current frontend entrypoint: `frontend/app/page.tsx`
- Structure database: `Database/`
- Sequence database: `effector_sequences.fasta`
- Existing ChimeraX config: `backend/config/chimerax.py`

## Workflow

1. Preserve the existing synchronous research demo path as the reference engine.
2. Add a separate hosted-service scaffold that creates persistent jobs instead of
   doing long-running work directly in the HTTP request.
3. Add a result-summary contract so the public app can email and display condensed
   results without exposing raw internal outputs by default.
4. Add a ChimeraX usage guide tied to this exact repository and validation path.

## Routing

- Current demo engine owner: `backend/main.py`
- Hosted async API owner: `backend/hosted_api/`
- Frontend integration owner: future follow-up after the hosted API stabilizes
- Visualization owner: `backend/utils/chimerax_render.py`

## Persona Squad

- Builder: product backend engineer
- Builder: applied research engineer
- Critic: systems reviewer

## Validation

- New scaffold lives beside the current demo instead of replacing it.
- New code has a dedicated dependency file.
- New docs explain exact next steps instead of broad architecture theory.

## Risks

- The current backend is still monolithic and remains the source of truth for the
  biology pipeline.
- The hosted API scaffold does not yet run the heavy pipeline asynchronously by
  itself; it provides the production shape and integration seams.
- Public hosting still needs deployment, persistent queueing, and email provider
  credentials.

## Immediate Build Steps

1. Stand up the hosted API scaffold locally with SQLite.
2. Add a worker process that calls the pipeline adapter.
3. Add email-on-completion using a real provider.
4. Switch the frontend from synchronous `/api/process/*` calls to async job
   creation and status polling.
5. After that works locally, add an HPC execution mode for heavy requests.
