"""The file reader: what it accepts, and what it refuses before anything else sees the file.

What these tests prove
* CSV and Excel both come out as the same rows, with the spreadsheet's own row numbers.
* Friendly headings, other delimiters and Excel's usual encodings all work.
* An Excel formula is never evaluated, and a hostile file (zip bomb, macros, XML entities,
  not-really-a-workbook) is refused with a plain message instead of being processed.
"""

import io
import zipfile

import openpyxl
import pytest
from openpyxl import Workbook

from apps.imports.parsing import MAX_FILE_BYTES, MAX_ROWS, ImportFileError, read_rows

HEADER = "Flat,Name,Phone,Email,Maintenance\n"


def csv_bytes(body, header=HEADER, encoding="utf-8"):
    return (header + body).encode(encoding)


def xlsx_bytes(rows, extra_sheet=None):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    if extra_sheet:
        workbook.create_sheet("Other").append(extra_sheet)
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


# --- CSV ----------------------------------------


def test_a_plain_csv_becomes_rows_with_spreadsheet_row_numbers():
    parsed = read_rows("flats.csv", csv_bytes("A-101,Ravi Kumar,9876543210,r@example.com,4500\n"))

    assert parsed.rows == [
        (
            2,
            {
                "flat": "A-101",
                "name": "Ravi Kumar",
                "phone": "9876543210",
                "email": "r@example.com",
                "maintenance": "4500",
            },
        )
    ]
    assert parsed.ignored_columns == []


def test_friendly_headings_are_understood_and_unknown_columns_are_reported_not_used():
    data = (
        b"Flat No.,Tenant Name,Mobile No,Email ID,Maintenance Fees,Parking Slot\n"
        b'B-2,Meena,99999 11111,m@x.in,"4,500",P7\n'
    )

    parsed = read_rows("flats.csv", data)

    assert parsed.rows[0][1] == {
        "flat": "B-2",
        "name": "Meena",
        "phone": "99999 11111",
        "email": "m@x.in",
        "maintenance": "4,500",
    }
    assert parsed.ignored_columns == ["Parking Slot"]  # never read, never stored


def test_a_semicolon_csv_from_a_european_locale_is_read():
    data = b"Flat;Name;Maintenance\nA-1;Ravi;4500\n"

    assert read_rows("f.csv", data).rows[0][1]["maintenance"] == "4500"


def test_excels_default_cp1252_csv_and_a_utf8_bom_both_decode():
    cp1252 = csv_bytes("A-1,Müller,,,4500\n", encoding="cp1252")
    bom = b"\xef\xbb\xbf" + csv_bytes("A-1,Müller,,,4500\n")

    assert read_rows("f.csv", cp1252).rows[0][1]["name"] == "Müller"
    assert read_rows("f.csv", bom).rows[0][1]["name"] == "Müller"


def test_blank_lines_are_skipped_but_row_numbers_still_match_the_sheet():
    parsed = read_rows("f.csv", csv_bytes("A-1,Ravi,,,4500\n\n,,,,\nA-2,Meena,,,4500\n"))

    assert [number for number, _ in parsed.rows] == [2, 5]


def test_a_title_line_above_the_headings_is_not_a_problem_if_the_headings_come_first():
    parsed = read_rows("f.csv", b"\n\nFlat,Name,Maintenance\nA-1,Ravi,4500\n")

    assert parsed.rows[0][0] == 4


# --- Excel ----------------------------------------


def test_an_xlsx_gives_the_same_rows_and_turns_numeric_cells_into_clean_text():
    data = xlsx_bytes(
        [
            ["Flat", "Name", "Phone", "Email", "Maintenance"],
            ["A-101", "Ravi Kumar", 9876543210, "r@example.com", 4500.0],
            ["A-102", "Meena", None, None, 1800.5],
        ]
    )

    parsed = read_rows("flats.xlsx", data)

    assert parsed.rows[0] == (
        2,
        {
            "flat": "A-101",
            "name": "Ravi Kumar",
            "phone": "9876543210",
            "email": "r@example.com",
            "maintenance": "4500",
        },
    )
    assert parsed.rows[1][1]["maintenance"] == "1800.5"
    assert parsed.rows[1][1]["phone"] == ""


def test_an_excel_formula_is_never_evaluated():
    """A workbook written by code has no saved result for its formulas; we read the saved value
    (nothing), never the formula text and never a freshly computed answer."""
    data = xlsx_bytes([["Flat", "Name", "Maintenance"], ["A-1", "Ravi", "=1500*3"]])

    parsed = read_rows("f.xlsx", data)

    assert parsed.rows[0][1]["maintenance"] == ""


def test_only_the_first_sheet_is_read():
    data = xlsx_bytes(
        [["Flat", "Name", "Maintenance"], ["A-1", "Ravi", 4500]],
        extra_sheet=["Z-9", "Hidden Person", 99999],
    )

    parsed = read_rows("f.xlsx", data)

    assert [values["flat"] for _, values in parsed.rows] == ["A-1"]


def test_openpyxl_is_using_defusedxml():
    assert openpyxl.xml.DEFUSEDXML is True


def _with_prefix_in_sheet_xml(workbook_bytes, prefix):
    """The same workbook with `prefix` placed at the very start of its sheet's XML."""
    result = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(workbook_bytes)) as source:
        with zipfile.ZipFile(result, "w") as target:
            for item in source.infolist():
                body = source.read(item.filename)
                if item.filename == "xl/worksheets/sheet1.xml":
                    body = prefix + body
                target.writestr(item, body)
    return result.getvalue()


def test_xml_with_entities_inside_a_workbook_is_refused():
    """The 'billion laughs' / external entity trick lives in a workbook's XML. The control proves
    the file is only refused because of the entity declaration, not because it was damaged."""
    good = xlsx_bytes([["Flat", "Name", "Maintenance"], ["A-1", "Ravi", 4500]])
    harmless = _with_prefix_in_sheet_xml(good, b"<!-- just a comment -->")
    hostile = _with_prefix_in_sheet_xml(good, b'<!DOCTYPE worksheet [<!ENTITY boom "boom">]>')

    assert read_rows("f.xlsx", harmless).rows[0][1]["name"] == "Ravi"
    with pytest.raises(ImportFileError, match="could not be read"):
        read_rows("f.xlsx", hostile)


def test_a_zip_bomb_is_refused_before_it_is_opened():
    bomb = io.BytesIO()
    with zipfile.ZipFile(bomb, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"0" * 12_000_000)  # ~12 KB compressed

    assert len(bomb.getvalue()) < MAX_FILE_BYTES
    with pytest.raises(ImportFileError, match="too large or unusual"):
        read_rows("f.xlsx", bomb.getvalue())


def test_a_workbook_with_macros_is_refused():
    macro = io.BytesIO()
    with zipfile.ZipFile(macro, "w") as archive:
        archive.writestr("xl/vbaProject.bin", b"fake")
        archive.writestr("[Content_Types].xml", b"<Types/>")

    with pytest.raises(ImportFileError, match="macros"):
        read_rows("f.xlsx", macro.getvalue())


def test_something_that_is_not_a_workbook_is_refused_even_if_named_xlsx():
    with pytest.raises(ImportFileError, match="real Excel"):
        read_rows("f.xlsx", b"just some text")


# --- limits and bad input ----------------------------------------


@pytest.mark.parametrize("name", ["flats.xls", "flats.xlsm", "flats.txt", "flats", ""])
def test_other_file_types_are_refused(name):
    with pytest.raises(ImportFileError, match=r"\.csv or \.xlsx"):
        read_rows(name, csv_bytes("A-1,Ravi,,,4500\n"))


def test_a_file_over_one_megabyte_is_refused():
    with pytest.raises(ImportFileError, match="larger than 1 MB"):
        read_rows("f.csv", b"x" * (MAX_FILE_BYTES + 1))


def test_more_than_300_rows_is_refused():
    body = "".join(f"A-{n},Person {n},,,4500\n" for n in range(MAX_ROWS + 1))

    with pytest.raises(ImportFileError, match="more than 300 rows"):
        read_rows("f.csv", csv_bytes(body))


def test_exactly_300_rows_is_fine():
    body = "".join(f"A-{n},Person {n},,,4500\n" for n in range(MAX_ROWS))

    assert len(read_rows("f.csv", csv_bytes(body)).rows) == MAX_ROWS


def test_missing_required_columns_are_named_in_plain_words():
    with pytest.raises(ImportFileError) as caught:
        read_rows("f.csv", b"Flat,Phone\nA-1,9876543210\n")

    assert "tenant name" in str(caught.value) and "maintenance amount" in str(caught.value)


@pytest.mark.parametrize("data, message", [(b"", "empty"), (b"Flat,Name,Maintenance\n", "no rows")])
def test_an_empty_file_or_one_with_only_headings_is_refused(data, message):
    with pytest.raises(ImportFileError, match=message):
        read_rows("f.csv", data)
