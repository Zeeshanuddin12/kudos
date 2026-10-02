# Kudos

A small feature for an internal employee portal: give kudos to a colleague, see recent kudos on a public feed, and let administrators hide, restore or delete inappropriate messages.

Built spec-first for the Datacom "Automation AI Accelerator" job simulation. See [SPECIFICATION.md](SPECIFICATION.md).

## Run it

    pip install -r requirements.txt
    python app.py

Open http://127.0.0.1:5000 and sign in as one of the sample users. "Aroha Ngata" is the administrator.

## Run the tests

    python -m unittest discover tests

## Files

- `app.py`: the Flask app (database, API and page routes)
- `templates/dashboard.html`: the dashboard page
- `tests/test_app.py`: automated tests
- `SPECIFICATION.md`: the approved requirements, design and plan
