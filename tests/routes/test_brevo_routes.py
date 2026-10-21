import pytest

from tests.conftest import brevo_http_error

ROUTES = {
    "newsletter": ("/api/signupNewsletter", "BREVO_NEWSLETTER_SIGNUP_LIST_ID", 2),
    "audit": ("/api/signupAuditList", "BREVO_AUDIT_SIGNUP_LIST_ID", 1),
}

route = pytest.mark.parametrize("kind", ROUTES)


def signup(client, kind, **payload):
    return client.post(ROUTES[kind][0], json={"name": "Ada Lovelace", "email": "ada@example.com", **payload})


@route
def test_signup_sends_the_contact_to_the_right_list(client, fake_brevo, kind):
    response = signup(client, kind)

    assert response.status_code == 200
    assert response.json() == {"status_code": "200", "message": "Successfully subscribed new contact", "data": None}

    sent = fake_brevo.requests[0]
    assert sent.url == "https://api.brevo.com/v3/contacts"
    assert sent.payload["email"] == "ada@example.com"
    assert sent.payload["attributes"] == {"FIRSTNAME": "Ada", "LASTNAME": "Lovelace"}
    assert sent.payload["listIds"] == [ROUTES[kind][2]]


@route
@pytest.mark.parametrize(
    "name, first, last",
    [("Ada", "Ada", ""), ("Ada Augusta King", "Ada", "Augusta King"), ("Ada  Lovelace", "Ada", " Lovelace")],
)
def test_signup_splits_the_name_into_first_and_last(client, fake_brevo, kind, name, first, last):
    signup(client, kind, name=name)

    assert fake_brevo.requests[0].payload["attributes"] == {"FIRSTNAME": first, "LASTNAME": last}


def test_only_the_audit_list_updates_existing_contacts(client, fake_brevo):
    signup(client, "audit")
    signup(client, "newsletter")

    assert fake_brevo.requests[0].payload["updateEnabled"] is True
    assert "updateEnabled" not in fake_brevo.requests[1].payload


@route
@pytest.mark.parametrize("payload", [{"name": ""}, {"email": "not-an-email"}])
def test_signup_rejects_bad_input(client, fake_brevo, kind, payload):
    response = signup(client, kind, **payload)

    assert response.status_code in (400, 422)
    assert fake_brevo.requests == []


@route
@pytest.mark.parametrize("payload", [{"name": "Ada"}, {"email": "ada@example.com"}, {}])
def test_signup_requires_name_and_email(client, fake_brevo, kind, payload):
    response = client.post(ROUTES[kind][0], json=payload)

    assert response.status_code == 422
    assert fake_brevo.requests == []


@route
@pytest.mark.parametrize("missing", ["BREVO_API_KEY", "list"])
def test_signup_needs_brevo_configuration(client, fake_brevo, monkeypatch, kind, missing):
    monkeypatch.delenv(ROUTES[kind][1] if missing == "list" else missing)

    response = signup(client, kind)

    assert response.status_code == 500
    assert response.json()["detail"] == "Brevo keys not configured."
    assert fake_brevo.requests == []


@route
def test_signup_reports_duplicate_contacts(client, fake_brevo, kind):
    fake_brevo.error = brevo_http_error(400, b'{"code": "duplicate_parameter", "message": "exists"}')

    response = signup(client, kind)

    assert response.status_code == 400
    assert response.json()["detail"] == {"message": "Dulplicate contact entry", "code": "duplicate_parameter"}


@route
def test_signup_passes_other_brevo_errors_through(client, fake_brevo, kind):
    fake_brevo.error = brevo_http_error(400, b'{"code": "invalid_parameter", "message": "Bad list"}')

    response = signup(client, kind)

    assert response.status_code == 400
    assert response.json()["detail"].endswith("Bad list")


@route
def test_signup_handles_non_json_brevo_errors(client, fake_brevo, kind):
    fake_brevo.error = brevo_http_error(502, b"<html>Bad Gateway</html>")

    response = signup(client, kind)

    assert response.status_code == 400
    assert "502" in response.json()["detail"]


@pytest.mark.xfail(
    strict=True,
    reason="Brevo answers 204 when it updates an existing contact; the route only handles 201 and returns "
    "nothing, which fails response validation",
)
def test_audit_signup_succeeds_when_brevo_updates_an_existing_contact(client, fake_brevo):
    fake_brevo.status = 204

    response = signup(client, "audit")

    assert response.status_code == 200
