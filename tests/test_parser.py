"""Tests for the email body parser."""

from mail_to_hero.parser import parse_body, parse_subject_name

SAMPLE = """first_name:Max;
last_name:Mustermann;
street:Musterstraße 12;
city:Musterstadt;
zipcode:12345;
email:max.mustermann@example.com;
phone_mobile_formatted:015112345678;
Privat: Privat;
partner_notes:Neubau, Smart Home, Guten Tag,

ich interessiere mich für Ihr Angebot.
Bitte melden Sie sich."""


def test_parse_full_sample():
    p = parse_body(SAMPLE)
    assert p.first_name == "Max"
    assert p.last_name == "Mustermann"
    assert p.street == "Musterstraße 12"
    assert p.city == "Musterstadt"
    assert p.zipcode == "12345"
    assert p.email == "max.mustermann@example.com"
    assert p.phone_mobile == "015112345678"
    assert p.partner_notes is not None
    assert "Neubau" in p.partner_notes
    assert "Smart Home" in p.partner_notes
    assert "ich interessiere mich" in p.partner_notes
    assert "Bitte melden Sie sich." in p.partner_notes
    # Unknown keys end up in extra (Privat → Privat)
    assert "Privat" in p.extra
    assert p.extra["Privat"] == "Privat"


def test_has_minimum_requires_email():
    p = parse_body("first_name:Foo;\nlast_name:Bar;")
    assert p.has_minimum is False
    p2 = parse_body("first_name:Foo;\nlast_name:Bar;\nemail:foo@bar.de;")
    assert p2.has_minimum is True


def test_crlf_line_endings():
    body = SAMPLE.replace("\n", "\r\n")
    p = parse_body(body)
    assert p.first_name == "Max"
    assert p.email == "max.mustermann@example.com"


def test_no_structured_content_falls_back_to_notes():
    p = parse_body("Hallo, das ist nur Fließtext.")
    assert p.email is None
    assert p.partner_notes == "Hallo, das ist nur Fließtext."


def test_subject_extraction():
    assert parse_subject_name("Anfrage von: Max Mustermann") == "Max Mustermann"
    assert parse_subject_name("anfrage von: nur kleinbuchstaben") == "nur kleinbuchstaben"
    assert parse_subject_name("Andere Sache") is None
    assert parse_subject_name("") is None


def test_partner_notes_contains_semicolons():
    body = """first_name:Foo;
email:foo@bar.de;
partner_notes:Linie 1; Linie 2; Linie 3.
Mehrzeilig."""
    p = parse_body(body)
    assert p.first_name == "Foo"
    assert p.email == "foo@bar.de"
    # Semicolons inside partner_notes must NOT be stripped.
    assert "Linie 1; Linie 2; Linie 3." in (p.partner_notes or "")
    assert "Mehrzeilig" in (p.partner_notes or "")


def test_phone_mobile_alias():
    p = parse_body("first_name:Foo;\nemail:foo@bar.de;\nphone_mobile_formatted:0123 456 789;")
    assert p.phone_mobile == "0123 456 789"
