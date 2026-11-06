from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from pypdf import PdfReader


# Pot do projekta in mape za PDF-obrazce.
ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "forms"
OUTPUT_DIR.mkdir(exist_ok=True)

# Prvi del para je prikazano besedilo,
# drugi pa vrednost, ki jo prebere aplikacija.
PURPOSES = [
    ("Izberite namen", "izberite"),
    ("Nakup vozila", "nakup_vozila"),
    ("Prenova stanovanja", "prenova_stanovanja"),
    ("Osebna poraba", "osebna_poraba"),
]


def create_form(
    path: Path,
    amount: str = "",
    purpose: str = "izberite",
    income: str = "",
) -> None:
    """Ustvari interaktivni PDF za kreditno vlogo."""

    pdf = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    navy = HexColor("#18334a")
    gray = HexColor("#64748b")
    border = HexColor("#93a3b5")
    background = HexColor("#f8fafc")

    # Glava dokumenta.
    pdf.setFillColor(navy)
    pdf.rect(0, height - 115, width, 115, fill=1, stroke=0)

    pdf.setFillColorRGB(1, 1, 1)
    pdf.setFont("Helvetica-Bold", 19)
    pdf.drawString(46, height - 65, "VLOGA ZA POTROSNISKI KREDIT")

    pdf.setFont("Helvetica", 10)
    pdf.drawString(
        46, height - 89,
        "Interaktivni obrazec | Credit Approval Workflow",
    )

    pdf.setFillColor(navy)
    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(46, height - 153, "Podatki o kreditni vlogi")

    pdf.setFillColor(gray)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        46, height - 172,
        "Izpolnite vsa tri polja in shranite PDF pred oddajo.",
    )

    def label(text: str, y: float) -> None:
        pdf.setFillColor(navy)
        pdf.setFont("Helvetica-Bold", 10)
        pdf.drawString(46, y + 29, text)

    # Polje 1: zaproseni znesek.
    label("Zaproseni znesek (EUR) *", height - 238)
    pdf.acroForm.textfield(
        name="zaprosen_znesek",
        tooltip="Zaproseni znesek v EUR",
        x=46,
        y=height - 238,
        width=500,
        height=26,
        borderWidth=1,
        borderColor=border,
        fillColor=background,
        textColor=navy,
        fontName="Helvetica",
        fontSize=11,
        value=amount,
        forceBorder=True,
    )

    # Polje 2: spustni seznam za namen kredita.
    label("Namen kredita *", height - 318)
    pdf.acroForm.choice(
        name="namen_kredita",
        tooltip="Namen kredita",
        x=46,
        y=height - 318,
        width=500,
        height=26,
        options=PURPOSES,
        value=purpose,
        borderWidth=1,
        borderColor=border,
        fillColor=background,
        textColor=navy,
        fontName="Helvetica",
        fontSize=11,
        fieldFlags="combo",
        forceBorder=True,
    )

    # Polje 3: mesecni prihodek.
    label("Mesecni prihodek (EUR) *", height - 398)
    pdf.acroForm.textfield(
        name="mesecni_prihodek",
        tooltip="Mesecni prihodek v EUR",
        x=46,
        y=height - 398,
        width=500,
        height=26,
        borderWidth=1,
        borderColor=border,
        fillColor=background,
        textColor=navy,
        fontName="Helvetica",
        fontSize=11,
        value=income,
        forceBorder=True,
    )

    # Navodila in opomba na dnu dokumenta.
    pdf.setFillColor(gray)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(
        46, height - 454,
        "* Obvezno polje. Za zneske uporabite števila brez simbola EUR.",
    )

    pdf.line(46, 70, width - 46, 70)
    pdf.drawString(
        46, 53,
        "Demonstracijski obrazec - ne vnasajte resničnih osebnih podatkov.",
    )

    pdf.save()


def main() -> None:
    """Ustvari predlogo in dva testna obrazca."""

    samples = {
        "kreditna_vloga_predloga.pdf": (
            "", "izberite", ""
        ),
        "kreditna_vloga_popolna.pdf": (
            "15000", "prenova_stanovanja", "2100"
        ),
        "kreditna_vloga_nepopolna.pdf": (
            "", "nakup_vozila", "1600"
        ),
    }

    expected_fields = {
        "zaprosen_znesek",
        "namen_kredita",
        "mesecni_prihodek",
    }

    for filename, values in samples.items():
        path = OUTPUT_DIR / filename
        create_form(path, *values)

        # Preverimo, da so polja res strojno berljiva.
        fields = PdfReader(path).get_fields() or {}
        assert set(fields) == expected_fields

        print(f"Ustvarjeno: {filename}")
        print({
            name: str(field.get("/V"))
            for name, field in fields.items()
        })


if __name__ == "__main__":
    main()
