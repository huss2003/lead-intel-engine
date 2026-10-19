from conftest import html

from lie.enrich.extract import contact_url, extract


def test_extracts_contact_and_tech_signals():
    pages = {
        "https://x.test/": html("hvac_home.html"),
        "https://x.test/contact-us": html("hvac_contact.html"),
    }
    e = extract(pages)
    assert e.emails == ["service@dallas-cool-hvac.test"]
    assert e.phones == ["+12145550142", "+12145550150"]
    assert e.socials == {
        "facebook": "https://www.facebook.com/dallascoolhvac",
        "instagram": "https://instagram.com/dallascoolhvac",
    }
    assert e.cms == "WordPress"
    assert e.has_ads and not e.has_chat and not e.has_booking
    assert e.hours_text and e.hours_text.lower().startswith("mon-fri 8am-5pm")
    assert not e.open_24_7


def test_detects_chat_booking_and_24_7():
    e = extract({"u": html("lonestar_home.html")})
    assert e.has_chat and e.has_booking and e.open_24_7
    assert e.emails == ["info@lonestarair.test"]
    assert e.socials == {"linkedin": "https://www.linkedin.com/company/lonestarair"}


def test_image_filenames_are_not_emails():
    e = extract({"u": "<body><img src='a@2x.png'> logo@2x.png sentry@wixpress.com</body>"})
    assert e.emails == ["sentry@wixpress.com"] or e.emails == []
    assert "logo@2x.png" not in e.emails


def test_invalid_phone_rejected():
    assert extract({"u": "<body>Call 123-456</body>"}).phones == []


def test_contact_url_same_site_only():
    base = "https://x.test/"
    assert contact_url(html("hvac_home.html"), base) == "https://x.test/contact-us"
    off = '<a href="https://other.test/contact">Contact</a>'
    assert contact_url(off, base) is None


def test_email_false_positives_filtered():
    page = (
        '<html><body><a href="mailto:Info%40shop.test?subject=hi">x</a>'
        '<a href="mailto:not-an-email">y</a><p>logo@2x.png icon@3x.webp</p></body></html>'
    )
    assert extract({"https://s.test/": page}).emails == ["info@shop.test"]
