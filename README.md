# Sistem za obravnavo kreditnih vlog

Aplikacija omogoča oddajo in obravnavo kreditnih vlog po vnaprej določenem poslovnem procesu. Implementirana je osnovna uspešna procesna pot (*happy path*), od oddaje vloge do odobritve.

Sistem podpira tri uporabniške vloge: **stranka**, **referent** in **vodja**. Omogoča nalaganje PDF-dokumentov, samodejno preverjanje osnovnih podatkov, spremljanje statusov in beleženje procesnih dogodkov z izvozom v CSV.

Aplikacija je razvita v **Python** z uporabo **Streamlit** za uporabniški vmesnik in **SQLite** za shranjevanje podatkov.

## Namestitev

**1. Kloniranje repozitorija**

```bash
git clone https://github.com/ninastevoska/credit-approval-workflow.git
cd credit-approval-workflow
```

**2. Ustvarjanje in aktivacija virtualnega okolja (Windows PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**3. Namestitev odvisnosti**

```powershell
python -m pip install -r requirements.txt
```

## Zagon aplikacije

```powershell
python -m streamlit run app.py
```

Aplikacija bo dostopna na naslovu:

**http://localhost:8501**

Ob prvem zagonu se podatkovna baza SQLite samodejno inicializira.