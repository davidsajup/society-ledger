"""The row rules: what counts as a valid flat/person/amount, and what each mistake says.

What these tests prove
* Every kind of mistake is reported against its row and column in plain words, and ALL mistakes
  are reported at once (not one per upload).
* Money is exact: a "4500" or "₹4,500" becomes the Decimal 4500.00, and anything that is not
  exact (3 decimals, text, negative) is refused.
* A flat shared by several people is one flat with one amount, and flats are never updated.
"""

from decimal import Decimal

import pytest

from apps.imports.services import clean_rows, summarize
from apps.societies.models import Flat, Society

pytestmark = pytest.mark.django_db


@pytest.fixture
def society():
    return Society.objects.create(name="Green Meadows", slug="green-meadows")


def row(number=2, **overrides):
    base = {
        "row": number,
        "flat": "A-101",
        "name": "Ravi Kumar",
        "phone": "",
        "email": "",
        "maintenance": "4500",
        "role": "",
    }
    return {**base, **overrides}


def only_error(society, **overrides):
    clean, errors = clean_rows(society, [row(**overrides)])
    assert clean == []
    assert len(errors) == 1
    return errors[0]


def test_a_good_row_is_normalised(society):
    clean, errors = clean_rows(
        society,
        [
            row(
                phone="+91 98765-43210",
                email="Ravi@Example.COM",
                maintenance="₹4,500",
                role="Resident",
            ),
        ],
    )

    assert errors == []
    assert clean == [
        {
            "row": 2,
            "flat": "A-101",
            "name": "Ravi Kumar",
            "phone": "+919876543210",
            "email": "ravi@example.com",
            "maintenance": "4500.00",
            "role": "resident",
        }
    ]


def test_the_default_role_is_resident_and_extra_spaces_are_squeezed(society):
    clean, _ = clean_rows(society, [row(flat="  A-101 ", name="Ravi    Kumar")])

    assert clean[0]["role"] == "resident"
    assert (clean[0]["flat"], clean[0]["name"]) == ("A-101", "Ravi Kumar")


@pytest.mark.parametrize(
    "overrides, field, fragment",
    [
        ({"flat": ""}, "flat", "Enter the flat number"),
        ({"flat": "X" * 21}, "flat", "too long"),
        ({"name": ""}, "name", "Enter the person's name"),
        ({"name": "N" * 101}, "name", "too long"),
        ({"maintenance": ""}, "maintenance", "Enter the maintenance amount"),
        ({"maintenance": "abc"}, "maintenance", "is not an amount"),
        ({"maintenance": "-5"}, "maintenance", "cannot be negative"),
        ({"maintenance": "1500.555"}, "maintenance", "2 decimal places"),
        ({"maintenance": "NaN"}, "maintenance", "negative"),
        ({"maintenance": "1e12"}, "maintenance", "too large"),
        ({"phone": "123"}, "phone", "7 to 15 digits"),
        ({"email": "not-an-email"}, "email", "valid email"),
        ({"role": "boss"}, "role", "must be one of"),
    ],
)
def test_each_mistake_is_reported_against_its_row_and_column(society, overrides, field, fragment):
    error = only_error(society, **overrides)

    assert error["row"] == 2
    assert error["field"] == field
    assert fragment in error["message"]


def test_every_mistake_in_the_file_is_reported_in_one_go(society):
    clean, errors = clean_rows(
        society,
        [
            row(2, maintenance="x"),
            row(3, flat="A-102", email="bad"),
            row(4, flat="A-103"),  # fine
        ],
    )

    assert [(e["row"], e["field"]) for e in errors] == [(2, "maintenance"), (3, "email")]
    assert [r["flat"] for r in clean] == ["A-103"]


def test_amounts_are_exact_decimals_never_floats(society):
    clean, _ = clean_rows(
        society, [row(maintenance="1800.50"), row(3, flat="A-2", maintenance="0")]
    )

    assert [Decimal(r["maintenance"]) for r in clean] == [Decimal("1800.50"), Decimal("0.00")]


def test_a_flat_that_already_exists_is_refused_even_with_different_capitals(society):
    Flat.objects.create(society=society, label="A-101")

    error = only_error(society, flat="a-101")

    assert error["field"] == "flat" and "already exists" in error["message"]


def test_the_same_label_in_another_society_is_not_a_clash(society):
    other = Society.objects.create(name="Lake View", slug="lake-view")
    Flat.objects.create(society=other, label="A-101")

    clean, errors = clean_rows(society, [row()])

    assert errors == [] and len(clean) == 1


def test_two_people_in_one_flat_share_one_flat_and_one_amount(society):
    clean, errors = clean_rows(
        society,
        [
            row(2, name="Ravi"),
            row(3, flat="a-101", name="Meena"),
        ],
    )

    assert errors == []
    assert {r["flat"] for r in clean} == {"A-101"}  # the first spelling wins
    assert summarize(clean) == {"flats": 1, "people": 2, "total_per_cycle": "4500.00"}


def test_two_people_in_one_flat_with_different_amounts_is_an_error_on_the_later_row(society):
    clean, errors = clean_rows(
        society, [row(2, name="Ravi"), row(3, name="Meena", maintenance="5000")]
    )

    assert len(clean) == 1
    assert errors[0]["row"] == 3 and "two different amounts" in errors[0]["message"]


def test_the_summary_counts_each_flat_once(society):
    clean, _ = clean_rows(
        society,
        [
            row(2, flat="A-1", maintenance="4500"),
            row(3, flat="A-1", name="Second", maintenance="4500"),
            row(4, flat="A-2", name="Other", maintenance="6000"),
        ],
    )

    assert summarize(clean) == {"flats": 2, "people": 3, "total_per_cycle": "10500.00"}
