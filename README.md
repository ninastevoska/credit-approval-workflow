
# Sistem za obravnavo kreditnih vlog

Spletna aplikacija za digitalizacijo in upravljanje procesa obravnave kreditnih vlog. Sistem omogoča oddajo interaktivnih PDF-obrazcev, samodejno preverjanje podatkov, obravnavo vlog po določenih poslovnih pravilih ter beleženje procesnih dogodkov za nadaljnjo analizo.

Aplikacija je razvita v **Pythonu**, z uporabo **Streamlit** za uporabniški vmesnik, **SQLite** za shranjevanje podatkov ter **pypdf** za obdelavo interaktivnih PDF-obrazcev.

## Funkcionalnosti

- Oddaja kreditnih vlog prek interaktivnih PDF-obrazcev.
- Samodejno branje in validacija podatkov iz PDF-ja.
- Upravljanje vlog glede na uporabniško vlogo: stranka, referent ali vodja.
- Prevzem, pregled in ocenjevanje kreditnih vlog.
- Odobritev ali zavrnitev kreditne vloge.
- Zahtevanje dopolnitve dokumentacije in ponovni pregled.
- Samodejno izvajanje določenih procesnih aktivnosti.
- Beleženje aktivnosti v dnevnik dogodkov in izvoz v CSV.
- Shranjevanje podatkov v SQLite z ohranjanjem zgodovine dogodkov.

## Procesne poti

Sistem trenutno podpira tri procesne poti:

1. **Odobritev:** oddaja → samodejno preverjanje → prevzem → pregled → ocena kreditne sposobnosti → odobritev → obveščanje.
2. **Dopolnitev:** oddaja → preverjanje → prevzem → pregled → zahteva za dopolnitev → oddaja dopolnjenega PDF-ja → ponovni pregled → ocena → odločitev → obveščanje.
3. **Zavrnitev:** oddaja → preverjanje → prevzem → pregled → ocena kreditne sposobnosti → zavrnitev → obveščanje.

Referent lahko neposredno odobri kreditne vloge do vključno 20.000 EUR z bonitetno oceno A ali B. Posredovanje vlog vodji v odločanje še ni implementirano; vodja ima trenutno pregled nad vlogami in dnevnikom dogodkov.

## Struktura projekta

```text
credit-approval-workflow/
├── app.py
├── config.py
├── database.py
├── models.py
├── requirements.txt
├── README.md
├── dnevnik.csv
├── services/
│   ├── application_service.py
│   ├── event_service.py
│   ├── file_service.py
│   ├── pdf_form_service.py
│   ├── verification_service.py
│   └── workflow_service.py
├── ui/
│   ├── components.py
│   ├── customer_view.py
│   ├── referent_view.py
│   └── manager_view.py
├── scripts/
│   └── generate_pdf_forms.py
├── forms/
│   ├── kreditna_vloga_predloga.pdf
│   ├── kreditna_vloga_popolna.pdf
│   └── kreditna_vloga_nepopolna.pdf
├── tests/
│   └── ...
└── data/
    └── uploads/
```

## Namestitev

Potrebujete Python 3.12 ali novejši.

**1. Kloniranje repozitorija**

```powershell
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

Aplikacija je dostopna na naslovu:

http://localhost:8501


## Interaktivni PDF-obrazci

Mapa `forms/` vsebuje prazno predlogo ter popoln in nepopoln testni obrazec.

Obrazec vsebuje naslednja polja:

- `zaprosen_znesek` – zaprošeni znesek kredita v EUR.
- `namen_kredita` – namen kredita (spustni seznam).
- `mesecni_prihodek` – mesečni prihodek v EUR.

Stranka izpolni in shrani obrazec ter ga naloži v aplikacijo. Sistem podatke samodejno prebere in preveri, zato ponovni vnos v spletni obrazec ni potreben.

Predlogo in testna obrazca je mogoče ponovno ustvariti z ukazom:

```powershell
python scripts/generate_pdf_forms.py
```

## Dnevnik dogodkov

Vsaka izvedena aktivnost se zabeleži z identifikatorjem primera, časom, izvajalcem, vlogo, statusom in pripadajočimi atributi.

Dnevnik je zasnovan kot zgodovina, ki je ni mogoče naknadno spreminjati. Izvoz CSV je urejen po identifikatorju primera, časovni oznaki in identifikatorju dogodka.

Datoteka `dnevnik.csv` vsebuje izvožene testne procesne dogodke.

## Testiranje

Za zagon vseh avtomatskih testov uporabite:

```powershell
python -m pytest -q
```

Testi preverjajo poslovna pravila, procesne prehode, validacijo PDF-obrazcev, shranjevanje podatkov, dnevnik dogodkov in različne procesne poti.
