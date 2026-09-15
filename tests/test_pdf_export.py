from dvra.exports import members_pdf, payments_pdf, roster_by_name_pdf


def test_pdf_export_allows_curly_apostrophe():
    name = "O\u2019Brien, Pat"
    pay = payments_pdf(
        [
            {
                "member_id": 1,
                "member_name": name,
                "call_sign": "K2XYZ",
                "payment_date": "2026-01-15",
                "paid_through": "2026-12-31",
                "membership_year": 2026,
                "membership_type": "Regular",
                "form_number": "",
                "notes": "didn\u2019t pay late",
            }
        ]
    )
    assert pay[:5] == b"%PDF-"
    assert b"Identity-H" in pay
    assert b"2019" in pay
    mem = members_pdf(
        [
            {
                "call_sign": "K2XYZ",
                "last_name": "O\u2019Brien",
                "first_name": "Pat",
                "email": "",
                "phone": "",
                "address_street": "",
                "address_city": "",
                "address_state": "",
                "address_zip": "",
                "license_class": "",
                "membership_type": "",
                "arrl_member": False,
                "key_number": None,
                "paid_through": "",
            }
        ]
    )
    assert mem[:5] == b"%PDF-"
    roster = roster_by_name_pdf([{"last_name": "O\u2019Brien", "first_name": "Pat", "call_sign": ""}])
    assert roster[:5] == b"%PDF-"
